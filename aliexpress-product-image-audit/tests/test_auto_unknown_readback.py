import tempfile
import unittest
from copy import deepcopy
from executor.local import LocalExecutor
from test_local_execution import ApplyTests

class UnknownReadbackTests(unittest.TestCase):
    def test_timeout_after_commit_is_resolved_by_readback_without_resave(self):
        with tempfile.TemporaryDirectory() as root:
            helper=ApplyTests();writer,plan=helper.fixture(root)
            def commit_then_timeout(pid,data,**kwargs):
                writer.calls+=1;writer.data=deepcopy(data);raise TimeoutError('response lost')
            writer.save=commit_then_timeout
            executor=LocalExecutor(writer,root)
            with self.assertRaises(TimeoutError):executor.execute(plan,helper.confirm(plan))
            recovered=executor.recover_readback(plan)
            self.assertEqual(recovered['write_outcome'],'MATCHED')
            self.assertTrue(recovered['read_only']);self.assertEqual(writer.calls,1)
    def test_unobserved_commit_never_authorizes_retry(self):
        with tempfile.TemporaryDirectory() as root:
            helper=ApplyTests();writer,plan=helper.fixture(root);writer.fail='timeout'
            executor=LocalExecutor(writer,root)
            with self.assertRaises(TimeoutError):executor.execute(plan,helper.confirm(plan))
            recovered=executor.recover_readback(plan)
            self.assertEqual(recovered['write_outcome'],'NOT_OBSERVED')
            self.assertFalse(recovered['retry_save_allowed']);self.assertEqual(writer.calls,1)
