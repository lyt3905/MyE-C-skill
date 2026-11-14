import copy
import unittest
from plan_v2 import validate_plan
from product_state import canonical_state_hash


def fixture():
    return dict(schema='token-opt-plan/v2',job_id='JOB_test',pid=1,shop=7,workflow_version='token-opt-v2',policy_version='v2',precondition={'state_sha256':canonical_state_hash({})},evidence_refs=[],ai_judgement_refs=[],desired={},post_actions={},review={'status':'RESOLVED'})


class StrictPlanTests(unittest.TestCase):
    def test_nested_rejections(self):
        mutations = [
            ('precondition', {'state_sha256':'0'*64,'approved':True}),
            ('evidence_refs',[{'path':'../secret','sha256':'0'*64}]),
            ('evidence_refs',[{'path':'C:\\secret','sha256':'0'*64}]),
            ('ai_judgement_refs',[{'path':'x','sha256':'INVALID'}]),
            ('desired', {'images':{'main':['url'],'private':['x']}}),
            ('desired', {'images':{'main':[{'url':'x'}]}}),
            ('desired', {'brandId':True}),
            ('desired', {'titleEn':[]}),
            ('post_actions', {'uploads':{}}),
            ('post_actions', {'translate_title':1}),
            ('post_actions', False),
            ('pid',True), ('job_id',''),
        ]
        for key,value in mutations:
            with self.subTest(key=key,value=value):
                plan=fixture(); plan[key]=value
                with self.assertRaises(ValueError): validate_plan(plan)

    def test_validation_returns_detached_snapshot(self):
        plan=fixture(); plan['desired']={'images':{'main':['original']}}
        result=validate_plan(plan)
        plan['desired']['images']['main'][0]='changed'
        self.assertEqual(result['desired']['images']['main'],['original'])

    def test_duplicate_upload_rejected(self):
        plan=fixture(); plan['desired']={'images':{'main':['x']}}
        upload={'path':'image.png','sha256':'0'*64,'pool':'main','index':0}
        plan['post_actions']={'uploads':[upload,copy.deepcopy(upload)]}
        with self.assertRaises(ValueError): validate_plan(plan)

class TicketShapeTests(unittest.TestCase):
    def test_nonfinite_expiration_and_boolean_limit_rejected(self):
        import tempfile
        import time
        from pathlib import Path
        from executor.authorization import Authorization, sign
        from plan_v2 import plan_hash
        with tempfile.TemporaryDirectory() as root:
            auth=Authorization(b'x'*32,Path(root)/'nonce.db')
            plan=fixture()
            payload=dict(job_id=plan['job_id'],pid=1,shop=7,plan_sha256=plan_hash(plan),expires_at=time.time()+60,allowed_operations=['site_save'],max_site_saves=1,nonce='n'*32)
            for key,value in [('expires_at',float('nan')),('expires_at',float('inf')),('max_site_saves',True),('pid',True)]:
                with self.subTest(key=key,value=value):
                    changed=dict(payload);changed[key]=value
                    with self.assertRaises(ValueError): auth.consume(sign(changed,b'x'*32),plan)

    def test_sign_detaches_payload(self):
        from executor.authorization import sign
        source={'nested':{'value':1}}
        ticket=sign(source,b'x'*32)
        source['nested']['value']=2
        self.assertEqual(ticket['payload']['nested']['value'],1)
