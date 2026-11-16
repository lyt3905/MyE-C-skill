import unittest,tempfile,json,os
from pathlib import Path
from unittest.mock import patch
from copy import deepcopy
from PIL import Image
from mye_c_automation.job_manager import JobManager
from mye_c_automation.automation_policy import AutomationPolicy
from mye_c_automation.workflow_runner import run_automatic
from mye_c_automation.candidate_quality import CandidateQualityGate
from test_auto_remedy import Inspector
from test_auto_decision import CONFIG
class DefaultReadSessionTests(unittest.TestCase):
 def test_default_audit_uses_the_supplied_read_session_not_environment_config(self):
  from mye_c_automation.audit_one import audit as actual_audit
  with tempfile.TemporaryDirectory() as root:
   class Reader:
    def account_fingerprint(self):return 'c'*64
    def readonly_client(self):return self
    def current_shop(self):return 7
    def product(self,pid):return {'id':pid,'status':'PENDING','title':'NA-H74 威震天','titleEn':'Hot Sale Transformation NA-H74 NAH74 Megatank Action Figures Collection Gifts','identityJson':{'modelCode':'NA-H74'},'brandId':200017853,'titleTranslationZh':'热销 NA-H74 威震天','images':{'main':['https://fake/main'],'detail':['https://fake/detail'],'sku':[]},'skus':[]}
    def download(self,url,path):Image.new('RGB',(800,800),'blue').save(path,format='PNG')
   reader=Reader();seen=[]
   class OCR:
    def __call__(self,image):return ([],None)
   def audit(pid,shop,output_dir,site):
    seen.append(site);return actual_audit(pid,shop,output_dir=output_dir,site=site,downloader=site.download,ocr_factory=OCR)
   class Judge:
    models=('a','b');metrics={'requests':0,'usage_available':False}
    def process_queue(self,queue,context):
     from watermark_fixtures import exhaustive,identity
     results={}
     for item in queue['items']:
      row={'task_type':item['task_type'],'item_id':item['id'],'evidence_ids':item['evidence_ids'],'confidence':.99,'abstain':False}
      if item['task_type']=='watermark':
       row=exhaustive(dict(row,classification='manufacturer_branding',owner='factory',location='bottom'),size=item['dimensions'])
      else:row=identity(dict(row,decision='MATCH',model='NA-H74',image_type='FIGURE',color='blue'))
      results[item['id']]={'status':'CLEAN','results':[deepcopy(row),deepcopy(row)],'models':['a','b']}
     return results
   manager=JobManager(root);job=manager.create(1,7,{'ai_requests':4},mode='audit')
   with patch('mye_c_automation.audit_one.audit',audit),patch.dict(os.environ,{'AE_READONLY_SITE_CFG':'Z:/must-not-read-other-account.json'}):
    result=run_automatic(manager,job,AutomationPolicy(dict(CONFIG,enabled=False)),writer=reader,judge=Judge(),quality_gate=CandidateQualityGate(Inspector()))
   self.assertEqual(seen,[reader]);self.assertEqual(result['status'],'CLEAN',result)
   path=manager.directory(job['job_id']);plan=json.loads((path/'plan.v2.json').read_text())
   self.assertEqual(plan['precondition']['account_fingerprint'],'c'*64)
