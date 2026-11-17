import contextlib,copy,hashlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from mye_c_automation.cli import main
from mye_c_automation.fake import run_fake
from test_auto_decision import CONFIG
from test_v2_vision import observation,reply_for_prompt


class SnapshotAuditTests(unittest.TestCase):
    def setup_source(self,root):
        seed=root/'seed';(seed/'logs').mkdir(parents=True)
        result=run_fake(seed,'keep');source=Path(result['report']).parent
        cfg=root/'config';cfg.mkdir()
        (cfg/'automation.local.json').write_text(json.dumps(CONFIG))
        (cfg/'model.local.json').write_text(json.dumps(dict(schema='model-gateway/v1',base_url='http://127.0.0.1:8788/v1',models=['deepseek-v4.1-flash'],max_output_tokens=16384,retries=0,timeout=150,reasoning_effort='low')))
        (cfg/'model-key.local.json').write_text(json.dumps(dict(VLM_API_KEY='SYNTHETIC_NOT_REAL')))
        (cfg/'download.local.json').write_text(json.dumps(dict(max_retries=0,retry_base_seconds=0,retry_max_seconds=0,min_interval_seconds=0)))
        return source,cfg

    def invoke(self,source,cfg,data,*,pid=1):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            code=main(['audit-snapshot','--source-job',str(source),'--pid',str(pid),'--shop','7','--config-dir',str(cfg),'--data-root',str(data),'--instruction','Re-audit the original product images using the corrected prompt'])
        return code,json.loads(output.getvalue())

    def test_native_snapshot_entry_uses_existing_audit_with_fresh_ledger_and_no_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,cfg=self.setup_source(root)
            before={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
            def model(request,timeout):
                body=json.loads(request.data);text=body['messages'][0]['content'][0]['text']
                item=json.loads(text[text.rfind('{"item":'):])['item']
                value=reply_for_prompt(observation(item),text)
                return io.BytesIO(json.dumps(dict(choices=[dict(message=dict(content=json.dumps(value)))],usage=dict(prompt_tokens=10,completion_tokens=10,total_tokens=20))).encode())
            with patch('mye_c_automation.site_client.ReadOnlySiteClient.__init__',side_effect=AssertionError('no live login')),patch('mye_c_automation.ai_judge.client._open_model_request',side_effect=model) as transport:
                code,result=self.invoke(source,cfg,root/'output')
            self.assertEqual(code,0,result);self.assertEqual(result['status'],'AUDITED')
            self.assertEqual(result['data_origin'],'SEALED_PRIOR_JOB')
            self.assertEqual(result['source_job_id'],source.name)
            self.assertNotEqual(result['job_id'],source.name)
            self.assertEqual((result['site_reads'],result['site_save_calls'],result['upload_calls']),(0,0,0))
            self.assertGreater(transport.call_count,0)
            target=Path(result['evidence_directory'])
            self.assertEqual(json.loads((target/'job.json').read_text())['mode'],'audit')
            self.assertFalse((target/'local_execution.json').exists())
            self.assertTrue((target/'budget.sqlite').exists())
            self.assertEqual(before,{str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()})

    def test_tampered_source_is_rejected_before_any_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,cfg=self.setup_source(root)
            inventory=json.loads((source/'full_inventory.json').read_text());image=Path(next(iter(inventory['contents'].values()))['file']);image.write_bytes(b'changed')
            with patch('mye_c_automation.ai_judge.client._open_model_request',side_effect=AssertionError('no model dispatch')):
                code,result=self.invoke(source,cfg,root/'output')
            self.assertEqual(code,2);self.assertEqual(result['status'],'ERROR')

    def test_wrong_product_cannot_reuse_archived_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,cfg=self.setup_source(root)
            with patch('mye_c_automation.ai_judge.client._open_model_request',side_effect=AssertionError('no model dispatch')):
                code,result=self.invoke(source,cfg,root/'output',pid=2)
            self.assertEqual(code,2);self.assertIn('SNAPSHOT_CONTEXT_MISMATCH',result['message'])

    def test_output_cannot_write_into_sealed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,cfg=self.setup_source(root)
            code,result=self.invoke(source,cfg,source/'new-data')
            self.assertEqual(code,2);self.assertIn('SNAPSHOT_OUTPUT_OVERLAP',result['message'])
