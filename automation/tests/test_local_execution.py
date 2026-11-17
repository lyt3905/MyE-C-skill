import tempfile, unittest
from copy import deepcopy
from mye_c_automation.executor.local import LocalExecutor
from mye_c_automation.plan_v2 import plan_hash
from mye_c_automation.product_state import canonical_state_hash

class LocalTests(unittest.TestCase):
 def test_confirm_noop_and_replay(self):
  class Writer:
   def product(self,pid):return {'id':1,'shopId':7,'status':'PENDING','images':{'main':['a'],'detail':['b'],'sku':['c']}}
   def save(self,*args,**kwargs):raise AssertionError('empty plan saved')
  with tempfile.TemporaryDirectory() as root:
   w=Writer(); p=dict(schema='token-opt-plan/v2',job_id='JOB_a',pid=1,shop=7,workflow_version='token-opt-v2',policy_version='v2',precondition={'state_sha256':canonical_state_hash(w.product(1))},evidence_refs=[],ai_judgement_refs=[],desired={},post_actions={},review={'status':'RESOLVED'})
   e=LocalExecutor(w,root)
   with self.assertRaises(ValueError):e.execute(p)
   c=dict(confirmed=True,job_id='JOB_a',pid=1,shop=7,plan_sha256=plan_hash(p))
   self.assertEqual(e.execute(p,c)['site_save_calls'],0)
   with self.assertRaises(FileExistsError):e.execute(p,c)

class ApplyTests(unittest.TestCase):
 def fixture(self, root):
  import hashlib
  from pathlib import Path
  class Writer:
   calls=0; uploads=0; fail=None
   data={'id':1,'shopId':7,'status':'PENDING','titleEn':'old','images':{'main':['a'],'detail':['b'],'sku':['c']}}
   def product(self,pid):return deepcopy(self.data)
   def save(self,pid,data,**kwargs):
    self.calls+=1
    if self.fail=='timeout':raise TimeoutError()
    if self.fail!='readback':self.data=deepcopy(data)
   def upload(self,path):
    self.uploads+=1
    raise RuntimeError('upload failed')
  w=Writer(); path=Path(root)/'evidence';path.write_bytes(b'evidence')
  ref={'path':'evidence','sha256':hashlib.sha256(b'evidence').hexdigest()}
  p=dict(schema='token-opt-plan/v2',job_id='JOB_a',pid=1,shop=7,workflow_version='token-opt-v2',policy_version='v2',precondition={'state_sha256':canonical_state_hash(w.product(1))},evidence_refs=[ref],ai_judgement_refs=[],desired={'titleEn':'new'},post_actions={},review={'status':'RESOLVED'})
  return w,p
 def confirm(self,p):return dict(confirmed=True,job_id=p['job_id'],pid=p['pid'],shop=p['shop'],plan_sha256=plan_hash(p))
 def test_save_and_checker(self):
  from unittest.mock import Mock
  with tempfile.TemporaryDirectory() as root:
   w,p=self.fixture(root); checker=Mock(return_value={'ok':True})
   result=LocalExecutor(w,root,checker).execute(p,self.confirm(p))
   self.assertTrue(result['verification_ok']);self.assertEqual(w.calls,1);checker.assert_called_once()
 def test_failures_and_no_retry(self):
  import json
  from pathlib import Path
  for failure in ('timeout','readback','check','drift','upload'):
   with self.subTest(failure=failure),tempfile.TemporaryDirectory() as root:
    w,p=self.fixture(root);w.fail=failure
    if failure=='drift':w.data=dict(w.data,titleEn='drift')
    if failure=='upload':
     from PIL import Image
     asset=Path(root)/'replacement.png'; Image.new('RGB',(800,800),'white').save(asset)
     import hashlib
     p['desired']={'images':deepcopy(w.data['images'])};p['post_actions']={'uploads':[dict(path='replacement.png',sha256=hashlib.sha256(asset.read_bytes()).hexdigest(),pool='main',index=0)]}
    e=LocalExecutor(w,root,lambda product:{'ok':failure!='check'})
    with self.assertRaises(Exception):e.execute(p,self.confirm(p))
    self.assertEqual(json.loads((Path(root)/'local_execution.json').read_text())['state'],'PREWRITE_FAILED' if failure=='drift' else 'APPLY_UNKNOWN')
    with self.assertRaises(FileExistsError):e.execute(p,self.confirm(p))
    self.assertEqual(w.calls,0 if failure in ('drift','upload') else 1)
 def test_identity_confirmation(self):
  for key in ('pid','shop','plan_sha256','job_id'):
   with tempfile.TemporaryDirectory() as root:
    w,p=self.fixture(root);c=self.confirm(p);c[key]='wrong'
    with self.assertRaises(ValueError):LocalExecutor(w,root).execute(p,c)
    self.assertEqual(w.calls,0)
