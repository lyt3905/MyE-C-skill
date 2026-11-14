import tempfile
import unittest
from test_local_execution import ApplyTests
from test_auto_decision import CONFIG
from automation_policy import AutomationPolicy
from plan_v2 import validate_plan

class ActionScopeTests(unittest.TestCase):
    def test_title_authority_cannot_remap_images(self):
        with tempfile.TemporaryDirectory() as root:
            writer,plan=ApplyTests().fixture(root)
            policy=AutomationPolicy(dict(CONFIG,allow_actions={'TITLE_REWRITE':True}))
            plan.update(schema='token-opt-plan/v3',automation={'policy_sha256':policy.sha256,'actions':['TITLE_REWRITE']})
            plan['post_actions']={'url_replacements':{'https://x/a':'https://x/b'}}
            with self.assertRaisesRegex(ValueError,'SCOPE'):validate_plan(plan)
