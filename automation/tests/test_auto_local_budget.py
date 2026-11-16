import tempfile
import unittest
from mye_c_automation.budget_manager import BudgetManager, BudgetExceeded
from mye_c_automation.executor.local import LocalExecutor
from mye_c_automation.automation_policy import AutomationPolicy
from test_auto_decision import CONFIG
from test_local_execution import ApplyTests

class LocalBudgetTests(unittest.TestCase):
    def test_auto_executor_cannot_bypass_save_budget(self):
        with tempfile.TemporaryDirectory() as root:
            writer,plan=ApplyTests().fixture(root)
            policy=AutomationPolicy(dict(CONFIG,allow_actions=dict(CONFIG['allow_actions'],TITLE_REWRITE=True)))
            plan.update(schema='token-opt-plan/v3',automation={'policy_sha256':policy.sha256,'actions':['TITLE_REWRITE']})
            budget=BudgetManager({'site_save':0,'translate_title':0,'uploads':0})
            with self.assertRaises(BudgetExceeded):LocalExecutor(writer,root,budget=budget).execute_auto(plan,policy)
            self.assertEqual(writer.calls,0)
            budget.close()
