import unittest
from test_auto_decision import CONFIG,remedy
from mye_c_automation.automation_policy import AutomationPolicy
from mye_c_automation.auto_decision import decide

class TwinIdentityTests(unittest.TestCase):
    def test_twin_requires_model_and_packaging_not_only_phash(self):
        row=remedy();row['checks']['model_match']=False;row['checks']['packaging_match']=True
        self.assertEqual(decide([row],AutomationPolicy(CONFIG),pid=1,shop=7)[0]['decision'],'DEFERRED')
