import tempfile,unittest,json
from pathlib import Path
from batch_scheduler import run_batch
from automation_policy import AutomationPolicy
from test_auto_decision import CONFIG
import test_auto_real_auditor_workflow as helpers

class UnknownBatchWorkflowTests(unittest.TestCase):
    def test_E24_E35_unknown_committed_save_gets_readback_and_stops_batch(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);calls=[]
            def run_one(pid,shop):
                calls.append(pid)
                return helpers.RealAuditorWorkflowTests().execute(root/str(pid),'erase',pid=pid,save_timeout=True)[0]
            result=run_batch([1,2,3],7,AutomationPolicy(CONFIG),run_one)
            self.assertTrue(result['halted']);self.assertEqual(result['not_started'],[2,3]);self.assertEqual(calls,[1])
            job=next((root/'1'/'jobs').glob('JOB_*'))
            self.assertEqual(json.loads((job/'state.json').read_text())['state'],'APPLY_UNKNOWN')
            self.assertEqual(json.loads((job/'recovery_readback.json').read_text())['write_outcome'],'MATCHED')
            self.assertFalse((root/'2').exists())
