import tempfile
import unittest
from pathlib import Path
from mye_c_automation.job_manager import JobManager, atomic_json
from mye_c_automation.candidate_quality import CandidateQualityGate
from test_auto_remedy import Inspector
import test_auto_workflow_more as helpers
from mye_c_automation.workflow_runner import resume_verification

class ResumeVerificationTests(unittest.TestCase):
    def test_resume_content_verification_does_not_upload_or_save_again(self):
        with tempfile.TemporaryDirectory() as root:
            result,writer,product=helpers.AdditionalWorkflowTests().execute_case(root,crop=True)
            manager=JobManager(root);directory=next(Path(root).glob('JOB_*'));job=manager.load(directory.name)
            atomic_json(directory/'state.json',{'state':'CONTENT_REVIEW_REQUIRED','automatic':True})
            checked=resume_verification(manager,job['job_id'],writer,CandidateQualityGate(Inspector()))
            self.assertEqual(checked['status'],'AUTO_VERIFIED',checked)
            self.assertEqual((writer.saves,writer.uploads),(1,1))
