"""Contracts observed during PID5097 real validation; no network in these tests."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_v2_vision as vision
import test_v2_workflow as fixtures
import test_v2_repairs_sku as sku_fixtures


class PlatformCompatibilityTests(unittest.TestCase):
    def test_observer_note_is_preserved_but_unknown_fields_still_rejected(self):
        from mye_c_automation.ai_judge.image_action_decision import validate
        item=dict(id='I',sha256='a'*64,image_type='MAIN',evidence_ids=['S'])
        for note in (None,'No retail box visible; bbox is null.'):
            row=vision.observation(item,retail_box_bbox_note=note)
            self.assertEqual(validate(row,item)['retail_box_bbox_note'],note)
        for extra in ({'arbitrary_override':True},{'retail_box_bbox_note':{'decision':'KEEP'}},{'retail_box_bbox_note':'x'*2001}):
            with self.subTest(extra=list(extra)),self.assertRaises(ValueError):
                validate(vision.observation(item,**extra),item)

    def test_no_id_assignment_uses_existing_row_hash_only_when_enabled(self):
        from mye_c_automation.sku_assignment import select_v2
        from mye_c_automation.snapshot_sku import row_hash
        product={'skus':[{'id':None,'skuName':'no retail box','skuImageUrl':'https://fake/0','originalBox':False,'price':12},{'id':None,'skuName':'with retail box','skuImageUrl':'https://fake/2','originalBox':True,'price':20}]}
        before=copy.deepcopy(product);rows=sku_fixtures.RepairSkuTests().records()
        self.assertFalse(select_v2(product,rows)['assignments'])
        selected=select_v2(product,rows,allow_snapshot_rows=True)
        self.assertFalse(selected['assignments'])
        self.assertEqual(selected['row_assignments'],[dict(index=n,source_sha256=row_hash(product['skus'][n]),url=url) for n,url in enumerate(('https://fake/0','https://fake/2'))])
        self.assertTrue(selected['capability_evidence']['second_reference_assigned'])
        self.assertFalse(selected['reason_codes'])
        self.assertEqual(len(selected['selected_sku_images']),2)
        self.assertEqual(product,before)
        self.assertIsNone(selected['selected_sku_images'][0]['target_sku_id'])

    def test_ambiguous_or_changed_snapshot_rows_are_not_mapped(self):
        from mye_c_automation.sku_assignment import select_v2
        rows=sku_fixtures.RepairSkuTests().records()
        for skus in ([dict(skuName='Without Box'),dict(skuName='Without Box')],[dict(skuName='With Box',originalBox=False)],[dict(skuName='Unknown Variant')]):
            self.assertFalse(select_v2({'skus':skus},rows,allow_snapshot_rows=True)['row_assignments'])

    def scenario(self,root,actions,**options):
        return fixtures.V2WorkflowTests.scenario(self,root,actions,**options)

    def test_no_id_sku_full_flow_preserves_nonimage_rows(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['KEEP','KEEP'],missing_sku_id=True,snapshot_sku_rows=True)
            self.assertEqual(s['writer'].saves,1)
            self.assertTrue(s['result']['content_validation']['ok'])
            self.assertTrue(s['result']['content_validation']['sku_references_exact'])
            self.assertNotIn('skuId',s['product']['skus'][0])
            self.assertEqual(s['product']['skus'][0]['price'],s['original']['skus'][0]['price'])
            selection=json.loads((s['root']/'v2_sku_selection.json').read_text(encoding='utf-8'))
            self.assertFalse(selection['assignments']);self.assertTrue(selection['row_assignments'])
            self.assertTrue(all(row['url'] in s['product']['images']['sku'] for row in selection['selected_sku_images']))

    def test_no_id_repair_updates_existing_reference_without_creating_id(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['REMOVE_TEXT','KEEP'],missing_sku_id=True,sku_on_first=True,snapshot_sku_rows=True)
            self.assertEqual(s['writer'].uploads,1)
            self.assertEqual(s['writer'].saves,1)
            self.assertEqual(s['product']['skus'][0]['skuImageUrl'],'https://fake/upload1')
            self.assertNotIn('skuId',s['product']['skus'][0])
            self.assertTrue(s['result']['content_validation']['ok'])

    def test_no_id_box_candidate_uses_the_existing_with_box_row(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['KEEP','KEEP'],box=True,missing_sku_id=True,snapshot_sku_rows=True)
            self.assertEqual(s['writer'].saves,1)
            self.assertTrue(s['result']['content_validation']['ok'])
            selection=json.loads((s['root']/'v2_sku_selection.json').read_text(encoding='utf-8'))
            self.assertEqual(selection['sku_packaging_decision'],'WITH_RETAIL_BOX')
            self.assertEqual(selection['row_assignments'][0]['index'],0)

    def test_sku_reference_drift_to_another_approved_url_is_detected(self):
        from mye_c_automation.v2_remediation import verify_content
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['KEEP','KEEP'],two_sku_rows=True)
            after=copy.deepcopy(s['product']);current=after['skus'][1]['skuImageUrl']
            replacement=next(url for url in after['images']['sku'] if url!=current)
            after['skus'][1]['skuImageUrl']=replacement
            plan=json.loads((s['root']/'plan.v2.json').read_text(encoding='utf-8'))
            with patch.object(s['writer'],'product',return_value=after):result=verify_content(s['root'],plan,s['writer'])
            self.assertFalse(result['ok'])
            self.assertFalse(result['sku_references_exact'])

    def test_real_two_row_shape_assigns_both_images_preserving_sku_attributes(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['KEEP','KEEP'],missing_sku_id=True,snapshot_sku_rows=True,two_sku_rows=True)
            for current,original in zip(s['product']['skus'],s['original']['skus']):
                self.assertEqual({k:v for k,v in current.items() if k!='skuImageUrl'}, {k:v for k,v in original.items() if k!='skuImageUrl'})
            self.assertNotEqual(s['product']['skus'][0]['skuImageUrl'],s['product']['skus'][1]['skuImageUrl'])
            self.assertEqual(s['result']['status'],'AUTO_VERIFIED')
            self.assertTrue(s['result']['content_validation']['ok'])
            self.assertTrue(all('skuId' not in row for row in s['product']['skus']))

    def test_no_id_referenced_deletion_rebinds_same_existing_row(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['DELETE','KEEP','KEEP'],missing_sku_id=True,sku_on_first=True,snapshot_sku_rows=True)
            removed=s['original']['images']['main'][0]
            self.assertNotIn(removed,s['product']['images']['main'])
            self.assertNotEqual(s['product']['skus'][0]['skuImageUrl'],removed)
            self.assertTrue(s['result']['content_validation']['ok'])

    def test_no_id_reference_only_repair_uses_real_reference_source(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['REMOVE_TEXT','KEEP'],missing_sku_id=True,reference_only=True,snapshot_sku_rows=True)
            self.assertEqual(s['writer'].uploads,1)
            self.assertEqual(s['product']['skus'][0]['skuImageUrl'],'https://fake/upload1')
            self.assertTrue(s['result']['content_validation']['ok'])

    def test_no_id_reference_only_deletion_remains_bound_to_approved_row(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['DELETE','KEEP','KEEP'],missing_sku_id=True,reference_only=True,snapshot_sku_rows=True)
            self.assertNotEqual(s['product']['skus'][0]['skuImageUrl'],s['original']['skus'][0]['skuImageUrl'])
            self.assertEqual(s['writer'].saves,1)
            self.assertTrue(s['result']['content_validation']['ok'])
