import tempfile
import unittest
from job_manager import JobManager,atomic_json
from automation_policy import AutomationPolicy
from test_auto_decision import CONFIG
from candidate_quality import CandidateQualityGate
from test_auto_remedy import Inspector
from workflow_runner import run_automatic

class DisabledAuditTests(unittest.TestCase):
    def test_disabled_auto_policy_still_allows_read_only_audit(self):
        with tempfile.TemporaryDirectory() as root:
            manager=JobManager(root);job=manager.create(1,7,{'ai_requests':0,'full_resolution_images':0},mode='audit')
            def audit(pid,shop,output_dir):
                atomic_json(output_dir/'audit_product.json',{'id':pid,'shopId':shop,'images':{'main':['https://x/a'],'detail':['https://x/b'],'sku':['https://x/c']}})
                from PIL import Image
                import hashlib
                rows=[]
                for pool,url in [('main','https://x/a'),('detail','https://x/b'),('sku','https://x/c')]:
                    path=output_dir/(pool+'.png');Image.new('RGB',(800,800),'white').save(path)
                    rows.append({'file':str(path),'kind':pool,'index':0,'url':url,'content_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
                atomic_json(output_dir/'audit_raw.json',{'pid':pid,'images':rows})
                atomic_json(output_dir/'audit_flags.json',{'pid':pid,'summary':{'ocr_enabled':True,'image_errors':0}})
            result=run_automatic(manager,job,AutomationPolicy(dict(CONFIG,enabled=False)),auditor=audit,quality_gate=CandidateQualityGate(Inspector()))
            self.assertEqual(result['status'],'CLEAN')
            self.assertFalse((manager.directory(job['job_id'])/'local_execution.json').exists())
