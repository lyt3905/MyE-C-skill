import tempfile
import unittest
from pathlib import Path
from automation_policy import AutomationPolicy
from test_auto_decision import CONFIG
from batch_scheduler import run_batch
import test_auto_workflow_more as helpers

class FullBatchWorkflowTests(unittest.TestCase):
    def test_one_three_ten_full_workflows_use_fake_upload_save_readback(self):
        for count in (1,3,10):
            with self.subTest(count=count),tempfile.TemporaryDirectory() as root:
                saves=[];uploads=[]
                def run_one(pid,shop):
                    result,writer,product=helpers.AdditionalWorkflowTests().execute_case(Path(root)/str(pid),crop=True,pid=pid)
                    saves.append(writer.saves);uploads.append(writer.uploads)
                    self.assertEqual(product['id'],pid)
                    return result
                result=run_batch(list(range(1,count+1)),7,AutomationPolicy(CONFIG),run_one)
                self.assertFalse(result['halted'],result)
                self.assertEqual(len(result['items']),count)
                self.assertTrue(all(r['result']['status']=='AUTO_VERIFIED' for r in result['items']))
                self.assertEqual(saves,[1]*count);self.assertEqual(uploads,[1]*count)
