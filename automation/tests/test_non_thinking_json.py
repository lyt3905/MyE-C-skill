import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from mye_c_automation.model_config import validate_config,load_config,fingerprint
from mye_c_automation.ai_judge.client import JudgeClient
from mye_c_automation.budget_manager import BudgetManager
from mye_c_automation.job_manager import JobManager
from model_budget_fixtures import request_with_fake_budget

PROFILE=dict(schema='model-gateway/v1',base_url='http://127.0.0.1:8788/v1',models=['deepseek-v4.1-flash'],max_output_tokens=16384,retries=0,timeout=150)


class NonThinkingTests(unittest.TestCase):
    def test_none_mode_validates_loads_and_is_frozen_in_new_jobs(self):
        config=dict(PROFILE,reasoning_effort='none')
        self.assertEqual(validate_config(config),config)
        self.assertNotEqual(fingerprint(config),fingerprint(dict(PROFILE,reasoning_effort='low')))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json';p.write_text(json.dumps(config),encoding='utf-8')
            self.assertEqual(load_config(p),config)
            manager=JobManager(Path(d)/'jobs');job=manager.create(1,7,{},model_config=config)
            self.assertEqual(manager.load(job['job_id'])['model_config'],config)

    def test_wire_turns_thinking_off_and_retains_json_mode(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'VLM_API_KEY':'fake-key'}):
            budget=BudgetManager(dict(ai_requests=1))
            try:
                client=JudgeClient(budget,Path(d)/'cache',config=dict(PROFILE,reasoning_effort='none'))
                class Reply:
                    def __enter__(self):return io.BytesIO(b'{}')
                    def __exit__(self,*a):return False
                with patch('mye_c_automation.ai_judge.client._open_model_request',return_value=Reply()) as send:
                    request_with_fake_budget(client,'deepseek-v4.1-flash',dict(id='A',task_type='image_quality_v2',evidence_ids=['A']),{})
                body=json.loads(send.call_args.args[0].data)
                self.assertEqual(body['reasoning_effort'],'none')
                self.assertEqual(body['thinking'],dict(type='disabled'))
                self.assertEqual(body['response_format'],dict(type='json_object'))
                self.assertEqual(client.metrics['reasoning_effort'],'none')
            finally:budget.close()

    def test_old_low_mode_wire_does_not_acquire_disabled_flag(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'VLM_API_KEY':'fake-key'}):
            budget=BudgetManager(dict(ai_requests=1))
            try:
                client=JudgeClient(budget,Path(d)/'cache',config=dict(PROFILE,reasoning_effort='low'))
                class Reply:
                    def __enter__(self):return io.BytesIO(b'{}')
                    def __exit__(self,*a):return False
                with patch('mye_c_automation.ai_judge.client._open_model_request',return_value=Reply()) as send:
                    request_with_fake_budget(client,'deepseek-v4.1-flash',dict(id='A',task_type='image_quality_v2',evidence_ids=['A']),{})
                body=json.loads(send.call_args.args[0].data)
                self.assertEqual(body['reasoning_effort'],'low');self.assertNotIn('thinking',body)
            finally:budget.close()
