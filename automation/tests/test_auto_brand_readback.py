import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from mye_c_automation.auto_workflow import verify_content
from mye_c_automation.job_manager import atomic_json
from mye_c_automation.candidate_quality import CandidateQualityGate

class BrandReadbackTests(unittest.TestCase):
    def test_brand_only_readback_is_verified_against_rule(self):
        with tempfile.TemporaryDirectory() as root:
            row={'remedy_id':'BRAND','action':'BRAND_CODE','decision':'AUTO_SAFE','target':{'field':'brandId'},'brandId':200017853,'brand_field_verified':True}
            atomic_json(Path(root)/'auto_decisions.json',{'items':[row]})
            writer=Mock();writer.product.return_value={'title':'NA-H74 威震天','brandId':200017853}
            result=verify_content(root,{'pid':1,'shop':7},writer,CandidateQualityGate())
            self.assertTrue(result['ok'])
            writer.product.return_value['brandId']=200014695
            self.assertFalse(verify_content(root,{'pid':1,'shop':7},writer,CandidateQualityGate())['ok'])
