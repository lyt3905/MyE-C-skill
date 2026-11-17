import tempfile
import unittest
from mye_c_automation.budget_manager import BudgetManager, BudgetExceeded
from mye_c_automation.job_manager import JobManager

class BindingBudgetAcceptance(unittest.TestCase):
    def test_token_reservation_settlement_and_unknown(self):
        b=BudgetManager({'total_tokens':100})
        r=b.reserve_tokens(80)
        with self.assertRaises(BudgetExceeded): b.reserve_tokens(30)
        b.settle_tokens(r,20)
        self.assertEqual(b.snapshot()['actual_tokens'],20)
        self.assertEqual(b.snapshot()['used']['total_tokens'],20)
        b.mark_tokens_unknown()
        self.assertIsNone(b.snapshot()['actual_tokens'])
        with self.assertRaisesRegex(BudgetExceeded, 'UNKNOWN'):
            b.reserve_tokens(1)
        b.close()

    def test_input_state_rebinding_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            m=JobManager(d); j=m.create(1,2,{'ai_requests':1})
            m.bind_input(j['job_id'],{'title':'first','weight':1})
            with self.assertRaisesRegex(ValueError,'STATE_DRIFT'):
                m.bind_input(j['job_id'],{'title':'changed','weight':1})
