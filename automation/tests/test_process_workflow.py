"""Public URL command exercises the existing V2 chain with synthetic boundaries."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
from mye_c_automation.fake import FakeWriter, FakeReader, image_bytes, observation
from mye_c_automation.resources import resource_path


class ProcessWorkflowTests(unittest.TestCase):
    def fixture(self, root, *, seven=False, partial=False):
        cfg = root/'config'; cfg.mkdir()
        site = dict(base='https://fake/', user='synthetic', pwd='not-a-real-password')
        policy = json.loads(resource_path('config/automation.v2.example.json').read_text())
        policy.update(enabled=True, pid_allowlist=[1], trim_seven_main_before_audit=True,
                      allow_snapshot_sku_rows=True, delete_decorated_composites=True)
        policy['allow_actions']['AI_REGENERATE'] = False
        # These fixtures mock image responses only; title integration has its
        # own full HTTP fixture and default-flow regression.
        policy['allow_actions']['TITLE_REWRITE'] = False
        model = dict(schema='model-gateway/v1', base_url='http://127.0.0.1:8788/v1',
                     models=['deepseek-v4.1-flash'], max_output_tokens=16384,
                     retries=0, timeout=150, reasoning_effort='low', image_concurrency=10,vision_protocol='legacy-v2')
        values = {'site.local.json': site, 'automation.local.json': policy,
                  'model.local.json': model, 'image-options.local.json': dict(rights='OWNED_OR_LICENSED'),
                  'model-key.local.json': dict(VLM_API_KEY='fake-key-do-not-print'),
                  'download.local.json': dict(max_retries=1, retry_base_seconds=0,
                                            retry_max_seconds=0, min_interval_seconds=0)}
        for name, value in values.items(): (cfg/name).write_text(json.dumps(value), encoding='utf-8')
        assets = {}
        for n in range(7 if seven else 3):
            im = Image.new('RGB', (800,800), (220,220,220))
            ImageDraw.Draw(im).rectangle((150+n*11,130,640,650), fill=(30+n*24,60,180))
            if n == 0: ImageDraw.Draw(im).text((18,748), 'STORE', fill='red')
            assets['https://fake/image/'+str(n)] = image_bytes(im)
        urls = list(assets)
        product = dict(id=1, shopId=7, title='Synthetic toy', price=10, weight=.2, presale=True,
                       status='READY_TO_PUBLISH', images=dict(main=urls[:], detail=urls[:], sku=urls[-2:]),
                       skus=[dict(skuId='a', skuName='no retail box', skuImageUrl=urls[-1], price=10),
                             dict(skuId='b', skuName='with retail box', skuImageUrl=urls[-1], price=20)],
                       descriptionJson=json.dumps([dict(type='text', text='fixed text'),
                           dict(type='image', url=urls[0]), dict(type='text', shopFooter=True, text='footer'),
                           dict(type='image', url='https://never-fetch/footer')]))
        original = copy.deepcopy(product)
        counters = dict(saves=0, uploads=0, independent_reads=0, independent_readbacks=0, model_calls=0)
        writer = FakeWriter(product, assets, counters)
        readers = []
        def reader(_cfg):
            value = FakeReader(product, assets, counters); readers.append(value); return value
        source = hashlib.sha256(assets[urls[0]]).hexdigest()
        review = hashlib.sha256(assets[urls[1]]).hexdigest() if partial else None
        actions={source:'REMOVE_TEXT'};transforms={}
        events = []
        def open_model(request, timeout):
            self.assertEqual(request.get_header('Authorization'), 'Bearer fake-key-do-not-print')
            body = json.loads(request.data)
            self.assertEqual(body['model'], 'deepseek-v4.1-flash')
            text = body['messages'][0]['content'][0]['text']
            payload = json.loads(text[text.rfind('{"item":'):])
            item = payload['item']; self.assertNotIn('descriptionJson', payload['context'])
            counters['model_calls'] += 1; events.append(('model', counters['saves']))
            if item['task_type'] == 'image_quality_v2':
                value = dict(task_type=item['task_type'], item_id=item['id'], decision='MATCH',
                    confidence=0., abstain=False, evidence_ids=item['evidence_ids'],
                    checks={k:True for k in ('identity_preserved','packaging_preserved','protected_print_preserved','overlay_removed','no_new_artifacts')})
            else:
                dirty = actions.get(item['sha256']) == 'REMOVE_TEXT'
                marks = [dict(kind='STORE_WATERMARK', owner='UNKNOWN', overlay_role='ADDED_WATERMARK',
                    bbox=[.01,.92,.14,.97], confidence=0., preserve_overlap_risk='LOW')] if dirty else []
                value = observation(item, 'REVIEW' if item['sha256']==review else 'REMOVE_TEXT' if dirty else 'KEEP', marks)
                if item['sha256'] in transforms:value=transforms[item['sha256']](value)
            return io.BytesIO(json.dumps(dict(choices=[dict(message=dict(content=json.dumps(value),
                reasoning_content='hidden fake reasoning'))])).encode())
        def open_image(request, *args, **kwargs):
            response=io.BytesIO(assets[request.full_url]);response.headers={'Content-Type':'image/png'};response.status=200;response.code=200
            return response
        result=dict(cfg=cfg, writer=writer, reader=reader, readers=readers, assets=assets,
                    counters=counters, original=original, events=events, model=open_model, image=open_image)
        result.update(actions=actions,transforms=transforms)
        return result

    def invoke(self, root, f, *extra, url='https://fake/products/1'):
        from mye_c_automation.cli import main
        from mye_c_automation.execution_ledger import ExecutionLedger
        output=io.StringIO()
        with patch.dict(os.environ, {'MYEC_DATA_ROOT':str(root/'runtime')}), \
             patch('mye_c_automation.one_command._writer', return_value=f['writer']), \
             patch('mye_c_automation.one_command._reader', side_effect=f['reader']), \
             patch('mye_c_automation.ai_judge.client._open_model_request', side_effect=f['model']), \
             patch('urllib.request.urlopen', side_effect=f['image']), \
             patch('mye_c_automation.execution_ledger.ExecutionLedger', side_effect=lambda:ExecutionLedger(root/'executions.sqlite')), \
             contextlib.redirect_stdout(output):
            os.environ.pop('VLM_API_KEY', None)
            code=main(['process',url,'--config-dir',str(f['cfg']),'--data-root',str(root/'runtime'),*extra])
        return code,json.loads(output.getvalue()),output.getvalue()

    def test_url_command_repairs_assigns_saves_and_independently_reads_without_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);f=self.fixture(root);code,result,text=self.invoke(root,f)
            self.assertEqual(code,0,text);self.assertEqual(result['status'],'AUTO_VERIFIED',text)
            self.assertEqual(f['counters']['saves'],1);self.assertEqual(f['counters']['uploads'],1)
            self.assertTrue(result['independent_verification']['ok'])
            self.assertGreaterEqual(len(f['readers']),2)
            skus=f['writer'].state['skus'];self.assertNotEqual(skus[0]['skuImageUrl'],skus[1]['skuImageUrl'])
            self.assertNotIn('fake-key',text);self.assertNotIn('hidden fake reasoning',text)
            self.assertNotIn('VLM_API_KEY',os.environ)
            self.assertTrue(Path(result['report']).is_file())

    def test_seven_preflight_precedes_every_model_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);f=self.fixture(root,seven=True);code,result,text=self.invoke(root,f)
            self.assertEqual(code,0,text);self.assertEqual(result['main_count_preflight']['main_count_after'],6)
            self.assertTrue(all(saves==1 for _,saves in f['events']))
            self.assertEqual(f['counters']['saves'],2)
            self.assertEqual(len(f['writer'].state['images']['main']),6)
            self.assertEqual(f['writer'].state['presale'],True)

    def test_review_is_terminal_partial_and_is_never_forced_into_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);f=self.fixture(root,partial=True);code,result,text=self.invoke(root,f)
            self.assertEqual(code,0,text);self.assertEqual(result['status'],'PARTIALLY_AUTO_FIXED')
            self.assertGreater(result['deferred_count'],0);self.assertFalse(result['whole_product_clean'])

    def test_audit_only_never_runs_preflight_upload_or_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);f=self.fixture(root,seven=True);code,result,text=self.invoke(root,f,'--audit-only')
            self.assertEqual(code,0,text);self.assertEqual(f['counters']['saves'],0)
            self.assertEqual(f['counters']['uploads'],0);self.assertTrue(result['read_only'])

    def test_foreign_or_malformed_url_stops_before_login_or_model(self):
        from mye_c_automation.one_command import product_id_from_url
        for url in ('https://other/products/1','http://fake/products/1','https://fake/products/0',
                    'https://fake/products/1?x=1','https://user:pass@fake/products/1','https://fake/products/1/extra'):
            with self.subTest(url=url),self.assertRaises(ValueError): product_id_from_url(url,'https://fake/')
        self.assertEqual(product_id_from_url('https://fake/products/5182','https://fake/'),5182)

    def test_completed_resume_does_not_repeat_models_or_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);f=self.fixture(root);_,first,_=self.invoke(root,f);before=dict(f['counters'])
            code,result,text=self.invoke(root,f,'--resume',first['job_id'])
            self.assertEqual(code,0,text);self.assertEqual(f['counters']['saves'],before['saves'])
            self.assertEqual(f['counters']['model_calls'],before['model_calls'])
            self.assertEqual(result['job_id'],first['job_id'])

    def test_product_override_preserves_global_rights_and_disabled_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);f=self.fixture(root);cfg=f['cfg'];local=cfg/'products/1';local.mkdir(parents=True)
            for name in ('automation.local.json','image-options.local.json'):
                (local/name).write_bytes((cfg/name).read_bytes())
            p=json.loads((cfg/'automation.local.json').read_text());p['enabled']=False
            (cfg/'automation.local.json').write_text(json.dumps(p));(cfg/'image-options.local.json').write_text('{"rights":"RIGHTS_UNKNOWN"}')
            before={p.name:p.read_bytes() for p in cfg.glob('*.json')}
            code,result,text=self.invoke(root,f);self.assertEqual(code,0,text)
            self.assertEqual(result['status'],'AUTO_VERIFIED')
            self.assertEqual(before,{p.name:p.read_bytes() for p in cfg.glob('*.json')})

    def test_disabled_execution_is_rejected_before_connecting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);f=self.fixture(root);p=f['cfg']/'automation.local.json'
            v=json.loads(p.read_text());v['enabled']=False;p.write_text(json.dumps(v))
            code,result,text=self.invoke(root,f)
            self.assertEqual(code,2,text);self.assertIn('AUTO_APPLY_DISABLED',text)
            self.assertEqual(f['readers'],[]);self.assertEqual(f['counters']['model_calls'],0)

    def test_known_partial_save_continues_automatically_without_rewriting_old_job(self):
        from mye_c_automation.execution_ledger import ExecutionLedger
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);f=self.fixture(root);original_image=f['image']
            recovered=Image.new('RGB',(1200,1200),'white');ImageDraw.Draw(recovered).ellipse((200,200,1000,1000),fill='green')
            f['assets']['https://fake/image/2']=image_bytes(recovered)
            def missing(request,*a,**kw):
                if request.full_url=='https://fake/image/2':raise FileNotFoundError('synthetic image unavailable')
                return original_image(request,*a,**kw)
            f['image']=missing
            code,first,text=self.invoke(root,f);self.assertEqual(code,0,text)
            self.assertEqual(first['technical_status'],'CONTENT_REVIEW_REQUIRED');self.assertEqual(f['counters']['saves'],1)
            previous=Path(first['evidence_directory'])
            before={p.relative_to(previous).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in previous.rglob('*') if p.is_file()}
            f['image']=original_image
            code,second,text=self.invoke(root,f);self.assertEqual(code,0,text)
            self.assertEqual(second['status'],'AUTO_VERIFIED',text);self.assertEqual(f['counters']['saves'],2)
            self.assertEqual(before,{p.relative_to(previous).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in previous.rglob('*') if p.is_file()})
            ledger=ExecutionLedger(root/'executions.sqlite')
            try:self.assertEqual(ledger.db.execute('select state from execution_followups').fetchall(),[('CONTENT_REVIEW_REQUIRED',)])
            finally:ledger.close()

    def test_lost_save_response_resume_only_reads_without_second_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);f=self.fixture(root);save=f['writer'].save
            def timeout(*a,**kw):save(*a,**kw);raise TimeoutError('fake saved but response lost')
            f['writer'].save=timeout
            code,first,text=self.invoke(root,f)
            self.assertEqual(code,3,text);self.assertEqual(first['status'],'APPLY_UNKNOWN')
            calls=f['counters']['model_calls'];self.assertEqual(f['counters']['saves'],1)
            code,second,text=self.invoke(root,f,'--resume',first['job_id'])
            self.assertEqual(code,0,text);self.assertEqual(second['status'],'AUTO_VERIFIED',text)
            self.assertEqual(f['counters']['saves'],1);self.assertEqual(f['counters']['model_calls'],calls)

    def test_unknown_prior_write_stops_new_job_before_any_model(self):
        from mye_c_automation.execution_ledger import ExecutionLedger
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);f=self.fixture(root);ledger=ExecutionLedger(root/'executions.sqlite')
            try:
                ledger.claim('f'*64,7,1,'JOB_previous','before','op');ledger.begin_side_effect('f'*64,7,1,'JOB_previous')
            finally:ledger.close()
            code,result,text=self.invoke(root,f);self.assertEqual(code,3,text)
            self.assertEqual(result['status'],'APPLY_UNKNOWN');self.assertEqual(f['counters']['model_calls'],0)

    def test_resume_other_product_and_policy_drift_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);f=self.fixture(root);_,first,_=self.invoke(root,f);calls=f['counters']['model_calls']
            code,result,text=self.invoke(root,f,'--resume',first['job_id'],url='https://fake/products/2')
            self.assertEqual(code,2,text)
            p=f['cfg']/'automation.local.json';value=json.loads(p.read_text());value['max_uploads_per_job']=11;p.write_text(json.dumps(value))
            code,result,text=self.invoke(root,f,'--resume',first['job_id']);self.assertEqual(code,2,text)
            self.assertIn('RESUME_POLICY_OR_URL_MISMATCH',text);self.assertEqual(f['counters']['model_calls'],calls)

    def test_seven_preflight_timeout_can_resume_entire_workflow_without_repeating_trim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);f=self.fixture(root,seven=True);save=f['writer'].save
            def timeout_once(*a,**kw):
                save(*a,**kw)
                if f['counters']['saves']==1:raise TimeoutError('fake preflight saved but response lost')
            f['writer'].save=timeout_once
            code,first,text=self.invoke(root,f);self.assertEqual(code,3,text)
            self.assertEqual(first['phase'],'main_count_preflight');self.assertEqual(f['counters']['model_calls'],0)
            code,second,text=self.invoke(root,f,'--resume',first['job_id'])
            self.assertEqual(code,0,text);self.assertEqual(second['status'],'AUTO_VERIFIED',text)
            self.assertEqual(f['counters']['saves'],2);self.assertEqual(len(f['writer'].state['images']['main']),6)

    def test_environment_key_takes_precedence_and_is_restored(self):
        from mye_c_automation.one_command import _runtime_environment
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);f=self.fixture(root)
            with patch.dict(os.environ,{'VLM_API_KEY':'existing-synthetic-key','MYEC_CONFIG_DIR':'before'}):
                with _runtime_environment(f['cfg'],root/'runtime'):
                    self.assertEqual(os.environ['VLM_API_KEY'],'existing-synthetic-key')
                self.assertEqual(os.environ['VLM_API_KEY'],'existing-synthetic-key')
                self.assertEqual(os.environ['MYEC_CONFIG_DIR'],'before')

    def test_independent_readback_failure_cannot_be_reported_as_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);f=self.fixture(root);reader=f['reader']
            def changed(config):
                value=reader(config);product=value.product
                def read(pid):
                    result=product(pid)
                    if f['counters']['saves']:result['price']=999
                    return result
                value.product=read;return value
            f['reader']=changed
            code,result,text=self.invoke(root,f);self.assertEqual(code,0,text)
            self.assertEqual(result['technical_status'],'CONTENT_REVIEW_REQUIRED')
            self.assertFalse(result['independent_verification']['ok']);self.assertFalse(result['whole_product_clean'])
            self.assertEqual(f['counters']['saves'],1)

    def test_offline_configuration_check_recognizes_local_key_without_printing_it(self):
        from mye_c_automation.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);f=self.fixture(root);output=io.StringIO()
            with patch.dict(os.environ),contextlib.redirect_stdout(output):
                os.environ.pop('VLM_API_KEY',None)
                code=main(['configure','check','--directory',str(f['cfg'])])
                self.assertNotIn('VLM_API_KEY',os.environ)
            result=json.loads(output.getvalue());self.assertEqual(code,0,output.getvalue())
            self.assertTrue(result['checks']['model_api_key_present']);self.assertNotIn('fake-key',output.getvalue())

    def test_url_entry_prefers_existing_same_photo_without_uploading(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);f=self.fixture(root)
            rng=np.random.default_rng(68)
            clean=Image.fromarray(rng.integers(20,235,(1000,1000,3),dtype=np.uint8))
            for _ in range(45):
                x,y=rng.integers(160,760,2);ImageDraw.Draw(clean).rectangle((x,y,x+45,y+65),outline='white',width=4)
            source=clean.copy();ImageDraw.Draw(source).rectangle((0,875,1000,1000),fill='red')
            f['assets']['https://fake/image/0']=image_bytes(source)
            f['assets']['https://fake/image/1']=image_bytes(clean)
            sha=hashlib.sha256(image_bytes(source)).hexdigest()
            f['actions'].clear();f['actions'][sha]='REMOVE_TEXT'
            def banner(value):
                value['watermarks'][0]['bbox']=[0,.875,1,1]
                return value
            f['transforms'][sha]=banner
            code,result,text=self.invoke(root,f);self.assertEqual(code,0,text)
            self.assertEqual(result['status'],'AUTO_VERIFIED',text);self.assertEqual(f['counters']['uploads'],0)
            self.assertEqual(f['writer'].state['images']['main'][0],'https://fake/image/1')
            self.assertEqual(f['writer'].state['images']['detail'][0],'https://fake/image/1')
            self.assertIn('https://fake/image/1',f['writer'].state['descriptionJson'])

    def test_url_entry_uses_actual_box_photo_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);f=self.fixture(root);sha=hashlib.sha256(f['assets']['https://fake/image/2']).hexdigest()
            def box(value):
                value.update(visual_class='TOY_WITH_RETAIL_BOX',retail_box_status='PRESENT',retail_box_bbox=[.6,.1,.9,.6])
                value['sku_suitability'].update(is_retail_box_photo=True,recommended_group='WITH_RETAIL_BOX')
                return value
            f['transforms'][sha]=box
            code,result,text=self.invoke(root,f);self.assertEqual(code,0,text)
            skus=f['writer'].state['skus'];self.assertEqual(skus[1]['skuImageUrl'],'https://fake/image/2')
            self.assertNotEqual(skus[0]['skuImageUrl'],skus[1]['skuImageUrl'])
