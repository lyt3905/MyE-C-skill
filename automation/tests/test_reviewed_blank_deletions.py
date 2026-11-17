import copy,io,json,tempfile,unittest
from pathlib import Path
from PIL import Image
from mye_c_automation.job_manager import JobManager,atomic_json
from mye_c_automation.automation_policy import AutomationPolicy
from mye_c_automation.resources import resource_path
from mye_c_automation.fake import FakeWriter,image_bytes
from mye_c_automation.final_state import pre_apply_validate


class ReviewedBlankDeletionTests(unittest.TestCase):
    def setup_case(self,tmp,main_count=8):
        root=Path(tmp);assets={'https://fake/'+str(n):image_bytes(Image.new('RGB',(800,800),(n*20,50,100))) for n in range(main_count)}
        b=io.BytesIO();Image.new('P',(1,1),0).save(b,format='GIF');assets['https://fake/blank']=b.getvalue()
        product=dict(id=1,shopId=7,status='PENDING',price=10,weight=.2,presale=True,title='product',
            images=dict(main=list(assets)[:-1],detail=['https://fake/0','https://fake/blank'],sku=['https://fake/0'],ai=[],scene=[],gallery=[],attachList=[]),
            skus=[dict(skuId='A',skuName='With Box',skuImageUrl='https://fake/0',price=10)],descriptionJson='Unchanged description')
        original=copy.deepcopy(product);counter=dict(saves=0,uploads=0,independent_reads=0,independent_readbacks=0)
        writer=FakeWriter(product,assets,counter);manager=JobManager(root/'jobs');job=manager.create(1,7,{'site_save':1},mode='auto_apply',image_workflow='v2');job=manager.bind_account(job['job_id'],writer.account_fingerprint());job=manager.bind_input(job['job_id'],product)
        cfg=json.loads(resource_path('config/automation.v2.example.json').read_text());cfg.update(enabled=True,pid_allowlist=[1]);cfg['allow_actions']={k:k=='DELETE' for k in cfg['allow_actions']};policy=AutomationPolicy(cfg)
        import hashlib
        targets=[dict(index=1,url='https://fake/blank',sha256=hashlib.sha256(assets['https://fake/blank']).hexdigest())]
        review=dict(source='EXPLICIT_USER_REVIEW',statement='3-5是空白像素，可以直接删除',authorized_actions=['DELETE'])
        return root,writer,manager,job,policy,targets,review,original,counter

    def compile(self,s):
        from mye_c_automation.reviewed_images import compile_blank_deletions
        root,w,m,j,p,t,r,original,c=s
        return compile_blank_deletions(m.directory(j['job_id']),j,w.product(1),p,t,r,fetch_image=w.fetch_image)

    def test_scoped_blank_deletion_preserves_preexisting_main_count_and_business_fields(self):
        from mye_c_automation.workflow_runner import live_dry_run
        from mye_c_automation.executor.local import LocalExecutor
        from mye_c_automation.reviewed_images import verify_reviewed_snapshot
        from jsonschema import Draft202012Validator
        for count in (7,8):
            with self.subTest(main_count=count),tempfile.TemporaryDirectory() as tmp:
                s=self.setup_case(tmp,count);root,w,m,j,p,t,r,original,c=s;plan,compiled=self.compile(s)
                schema=json.loads(resource_path('config/schemas/plan.v3.schema.json').read_text());self.assertEqual(list(Draft202012Validator(schema).iter_errors(plan)),[])
                m.transition(j['job_id'],'NEEDS_REVIEW');m.automatic_plan_ready(j['job_id'],compiled);live_dry_run(m,j['job_id'],w)
                result=LocalExecutor(w,m.directory(j['job_id'])).execute_auto(plan,p)
                self.assertEqual(c['saves'],1);self.assertEqual(c['uploads'],0);self.assertTrue(result['verification_ok'])
                expected=copy.deepcopy(original);expected['images']['detail'].pop(1);self.assertEqual(w.state,expected)
                checked=verify_reviewed_snapshot(m.directory(j['job_id']),plan,w.product(1));self.assertTrue(checked['ok'])
                self.assertTrue(checked['existing_state_findings']);self.assertFalse(checked['whole_product_verified'])

    def test_normal_plan_with_excess_main_images_remains_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=self.setup_case(tmp);plan,_=self.compile(s);plan['post_actions']={}
            self.assertFalse(pre_apply_validate(s[7],plan)['ok'])

    def test_nonblank_image_cannot_enter_user_confirmed_blank_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=self.setup_case(tmp);s[5][0].update(index=0,url='https://fake/0')
            import hashlib
            s[5][0]['sha256']=hashlib.sha256(s[1].assets['https://fake/0']).hexdigest()
            with self.assertRaises(ValueError):self.compile(s)
            self.assertEqual(s[-1]['saves'],0)

    def test_missing_user_deletion_authorization_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=self.setup_case(tmp);s[6]['authorized_actions']=[]
            with self.assertRaises(ValueError):self.compile(s)

    def test_extra_main_or_sku_change_does_not_get_scoped_exception(self):
        for field in ('main','sku'):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as tmp:
                s=self.setup_case(tmp);plan,_=self.compile(s);plan['desired']['images'][field]=['https://fake/1']
                self.assertFalse(pre_apply_validate(s[7],plan)['ok'])

    def test_changed_bound_review_or_pixel_bytes_stops_before_write(self):
        from mye_c_automation.executor.service import ExecutorService
        for which in ('review','bytes'):
            with self.subTest(which=which),tempfile.TemporaryDirectory() as tmp:
                s=self.setup_case(tmp);plan,_=self.compile(s);directory=s[2].directory(s[3]['job_id'])
                path=directory/'reviewed_images.json' if which=='review' else next((directory/'reviewed_images').iterdir())
                path.write_bytes(b'changed')
                with self.assertRaises(ValueError):ExecutorService(None,None,directory).execute(plan,dry_run=True)
                self.assertEqual(s[-1]['saves'],0)

    def test_save_response_lost_is_recovered_without_second_save(self):
        from mye_c_automation.workflow_runner import live_dry_run
        from mye_c_automation.executor.local import LocalExecutor
        with tempfile.TemporaryDirectory() as tmp:
            s=self.setup_case(tmp);root,w,m,j,p,t,r,original,c=s;plan,compiled=self.compile(s)
            m.transition(j['job_id'],'NEEDS_REVIEW');m.automatic_plan_ready(j['job_id'],compiled);live_dry_run(m,j['job_id'],w)
            save=w.save
            def lost(*a,**kw):save(*a,**kw);raise TimeoutError('saved but response lost')
            w.save=lost;executor=LocalExecutor(w,m.directory(j['job_id']))
            with self.assertRaises(TimeoutError):executor.execute_auto(plan,p)
            self.assertEqual(executor.recover_readback(plan)['write_outcome'],'MATCHED')
            with self.assertRaises(FileExistsError):executor.execute_auto(plan,p)
            self.assertEqual(c['saves'],1)

    def test_formal_recovery_keeps_partial_scope_instead_of_claiming_whole_product(self):
        from mye_c_automation.workflow_runner import live_dry_run,resume_verification
        from mye_c_automation.executor.local import LocalExecutor
        from mye_c_automation.full_product_audit import build_inventory
        from mye_c_automation.execution_ledger import ExecutionLedger,operation_digest
        from mye_c_automation.candidate_quality import CandidateQualityGate
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            s=self.setup_case(tmp);root,w,m,j,p,t,r,original,c=s;plan,compiled=self.compile(s);directory=m.directory(j['job_id'])
            rows=[]
            for index,(url,data) in enumerate(w.assets.items()):
                path=directory/('retained-'+str(index)+'.bin');path.write_bytes(data)
                rows.append(dict(kind='detail',index=index,url=url,file=str(path)))
            atomic_json(directory/'full_inventory.json',build_inventory(original,rows))
            m.transition(j['job_id'],'NEEDS_REVIEW');m.automatic_plan_ready(j['job_id'],compiled);live_dry_run(m,j['job_id'],w)
            ledger=ExecutionLedger(root/'ledger.sqlite')
            try:
                ledger.claim(w.account_fingerprint(),7,1,j['job_id'],j['input_state_sha256'],operation_digest(plan))
                LocalExecutor(w,directory,before_remote_write=lambda:ledger.begin_side_effect(w.account_fingerprint(),7,1,j['job_id'])).execute_auto(plan,p)
            finally:ledger.close()
            with patch('mye_c_automation.execution_ledger.ExecutionLedger',side_effect=lambda:ExecutionLedger(root/'ledger.sqlite')):
                result=resume_verification(m,j['job_id'],w,quality_gate=CandidateQualityGate())
            self.assertEqual(result['status'],'PARTIALLY_AUTO_FIXED')
            self.assertEqual(c['saves'],1)
