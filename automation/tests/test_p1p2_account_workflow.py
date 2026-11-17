import unittest,tempfile,json
from pathlib import Path
import test_auto_workflow_more as helpers
class AccountWorkflowTests(unittest.TestCase):
 def execute(self,root,**kwargs):
  from unittest.mock import patch
  from mye_c_automation.execution_ledger import ExecutionLedger
  with patch('mye_c_automation.execution_ledger.ExecutionLedger',side_effect=lambda:ExecutionLedger(Path(root)/'fake-ledger.sqlite')):
   return helpers.AdditionalWorkflowTests().execute_case(root,**kwargs)
 def test_P0_ACCOUNT_01_standard_plan_and_job_bind_same_verified_account(self):
  with tempfile.TemporaryDirectory() as root:
   result,writer,product=self.execute(root,crop=True,account='a'*64)
   path=next(Path(root).glob('JOB_*'));job=json.loads((path/'job.json').read_text());plan=json.loads((path/'plan.v2.json').read_text())
   self.assertEqual(job['account_fingerprint'],'a'*64)
   self.assertEqual(plan['precondition']['account_fingerprint'],'a'*64)
   self.assertIn('audit_account.json',{r['path'] for r in plan['evidence_refs']})
   self.assertEqual(writer.saves,1)
 def test_P0_ACCOUNT_02_audit_and_writer_mismatch_rejected_before_plan(self):
  with tempfile.TemporaryDirectory() as root:
   with self.assertRaisesRegex(ValueError,'ACCOUNT_MISMATCH'):
    self.execute(root,crop=True,account='a'*64,audit_account='b'*64)
   self.assertFalse(list(Path(root).glob('JOB_*/save_attempt.json')))
   self.assertFalse(list(Path(root).glob('JOB_*/upload_receipts.json')))
