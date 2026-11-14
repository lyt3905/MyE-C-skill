import unittest,tempfile,hashlib
from pathlib import Path
from copy import deepcopy
from PIL import Image
from job_manager import JobManager,atomic_json
from workflow_runner import run_automatic
from automation_policy import AutomationPolicy
from candidate_quality import CandidateQualityGate
from test_auto_decision import CONFIG
from test_auto_remedy import Inspector
class BoxWorkflowTests(unittest.TestCase):
 def test_small_box_uploads_once_saves_once_and_reads_back(self):
  with tempfile.TemporaryDirectory() as root:
   manager=JobManager(root);job=manager.create(1,7,{'ai_requests':30,'full_resolution_images':20},mode='auto_apply')
   product={'id':1,'shopId':7,'status':'PENDING','identityJson':{'modelCode':'NA-H74'},'images':{'main':['https://x/box'],'detail':['https://x/body'],'sku':['https://x/box']},'skus':[]}
   def auditor(pid,shop,output_dir):
    rows=[]
    for pool,url,size in [('main','https://x/box',(400,600)),('detail','https://x/body',(800,800))]:
     path=output_dir/(pool+'.png');Image.new('RGB',size,'blue').save(path);rows.append({'file':str(path),'kind':pool,'index':0,'url':url})
    atomic_json(output_dir/'audit_product.json',product);atomic_json(output_dir/'audit_raw.json',{'pid':1,'images':rows});atomic_json(output_dir/'audit_flags.json',{'pid':1,'summary':{'ocr_enabled':True}})
   class Judge:
    metrics={'requests':0,'usage_available':False}
    def process_queue(self,queue,context):return {}
   class Quality(Inspector):
    def observe_image(self,path,context):return {'verified':True,'clean':True,'image_type':'BOX','model':'NA-H74','sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'evidence_ids':['BOX_DUAL']}
   class Writer:
    saves=0;uploads=0
    def current_shop(self):return 7
    def product(self,pid):return deepcopy(product)
    def upload(self,path):self.uploads+=1;self.data=Path(path).read_bytes();return 'https://x/upload'
    def fetch_image(self,url):return self.data
    def save(self,pid,desired,**kwargs):self.saves+=1;product.clear();product.update(deepcopy(desired))
   # Exercise the separately authorized normalization fallback. Genuine existing
   # HD replacement now takes priority and has its own standard-CLI tests.
   writer=Writer();config=dict(CONFIG,allow_actions=dict(CONFIG['allow_actions'],BOX_NORMALIZE=True,REPLACE_TWIN=False))
   result=run_automatic(manager,job,AutomationPolicy(config),writer=writer,auditor=auditor,judge=Judge(),quality_gate=CandidateQualityGate(Quality()))
   import json
   plan=json.loads((manager.directory(job['job_id'])/'plan.v2.json').read_text(encoding='utf-8'))
   self.assertIn('box_validation.json',{r['path'] for r in plan['evidence_refs']})
   self.assertEqual((writer.uploads,writer.saves),(1,1),result)
   self.assertEqual(product['images']['main'],['https://x/upload'])
   self.assertTrue(result['content_validation']['ok'] if 'content_validation' in result else result['status'] in {'AUTO_VERIFIED','PARTIALLY_AUTO_FIXED'},result)
