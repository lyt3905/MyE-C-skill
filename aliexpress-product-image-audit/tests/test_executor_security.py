import tempfile
import time
import unittest
from pathlib import Path
from executor.authorization import Authorization, sign
from executor.service import ExecutorService
from plan_v2 import plan_hash
from product_state import canonical_state_hash

class SecurityTests(unittest.TestCase):
    def test_ticket_binding_replay_and_dry_run(self):
        with tempfile.TemporaryDirectory() as root:
            auth = Authorization(b'x'*32,Path(root)/'nonce.db')
            plan = dict(schema='token-opt-plan/v2',job_id='JOB_test',pid=1,shop=7,workflow_version='token-opt-v2',policy_version='v2',precondition={'state_sha256':canonical_state_hash({'images':{'main':['https://x/a'],'detail':['https://x/b']}})},evidence_refs=[],ai_judgement_refs=[],desired={},post_actions=[],review={'status':'RESOLVED'})
            class Writer:
                saves=0
                def product(self,pid): return {'id':1,'shopId':7,'images':{'main':['https://x/a'],'detail':['https://x/b']}}
                def save(self,*a,**k): self.saves+=1
            writer=Writer()
            service=ExecutorService(auth,writer,root)
            self.assertEqual(service.execute(plan)['site_save_calls'],0)
            with self.assertRaises(ValueError): service.execute(plan,dry_run=False)
            payload=dict(job_id='JOB_test',pid=1,shop=7,plan_sha256=plan_hash(plan),expires_at=time.time()+60,allowed_operations=['site_save'],max_site_saves=1,nonce='n'*32)
            ticket=sign(payload,b'x'*32)
            changed=dict(plan,shop=8)
            with self.assertRaises(ValueError): service.execute(changed,ticket,False)
            self.assertTrue(service.execute(plan,ticket,False)['verification_ok'])
            with self.assertRaises(ValueError): service.execute(plan,ticket,False)
            self.assertEqual(writer.saves,0)  # Authorized no-op consumes nonce but never saves.
    def test_review_and_expiry_rejected(self):
        from plan_v2 import validate_plan
        with self.assertRaises(ValueError): validate_plan({'schema':'token-opt-plan/v2'})
        with tempfile.TemporaryDirectory() as root:
            auth=Authorization(b'x'*32,Path(root)/'nonce.db')
            plan={'job_id':'JOB_x','pid':1,'shop':7,'post_actions':{}}
            payload=dict(job_id='JOB_x',pid=1,shop=7,plan_sha256=plan_hash(plan),expires_at=0,allowed_operations=['site_save'],max_site_saves=1,nonce='x'*32)
            with self.assertRaises(ValueError): auth.consume(sign(payload,b'x'*32),plan)
            ticket=sign(dict(payload,expires_at=time.time()+60),b'x'*32)
            ticket['payload']['pid']=2
            with self.assertRaises(ValueError): auth.consume(ticket,plan)
    def test_upload_uses_validated_snapshot(self):
        import hashlib
        from copy import deepcopy
        with tempfile.TemporaryDirectory() as root:
            original = Path(root)/'image.png'
            from PIL import Image
            Image.new('RGB',(800,800),'white').save(original)
            validated=original.read_bytes()
            ref = {'path':'image.png','sha256':hashlib.sha256(validated).hexdigest()}
            plan = dict(schema='token-opt-plan/v2',job_id='JOB_snapshot',pid=1,shop=7,workflow_version='token-opt-v2',policy_version='v2',precondition={'state_sha256':canonical_state_hash({'images':{'main':['https://x/a'],'detail':['https://x/b']}})},evidence_refs=[ref],ai_judgement_refs=[],desired={'images':{'main':['pending'],'detail':['https://x/b']}},post_actions={'uploads':[dict(ref,pool='main',index=0)]},review={'status':'RESOLVED'})
            class Auth:
                def consume(self,*args): original.write_bytes(b'attacker replacement')
            class Writer:
                state={'id':1,'shopId':7,'images':{'main':['https://x/a'],'detail':['https://x/b']}}
                path=None
                def product(self,pid): return deepcopy(self.state)
                def upload(self,path):
                    self.path=path
                    self_data=path.read_bytes()
                    if self_data != validated: raise AssertionError(self_data)
                    if path == original: raise AssertionError('original path reused')
                    return 'https://example.com/upload.png'
                def save(self,pid,value,**kwargs): self.state=value
            writer=Writer()
            result=ExecutorService(Auth(),writer,root).execute(plan,{},False)
            self.assertTrue(result['verification_ok'])
            self.assertFalse(writer.path.exists())
