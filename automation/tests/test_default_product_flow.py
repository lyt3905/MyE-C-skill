import copy
import json
import tempfile
import unittest
from pathlib import Path


def fixture(count):
    urls=['https://fake/'+str(i) for i in range(count)]
    return dict(id=1,images=dict(main=urls,detail=[urls[0],urls[-1]],sku=[urls[0],urls[-1]],ai=[],scene=[],gallery=[],attachList=[]),
        skus=[dict(skuId='A',skuName='With Box',skuImageUrl=urls[0],imageUrl=urls[0],price=12,originalBox=True),
              dict(skuId='B',skuName='No Box',skuImageUrl=urls[-1],price=10,originalBox=False)],
        descriptionJson=[dict(type='text',text='preserve me'),dict(type='image',url=urls[0]),
            dict(type='image',url=urls[-1]),dict(shopFooter=True,type='image',url=urls[0])],
        title='Original',titleEn='Original English',price=10,weight=.2,presale=True,status='READY_TO_PUBLISH')


class DefaultProductFlowTests(unittest.TestCase):
    def run_preflight(self,root,count,*,product=None,unknown=False):
        from test_seven_main_promo import policy
        from mye_c_automation.workflow_runner import run_main_count_preflight
        from mye_c_automation.job_manager import JobManager
        from mye_c_automation.execution_ledger import ExecutionLedger
        from mye_c_automation.product_state import canonical_state_hash
        original=copy.deepcopy(product or fixture(count));events=[]
        class Writer:
            def __init__(self):self.value=copy.deepcopy(original);self.saves=0
            def product(self,pid):return copy.deepcopy(self.value)
            def account_fingerprint(self):return 'a'*64
            def current_shop(self):return 7
            def save(self,pid,value,*,expected_state_sha256,**kwargs):
                if canonical_state_hash(self.value)!=expected_state_sha256:raise ValueError('STATE_DRIFT')
                if value.get('descriptionJson')!=self.value.get('descriptionJson'):
                    if kwargs.get('description_image_deletions')!=[original['images']['main'][0]]:raise AssertionError('Missing bounded body deletion permission')
                self.saves+=1;events.append('save');self.value=copy.deepcopy(value)
                if unknown:raise TimeoutError('response lost after save')
        writer=Writer()
        class Reader:
            def product(self,pid):events.append('independent_read');return writer.product(pid)
            def account_fingerprint(self):return 'a'*64
            def current_shop(self):return 7
        manager=JobManager(Path(root)/'jobs');ledger=ExecutionLedger(Path(root)/'ledger.sqlite')
        try:result=run_main_count_preflight(manager,1,7,policy(),writer,Reader,execution_ledger=ledger)
        finally:ledger.close()
        return result,writer,events,original,manager

    def test_more_than_six_removes_one_target_and_all_its_product_references(self):
        for count in [7,8,10]:
            with self.subTest(count=count),tempfile.TemporaryDirectory() as d:
                result,writer,events,before,_=self.run_preflight(d,count)
                self.assertEqual(result['status'],'AUTO_VERIFIED')
                self.assertEqual(len(writer.value['images']['main']),count-1)
                target=before['images']['main'][0]
                for pool in ['main','detail','sku']:self.assertNotIn(target,writer.value['images'][pool])
                self.assertIsNone(writer.value['skus'][0]['skuImageUrl']);self.assertIsNone(writer.value['skus'][0]['imageUrl'])
                self.assertEqual(writer.value['skus'][0]['price'],12);self.assertTrue(writer.value['skus'][0]['originalBox'])
                self.assertEqual(writer.value['descriptionJson'],[before['descriptionJson'][0],before['descriptionJson'][2],before['descriptionJson'][3]])
                self.assertEqual(writer.saves,1);self.assertEqual(events,['save','independent_read'])
                self.assertEqual(result['main_count_before'],count);self.assertEqual(result['main_count_after'],count-1)
                self.assertTrue(writer.value['presale']);self.assertEqual(writer.value['status'],before['status'])

    def test_six_or_fewer_never_writes(self):
        for count in [1,5,6]:
            with self.subTest(count=count),tempfile.TemporaryDirectory() as d:
                result,writer,_,before,_=self.run_preflight(d,count)
                self.assertEqual(result['status'],'NOT_NEEDED');self.assertEqual(writer.saves,0);self.assertEqual(writer.value,before)

    def test_matching_only_detail_and_sku_pools_can_become_empty_without_deleting_sku(self):
        with tempfile.TemporaryDirectory() as d:
            p=fixture(8);p['images']['detail']=[p['images']['main'][0]];p['images']['sku']=[p['images']['main'][0]]
            result,writer,_,before,_=self.run_preflight(d,8,product=p)
            self.assertEqual(result['status'],'AUTO_VERIFIED');self.assertEqual(writer.value['images']['detail'],[])
            self.assertEqual(writer.value['images']['sku'],[]);self.assertEqual(len(writer.value['skus']),len(before['skus']))

    def test_cleanup_recipe_cannot_target_a_different_url_or_modify_price(self):
        from mye_c_automation.plan_compiler import compile_main_count_preflight
        from mye_c_automation.final_state import pre_apply_validate
        from mye_c_automation.job_manager import JobManager
        from test_seven_main_promo import policy
        with tempfile.TemporaryDirectory() as d:
            manager=JobManager(Path(d)/'jobs');p=fixture(8);job=manager.create(1,7,{'site_save':1},mode='auto_apply')
            job=manager.bind_account(job['job_id'],'a'*64);job=manager.bind_input(job['job_id'],p)
            plan,_=compile_main_count_preflight(manager.directory(job['job_id']),job,p,policy())
            corrupt=copy.deepcopy(plan);corrupt['post_actions']['main_reference_cleanup']['removed_url']=p['images']['main'][1]
            with self.assertRaises(ValueError):pre_apply_validate(p,corrupt)
            from mye_c_automation.main_preprocessing import expected,verify_snapshot
            after=expected(p,plan);after['price']=999
            self.assertFalse(verify_snapshot(p,plan,after)['ok'])

    def test_new_configuration_defaults_include_title_preflight_and_image_rights(self):
        from mye_c_automation.configuration import initialize_config,load_image_options
        from mye_c_automation.job_manager import JobManager
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);initialize_config(root/'local')
            policy=json.loads((root/'local/automation.local.json').read_text(encoding='utf-8'))
            self.assertTrue(policy['allow_actions']['TITLE_REWRITE']);self.assertTrue(policy['trim_seven_main_before_audit'])
            self.assertFalse(policy['enabled'])
            self.assertEqual(load_image_options(root/'local/image-options.local.json')['rights'],'OWNED_OR_LICENSED')
            job=JobManager(root/'jobs').create(1,7,{},image_workflow='v2')
            self.assertEqual(job['image_options']['rights'],'OWNED_OR_LICENSED')

    def test_explicit_unknown_rights_are_not_fabricated_by_loader(self):
        from mye_c_automation.configuration import load_image_options
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'options.json';p.write_text(json.dumps(dict(rights='RIGHTS_UNKNOWN',max_mask_area=.25)))
            self.assertEqual(load_image_options(p)['rights'],'RIGHTS_UNKNOWN')

    def test_subsequent_automatic_workflow_can_keep_remaining_seven(self):
        from mye_c_automation.final_state import pre_apply_validate
        from mye_c_automation.product_state import canonical_state_hash
        from mye_c_automation.main_preprocessing import verify_receipt
        from mye_c_automation.job_manager import atomic_json
        from test_seven_main_promo import policy
        with tempfile.TemporaryDirectory() as d:
            product=fixture(8)
            for field in ('skuImageUrl','imageUrl'):product['skus'][0][field]=product['images']['main'][-1]
            result,writer,_,_,manager=self.run_preflight(d,8,product=product)
            before=writer.product(1);root=Path(d)/'jobs'/'JOB_continuation';root.mkdir()
            atomic_json(root/'audit_product.json',before)
            plan=dict(schema='token-opt-plan/v3',pid=1,shop=7,desired={},post_actions={},
                precondition=dict(state_sha256=canonical_state_hash(before),account_fingerprint='a'*64,
                    main_count_preflight=dict(job_id=result['job_id'],main_count=7)),
                automation=dict(policy_sha256=policy().sha256,actions=[]))
            verify_receipt(root,plan)
            self.assertTrue(pre_apply_validate(before,plan)['ok'])
            plan['precondition']['main_count_preflight']['job_id']='JOB_missing'
            with self.assertRaises(FileNotFoundError):verify_receipt(root,plan)

    def test_unknown_save_recovery_does_not_delete_again_or_resave(self):
        from unittest.mock import patch
        from mye_c_automation.workflow_runner import resume_main_count_preflight
        from mye_c_automation.execution_ledger import ExecutionLedger
        from mye_c_automation.job_manager import JobManager
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(TimeoutError):self.run_preflight(root,8,unknown=True)
            manager=JobManager(root/'jobs');folder=next((root/'jobs').glob('JOB_*'))
            after=json.loads((folder/'expected_after.json').read_text(encoding='utf-8'))
            class ReadOnly:
                def product(self,pid):return copy.deepcopy(after)
                def account_fingerprint(self):return 'a'*64
                def current_shop(self):return 7
                def save(self,*args,**kwargs):raise AssertionError('Recovery must not save')
            with patch('mye_c_automation.execution_ledger.ExecutionLedger',side_effect=lambda:ExecutionLedger(root/'ledger.sqlite')):
                result=resume_main_count_preflight(manager,folder.name,ReadOnly())
            self.assertEqual(result['status'],'AUTO_VERIFIED')
            self.assertEqual(result['main_count_before'],8);self.assertEqual(result['main_count_after'],7)

    def test_automatic_plan_cannot_increase_existing_excess(self):
        from mye_c_automation.final_state import pre_apply_validate
        p=fixture(7);images=copy.deepcopy(p['images']);images['main'].append('https://fake/new')
        plan=dict(schema='token-opt-plan/v3',desired=dict(images=images),post_actions={},automation=dict(actions=['DELETE']))
        checked=pre_apply_validate(p,plan)
        self.assertFalse(checked['ok']);self.assertIn('MAIN_COUNT',[r['rule_id'] for r in checked['errors']])

    def test_public_default_title_and_eight_main_preflight_complete_together(self):
        from test_title_workflow_v2 import TitleWorkflowTests
        from mye_c_automation.fake import image_bytes
        from mye_c_automation.resources import resource_path
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);h,f=TitleWorkflowTests().fixture(root)
            defaults=json.loads(resource_path('config/automation.v2.example.json').read_text(encoding='utf-8'))
            defaults.update(enabled=True,pid_allowlist=[1]);(f['cfg']/'automation.local.json').write_text(json.dumps(defaults))
            first=f['writer'].state['images']['main'][0]
            for sku in f['writer'].state['skus']:sku['skuImageUrl']=first
            for i in range(3,8):
                url='https://fake/image/'+str(i);f['assets'][url]=image_bytes(Image.new('RGB',(800,800),(i*20,60,150)))
                f['writer'].state['images']['main'].append(url)
            code,result,text=h.invoke(root,f)
            self.assertEqual(code,0,text);self.assertEqual(result['status'],'AUTO_VERIFIED',text)
            self.assertEqual(len(f['writer'].state['images']['main']),7)
            for pool in ['main','detail','sku']:self.assertNotIn(first,f['writer'].state['images'][pool])
            self.assertEqual(f['title_calls'],1);self.assertTrue(result['title']['applied'])
            self.assertEqual(f['counters']['saves'],2);self.assertTrue(result['independent_verification']['ok'])
