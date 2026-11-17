import unittest
from mye_c_automation.ai_judge.client import safe_payload
from mye_c_automation.ai_judge.schemas import validate_result

class QualityContractTests(unittest.TestCase):
    def test_model_payload_has_no_paths_or_credentials(self):
        item={'id':'WM_MAIN_000','task_type':'watermark','image_id':'MAIN_000','local':'C:/private/key.jpg','local_path':'C:/private/file','cookie':'secret','extra_images':[{'path':'C:/private/source','sha256':'a'*64}]}
        context={'pid':1,'shop':7,'title':'Toy','cookie':'secret','skus':[{'skuId':1,'skuName':'without box','api_key':'secret'}],'identityJson':{'modelCode':'NA-H74','password':'secret'}}
        import json
        value=json.dumps(safe_payload(item,context))
        self.assertNotIn('private',value);self.assertNotIn('secret',value);self.assertIn('MAIN_000',value)
    def test_quality_result_requires_independent_flags(self):
        row={'task_type':'remedy_quality','item_id':'Q1','confidence':0.99,'abstain':False,'evidence_ids':['E1'],'decision':'MATCH'}
        with self.assertRaises(ValueError):validate_result(row,'remedy_quality','Q1')
        row['checks']={k:True for k in ('product_identity_match','source_clean','candidate_visual_validation','protected_elements_preserved','residual_pass','subject_bounds_safe')}
        self.assertEqual(validate_result(row,'remedy_quality','Q1'),row)
