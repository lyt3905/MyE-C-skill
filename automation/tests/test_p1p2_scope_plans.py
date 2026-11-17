import unittest,tempfile,copy
import test_local_execution as helpers
from mye_c_automation.plan_v2 import validate_plan
from mye_c_automation.automation_policy import AutomationPolicy
from test_auto_decision import CONFIG
class ScopePlanV12Tests(unittest.TestCase):
 def test_SCOPE_07_old_description_desired_and_post_actions_fail_closed(self):
  with tempfile.TemporaryDirectory() as root:
   _,base=helpers.ApplyTests().fixture(root)
   for schema in ('token-opt-plan/v2','token-opt-plan/v3'):
    for field,action in [('desired','descriptionJson'),('post_actions','DESCRIPTION_URL_REMAP'),('post_actions','DELETE_DESCRIPTION_URLS'),('post_actions','REPLACE_DESCRIPTION_URL')]:
     with self.subTest(schema=schema,field=field,action=action):
      plan=copy.deepcopy(base);plan['schema']=schema;plan['desired']={}
      if schema.endswith('v3'):plan['automation']={'policy_sha256':'a'*64,'actions':['REPLACE_TWIN']}
      plan[field][action]='https://x/new'
      with self.assertRaises(ValueError):validate_plan(plan)
 def test_SCOPE_07_old_description_permission_requires_migration(self):
  config=copy.deepcopy(CONFIG);config['allow_actions']['DESCRIPTION_URL_REMAP']=True
  with self.assertRaisesRegex(ValueError,'DESCRIPTION.*MIGRATION'):AutomationPolicy(config)
