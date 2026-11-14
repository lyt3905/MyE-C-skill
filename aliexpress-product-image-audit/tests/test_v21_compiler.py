import tempfile,json,unittest
from pathlib import Path
from job_manager import JobManager,atomic_json
from plan_compiler import compile_plan
from manual_review import evidence_hash,submit
class CompilerReviewTests(unittest.TestCase):
 def fixture(self,root):
  manager=JobManager(root); job=manager.create(1,7,{})
  path=manager.directory(job['job_id'])
  for name,data in {'audit_product.json':{'titleEn':'Toy'},'audit_flags.json':{'anomalies':[]},'audit_raw.json':{'images':[]},'ai_judgements.json':{},'ai_queue.json':{'items':[]}}.items(): atomic_json(path/name,data)
  atomic_json(path/'evidence_manifest.json',{'schema':'evidence-manifest/v1','files':[],'sources':[]})
  return manager,job,path
 def test_deterministic_empty_plan(self):
  with tempfile.TemporaryDirectory() as root:
   m,j,p=self.fixture(root); a=compile_plan(p,j); b=compile_plan(p,j)
   self.assertEqual(a,b);self.assertTrue(a['ok'])
 def test_unresolved_requires_review(self):
  with tempfile.TemporaryDirectory() as root:
   m,j,p=self.fixture(root);atomic_json(p/'ai_judgements.json',{'X':{'status':'NEEDS_REVIEW'}})
   self.assertFalse(compile_plan(p,j)['ok'])
 def test_review_evidence_mutation_rejected(self):
  with tempfile.TemporaryDirectory() as root:
   m,j,p=self.fixture(root);atomic_json(p/'state.json',{'state':'NEEDS_REVIEW'})
   r={'schema':'manual-review/v1','job_id':j['job_id'],'pid':1,'shop_id':7,'evidence_sha256':evidence_hash(p),'items':[]}
   atomic_json(p/'audit_raw.json',{'changed':True})
   with self.assertRaisesRegex(ValueError,'evidence changed'):submit(m,j['job_id'],r)
 def test_forbidden_change_rejected(self):
  with tempfile.TemporaryDirectory() as root:
   m,j,p=self.fixture(root)
   r={'schema':'manual-review/v1','job_id':j['job_id'],'pid':1,'shop_id':7,'evidence_sha256':evidence_hash(p),'items':[],'changes':[{'field':'price','value':1,'item_ids':[]}]}
   with self.assertRaisesRegex(ValueError,'forbidden'):compile_plan(p,j,r)

 def test_live_dry_run_and_bound_receipt(self):
  from workflow_runner import live_dry_run,record_executor_receipt
  from plan_v2 import plan_hash
  from unittest.mock import Mock
  with tempfile.TemporaryDirectory() as root:
   m,j,p=self.fixture(root);compile_plan(p,j)
   atomic_json(p/'state.json',{'state':'PLAN_READY'})
   reader=Mock();reader.product.return_value={'titleEn':'Toy'}
   result=live_dry_run(m,j['job_id'],reader)
   self.assertTrue(result['live']);reader.product.assert_called_once_with(1)
   plan=json.loads((p/'plan.v2.json').read_text())
   bad={'ok':True,'dry_run':False,'verification_ok':True,'job_id':j['job_id'],'plan_sha256':'bad'}
   with self.assertRaises(ValueError):record_executor_receipt(m,j['job_id'],bad)
   bad['plan_sha256']=plan_hash(plan)
   record_executor_receipt(m,j['job_id'],bad)
   self.assertEqual(json.loads((p/'state.json').read_text())['state'],'STRUCTURE_CHECKED')

 def test_T09_box_deletion_rejected(self):
  with tempfile.TemporaryDirectory() as root:
   m,j,p=self.fixture(root)
   atomic_json(p/'audit_product.json',{'titleEn':'Toy','images':{'main':['box','body'],'detail':['box'],'sku':['body']}})
   atomic_json(p/'audit_raw.json',{'images':[{'url':'box','image_type':'box'}]})
   atomic_json(p/'ai_queue.json',{'items':[{'id':'X','kind':'main','index':0,'evidence_ids':['X']}]})
   r={'schema':'manual-review/v1','job_id':j['job_id'],'pid':1,'shop_id':7,'evidence_sha256':evidence_hash(p),'items':[{'item_id':'X','decision':'REMOVE_CANDIDATE','authorized_actions':['DELETE'],'reviewed_at':'now','reviewer':'user','reason':'test','evidence_ids':['X']}],'changes':[{'field':'images','action':'DELETE','target':{'pool':'main','index':0},'value':{'main':['body'],'detail':['box'],'sku':['body']},'item_ids':['X']}]}
   with self.assertRaisesRegex(ValueError,'box image deletion'):compile_plan(p,j,r)
 def test_T23_plan_tampering_rejected_before_get(self):
  from workflow_runner import live_dry_run
  from unittest.mock import Mock
  with tempfile.TemporaryDirectory() as root:
   m,j,p=self.fixture(root);compile_plan(p,j);atomic_json(p/'state.json',{'state':'PLAN_READY'})
   plan=json.loads((p/'plan.v2.json').read_text());plan['desired']={'titleEn':'Tampered'};atomic_json(p/'plan.v2.json',plan)
   reader=Mock()
   with self.assertRaisesRegex(ValueError,'plan hash changed'):live_dry_run(m,j['job_id'],reader)
   reader.product.assert_not_called()
 def test_T23_evidence_tampering_rejected_before_get(self):
  from workflow_runner import live_dry_run
  from unittest.mock import Mock
  with tempfile.TemporaryDirectory() as root:
   m,j,p=self.fixture(root);compile_plan(p,j);atomic_json(p/'state.json',{'state':'PLAN_READY'})
   atomic_json(p/'audit_raw.json',{'changed':True});reader=Mock()
   with self.assertRaisesRegex(ValueError,'evidence changed'):live_dry_run(m,j['job_id'],reader)
   reader.product.assert_not_called()
