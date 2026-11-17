import unittest,tempfile
from pathlib import Path
from mye_c_automation.execution_ledger import ExecutionLedger
class P0LedgerStateTests(unittest.TestCase):
 def fixture(self,root):return ExecutionLedger(Path(root)/'ledger.sqlite')
 def test_P0_LEDGER_01_reservation_is_not_remote_write(self):
  with tempfile.TemporaryDirectory() as root:
   ledger=self.fixture(root)
   try:
    self.assertTrue(ledger.claim('account',7,1,'JOB_a','before','op')['ok'])
    state=ledger.db.execute('SELECT state FROM executions').fetchone()[0]
    self.assertEqual(state,'RESERVED')
    self.assertFalse(ledger.claim('account',7,1,'JOB_b','before','other')['ok'])
   finally:ledger.close()
 def test_P0_LEDGER_02_proven_prewrite_failure_can_retry_same_operation(self):
  with tempfile.TemporaryDirectory() as root:
   ledger=self.fixture(root)
   try:
    ledger.claim('account',7,1,'JOB_a','before','op')
    ledger.prewrite_failed('account',7,1,'JOB_a')
    self.assertTrue(ledger.claim('account',7,1,'JOB_b','before','op')['ok'])
   finally:ledger.close()
 def test_P0_LEDGER_03_side_effect_state_cannot_be_released_as_prewrite_failure(self):
  with tempfile.TemporaryDirectory() as root:
   ledger=self.fixture(root)
   try:
    ledger.claim('account',7,1,'JOB_a','before','op')
    ledger.begin_side_effect('account',7,1,'JOB_a')
    with self.assertRaises(ValueError):ledger.prewrite_failed('account',7,1,'JOB_a')
    blocked=ledger.claim('account',7,1,'JOB_b','before','op')
    self.assertEqual(blocked['status'],'APPLY_UNKNOWN');self.assertFalse(blocked['ok'])
   finally:ledger.close()
 def test_P0_LEDGER_05_restart_cannot_replay_reserved_or_started_operation(self):
  for started in (False,True):
   with self.subTest(started=started),tempfile.TemporaryDirectory() as root:
    path=Path(root)/'ledger.sqlite';ledger=ExecutionLedger(path)
    ledger.claim('account',7,1,'JOB_a','before','op')
    if started:ledger.begin_side_effect('account',7,1,'JOB_a')
    ledger.close();reopened=ExecutionLedger(path)
    try:
     for before,operation in [('before','op'),('different','different')]:
      blocked=reopened.claim('account',7,1,'JOB_new',before,operation)
      self.assertFalse(blocked['ok']);self.assertEqual(blocked['status'],'APPLY_UNKNOWN' if started else 'RESERVED')
    finally:reopened.close()
