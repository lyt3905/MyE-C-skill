"""Current user rule: model content decisions, fixed executable safeguards only."""
import copy
import tempfile
import unittest
from unittest.mock import patch
import test_v2_vision as vision
from test_v2_vision import observation


def mark(**changes):
    value=dict(kind='UNKNOWN_TEXT',owner='UNKNOWN',bbox=[.02,.8,.2,.9],
               confidence=0.,preserve_overlap_risk='LOW')
    value.update(changes)
    return value


class ModelDirectedTests(unittest.TestCase):
    setUp=vision.VisionTests.setUp
    client=vision.VisionTests.client
    decide=vision.VisionTests.decide

    def test_delete_survives_unknown_class_owner_and_box_attributes(self):
        client,_=self.client(lambda m,i:observation(i,'DELETE',visual_class='UNKNOWN',
            retail_box_status='UNCERTAIN',watermarks=[mark()],clear=False,subject_complete=False))
        result=self.decide(client)
        self.assertEqual(result['decision'],'DELETE')
        self.assertEqual(result['observation'],result['results'][0])
        self.assertEqual(result['reason_codes'],[])
        self.assertEqual(result['policy_adjustments'],[])
        self.assertEqual(result['decision_authority'],'MODEL')

    def test_keep_is_not_overridden_by_store_frame_geometry(self):
        client,_=self.client(lambda m,i:observation(i,'KEEP',visual_class='DECORATED_COMPOSITE',
            watermarks=[mark(kind='STORE_WATERMARK',overlay_role='OTHER_STORE_FRAME',bbox=[0,0,1,1])]))
        with patch('mye_c_automation.ai_judge.image_action_decision.apply_visual_rules',side_effect=AssertionError('no program semantic decision')):
            result=self.decide(client)
        self.assertEqual(result['decision'],'KEEP')
        self.assertEqual(result['observation'],result['results'][0])

    def test_review_abstain_and_transport_failure_stay_unresolved(self):
        for action,abstain in (('REVIEW',False),('DELETE',True)):
            client,_=self.client(lambda m,i:observation(i,action,abstain=abstain))
            client.result_cache.root=self.root/(action+str(abstain))
            self.assertEqual(self.decide(client)['decision'],'REVIEW')
        client,_=self.client(lambda m,i:{})
        client.result_cache.root=self.root/'invalid'
        self.assertEqual(self.decide(client)['decision'],'REVIEW')

    def test_explicit_region_action_controls_execution_not_owner_or_kind(self):
        from mye_c_automation.ai_judge.image_action_decision import validate,mark_disposition
        from mye_c_automation.image_repairs_v2 import mask_for
        erase=mark(action='REMOVE_TEXT',kind='PRODUCT_PRINT',owner='PRODUCT')
        retain=mark(action='KEEP',kind='STORE_WATERMARK',owner='THIRD_PARTY_STORE',bbox=[.3,.8,.5,.9])
        row=observation(self.item,'REMOVE_TEXT',watermarks=[erase,retain])
        self.assertEqual(validate(row,self.item),row)
        self.assertEqual(mark_disposition(erase),'REMOVABLE')
        self.assertEqual(mark_disposition(retain),'PROTECTED')
        mask,_=mask_for((800,800),row)
        self.assertTrue(mask[680,80])
        self.assertFalse(mask[680,320])
        row['preserve_regions']=[dict(kind='AI_PROTECTED',bbox=erase['bbox'])]
        with self.assertRaisesRegex(ValueError,'PROTECTED_REGION_OVERLAP'):mask_for((800,800),row)

    def test_bad_region_action_and_bad_coordinates_are_rejected(self):
        from mye_c_automation.ai_judge.image_action_decision import validate
        for value in (mark(action='RUN_CODE'),mark(action='REMOVE_TEXT',bbox=[-1,0,.2,.2])):
            with self.assertRaises(ValueError):validate(observation(self.item,'REMOVE_TEXT',watermarks=[value]),self.item)

    def test_sku_uses_ai_attributes_without_class_or_watermark_veto(self):
        from test_v2_repairs_sku import RepairSkuTests
        from mye_c_automation.sku_assignment import select_v2
        rows=RepairSkuTests().records()[:2]
        for r in rows:
            r['observation'].update(visual_class='UNKNOWN',clear=False,subject_complete=False,
                watermarks=[mark(kind='STORE_WATERMARK')])
        result=select_v2(dict(skus=[dict(skuId='a',skuName='no retail box'),dict(skuId='b',skuName='with retail box')]),rows)
        self.assertEqual(len(result['assignments']),2)
        self.assertEqual(len(set(result['assignments'].values())),2)
        for r in rows:r['observation']['retail_box_status']='UNCERTAIN'
        self.assertFalse(select_v2(dict(skus=[dict(skuId='a',skuName='no retail box')]),rows)['assignments'])
        for r in rows:r.update(width=0)
        self.assertFalse(select_v2(dict(skus=[]),rows)['selected_sku_images'])

    def test_same_photo_candidate_uses_ai_keep_and_technical_dimensions(self):
        from mye_c_automation.visual_versions import clean_candidate
        row=observation(self.item,visual_class='UNKNOWN',retail_box_status='UNCERTAIN',clear=False,watermarks=[mark()])
        result=dict(decision='KEEP',observation=row)
        content=dict(width=800,height=800,format='JPEG')
        self.assertTrue(clean_candidate(result,content))
        self.assertFalse(clean_candidate(dict(result,decision='REVIEW'),content))
        self.assertTrue(clean_candidate(result,dict(content,width=799)))
        self.assertFalse(clean_candidate(result,dict(content,width=0)))

    def test_model_unknown_sku_recommendation_is_not_invented_from_photo_flags(self):
        from test_v2_repairs_sku import RepairSkuTests
        from mye_c_automation.sku_assignment import select_v2
        rows=RepairSkuTests().records()
        for r in rows:r['observation']['sku_suitability']['recommended_group']='UNKNOWN'
        before=copy.deepcopy(rows)
        result=select_v2(dict(skus=[dict(skuId='a',skuName='no retail box')]),rows)
        self.assertFalse(result['assignments'])
        self.assertFalse(result['selected_sku_images'])
        self.assertIn('MODEL_SKU_UNRESOLVED',result['reason_codes'])
        self.assertEqual(rows,before)

    def test_unused_unknown_recommendation_does_not_block_approved_sku_choices(self):
        from test_v2_repairs_sku import RepairSkuTests
        from mye_c_automation.sku_assignment import select_v2
        rows=RepairSkuTests().records()
        rows[-1]['observation']['sku_suitability']['recommended_group']='UNKNOWN'
        result=select_v2(dict(skus=[dict(skuId='a',skuName='no retail box'),dict(skuId='b',skuName='with retail box')]),rows)
        self.assertEqual(len(result['assignments']),2)
        self.assertEqual(len(set(result['assignments'].values())),2)
        self.assertNotIn('MODEL_SKU_UNRESOLVED',result['reason_codes'])

    def test_fake_delete_unknown_attributes_syncs_aliases_and_body(self):
        import test_v2_workflow as workflow
        from test_v2_reusable_rules import WorkflowTests
        def reply(item,decision='KEEP',**changes):
            row=observation(item,decision,**changes)
            if decision=='DELETE':row.update(visual_class='UNKNOWN',retail_box_status='UNCERTAIN',watermarks=[mark()])
            return row
        with tempfile.TemporaryDirectory() as tmp,patch('test_v2_workflow.observation',side_effect=reply),patch('mye_c_automation.v2_remediation.record_seller_reassessment',side_effect=AssertionError('legacy program content review must not run')):
            result=workflow.V2WorkflowTests.scenario(self,tmp,['DELETE','KEEP'],product_transform=WorkflowTests.body)
        self.assertEqual(result['writer'].saves,1)
        self.assertEqual(result['writer'].uploads,0)
        self.assertTrue(result['result']['content_validation']['ok'])
        self.assertNotIn('body-alias',result['product']['descriptionJson'])
