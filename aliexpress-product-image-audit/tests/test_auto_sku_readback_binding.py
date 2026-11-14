import tempfile
import unittest
import hashlib
from pathlib import Path
from unittest.mock import Mock
from auto_workflow import verify_content
from candidate_quality import CandidateQualityGate
from job_manager import atomic_json

class SkuReadbackBindingTests(unittest.TestCase):
    def test_clean_wrong_model_or_changed_bytes_cannot_verify(self):
        with tempfile.TemporaryDirectory() as root:
            digest=hashlib.sha256(b'expected bytes').hexdigest()
            row={'remedy_id':'SKU','action':'SKU_ASSIGN','decision':'AUTO_SAFE','target':{'sku_ids':['1']},'assignments':{'1':'https://x/body'},'assignment_evidence':{'1':{'sha256':digest,'model':'NA-H74','image_type':'FIGURE'}}}
            atomic_json(Path(root)/'auto_decisions.json',{'items':[row]})
            atomic_json(Path(root)/'audit_raw.json',{'images':[]})
            writer=Mock();writer.product.return_value={'skus':[{'skuId':1,'skuName':'without box','skuImageUrl':'https://x/body'}]};writer.fetch_image.return_value=b'expected bytes'
            inspector=Mock();inspector.observe_image.return_value={'clean':True,'verified':True,'image_type':'FIGURE','model':'MS-01'}
            result=verify_content(root,{'pid':1},writer,CandidateQualityGate(inspector))
            self.assertFalse(result['ok'])
            inspector.observe_image.return_value['model']='NA-H74';writer.fetch_image.return_value=b'wrong bytes'
            self.assertFalse(verify_content(root,{'pid':1},writer,CandidateQualityGate(inspector))['ok'])
    def test_generated_assignment_reads_final_uploaded_url_and_bound_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            digest=hashlib.sha256(b'crop bytes').hexdigest()
            row={'remedy_id':'SKU','action':'SKU_ASSIGN','decision':'AUTO_SAFE','target':{'sku_ids':['1']},'assignments':{'1':'https://x/dirty'},'requires_remedy_ids':['CROP'],'assignment_evidence':{'1':{'sha256':digest,'model':'NA-H74','image_type':'FIGURE'}}}
            atomic_json(Path(root)/'auto_decisions.json',{'items':[row]});atomic_json(Path(root)/'audit_raw.json',{'images':[]})
            expected={'skus':[{'skuId':1,'skuName':'without box','skuImageUrl':'https://x/uploaded'}]}
            atomic_json(Path(root)/'expected_after.json',expected)
            writer=Mock();writer.product.return_value=expected
            def fetch(url):
                self.assertEqual(url,'https://x/uploaded');return b'crop bytes'
            writer.fetch_image.side_effect=fetch
            inspector=Mock();inspector.observe_image.return_value={'clean':True,'verified':True,'image_type':'FIGURE','model':'NA-H74'}
            self.assertTrue(verify_content(root,{'pid':1},writer,CandidateQualityGate(inspector))['ok'])
