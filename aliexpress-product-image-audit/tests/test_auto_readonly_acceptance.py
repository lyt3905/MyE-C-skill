import tempfile,unittest,json
from pathlib import Path
from job_manager import JobManager,atomic_json
from automation_policy import AutomationPolicy
from test_auto_decision import CONFIG
from candidate_quality import CandidateQualityGate
from test_auto_remedy import Inspector
from workflow_runner import run_automatic
from check import check_saved_job
import test_auto_real_auditor_workflow as helpers

class ReadonlyAcceptanceTests(unittest.TestCase):
    def test_E01_clean_real_auditor_job_has_verifiable_readonly_artifacts(self):
        with tempfile.TemporaryDirectory() as root:
            result,writer,path=helpers.RealAuditorWorkflowTests().execute(root,'clean')
            self.assertEqual(result['status'],'CLEAN',result)
            self.assertEqual((writer.saves,writer.uploads),(0,0))
            self.assertTrue(check_saved_job(path)['ok'])
    def test_missing_image_evidence_cannot_be_clean(self):
        with tempfile.TemporaryDirectory() as root:
            manager=JobManager(root);job=manager.create(1,7,{'ai_requests':0,'full_resolution_images':0},mode='audit')
            def auditor(pid,shop,output_dir):
                atomic_json(output_dir/'audit_product.json',{'id':pid,'shopId':shop,'images':{'main':['https://x/a'],'detail':['https://x/b'],'sku':[]}})
                atomic_json(output_dir/'audit_raw.json',{'pid':pid,'images':[]})
                atomic_json(output_dir/'audit_flags.json',{'pid':pid,'summary':{'ocr_enabled':True,'image_errors':0}})
            result=run_automatic(manager,job,AutomationPolicy(CONFIG),auditor=auditor,quality_gate=CandidateQualityGate(Inspector()))
            self.assertEqual(result['status'],'DEFERRED')
