import tempfile
import unittest
from pathlib import Path
from execution_ledger import ExecutionLedger

class LedgerTests(unittest.TestCase):
    def test_unknown_write_blocks_new_job_for_same_pid(self):
        with tempfile.TemporaryDirectory() as root:
            ledger=ExecutionLedger(Path(root)/'ledger.sqlite')
            self.assertTrue(ledger.claim('account',7,1,'JOB_a','before','operation')['ok'])
            ledger.begin_side_effect('account',7,1,'JOB_a')
            blocked=ledger.claim('account',7,1,'JOB_b','different','other')
            self.assertFalse(blocked['ok']);self.assertEqual(blocked['previous_job_id'],'JOB_a')
            self.assertEqual(blocked['status'],'APPLY_UNKNOWN');ledger.close()
    def test_completed_operation_is_not_replayed_from_same_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            ledger=ExecutionLedger(Path(root)/'ledger.sqlite')
            ledger.claim('account',7,1,'JOB_a','before','operation')
            ledger.finish('account',7,1,'JOB_a','AUTO_VERIFIED')
            self.assertFalse(ledger.claim('account',7,1,'JOB_b','before','operation')['ok'])
            self.assertTrue(ledger.claim('account',7,1,'JOB_c','new-before','new-operation')['ok'])
            ledger.close()
