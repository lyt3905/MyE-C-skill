import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from watermark_module_fixtures import sample


class WatermarkIntegrationTests(unittest.TestCase):
    def test_plan_verification_binds_module_receipt(self):
        from mye_c_automation.v2_remediation import verify
        with tempfile.TemporaryDirectory() as d:
            s=self.scenario(d)
            proofs=json.loads((s['root']/'v2_action_proofs.json').read_text())['candidates']
            row=next(x for x in proofs if x['action']=='REMOVE_TEXT')
            verify(s['root'],row,s['original'])
            receipt=next(s['root'].glob('v2_candidates/**/processing-result.json'));receipt.write_text('{}')
            with self.assertRaisesRegex(ValueError,'MODULE_RECEIPT'):verify(s['root'],row,s['original'])

    def test_nested_area_limit_is_respected_by_existing_remove_text(self):
        from mye_c_automation.image_repairs_v2 import remove_text
        with tempfile.TemporaryDirectory() as d:
            r=sample(d)
            with self.assertRaisesRegex(ValueError,'MASK_AREA'):
                remove_text(r['image_path'],r,Path(d)/'out',rights='OWNED_OR_LICENSED',processing_policy=dict(max_mask_area=.001))

    def test_complex_lama_load_failure_has_receipt_and_no_upload(self):
        with tempfile.TemporaryDirectory() as d:
            model=Path(d)/'bad-model.pt';model.write_bytes(b'bad local weights')
            with patch('mye_c_automation.image_repairs_v2.lama_torchscript',side_effect=ValueError('LAMA_LOAD_FAILURE')):
                s=self.scenario(d,complexity='COMPLEX',options=dict(lama_model_path=str(model)))
            self.assertEqual(s['writer'].uploads,0)
            receipts=[json.loads(p.read_text()) for p in s['root'].glob('v2_candidates/**/processing-result.json')]
            self.assertEqual(len(receipts),1);self.assertEqual(receipts[0]['processing_status'],'FAILED')
            self.assertIn('LAMA_LOAD_FAILURE',receipts[0]['failure_reason'])

    def test_configuration_and_safe_review_payload_preserve_only_image_observations(self):
        from mye_c_automation.job_manager import JobManager
        from mye_c_automation.ai_judge.client import safe_payload
        with tempfile.TemporaryDirectory() as d:
            r=sample(d);job=JobManager(Path(d)/'jobs').create(1,7,{},image_workflow='v2',image_options=dict(watermark_processing=dict(context_pixels=24)))
            self.assertEqual(job['image_options']['watermark_processing']['context_pixels'],24)
            r['descriptionJson']='secret description';r['price']=12345
            sent=safe_payload(dict(id='Q',task_type='image_quality_v2',repair_observation=r),{})
            self.assertEqual(sent['item']['repair_observation']['watermarks'],r['watermarks'])
            self.assertNotIn('secret description',json.dumps(sent));self.assertNotIn('12345',json.dumps(sent));self.assertNotIn('image_path',json.dumps(sent))

    def test_existing_remove_text_delegates_explicit_regions_and_preserves_receipt(self):
        from mye_c_automation.image_repairs_v2 import remove_text
        with tempfile.TemporaryDirectory() as d:
            r=sample(d,boxes=[[.02,.1,.12,.2],[.7,.6,.8,.7]])
            observation=dict(r,background_complexity='SMOOTH')
            result=remove_text(r['image_path'],observation,Path(d)/'out',rights='OWNED_OR_LICENSED')
            self.assertEqual(result.get('processing_status'),'PROCESSED','Explicit V2 path still bypasses module')
            self.assertEqual(result['quality_status'],'PENDING_AI_REVIEW')
            self.assertEqual(result['watermark_instances_processed'],2)
            self.assertTrue(Path(result['visualization_path']).is_file())

    def scenario(self,root,*,quality=False,rights='OWNED_OR_LICENSED',complexity='SMOOTH',options=None):
        from test_v2_workflow import V2WorkflowTests
        fixture=sample(Path(root)/'fixture',boxes=[[.02,.1,.12,.16],[.76,.6,.9,.65]],complexity=complexity)
        def transform(row,item):
            if row['decision']=='REMOVE_TEXT':row.update(watermarks=fixture['watermarks'],preserve_regions=fixture['preserve_regions'],background_complexity=complexity)
            return row
        return V2WorkflowTests().scenario(Path(root),['REMOVE_TEXT','KEEP'],rights=rights,quality_fail=quality,
            asset_images={0:fixture['image_path']},observation_transform=transform,image_options=options)

    def test_native_multi_region_reaches_existing_plan_once_save_and_readback(self):
        with tempfile.TemporaryDirectory() as d:
            s=self.scenario(d)
            self.assertEqual((s['writer'].uploads,s['writer'].saves),(1,1))
            self.assertEqual(s['calls'].count('image_quality_v2'),1)
            receipts=list(s['root'].glob('v2_candidates/**/processing-result.json'))
            self.assertTrue(receipts,'Native REMOVE_TEXT has no generic module evidence')
            receipt=json.loads(receipts[0].read_text());self.assertEqual(receipt['watermark_instances_processed'],2)
            self.assertTrue(s['result']['content_validation']['ok']);self.assertEqual(s['product']['descriptionJson'],s['original']['descriptionJson'])

    def test_denied_identity_unknown_or_residual_cannot_publish(self):
        for mode in ('identity','residual','unknown-rights'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                s=self.scenario(d,quality='identity' if mode=='identity' else mode=='residual',rights='RIGHTS_UNKNOWN' if mode=='unknown-rights' else 'OWNED_OR_LICENSED')
                self.assertEqual(s['writer'].uploads,0)
                self.assertLessEqual(s['calls'].count('image_quality_v2'),2)
                self.assertEqual(s['product']['images']['main'],s['original']['images']['main'])
                if mode=='identity':self.assertEqual(s['calls'].count('image_quality_v2'),1)
                if mode=='residual':
                    receipts=[json.loads(p.read_text()) for p in s['root'].glob('v2_candidates/**/processing-result.json')]
                    self.assertEqual(len(receipts),2)
                    self.assertEqual(receipts[0]['algorithm_used'],['OPENCV_TELEA']);self.assertEqual(receipts[1]['algorithm_used'],['OPENCV_NS'])

    def test_simple_roi_does_not_load_configured_lama(self):
        with tempfile.TemporaryDirectory() as d:
            model=Path(d)/'unused-model.pt';model.write_bytes(b'not a real model, must not load for simple ROI')
            with patch('mye_c_automation.image_repairs_v2.lama_torchscript',side_effect=AssertionError('Unneeded LaMa load')):
                s=self.scenario(d,options=dict(lama_model_path=str(model)))
            self.assertEqual(s['writer'].uploads,1)

    def test_existing_reviewer_gets_original_observation_and_mask_preview(self):
        from mye_c_automation.visual_quality import VisualQualityInspector
        from mye_c_automation.image_repairs_v2 import remove_text
        from mye_c_automation.ai_judge.client import JudgeClient
        from mye_c_automation.budget_manager import BudgetManager
        calls=[]
        def respond(model,item,context):
            calls.append(item)
            row=dict(task_type='image_quality_v2',item_id=item['id'],confidence=0.0,abstain=False,decision='MATCH',evidence_ids=item['evidence_ids'],checks={k:True for k in ('identity_preserved','packaging_preserved','protected_print_preserved','overlay_removed','no_new_artifacts')})
            return dict(choices=[dict(message=dict(content=json.dumps(row)))],usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);r=sample(root);repair=remove_text(r['image_path'],r,root/'out',rights='OWNED_OR_LICENSED');budget=BudgetManager(dict(ai_requests=2,full_resolution_images=10))
            try:
                client=JudgeClient(budget,root/'cache',transport=respond,models=('deepseek-v4.1-flash',),retries=0)
                inspector=VisualQualityInspector(root,dict(budget={}),judge=client)
                checked=inspector.inspect_v2(r['image_path'],repair['output_path'],{},'REMOVE_TEXT',repair['mask_path'],observation=r)
                self.assertTrue(checked['ok'])
                self.assertEqual(calls[0].get('repair_observation',{}).get('watermarks'),r['watermarks'])
                self.assertIn('MASK_VISUALIZATION',calls[0]['evidence_ids'])
            finally:budget.close()
