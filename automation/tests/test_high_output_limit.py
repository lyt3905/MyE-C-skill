import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from mye_c_automation.model_config import validate_config,load_config
from mye_c_automation.job_manager import JobManager
from mye_c_automation.budget_manager import BudgetManager
from mye_c_automation.ai_judge.client import JudgeClient
from model_budget_fixtures import request_with_fake_budget

PROFILE=dict(schema='model-gateway/v1',base_url='http://127.0.0.1:8788/v1',models=['deepseek-v4.1-flash'],max_output_tokens=100000,retries=0,timeout=150,reasoning_effort='low',image_concurrency=10)


class HighOutputTests(unittest.TestCase):
    def test_hundred_thousand_profile_schema_and_new_job_are_bound(self):
        self.assertEqual(validate_config(PROFILE),PROFILE)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'model.json';path.write_text(json.dumps(PROFILE))
            self.assertEqual(load_config(path),PROFILE)
            manager=JobManager(Path(d)/'jobs');job=manager.create(1,7,{},model_config=PROFILE)
            self.assertEqual(manager.load(job['job_id'])['model_config'],PROFILE)

    def test_wire_has_low_thinking_and_hundred_thousand_not_disabled(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'VLM_API_KEY':'fake-key'}):
            budget=BudgetManager(dict(ai_requests=1))
            try:
                client=JudgeClient(budget,Path(d)/'cache',config=PROFILE)
                class Reply:
                    def __enter__(self):return io.BytesIO(b'{}')
                    def __exit__(self,*a):return False
                with patch('mye_c_automation.ai_judge.client._open_model_request',return_value=Reply()) as send:
                    request_with_fake_budget(client,'deepseek-v4.1-flash',dict(id='I',task_type='image_quality_v2',evidence_ids=['I']),{})
                body=json.loads(send.call_args.args[0].data)
                self.assertEqual(body['max_tokens'],100000);self.assertEqual(body['reasoning_effort'],'low')
                self.assertNotIn('thinking',body);self.assertEqual(body['response_format'],dict(type='json_object'))
            finally:budget.close()

    def test_environment_accepts_new_range_and_rejects_above_bound(self):
        with tempfile.TemporaryDirectory() as d:
            for value in ('16384','16385','100000','100001'):
                with self.subTest(value=value),patch.dict(os.environ,{'VLM_MAX_OUTPUT_TOKENS':value}):
                    budget=BudgetManager(dict(ai_requests=0))
                    try:
                        if value=='100001':
                            with self.assertRaises(ValueError):JudgeClient(budget,d)
                        else:self.assertEqual(JudgeClient(budget,d).max_output_tokens,int(value))
                    finally:budget.close()
