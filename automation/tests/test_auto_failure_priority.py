import unittest,tempfile
from unittest.mock import patch
from mye_c_automation.executor.local import LocalExecutor
from test_auto_workflow_more import AdditionalWorkflowTests
class FailurePriorityTests(unittest.TestCase):
 def test_content_failure_overrides_pending_translation(self):
  original=LocalExecutor.execute_auto
  def pending(self,*args,**kwargs):
   result=original(self,*args,**kwargs);result['translation_status']='TRANSLATION_PENDING';return result
  with tempfile.TemporaryDirectory() as root,patch.object(LocalExecutor,'execute_auto',pending),patch('mye_c_automation.auto_workflow.verify_content',return_value={'ok':False,'items':[]}):
   result,_,_=AdditionalWorkflowTests().execute_case(root,crop=True)
   self.assertEqual(result['status'],'CONTENT_REVIEW_REQUIRED')
 def test_mixed_failure_halts_next_product(self):
  from mye_c_automation.batch_scheduler import run_batch
  from mye_c_automation.automation_policy import AutomationPolicy
  from test_auto_decision import CONFIG
  original=LocalExecutor.execute_auto;calls=[]
  def pending(self,*args,**kwargs):
   result=original(self,*args,**kwargs);result['translation_status']='TRANSLATION_PENDING';return result
  with tempfile.TemporaryDirectory() as root,patch.object(LocalExecutor,'execute_auto',pending),patch('mye_c_automation.auto_workflow.verify_content',return_value={'ok':False,'items':[]}):
   def run_one(pid,shop):
    calls.append(pid);return AdditionalWorkflowTests().execute_case(root,crop=True,pid=pid)[0]
   result=run_batch([1,2],7,AutomationPolicy(CONFIG),run_one)
   self.assertTrue(result['halted']);self.assertEqual(result['not_started'],[2]);self.assertEqual(calls,[1])
