import copy,json,tempfile,unittest
from pathlib import Path
import test_v2_repairs_sku as repair
import test_v2_two_sku_images as existing
from mye_c_automation.sku_assignment import select_v2

class PackagingSplitTests(unittest.TestCase):
    def records(self):
        rows=repair.RepairSkuTests().records()
        box=rows[-1]['observation'];box.update(visual_class='RETAIL_BOX_ONLY',retail_box_status='PRESENT',retail_box_bbox=[.1,.1,.9,.9])
        box['sku_suitability'].update(is_toy_photo=False,is_retail_box_photo=True)
        return rows

    def product(self):
        p=existing.TwoSkuImagesTests().product()
        for row in p['skus']:row['skuImageUrl']='https://fake/2'
        return p

    def test_existing_shared_box_photo_is_split_by_actual_packaging(self):
        p=self.product();before=copy.deepcopy(p);result=select_v2(p,self.records())
        self.assertEqual(result['assignments'],{'without':'https://fake/0','with':'https://fake/2'})
        self.assertFalse(result['reason_codes']);self.assertEqual(p,before)
        self.assertEqual([r['source_retail_box_status'] for r in result['selected_sku_images']],['ABSENT','PRESENT'])

    def test_reversed_rows_and_no_ids_bind_by_name_or_snapshot(self):
        p=self.product();p['skus'].reverse()
        result=select_v2(p,self.records());self.assertEqual(result['assignments'],{'without':'https://fake/0','with':'https://fake/2'})
        for row in p['skus']:row.pop('skuId')
        result=select_v2(p,self.records(),allow_snapshot_rows=True)
        self.assertEqual({r['index']:r['url'] for r in result['row_assignments']},{0:'https://fake/2',1:'https://fake/0'})

    def test_single_without_sku_still_selects_nonbox_when_box_exists(self):
        p=self.product();p['skus']=p['skus'][:1]
        result=select_v2(p,self.records());self.assertEqual(result['assignments'],{'without':'https://fake/0'})
        self.assertEqual(len(result['selected_sku_images']),1)

    def test_box_only_does_not_fill_no_box_sku_and_reports_shortage(self):
        result=select_v2(self.product(),self.records()[-1:])
        self.assertEqual(result['assignments'],{'with':'https://fake/2'})
        self.assertIn('SKU_NO_NONBOX_IMAGE',result['reason_codes'])

    def test_no_box_fallback_is_another_distinct_nonbox_photo(self):
        rows=repair.RepairSkuTests().records();result=select_v2(self.product(),rows)
        self.assertNotEqual(result['assignments']['without'],result['assignments']['with'])
        self.assertTrue(all(r['source_retail_box_status']=='ABSENT' for r in result['selected_sku_images']))

    def test_ineligible_nonbox_is_not_used_to_hide_shortage(self):
        rows=self.records()
        for row in rows[:-1]:row['decision']='REVIEW'
        result=select_v2(self.product(),rows)
        self.assertEqual(result['assignments'],{'with':'https://fake/2'});self.assertIn('SKU_NO_NONBOX_IMAGE',result['reason_codes'])

    def test_unusable_box_does_not_block_two_verified_nonbox_choices(self):
        rows=self.records();rows[-1]['decision']='REVIEW'
        result=select_v2(self.product(),rows)
        self.assertEqual(set(result['assignments']),{'without','with'})
        self.assertNotEqual(result['assignments']['without'],result['assignments']['with'])
        self.assertTrue(all(r['source_retail_box_status']=='ABSENT' for r in result['selected_sku_images']))

    def test_formal_fake_workflow_assigns_product_and_box_and_preserves_other_fields(self):
        from test_v2_workflow import V2WorkflowTests
        def obs(value,item):
            if value['image_sha256']==self.box_digest:
                value.update(visual_class='RETAIL_BOX_ONLY',retail_box_status='PRESENT',retail_box_bbox=[.1,.1,.9,.9]);value['sku_suitability'].update(is_toy_photo=False,is_retail_box_photo=True)
            return value
        def product(p,assets,urls):
            import hashlib
            self.box_digest=hashlib.sha256(assets[urls[1]]).hexdigest()
        for missing in (False,True):
            with self.subTest(missing=missing),tempfile.TemporaryDirectory() as root:
                result=V2WorkflowTests.scenario(self,root,['KEEP','KEEP'],two_sku_rows=True,missing_sku_id=missing,snapshot_sku_rows=missing,product_transform=product,observation_transform=obs)
                self.assertEqual(result['product']['skus'][0]['skuImageUrl'],'https://fake/0')
                self.assertEqual(result['product']['skus'][1]['skuImageUrl'],'https://fake/1')
                self.assertEqual(result['writer'].saves,1);self.assertEqual(result['writer'].uploads,0)
                self.assertEqual(result['result']['status'],'AUTO_VERIFIED')
                for index,sku in enumerate(result['product']['skus']):self.assertEqual({k:v for k,v in sku.items() if k!='skuImageUrl'},{k:v for k,v in result['original']['skus'][index].items() if k!='skuImageUrl'})

    def test_new_sku_only_job_reuses_readonly_source_and_existing_executor_without_models(self):
        from test_v2_workflow import V2WorkflowTests
        from mye_c_automation.plan_compiler import compile_reviewed_sku_plan,verify_reviewed_sku_source
        from mye_c_automation.executor.local import LocalExecutor
        from mye_c_automation.execution_ledger import ExecutionLedger,operation_digest
        from mye_c_automation.workflow_runner import live_dry_run
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            s=V2WorkflowTests.scenario(self,tmp,['KEEP','KEEP'],two_sku_rows=True)
            source=s['root'];sealed={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
            s['product']['skus'][0]['skuImageUrl']=s['product']['skus'][1]['skuImageUrl']
            before=copy.deepcopy(s['product']);calls=len(s['calls']);saves=s['writer'].saves
            manager=s['manager'];job=manager.create(1,7,{'ai_requests':0,'site_save':1,'uploads':0},mode='auto_apply',image_workflow='v2')
            account=s['writer'].account_fingerprint();job=manager.bind_account(job['job_id'],account);job=manager.bind_input(job['job_id'],before)
            root=manager.directory(job['job_id'])
            plan,compiled=compile_reviewed_sku_plan(root,job,before,s['policy'],source,fetch_image=s['writer'].fetch_image)
            self.assertTrue(compiled['ok']);self.assertEqual(plan['automation']['actions'],['SKU_ASSIGN'])
            manager.transition(job['job_id'],'NEEDS_REVIEW');manager.automatic_plan_ready(job['job_id'],compiled);live_dry_run(manager,job['job_id'],s['writer'])
            ledger=ExecutionLedger(Path(tmp)/'correction-ledger.sqlite')
            try:
                claim=ledger.claim(account,7,1,job['job_id'],job['input_state_sha256'],operation_digest(plan));self.assertTrue(claim['ok'])
                def before_write():verify_reviewed_sku_source(root);ledger.begin_side_effect(account,7,1,job['job_id'])
                LocalExecutor(s['writer'],root,before_remote_write=before_write).execute_auto(plan,s['policy'])
            finally:ledger.close()
            self.assertEqual(len(s['calls']),calls);self.assertEqual(s['writer'].saves,saves+1)
            self.assertNotEqual(s['product']['skus'][0]['skuImageUrl'],s['product']['skus'][1]['skuImageUrl'])
            for pool in ('main','detail'):self.assertEqual(s['product']['images'][pool],before['images'][pool])
            self.assertEqual(s['product']['descriptionJson'],before['descriptionJson'])
            self.assertEqual(sealed,{p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()})
            (source/'full_ai_judgements.json').write_text('{}')
            with self.assertRaises(ValueError):verify_reviewed_sku_source(root)
