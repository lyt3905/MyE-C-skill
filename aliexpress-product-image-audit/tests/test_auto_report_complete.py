import tempfile,unittest,json
from pathlib import Path
import test_auto_workflow_more as helpers

class AutomaticReportTests(unittest.TestCase):
    def test_partial_job_report_has_counts_provenance_budget_and_readback(self):
        with tempfile.TemporaryDirectory() as root:
            result,writer,product=helpers.AdditionalWorkflowTests().execute_case(root,partial=True)
            path=next(Path(root).glob('JOB_*'))
            report=json.loads((path/'report_data.json').read_text(encoding='utf-8'))
            self.assertEqual(report['status'],'PARTIALLY_AUTO_FIXED')
            self.assertEqual(report['audit']['image_occurrences'],3)
            self.assertEqual(report['executor']['site_save_calls'],1)
            self.assertEqual(report['executor']['status_calls'],0);self.assertEqual(report['executor']['publish_calls'],0)
            self.assertIsNone(report['ai']['actual_tokens']);self.assertEqual(report['ai']['token_status'],'UNKNOWN')
            self.assertEqual(report['action_details'][0]['before'],'https://x/bad')
            self.assertEqual(report['action_details'][0]['after'],'https://x/clean')
            self.assertTrue(report['deferred']);self.assertTrue(report['verification']['content']['ok'])
            self.assertGreater(report['timing_ms']['total_ms'],0)
