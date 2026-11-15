from model_budget_fixtures import authorize_http_fake,request_with_fake_budget
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from ai_judge import JudgeClient
from budget_manager import BudgetManager


class GatewayDiagnosticsTests(unittest.TestCase):
    def test_unreadable_gateway_json_marks_usage_unknown_and_blocks_next_request(self):
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'VLM_API_KEY':'fake-test-key'}):
            budget=BudgetManager({'ai_requests':4,'total_tokens':50000})
            try:
                client=JudgeClient(budget,root,models=('fake',),retries=0)
                authorize_http_fake(client)
                with patch('ai_judge.client._open_model_request',side_effect=lambda *args,**kwargs:io.BytesIO(b'not-json')) as upstream:
                    first=client.classify('watermark',{'id':'A','task_type':'watermark','evidence_ids':['A'],'dimensions':[800,800]},{'pid':1})
                    self.assertEqual(first['status'],'NEEDS_REVIEW')
                    self.assertEqual(budget.snapshot()['token_status'],'UNKNOWN')
                    self.assertFalse(client.metrics['usage_available'])
                    self.assertIsNone(client.metrics['total_tokens'])
                    second=client.classify('watermark',{'id':'B','task_type':'watermark','evidence_ids':['B'],'dimensions':[800,800]},{'pid':1})
                    self.assertEqual(second['error'],'BUDGET_EXCEEDED')
                    self.assertEqual(upstream.call_count,1)
                    self.assertEqual(client.metrics['requests'],1)
            finally:budget.close()

    def test_known_usage_schema_failure_preserves_actual_token_accounting(self):
        with tempfile.TemporaryDirectory() as root:
            budget=BudgetManager({'ai_requests':1,'total_tokens':20000})
            try:
                client=JudgeClient(budget,root,models=('fake',),retries=0,transport=lambda *args:
                    {'choices':[{'message':{'content':'{}'}}],
                     'usage':{'prompt_tokens':1,'completion_tokens':2,'total_tokens':3}})
                result=client.classify('watermark',{'id':'A','evidence_ids':['A'],'dimensions':[800,800]},{'pid':1})
                self.assertEqual(result['status'],'NEEDS_REVIEW')
                self.assertEqual(budget.snapshot()['token_status'],'ACTUAL_REPORTED')
                self.assertEqual(client.metrics['total_tokens'],3)
            finally:budget.close()

    def test_configured_output_limit_reaches_wire_and_default_is_unchanged(self):
        for setting, expected in ((None, 2000), ('4096', 4096)):
            with self.subTest(setting=setting), tempfile.TemporaryDirectory() as root:
                env={'VLM_API_KEY':'fake-test-key'}
                if setting:env['VLM_MAX_OUTPUT_TOKENS']=setting
                with patch.dict(os.environ,env,clear=True):
                    budget=BudgetManager({'ai_requests':1})
                    try:
                        client=JudgeClient(budget,root,models=('fake',),retries=0)
                        authorize_http_fake(client)
                        class Reply:
                            def __enter__(self):return io.BytesIO(b'{}')
                            def __exit__(self,*args):return False
                        with patch('ai_judge.client._open_model_request',return_value=Reply()) as mocked:
                            request_with_fake_budget(client,'fake',{'id':'A','task_type':'watermark','evidence_ids':['A'],'dimensions':[800,800]},{'pid':1})
                        body=json.loads(mocked.call_args.args[0].data)
                        self.assertEqual(body['max_tokens'],expected)
                    finally:budget.close()

    def test_output_limit_is_reserved_before_provider_call(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ,{'VLM_MAX_OUTPUT_TOKENS':'4096'}):
            budget=BudgetManager({'ai_requests':1,'total_tokens':7000})
            try:
                client=JudgeClient(budget,root,models=('fake',),retries=0,
                    transport=lambda *args:self.fail('Configured output was not reserved'))
                result=client.classify('watermark',{'id':'A','evidence_ids':['A'],'dimensions':[800,800]},{'pid':1})
                self.assertEqual(result['error'],'BUDGET_EXCEEDED')
                self.assertEqual(client.metrics['requests'],0)
                self.assertEqual(budget.snapshot()['used']['ai_requests'],0)
            finally:budget.close()

    def test_invalid_output_limit_fails_before_requests(self):
        for value in ('0','-1','16385','a','4.5',''):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as root:
                with patch.dict(os.environ,{'VLM_MAX_OUTPUT_TOKENS':value}):
                    budget=BudgetManager({'ai_requests':1})
                    try:
                        with self.assertRaisesRegex(ValueError,'VLM_MAX_OUTPUT_TOKENS'):
                            JudgeClient(budget,root)
                    finally:budget.close()

    def test_http_failure_keeps_safe_diagnostics_and_unknown_usage(self):
        for code, message, expected in (
            (502,'WorkBuddy: an empty reply; the whole output spent on reasoning. fake-test-key','OUTPUT_LIMIT_EXHAUSTED'),
            (429,'private upstream body fake-test-key',None),
        ):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as root:
                budget=BudgetManager({'ai_requests':5,'total_tokens':50000})
                def fail(*args):
                    raise urllib.error.HTTPError('http://localhost/v1',code,'upstream',{},
                        io.BytesIO(json.dumps({'error':{'message':message}}).encode()))
                try:
                    client=JudgeClient(budget,root,models=('fake',),retries=0,transport=fail)
                    result=client.classify('watermark',{'id':'A','evidence_ids':['A'],'dimensions':[800,800]},{'pid':1})
                    event=client.metrics['calls'][0]
                    self.assertEqual(result['status'],'NEEDS_REVIEW')
                    self.assertEqual(event.get('http_status'),code)
                    self.assertEqual(result.get('http_status'),code)
                    self.assertEqual(event.get('provider_error_code'),expected)
                    self.assertIsNone(event['total_tokens'])
                    self.assertEqual(budget.snapshot()['token_status'],'UNKNOWN')
                    self.assertNotIn('fake-test-key',json.dumps([event,result]))
                    self.assertNotIn('private upstream',json.dumps([event,result]))
                    self.assertEqual(client.metrics['requests'],1)
                finally:budget.close()


if __name__=='__main__':unittest.main()
