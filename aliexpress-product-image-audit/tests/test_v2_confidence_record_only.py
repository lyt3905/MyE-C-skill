"""V2 model confidence is an unchanged observation, never an action gate."""
import copy
import json
import tempfile
import unittest
from unittest.mock import patch
import test_v2_vision as vision
import test_v2_repairs_sku as sku_fixtures
import test_v2_workflow as workflow


def low_scores(row):
    row=copy.deepcopy(row)
    for key in ('confidence','retail_box_confidence','toy_confidence'):
        if key in row:row[key]=0.0
    if 'field_confidences' in row:
        row['field_confidences']={k:0.0 for k in row['field_confidences']}
    for mark in row.get('watermarks',[]):mark['confidence']=0.0
    return row


def scenario(case,root,actions,**options):
    from ai_judge.client import JudgeClient
    original=JudgeClient.__init__
    def initialize(client,*args,**kwargs):
        transport=kwargs['transport']
        def send(model,item,context):
            raw=copy.deepcopy(transport(model,item,context))
            row=json.loads(raw['choices'][0]['message']['content'])
            raw['choices'][0]['message']['content']=json.dumps(low_scores(row))
            return raw
        kwargs['transport']=send
        original(client,*args,**kwargs)
    with patch.object(JudgeClient,'__init__',initialize):
        return workflow.V2WorkflowTests.scenario(case,root,actions,**options)


