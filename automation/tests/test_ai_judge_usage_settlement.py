import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from mye_c_automation.ai_judge import JudgeClient
from mye_c_automation.budget_manager import BudgetManager, BudgetExceeded


class UsageSettlementTests(unittest.TestCase):
    def test_known_inflight_usage_is_settled_after_another_call_becomes_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            budget=BudgetManager({'ai_requests':6,'total_tokens':100000},Path(temp)/'budget.sqlite')
            admitted=Event();failed=Event()
            def transport(model,item,context):
                if item['id']=='failure':
                    if not admitted.wait(5):raise AssertionError('success request not admitted')
                    raise TimeoutError('fake missing provider usage')
                admitted.set()
                if not failed.wait(5):raise AssertionError('unknown response not completed')
                result={'task_type':'watermark','item_id':'success','classification':'product_print',
                        'owner':'factory','location':'bottom','confidence':.99,'abstain':False,'evidence_ids':['success'],'dimensions':[800,800]}
                return {'choices':[{'message':{'content':json.dumps(result)}}],
                        'usage':{'prompt_tokens':30,'completion_tokens':20,'total_tokens':50}}
            client=JudgeClient(budget,Path(temp)/'cache',models=('a','b'),transport=transport,retries=0)
            def fail_call():
                try:return client.classify('watermark',{'id':'failure','evidence_ids':['failure'],'dimensions':[800,800]},{})
                finally:failed.set()
            try:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    future=pool.submit(fail_call)
                    success=pool.submit(client.classify,'watermark',{'id':'success','evidence_ids':['success'],'dimensions':[800,800]},{})
                    future.result(timeout=10);success.result(timeout=10)
                known_calls=[c for c in client.metrics['calls'] if c.get('usage_status')=='ACTUAL_REPORTED']
                self.assertEqual(sum(c['total_tokens'] for c in known_calls),50)
                self.assertEqual(budget._db.execute('select actual from token_usage where id=1').fetchone()[0],50)
                self.assertEqual(budget.snapshot()['token_status'],'UNKNOWN')
                self.assertIsNone(budget.snapshot()['actual_tokens'])
                self.assertIsNone(client.metrics['total_tokens'])
                with self.assertRaises(BudgetExceeded):budget.reserve_call(1)
            finally:budget.close()
