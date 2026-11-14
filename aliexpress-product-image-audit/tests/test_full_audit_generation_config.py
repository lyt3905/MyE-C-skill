"""Only Fake HTTP responses; verify main gateway request generation options."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ai_judge import JudgeClient
from budget_manager import BudgetManager
from job_manager import JobManager
from model_config import validate_config,fingerprint
from test_model_gateway_cli import PROFILE,response

class FullAuditGenerationConfigTests(unittest.TestCase):
    def test_low_effort_and_larger_output_reach_both_models_and_frozen_job(self):
        profile=dict(PROFILE,base_url='http://127.0.0.1:8788/v1',models=['deepseek-v4.1-flash','kimi-k3-1'],
                     max_output_tokens=16384,reasoning_effort='low')
        self.assertEqual(validate_config(profile),profile)
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'VLM_API_KEY':'fake-key'}):
            budget=BudgetManager({'ai_requests':2});sent=[]
            try:
                manager=JobManager(Path(tmp)/'jobs');job=manager.create(1,7,{},model_config=profile)
                self.assertEqual(manager.load(job['job_id'])['model_config'],profile)
                c=JudgeClient(budget,Path(tmp)/'cache',config=profile,continue_model_errors=True)
                def send(req,timeout):
                    sent.append(json.loads(req.data));return io.BytesIO(json.dumps(response({'id':'A','evidence_ids':['A']})).encode())
                with patch('urllib.request.urlopen',side_effect=send):
                    result=c.classify('watermark',{'id':'A','task_type':'watermark','dimensions':[800,800],'evidence_ids':['A']},{})
                self.assertEqual(result['status'],'CLEAN')
                self.assertEqual([r['model'] for r in sent],profile['models'])
                self.assertTrue(all(r['reasoning_effort']=='low' and r['max_tokens']==16384 for r in sent))
                self.assertEqual(c.metrics['reasoning_effort'],'low')
            finally:budget.close()

    def test_original_profile_hash_and_wire_remain_compatible(self):
        expected=hashlib.sha256(json.dumps(PROFILE,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(validate_config(PROFILE),PROFILE)
        self.assertEqual(fingerprint(PROFILE),expected)
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'VLM_API_KEY':'fake-key'}):
            b=BudgetManager({'ai_requests':2});sent=[]
            try:
                c=JudgeClient(b,tmp,config=PROFILE)
                def send(req,timeout):
                    sent.append(json.loads(req.data));return io.BytesIO(json.dumps(response({'id':'A','evidence_ids':['A']})).encode())
                with patch('urllib.request.urlopen',side_effect=send):
                    c.classify('watermark',{'id':'A','task_type':'watermark','dimensions':[800,800],'evidence_ids':['A']},{})
                self.assertEqual(len(sent),2)
                self.assertTrue(all('reasoning_effort' not in row for row in sent))
            finally:b.close()

    def test_invalid_reasoning_effort_is_rejected(self):
        for value in (None,True,0,[],{},'auto','LOW',''):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'INVALID_MODEL_CONFIG:reasoning_effort'):
                validate_config(dict(PROFILE,reasoning_effort=value))

    def test_effort_changes_are_bound_into_profile_fingerprint(self):
        low=dict(PROFILE,reasoning_effort='low');high=dict(PROFILE,reasoning_effort='high')
        self.assertNotEqual(fingerprint(low),fingerprint(PROFILE))
        self.assertNotEqual(fingerprint(low),fingerprint(high))

if __name__=='__main__':unittest.main()
