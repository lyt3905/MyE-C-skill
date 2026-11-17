import tempfile, unittest, json, hashlib
from copy import deepcopy
from pathlib import Path
from PIL import Image
from mye_c_automation.job_manager import JobManager, atomic_json
from mye_c_automation.workflow_runner import run, live_dry_run, local_apply
from mye_c_automation.manual_review import submit, evidence_hash
from mye_c_automation.plan_v2 import plan_hash
class VerticalTests(unittest.TestCase):
 def test_review_dryrun_apply(self):
  with tempfile.TemporaryDirectory() as temp:
   manager=JobManager(temp);job=manager.create(123,7,{'ai_requests':10,'full_resolution_images':3})
   product={'id':123,'shopId':7,'status':'PENDING','titleEn':'Before','images':{'main':['a'],'detail':['a'],'sku':['a']},'skus':[]}
   def audit(pid,shop,output_dir):
    path=output_dir/'image.jpg';Image.new('RGB',(800,800),'white').save(path)
    atomic_json(output_dir/'audit_product.json',product)
    atomic_json(output_dir/'audit_raw.json',{'pid':pid,'images':[{'file':str(path),'kind':'main','index':0,'url':'a','content_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]})
    atomic_json(output_dir/'audit_flags.json',{'pid':pid,'summary':{'ocr_enabled':True},'ocr_hits':[{'image':str(path)}]})
   class Judge:
    metrics={'requests':1,'usage_available':False}
    def process_queue(self,q,c):return {q['items'][0]['id']:{'status':'NEEDS_REVIEW','results':[]}}
   run(manager,job,audit,Judge());root=manager.directory(job['job_id'])
   self.assertEqual(json.loads((root/'state.json').read_text())['state'],'NEEDS_REVIEW')
   item=json.loads((root/'ai_queue.json').read_text())['items'][0]
   review={'schema':'manual-review/v1','job_id':job['job_id'],'pid':123,'shop_id':7,'evidence_sha256':evidence_hash(root),'items':[{'item_id':item['id'],'decision':'REMOVE_CANDIDATE_CONFIRMED','authorized_actions':['UPDATE_TITLE'],'reviewed_at':'2026-11-12','reviewer':'user','reason':'reviewed','evidence_ids':item['evidence_ids']}],'changes':[{'field':'titleEn','action':'UPDATE_TITLE','value':'After','item_ids':[item['id']]}]}
   self.assertTrue(submit(manager,job['job_id'],review)['ok'])
   class Writer:
    saves=0;uploads=0
    def product(self,pid):return deepcopy(product)
    def save(self,pid,desired,**kw):self.saves+=1;product.clear();product.update(deepcopy(desired))
    def upload(self,path):self.uploads+=1;return 'uploaded'
   writer=Writer();live_dry_run(manager,job['job_id'],writer);self.assertEqual(writer.saves,0)
   plan=json.loads((root/'plan.v2.json').read_text());confirmation=dict(confirmed=True,job_id=job['job_id'],pid=123,shop=7,plan_sha256=plan_hash(plan))
   with self.assertRaises(ValueError):local_apply(manager,job['job_id'],writer,{})
   receipt=local_apply(manager,job['job_id'],writer,confirmation)
   self.assertTrue(receipt['verification_ok']);self.assertEqual(writer.saves,1);self.assertEqual(product['titleEn'],'After')
   self.assertEqual(json.loads((root/'state.json').read_text())['state'],'STRUCTURE_CHECKED')
   with self.assertRaises(ValueError):local_apply(manager,job['job_id'],writer,confirmation)

 def test_save_timeout_journal_blocks_retry(self):
  from mye_c_automation.executor.local import LocalExecutor
  from mye_c_automation.product_state import canonical_state_hash
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);atomic_json(root/'evidence.json',{})
   product={'id':1,'shopId':7,'status':'PENDING','images':{'main':['a'],'detail':['a'],'sku':['a']}}
   plan={'schema':'token-opt-plan/v2','job_id':'JOB_test','pid':1,'shop':7,'workflow_version':'token-opt-v2','policy_version':'v2','precondition':{'state_sha256':canonical_state_hash(product)},'evidence_refs':[{'path':'evidence.json','sha256':hashlib.sha256((root/'evidence.json').read_bytes()).hexdigest()}],'ai_judgement_refs':[],'desired':{'titleEn':'Changed'},'post_actions':{},'review':{'status':'RESOLVED'}}
   class Writer:
    calls=0
    def product(self,pid):return deepcopy(product)
    def save(self,*a,**k):self.calls+=1;raise TimeoutError()
   writer=Writer();executor=LocalExecutor(writer,root)
   confirmation=dict(confirmed=True,job_id='JOB_test',pid=1,shop=7,plan_sha256=plan_hash(plan))
   with self.assertRaises(TimeoutError):executor.execute(plan,confirmation)
   self.assertEqual(json.loads((root/'local_execution.json').read_text())['state'],'APPLY_UNKNOWN')
   with self.assertRaises(FileExistsError):executor.execute(plan,confirmation)
   self.assertEqual(writer.calls,1)

 def test_T10_excess_main_images_fail_delivery(self):
  from mye_c_automation.check import verify_snapshot
  result=verify_snapshot({'id':1,'shopId':7,'status':'PENDING','images':{'main':['a']*7,'detail':['a'],'sku':['a']}})
  self.assertFalse(result['ok']);self.assertFalse(result['checks']['main_count'])
