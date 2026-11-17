import unittest
from mye_c_automation.automation_policy import AutomationPolicy
from test_auto_decision import CONFIG
from mye_c_automation.batch_scheduler import run_batch

class BatchTests(unittest.TestCase):
    def test_one_three_ten_products(self):
        for count in (1,3,10):
            calls=[]
            result=run_batch(list(range(1,count+1)),7,AutomationPolicy(CONFIG),lambda pid,shop: calls.append(pid) or {'status':'AUTO_VERIFIED'})
            self.assertEqual(calls,list(range(1,count+1)));self.assertFalse(result['halted'])
    def test_unknown_write_halts_remaining(self):
        calls=[]
        result=run_batch([1,2,3],7,AutomationPolicy(CONFIG),lambda pid,shop:calls.append(pid) or {'status':'APPLY_UNKNOWN'})
        self.assertEqual(calls,[1]);self.assertTrue(result['halted']);self.assertEqual(result['not_started'],[2,3])
    def test_failure_isolated_unless_integrity_fatal(self):
        result=run_batch([1,2,3],7,AutomationPolicy(CONFIG),lambda pid,shop:{'status':'DEFERRED' if pid==2 else 'AUTO_VERIFIED'})
        self.assertEqual(len(result['items']),3)
        result=run_batch([1,2,3],7,AutomationPolicy(CONFIG),lambda pid,shop:{'status':'BLOCKED_FATAL'})
        self.assertEqual(len(result['items']),1);self.assertTrue(result['halted'])
    def test_oversized_and_duplicate_batches_rejected_before_any_job(self):
        for pids in ([1,1],list(range(1,12))):
            calls=[]
            with self.assertRaises(ValueError):run_batch(pids,7,AutomationPolicy(CONFIG),lambda *args:calls.append(args))
            self.assertFalse(calls)
