"""Current single-reviewer and record-only listing identity contract."""
import copy
import json
import unittest
from unittest.mock import patch
import test_v2_vision as vision
import test_v2_repairs_sku as sku_fixtures
from test_v2_vision import observation


class DeepSeekOnlyTests(unittest.TestCase):
    setUp=vision.VisionTests.setUp
    client=vision.VisionTests.client
    decide=vision.VisionTests.decide

    def test_identity_unknown_no_and_low_field_score_do_not_block(self):
        def reply(model,item):
            self.assertEqual(model,'deepseek-v4.1-flash')
            return observation(item,confidence=.8,
                product_identity=dict(same_product_as_context='UNKNOWN',structure_match='NO',model_visible='NO',color_match='UNKNOWN'),
                field_confidences=dict(visual_class=.9,product_identity=.2,box_relation=.9,watermark_ownership=.9,sku_suitability=.9))
        client,calls=self.client(reply)
        result=self.decide(client)
        self.assertEqual(result['decision'],'KEEP')
        self.assertEqual(result['observation']['product_identity']['structure_match'],'NO')
        self.assertEqual(result['observation']['field_confidences']['product_identity'],.2)
        self.assertEqual([m for m,_ in calls],['deepseek-v4.1-flash'])
        self.assertFalse(result['second_model_called'])
        self.assertEqual(result['models'],['deepseek-v4.1-flash'])

    def test_old_pair_profile_cannot_invoke_mimo_for_audit(self):
        from mye_c_automation.ai_judge.image_action_decision import decide
        client,calls=self.client(lambda m,i:observation(i,'DELETE'))
        client.models=('deepseek-v4.1-flash','mimo-v2.6-pro')
        self.assertEqual(decide(client,self.item,{})['decision'],'DELETE')
        self.assertEqual([m for m,_ in calls],['deepseek-v4.1-flash'])

    def test_old_pair_profile_cannot_invoke_mimo_for_quality(self):
        client,calls=self.client(lambda m,i:dict(task_type='image_quality_v2',item_id=i['id'],decision='MATCH',confidence=.8,abstain=False,evidence_ids=i['evidence_ids'],checks={k:True for k in ('identity_preserved','packaging_preserved','protected_print_preserved','overlay_removed','no_new_artifacts')}))
        client.models=('deepseek-v4.1-flash','mimo-v2.6-pro')
        result=client.classify('image_quality_v2',dict(self.item,task_type='image_quality_v2'),{})
        self.assertEqual(result['status'],'CLEAN')
        self.assertEqual(len(result['results']),1)
        self.assertEqual([m for m,_ in calls],['deepseek-v4.1-flash'])

    def test_mimo_only_profile_fails_before_transport(self):
        client,calls=self.client(lambda m,i:self.fail('disabled reviewer called'))
        client.models=('mimo-v2.6-pro',)
        with self.assertRaisesRegex(ValueError,'DEEPSEEK_REVIEW_MODEL_REQUIRED'):
            self.decide(client)
        self.assertFalse(calls)

    def test_single_model_config_and_mimo_dispatch_disabled(self):
        from mye_c_automation.model_config import validate_config, require_enabled_model
        config=dict(schema='model-gateway/v1',base_url='http://127.0.0.1:8788/v1',models=['deepseek-v4.1-flash'],max_output_tokens=16384,retries=0,timeout=150)
        self.assertEqual(validate_config(config)['models'],config['models'])
        for model in ('mimo-v2.6-pro','workbuddy/mimo-v2.6-pro'):
            with self.assertRaisesRegex(ValueError,'MODEL_DISABLED_BY_PROJECT_SELECTION'):
                require_enabled_model(model)

    def test_sku_selection_does_not_require_listing_identity_match(self):
        from mye_c_automation.sku_assignment import select_v2
        records=sku_fixtures.RepairSkuTests().records()
        for row in records:
            row['observation']['product_identity']=dict(same_product_as_context='NO',structure_match='UNKNOWN',model_visible='UNKNOWN',color_match='UNKNOWN')
        original=copy.deepcopy(records)
        selection=select_v2({'skus':[dict(skuId='real',skuName='Without Box')]},records)
        self.assertEqual(len(selection['selected_sku_images']),2)
        self.assertTrue(selection['assignments'])
        self.assertEqual(records,original)

    def test_low_action_confidence_is_record_only_and_abstention_still_reviews(self):
        for changes in (dict(confidence=.79),dict(abstain=True),dict(decision='REVIEW')):
            client,calls=self.client(lambda m,i:observation(i,**changes))
            client.result_cache.root=self.root/str(len(str(changes)))
            client.cache=client.result_cache.root;client.cache.mkdir(exist_ok=True)
            result=self.decide(client)
            self.assertEqual(result['decision'],'KEEP' if 'confidence' in changes else 'REVIEW')
            if 'confidence' in changes:self.assertEqual(result['observation']['confidence'],changes['confidence'])
            self.assertEqual(len(calls),1)

    def test_fake_repair_save_and_readback_use_only_deepseek(self):
        import tempfile
        from test_v2_workflow import V2WorkflowTests
        def recorded_identity(item,decision='KEEP',**changes):
            row=observation(item,decision,**changes)
            row['product_identity']=dict(same_product_as_context='NO',structure_match='UNKNOWN',model_visible='NO',color_match='UNKNOWN')
            return row
        with tempfile.TemporaryDirectory() as root,patch('test_v2_workflow.observation',side_effect=recorded_identity):
            s=V2WorkflowTests.scenario(self,root,['REMOVE_TEXT','KEEP'])
            self.assertEqual(s['writer'].uploads,1)
            self.assertEqual(s['writer'].saves,1)
            self.assertTrue(s['result']['content_validation']['ok'])
            report=json.loads((s['root']/'full_audit_report.json').read_text())
            metrics=json.loads((s['root']/'full_ai_metrics.json').read_text())
            self.assertEqual(report['models'],['deepseek-v4.1-flash'])
            self.assertEqual({c['model'] for c in metrics['calls']},{'deepseek-v4.1-flash'})
            evidence_files=list((s['root']/'quality_evidence').glob('*.json'))
            self.assertTrue(evidence_files)
            for evidence in evidence_files:
                quality=json.loads(evidence.read_text())
                self.assertEqual(quality['judgement']['models'],['deepseek-v4.1-flash'])
                self.assertEqual(len(quality['judgement']['results']),1)
            self.assertEqual(s['product']['descriptionJson'],s['original']['descriptionJson'])


if __name__=='__main__':unittest.main()
