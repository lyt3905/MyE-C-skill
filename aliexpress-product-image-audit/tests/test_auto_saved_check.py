import tempfile
import unittest
from pathlib import Path
import test_auto_workflow_more as helpers
from check import check_saved_job

class SavedJobCheckTests(unittest.TestCase):
    def test_structure_and_content_check_existing_fake_workflow(self):
        with tempfile.TemporaryDirectory() as root:
            result,writer,product=helpers.AdditionalWorkflowTests().execute_case(root,crop=True)
            self.assertEqual(result['status'],'AUTO_VERIFIED')
            job_dir=next(Path(root).glob('JOB_*'))
            checked=check_saved_job(job_dir)
            self.assertTrue(checked['ok'],checked)
            (job_dir/'content_validation.json').unlink()
            self.assertFalse(check_saved_job(job_dir)['ok'])
