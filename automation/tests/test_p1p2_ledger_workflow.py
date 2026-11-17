import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch,Mock
from mye_c_automation import execution_ledger
from mye_c_automation.executor.local import LocalExecutor
import test_auto_workflow_more as helpers
class LedgerWorkflowTests(unittest.TestCase):
 def test_P0_LEDGER_01_02_read_or_shop_failure_releases_proven_zero_write(self):
  for failure in ('GET','SHOP'):
   with self.subTest(failure=failure),tempfile.TemporaryDirectory() as root:
    ledger=execution_ledger.ExecutionLedger(Path(root)/'ledger.sqlite');captured=[];original=LocalExecutor.execute_auto
    def inject(executor,*args,**kwargs):
     captured.append(executor.writer)
     if failure=='GET':executor.writer.product=Mock(side_effect=TimeoutError('read only timeout'))
     else:executor.writer.current_shop=lambda:99
     return original(executor,*args,**kwargs)
    try:
     with patch('mye_c_automation.execution_ledger.ExecutionLedger',return_value=ledger),patch.object(ledger,'close'),patch.object(LocalExecutor,'execute_auto',inject):
      with self.assertRaises((ValueError,TimeoutError)):helpers.AdditionalWorkflowTests().execute_case(root,crop=True)
     writer=captured[0];self.assertEqual((writer.saves,writer.uploads),(0,0))
     state=ledger.db.execute('SELECT account,shop,pid,job,before_hash,operation,state FROM executions').fetchone()
     self.assertEqual(state[-1],'PREWRITE_FAILED')
     self.assertEqual(json.loads(next(Path(root).glob('JOB_*/state.json')).read_text())['state'],'PREWRITE_FAILED')
     self.assertTrue(ledger.claim(state[0],state[1],state[2],'JOB_retry',state[4],state[5])['ok'])
    finally:ledger.close()
 def test_P0_LEDGER_03_upload_timeout_is_unknown_and_cannot_reclaim(self):
  with tempfile.TemporaryDirectory() as root:
   ledger=execution_ledger.ExecutionLedger(Path(root)/'ledger.sqlite');captured=[];original=LocalExecutor.execute_auto
   def inject(executor,*args,**kwargs):
    captured.append(executor.writer)
    executor.writer.upload=Mock(side_effect=TimeoutError('upload response lost'))
    return original(executor,*args,**kwargs)
   try:
    with patch('mye_c_automation.execution_ledger.ExecutionLedger',return_value=ledger),patch.object(ledger,'close'),patch.object(LocalExecutor,'execute_auto',inject):
     with self.assertRaises(RuntimeError):helpers.AdditionalWorkflowTests().execute_case(root,crop=True)
    self.assertEqual(captured[0].saves,0)
    state=ledger.db.execute('SELECT account,shop,pid,job,before_hash,operation,state FROM executions').fetchone()
    self.assertEqual(state[-1],'APPLY_UNKNOWN')
    self.assertFalse(ledger.claim(state[0],state[1],state[2],'JOB_retry',state[4],state[5])['ok'])
   finally:ledger.close()
