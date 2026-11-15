import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
from test_v2_vision import observation
from test_auto_decision import CONFIG
from automation_policy import AutomationPolicy,ACTIONS
from job_manager import JobManager
from budget_manager import BudgetManager
from ai_judge.client import JudgeClient
from candidate_quality import CandidateQualityGate
from workflow_runner import run_automatic


class V2WorkflowTests(unittest.TestCase):
    def scenario(self,root,actions,mode='auto_apply',rights='OWNED_OR_LICENSED',quality_fail=False,edit_backend=False,save_timeout=False,box=False,corrupt_readback=None,image_options=None,product_id=1,ledger_path=None,reference_only=False,sku_on_first=False,missing_sku_id=False,upload_fail=False,watermark_color='red',snapshot_sku_rows=False,two_sku_rows=False,product_transform=None,asset_images=None,observation_transform=None):
        from full_product_audit import download_only
        assets={};digest_actions={}
        for n,action in enumerate(actions):
            im=Image.new('RGB',(800,800),'white');draw=ImageDraw.Draw(im)
            draw.rectangle((250,200,550,600),fill=(20+n*30,70,140))
            if action=='REMOVE_TEXT':draw.text((20,740),'STORE',fill=watermark_color)
            b=io.BytesIO();im.save(b,format='PNG');data=Path(asset_images[n]).read_bytes() if asset_images and n in asset_images else b.getvalue()
            assets['https://fake/'+str(n)]=data;digest_actions[hashlib.sha256(data).hexdigest()]=action
        urls=list(assets)
        product=dict(id=product_id,shopId=7,status='READY_TO_PUBLISH',price=20,weight=.2,
            descriptionJson={'opaque':['https://must-not-download/description']},
            images={'main':urls.copy(),'detail':urls.copy(),'sku':[urls[-1]],'scene':['https://must-not-download/scene']},
            skus=[{'skuId':'real1','skuName':'Without Box','skuImageUrl':urls[-1],'price':10}])
        if two_sku_rows:product['skus'].append(dict(skuId='real2',skuName='With Retail Box',skuImageUrl=urls[-1],originalBox=True,price=20))
        original=copy.deepcopy(product)
        if box:
            product['skus'][0].update(skuName='With Retail Box',skuImageUrl=urls[0]);product['images']['sku']=[urls[0]]
            original=copy.deepcopy(product)
        if reference_only:
            product['images']['main']=urls[1:];product['images']['detail']=urls[1:]
            product['images']['sku']=[urls[-1]];product['skus'][0]['skuImageUrl']=urls[0]
            original=copy.deepcopy(product)
        if sku_on_first:
            product['images']['sku']=[urls[0]];product['skus'][0]['skuImageUrl']=urls[0]
            original=copy.deepcopy(product)
        if missing_sku_id:
            for sku in product['skus']:sku.pop('skuId',None)
            original=copy.deepcopy(product)
        if product_transform:
            product_transform(product,assets,urls)
            original=copy.deepcopy(product)
        class Writer:
            saves=0;uploads=0
            def product(self,pid):return copy.deepcopy(product)
            def current_shop(self):return 7
            def account_fingerprint(self):return 'b'*64
            def fetch_image(self,url):return assets[url]
            def save(self,pid,desired,**kwargs):
                self.saves+=1
                if save_timeout and save_timeout!='after':raise TimeoutError('fake unknown save')
                product.clear();product.update(copy.deepcopy(desired))
                if save_timeout=='after':raise TimeoutError('fake saved but response lost')
                if corrupt_readback=='description':product['descriptionJson']={'changed':True}
                elif corrupt_readback=='sku':product['skus'][0]['skuImageUrl']='https://fake/wrong'
                elif corrupt_readback=='retained_bytes':
                    buffer=io.BytesIO();Image.new('RGB',(800,800),'green').save(buffer,format='PNG');assets[urls[-1]]=buffer.getvalue()
            def upload(self,path):
                self.uploads+=1
                if upload_fail:raise OSError('fake upload unavailable')
                url='https://fake/upload'+str(self.uploads);assets[url]=Path(path).read_bytes();return url
        writer=Writer();manager=JobManager(Path(root)/'jobs')
        options={'rights':rights};options.update(image_options or {})
        job=manager.create(product_id,7,{'ai_requests':80,'full_resolution_images':40},mode=mode,image_workflow='v2',image_options=options,model_budget={'mode':'RECORD_ONLY','usage_source':'FAKE_TRANSPORT'})
        directory=manager.directory(job['job_id'])
        budget=BudgetManager(job['budget'],directory/'budget.sqlite')
        calls=[]
        def transport(model,item,context):
            self.assertNotIn('descriptionJson',context);self.assertNotIn('scene',json.dumps(item));calls.append(item['task_type'])
            if item['task_type']=='image_quality_v2':
                checks={k:True for k in ('identity_preserved','packaging_preserved','protected_print_preserved','overlay_removed','no_new_artifacts')}
                if quality_fail:checks['identity_preserved' if quality_fail=='identity' else 'overlay_removed']=False
                result=dict(task_type=item['task_type'],item_id=item['id'],confidence=.95,abstain=False,decision='MATCH',evidence_ids=item['evidence_ids'],checks=checks)
            else:
                action=digest_actions[item['sha256']];result=observation(item,action)
                if box and item['sha256']==hashlib.sha256(assets[urls[-1]]).hexdigest():
                    result.update(visual_class='TOY_WITH_RETAIL_BOX',retail_box_status='PRESENT',retail_box_bbox=[.6,.1,.9,.6],retail_box_confidence=.8,box_relation='SAME_PRODUCT')
                    result['sku_suitability'].update(is_retail_box_photo=True,recommended_group='WITH_RETAIL_BOX')
                if action=='REMOVE_TEXT':result['watermarks']=[dict(kind='STORE_WATERMARK',bbox=[.02,.92,.12,.95],confidence=.95,preserve_overlap_risk='LOW')]
                if observation_transform:result=observation_transform(result,item)
            return {'choices':[{'message':{'content':json.dumps(result)}}],'usage':{'prompt_tokens':20,'completion_tokens':20,'total_tokens':40}}
        judge=JudgeClient(budget,directory/'cache',transport=transport,retries=0)
        from visual_quality import VisualQualityInspector
        inspector=VisualQualityInspector(directory,job,judge=judge)
        if edit_backend:
            def edit(source,context,obs,dest):
                self.assertNotIn('descriptionJson',context)
                im=Image.open(source).convert('RGB');ImageDraw.Draw(im).rectangle((0,740,100,790),fill='white');ImageDraw.Draw(im).point((1,1),fill='gray')
                path=dest/'edited.png';im.save(path)
                result={'candidate_path':str(path),'usage':{'prompt_tokens':5,'completion_tokens':5,'total_tokens':10}}
                if edit_backend=='unknown_usage':result.pop('usage')
                return result
            inspector.image_edit_backend=edit;inspector.image_edit_model='deepseek-v4.1-flash'
        def downloader(url,path):Path(path).write_bytes(assets[url])
        def auditor(pid,shop,output_dir,site):return download_only(pid,shop,output_dir=output_dir,site=site,downloader=downloader)
        config=copy.deepcopy(CONFIG);config['allow_actions'].update({a:True for a in ('DELETE','REMOVE_TEXT','AI_REGENERATE','SKU_ASSIGN')})
        if snapshot_sku_rows:config['allow_snapshot_sku_rows']=True
        policy=AutomationPolicy(config)
        from execution_ledger import ExecutionLedger
        try:
            with patch('execution_ledger.ExecutionLedger',side_effect=lambda:ExecutionLedger(ledger_path or Path(root)/'fake-ledger.sqlite')),patch('audit_one.audit',side_effect=AssertionError('legacy audit forbidden')),patch('audit_one.run_ocr',side_effect=AssertionError('OCR forbidden')),patch('audit_one.border_candidates',side_effect=AssertionError('CV semantics forbidden')):
                try:result=run_automatic(manager,job,policy,writer=writer,auditor=auditor,full_audit_reader=writer,judge=judge,quality_gate=CandidateQualityGate(inspector))
                except TimeoutError:
                    if not save_timeout:raise
                    result=json.loads((directory/'automatic_result.json').read_text())
                except ValueError as exc:
                    if not corrupt_readback or str(exc)!='post-write verification failed':raise
                    result=json.loads((directory/'automatic_result.json').read_text())
                except RuntimeError:
                    if not upload_fail:raise
                    result=json.loads((directory/'automatic_result.json').read_text())
        finally:budget.close()
        return dict(result=result,writer=writer,product=product,original=original,root=directory,calls=calls,manager=manager,policy=policy,transport=transport,auditor=auditor)

    def test_delete_keep_and_independent_deferred_one_save(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['DELETE','REVIEW','KEEP'])
            self.assertEqual(s['writer'].saves,1)
            self.assertEqual(s['result']['status'],'PARTIALLY_AUTO_FIXED')
            self.assertEqual(len(s['product']['images']['main']),2)
            self.assertEqual(s['product']['descriptionJson'],s['original']['descriptionJson'])
            self.assertEqual(s['calls'].count('image_action_decision'),3)

    def test_remove_text_dedup_upload_and_readback(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['REMOVE_TEXT','KEEP'])
            self.assertEqual(s['writer'].saves,1);self.assertEqual(s['writer'].uploads,1)
            self.assertTrue(s['result']['content_validation']['ok'])
            self.assertEqual(s['product']['images']['main'][0],s['product']['images']['detail'][0])

    def test_rights_unknown_preserves_original(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['REMOVE_TEXT','KEEP'],rights='RIGHTS_UNKNOWN')
            self.assertEqual(s['writer'].uploads,0)
            self.assertEqual(s['product']['images']['main'],s['original']['images']['main'])

    def test_unconfigured_regeneration_remains_deferred(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['AI_REGENERATE','KEEP'])
            text=(s['root']/'deferred_items.json').read_text()
            self.assertIn('IMAGE_EDIT_BACKEND_UNAVAILABLE',text)
            self.assertEqual(s['writer'].uploads,0)

    def test_quality_failure_never_uploads(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['REMOVE_TEXT','KEEP'],quality_fail=True)
            self.assertEqual(s['writer'].uploads,0)
            records=json.loads((s['root']/'v2_quality.json').read_text())['items']
            self.assertEqual(len(records),2)

    def test_configured_fake_edit_uses_existing_budget_and_quality(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['AI_REGENERATE','KEEP'],edit_backend=True)
            self.assertEqual(s['writer'].uploads,1);self.assertEqual(s['writer'].saves,1)
            db=sqlite3.connect(s['root']/'budget.sqlite')
            try:
                rows=db.execute('SELECT metadata,actual FROM model_calls').fetchall()
                edit=[r for r in rows if json.loads(r[0])['task_type']=='image_edit_v2']
                self.assertEqual(len(edit),1);self.assertEqual(edit[0][1],10)
            finally:db.close()
            summary=json.loads((s['root']/'report_data.json').read_text())
            self.assertEqual(summary['ai']['metrics_completeness'],'VERIFIED')
            self.assertEqual(summary['ai']['reported_requests'],len(s['calls'])+1)

    def test_identity_damage_does_not_retry_alternate_algorithm(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['REMOVE_TEXT','KEEP'],quality_fail='identity')
            self.assertEqual(s['writer'].uploads,0)
            records=json.loads((s['root']/'v2_quality.json').read_text())['items']
            self.assertEqual(len(records),1)
            self.assertEqual(records[0]['quality_status'],'FAIL_IDENTITY')

    def test_unknown_save_has_no_resend(self):
        from executor.local import LocalExecutor
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['DELETE','KEEP'],save_timeout=True)
            self.assertEqual(s['result']['status'],'APPLY_UNKNOWN')
            self.assertEqual(s['writer'].saves,1)
            plan=json.loads((s['root']/'plan.v2.json').read_text())
            observed=LocalExecutor(s['writer'],s['root']).recover_readback(plan)
            self.assertEqual(s['writer'].saves,1)
            self.assertNotEqual(observed['write_outcome'],'MATCHED')

    def test_box_branch_binds_existing_sku_without_creating_variants(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['KEEP','KEEP'],box=True)
            self.assertEqual(s['writer'].saves,1);self.assertEqual(s['writer'].uploads,0)
            self.assertEqual(s['product']['skus'][0]['skuImageUrl'],'https://fake/1')
            self.assertEqual(s['product']['skus'][0]['skuId'],'real1')
            self.assertEqual(len(s['product']['skus']),1)

    def test_description_and_sku_corruption_never_pass_readback(self):
        for field in ('description','sku'):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as root:
                s=self.scenario(root,['DELETE','KEEP'],corrupt_readback=field)
                self.assertEqual(s['writer'].saves,1)
                self.assertNotIn(s['result']['status'],{'AUTO_VERIFIED','PARTIALLY_AUTO_FIXED'})

    def test_cli_defaults_to_bound_v2_and_can_use_relative_job_root(self):
        import os
        import workflow_runner
        from job_manager import atomic_json
        with tempfile.TemporaryDirectory(dir=Path.cwd()/'work') as directory:
            base=Path(directory);atomic_json(base/'site.json',{})
            config=copy.deepcopy(CONFIG);atomic_json(base/'policy.json',config)
            seen=[]
            def fake_run(manager,job,policy,**kwargs):seen.append(job);return {'status':'FAKE_ONLY'}
            argv=['workflow_runner.py','run','--pid','1','--shop','7','--mode','audit','--site-config',str(base/'site.json'),'--automation-config',str(base/'policy.json'),'--root',str(base/'jobs')]
            with patch('sys.argv',argv),patch('site_client.ReadOnlySiteClient'),patch('workflow_runner.run_automatic',side_effect=fake_run):workflow_runner.main()
            self.assertEqual(seen[0]['image_workflow'],'v2')
            self.assertFalse(seen[0]['templates_required'])
            relative=os.path.relpath(base/'relative-jobs',Path.cwd())
            s=self.scenario(relative,['KEEP','KEEP'],box=True)
            self.assertEqual(s['writer'].saves,1)


if __name__=='__main__':unittest.main()