class ConfidenceRecordOnlyTests(unittest.TestCase):
    setUp=vision.VisionTests.setUp
    client=vision.VisionTests.client
    decide=vision.VisionTests.decide

    def test_zero_confidence_does_not_override_keep_delete_or_remove_text(self):
        for action in ('KEEP','DELETE','REMOVE_TEXT'):
            with self.subTest(action=action):
                def reply(model,item):
                    row=vision.observation(item,action,field_confidences={k:0.0 for k in ('visual_class','product_identity','box_relation','watermark_ownership','sku_suitability')})
                    if action=='REMOVE_TEXT':
                        row['watermarks']=[dict(kind='STORE_WATERMARK',owner='THIRD_PARTY_STORE',bbox=[.01,.8,.1,.9],confidence=0.0,preserve_overlap_risk='LOW')]
                    return low_scores(row)
                client,calls=self.client(reply)
                client.cache=self.root/action;client.cache.mkdir();client.result_cache.root=client.cache
                result=self.decide(client)
                self.assertEqual(result['decision'],action)
                self.assertEqual(result['observation']['confidence'],0.0)
                self.assertEqual(result['confidence_policy'],'RECORD_ONLY')
                self.assertEqual(len(calls),1)

    def test_zero_region_confidence_still_generates_only_the_requested_mask(self):
        from image_repairs_v2 import mask_for
        row=vision.observation(self.item,'REMOVE_TEXT',watermarks=[dict(kind='STORE_WATERMARK',owner='THIRD_PARTY_STORE',bbox=[.1,.8,.2,.9],confidence=0.0,preserve_overlap_risk='LOW')])
        mask,area=mask_for((100,100),row)
        self.assertGreater(area,0)
        self.assertEqual(mask[85,15],255)
        self.assertEqual(mask[40,40],0)
        self.assertEqual(row['watermarks'][0]['confidence'],0.0)

    def test_sku_ranking_and_eligibility_do_not_use_any_confidence(self):
        from sku_assignment import select_v2
        records=sku_fixtures.RepairSkuTests().records()
        product=dict(skus=[dict(skuId='A',skuName='Without Box'),dict(skuId='B',skuName='With Box')])
        baseline=select_v2(product,records)
        for n,row in enumerate(records):
            row['observation']=low_scores(row['observation'])
            row['observation']['confidence']=n*.1
        after=select_v2(product,records)
        self.assertEqual(after['assignments'],baseline['assignments'])
        self.assertEqual([r['sha256'] for r in after['selected_sku_images']],[r['sha256'] for r in baseline['selected_sku_images']])

    def test_low_box_score_does_not_prevent_box_selection(self):
        from sku_assignment import select_v2
        records=sku_fixtures.RepairSkuTests().records()[:1]
        o=records[0]['observation'];o.update(visual_class='RETAIL_BOX_ONLY',retail_box_status='PRESENT',box_relation='SAME_PRODUCT',retail_box_bbox=[.2,.2,.8,.8])
        o['sku_suitability'].update(is_retail_box_photo=True,recommended_group='WITH_RETAIL_BOX')
        records[0]['observation']=low_scores(o)
        self.assertEqual(select_v2(dict(skus=[dict(skuId='B',skuName='With Box')]),records)['assignments'],{'B':'https://fake/0'})

    def test_fake_repair_quality_sku_save_and_readback_accept_zero_scores(self):
        for missing in (False,True):
            with self.subTest(missing_id=missing),tempfile.TemporaryDirectory() as root:
                s=scenario(self,root,['REMOVE_TEXT','KEEP'],two_sku_rows=True,missing_sku_id=missing,snapshot_sku_rows=missing)
                self.assertEqual(s['writer'].uploads,1)
                self.assertEqual(s['writer'].saves,1)
                self.assertEqual(s['result']['status'],'AUTO_VERIFIED')
                self.assertTrue(s['result']['content_validation']['ok'])
                self.assertEqual(s['product']['descriptionJson'],s['original']['descriptionJson'])
                metrics=json.loads((s['root']/'full_ai_metrics.json').read_text())
                self.assertTrue(all(c['result']['confidence']==0.0 for c in metrics['calls']))
                protocol=json.loads((s['root']/'full_audit_protocol.json').read_text())
                self.assertEqual(protocol['confidence_policy'],'RECORD_ONLY')
                self.assertIsNone(protocol['threshold'])
                quality=json.loads((s['root']/'v2_quality.json').read_text())['items']
                self.assertTrue(quality)
                self.assertEqual(quality[0]['judgement']['results'][0]['confidence'],0.0)

    def test_low_score_never_overrides_an_explicit_quality_failure(self):
        with tempfile.TemporaryDirectory() as root:
            s=scenario(self,root,['REMOVE_TEXT','KEEP'],quality_fail='identity')
            self.assertEqual(s['writer'].uploads,0)
            self.assertEqual(s['product']['images']['main'],s['original']['images']['main'])
            quality=json.loads((s['root']/'v2_quality.json').read_text())['items']
            self.assertEqual(quality[0]['quality_status'],'FAIL_IDENTITY')

    def test_scoring_does_not_relabel_low_score_prediction_as_review(self):
        from shadow_evaluate import v2_quality_metrics
        from test_v2_accuracy import sample
        row=sample(confidence=0.0)
        report=v2_quality_metrics([row])
        self.assertEqual(report['synthetic']['actions']['DELETE']['proposed'],1)
        self.assertEqual(report['synthetic']['deferred_rate'],0)
        self.assertEqual(row['confidence'],0.0)

    def test_retained_box_evidence_uses_observation_not_low_score(self):
        def boxes(item,decision='KEEP',**changes):
            row=vision.observation(item,decision,**changes)
            row.update(visual_class='TOY_WITH_RETAIL_BOX',retail_box_status='PRESENT',retail_box_bbox=[.1,.1,.3,.4],box_relation='SAME_PRODUCT')
            row['sku_suitability'].update(is_retail_box_photo=True,recommended_group='WITH_RETAIL_BOX')
            row['product_identity']['same_product_as_context']='UNKNOWN'
            return row
        with tempfile.TemporaryDirectory() as root,patch('test_v2_workflow.observation',side_effect=boxes):
            s=scenario(self,root,['DELETE','KEEP'])
            self.assertEqual(s['writer'].saves,1)
            self.assertNotIn(s['original']['images']['main'][0],s['product']['images']['main'])
            self.assertTrue(s['result']['content_validation']['ok'])


if __name__=='__main__':unittest.main()
