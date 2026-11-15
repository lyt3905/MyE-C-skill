import json,tempfile,unittest
from pathlib import Path
from budget_manager import BudgetManager
from ai_judge import JudgeClient
from job_manager import JobManager

class RecordOnlyMainflowTests(unittest.TestCase):
    def test_record_only_runs_without_token_usd_price_caps(self):
        with tempfile.TemporaryDirectory() as d:
            b=BudgetManager({'ai_requests':0,'full_resolution_images':0,'total_tokens':1},Path(d)/'budget.sqlite')
            try:
                b.configure_model_budget({'mode':'RECORD_ONLY','usage_source':'GATEWAY_REPORTED_UNVERIFIED'},'JOB_fake')
                for i in range(3):b.model_call('a','https://fake/v1',5097,[],2000,{},lambda:{'usage':{'prompt_tokens':100,'completion_tokens':200,'total_tokens':300}})
                self.assertEqual(b.model_snapshot()['known_tokens'],900)
                self.assertEqual(b.model_snapshot()['requests'],3)
            finally:b.close()
    def test_missing_usage_is_recorded_and_next_call_still_runs(self):
        with tempfile.TemporaryDirectory() as d:
            b=BudgetManager({},Path(d)/'budget.sqlite')
            try:
                b.configure_model_budget({'mode':'RECORD_ONLY','usage_source':'GATEWAY_REPORTED_UNVERIFIED'},'JOB_fake')
                b.model_call('a','https://fake/v1',5097,[],2000,{},lambda:{})
                b.model_call('b','https://fake/v1',5097,[],2000,{},lambda:{'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}})
                s=b.model_snapshot();self.assertIsNone(s['total_tokens']);self.assertEqual(s['known_tokens'],2);self.assertEqual(s['requests'],2)
            finally:b.close()
    def test_real_client_and_auxiliary_job_use_same_record_only_ledger(self):
        from unittest.mock import patch
        import io
        with tempfile.TemporaryDirectory() as d:
            m=JobManager(d);job=m.create(5097,7,{'ai_requests':0,'total_tokens':1},mode='auto_apply',model_budget={'mode':'RECORD_ONLY','usage_source':'GATEWAY_REPORTED_UNVERIFIED'})
            b=BudgetManager(job['budget'],m.directory(job['job_id'])/'budget.sqlite')
            try:
                c=JudgeClient(b,m.directory(job['job_id'])/'cache',models=('a','b'))
                item={'id':'x','task_type':'title_semantics','evidence_ids':['x']}
                response={'choices':[{'message':{'content':json.dumps(dict(task_type='title_semantics',item_id='x',decision='MATCH',confidence=.99,abstain=False,evidence_ids=['x']))}}]}
                with patch.dict('os.environ',{'VLM_API_KEY':'fake'}),patch('ai_judge.client._open_model_request',side_effect=lambda *a,**k:io.BytesIO(json.dumps(response).encode())):
                    result=c.classify('title_semantics',item,{'pid':5097})
                self.assertEqual(result['status'],'CLEAN');self.assertEqual(c.metrics['requests'],2)
                self.assertIsNone(c.metrics['total_tokens']);self.assertEqual(b.model_snapshot()['requests'],2)
            finally:b.close()
