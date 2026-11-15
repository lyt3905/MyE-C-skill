import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock
from job_manager import JobManager, atomic_json
from full_product_audit import run_full_audit
import test_full_product_audit as fixtures
from automation_policy import AutomationPolicy
from test_auto_decision import CONFIG
from test_auto_remedy import Inspector
from candidate_quality import CandidateQualityGate

class FullAuditRemediationBridgeTests(unittest.TestCase):
    def fixture(self,root,unknown=False):
        helper=fixtures.FullProductAuditTests(); product,raw=helper.fixture(root)
        # Stable SKU IDs are independent of the audit row labels.
        product['skus'][0]['id']=101;product['skus'][1]['id']=102
        raw=[dict(next(r for r in raw if r['url']==url),kind=pool,index=index) for pool in ('main','detail','sku') for index,url in enumerate(product['images'][pool])]
        from full_product_audit import build_inventory
        results=helper.decisions(build_inventory(product,raw))
        if unknown:results.pop(next(iter(results)))
        class Reader:
            def current_shop(self):return 7
            def account_fingerprint(self):return 'a'*64
            def product(self,pid):return deepcopy(product)
        def auditor(pid,shop,output_dir,site):
            atomic_json(output_dir/'audit_product.json',product)
            atomic_json(output_dir/'audit_raw.json',{'pid':pid,'images':raw})
            atomic_json(output_dir/'audit_flags.json',{'pid':pid,'summary':{'ocr_enabled':True},'duplicates':[],'anomalies':[]})
        class Judge:
            models=('a','b');metrics={'requests':0,'total_tokens':0,'usage_available':True,'calls':[]}
            calls=0
            def process_queue(self,queue,context):self.calls+=1;return self.results
        Judge.results=results
        template=Path(root)/'templates.json';atomic_json(template,{'required_shop_ids':[],'no_applicable_shop_ids':[7],'templates':[]})
        return product,raw,Reader(),auditor,Judge(),template
    def complete(self,root,unknown=False):
        product,raw,reader,auditor,judge,template=self.fixture(root,unknown)
        result=run_full_audit(Path(root)/'jobs',1,7,reader,judge=judge,auditor=auditor,template_config=template)
        manager=JobManager(Path(root)/'jobs');job=manager.load(result['job_id']);directory=manager.directory(job['job_id'])
        return directory,job,judge
    def test_all_business_positions_project_without_second_audit(self):
        from full_product_audit import remediation_inputs
        with tempfile.TemporaryDirectory() as root:
            d,job,judge=self.complete(root);items,results,deferred=remediation_inputs(d,job)
            self.assertEqual(len(items),7);self.assertEqual(judge.calls,1)
            self.assertEqual(len({r['id'] for r in items}),7)
            self.assertEqual({r['sku_id'] for r in items if r['task_type']=='sku_match'},{'101','102'})
            self.assertTrue(all(r.get('full_source_task_id') for r in items))
    def test_unknown_survives_plan_compilation(self):
        from full_product_audit import remediation_inputs
        from auto_workflow import prepare
        with tempfile.TemporaryDirectory() as root:
            d,job,judge=self.complete(root,True);items,results,deferred=remediation_inputs(d,job)
            self.assertTrue(deferred)
            result=prepare(d,job,AutomationPolicy(CONFIG),CandidateQualityGate(Inspector()))
            self.assertNotEqual(result['status'],'CLEAN');self.assertGreater(result.get('deferred_count',0),0)
            self.assertEqual(judge.calls,1)
    def test_modified_report_or_source_is_rejected(self):
        from full_product_audit import remediation_inputs
        for name in ('full_audit_report.json','full_ai_judgements.json','audit_product.json'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as root:
                d,job,_=self.complete(root);(d/name).write_text('{}')
                with self.assertRaises(ValueError):remediation_inputs(d,job)
    def test_different_job_or_shop_rejected(self):
        from full_product_audit import remediation_inputs
        with tempfile.TemporaryDirectory() as root:
            d,job,_=self.complete(root)
            for field,value in [('job_id','JOB_other'),('shop_id',8),('input_state_sha256','0'*64)]:
                with self.subTest(field=field),self.assertRaises(ValueError):remediation_inputs(d,dict(job,**{field:value}))
    def test_same_job_full_audit_default_automatic_does_not_use_narrow_pipeline(self):
        from workflow_runner import run_automatic
        with tempfile.TemporaryDirectory() as root:
            product,raw,reader,auditor,judge,template=self.fixture(root,True)
            manager=JobManager(Path(root)/'jobs');job=manager.create(1,7,{'ai_requests':40,'full_resolution_images':32,'total_tokens':500000},mode='audit',templates_required=True)
            from template_applicability import snapshot
            snapshot(template,manager.directory(job['job_id']))
            result=run_automatic(manager,job,AutomationPolicy(CONFIG),writer=reader,auditor=auditor,judge=judge,
                quality_gate=CandidateQualityGate(Inspector()),full_audit_reader=reader)
            self.assertEqual(judge.calls,1);self.assertEqual(result['status'],'DEFERRED')
            self.assertTrue((manager.directory(job['job_id'])/'full_audit_report.json').is_file())

    def test_changed_prompt_or_image_bytes_cannot_reuse_full_audit(self):
        from full_product_audit import remediation_inputs
        from unittest.mock import patch
        import ai_judge.watermark as watermark
        with tempfile.TemporaryDirectory() as root:
            d,job,_=self.complete(root)
            with patch.object(watermark,'PROMPT',watermark.PROMPT+' changed'):
                with self.assertRaises(ValueError):remediation_inputs(d,job)
            raw=json.loads((d/'audit_raw.json').read_text())
            Path(raw['images'][0]['file']).write_bytes(b'changed image')
            with self.assertRaises(ValueError):remediation_inputs(d,job)

    def test_completed_full_job_is_returned_without_second_model_queue(self):
        from workflow_runner import run_automatic
        with tempfile.TemporaryDirectory() as root:
            product,raw,reader,auditor,judge,template=self.fixture(root,True)
            manager=JobManager(Path(root)/'jobs');job=manager.create(1,7,{'ai_requests':40,'full_resolution_images':32,'total_tokens':500000},mode='audit')
            options=dict(writer=reader,auditor=auditor,judge=judge,quality_gate=CandidateQualityGate(Inspector()),full_audit_reader=reader)
            first=run_automatic(manager,job,AutomationPolicy(CONFIG),**options)
            job=manager.load(job['job_id'])
            second=run_automatic(manager,job,AutomationPolicy(CONFIG),**options)
            self.assertEqual(first['status'],second['status']);self.assertEqual(judge.calls,1)

    def test_actual_default_full_stage_uses_reader_and_keeps_unknown(self):
        from workflow_runner import run_automatic
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as root:
            product,raw,reader,auditor,judge,template=self.fixture(root,True)
            reader.readonly_client=lambda:reader
            manager=JobManager(Path(root)/'jobs');job=manager.create(1,7,{'ai_requests':40,'full_resolution_images':32,'total_tokens':500000},mode='audit')
            with patch('audit_one.audit',auditor):
                result=run_automatic(manager,job,AutomationPolicy(CONFIG),writer=reader,judge=judge,quality_gate=CandidateQualityGate(Inspector()))
            self.assertEqual(result['status'],'DEFERRED');self.assertEqual(judge.calls,1)
            self.assertTrue((manager.directory(job['job_id'])/'full_audit_report.json').exists())

    def test_missing_full_authority_cannot_fall_back_to_narrow_queue(self):
        from auto_workflow import prepare
        with tempfile.TemporaryDirectory() as root:
            d,job,_=self.complete(root)
            (d/'full_audit_report.json').unlink();(d/'full_audit_evidence_manifest.json').unlink()
            atomic_json(d/'ai_queue.json',{'items':[]});atomic_json(d/'ai_judgements.json',{})
            with self.assertRaises((ValueError,OSError)):prepare(d,job,AutomationPolicy(CONFIG),CandidateQualityGate(Inspector()))

    def test_confirmed_full_audit_reaches_fake_save_and_byte_readback_once(self):
        from workflow_runner import run_automatic
        from unittest.mock import patch
        from execution_ledger import ExecutionLedger
        import hashlib
        with tempfile.TemporaryDirectory() as root:
            product,raw,reader,auditor,judge,template=self.fixture(root)
            key=next(k for k in judge.results if k.startswith('WM_'))
            for row in judge.results[key]['results']:
                row.update(classification='third_party_store_banner',owner='Known Toy Store')
                row['marks'][0].update(classification='third_party_store_banner',owner='Known Toy Store')
            judge.results[key]['status']='HIT'
            reader.readonly_client=lambda:reader
            reader.saves=0
            def save(pid,desired,**kwargs):
                reader.saves+=1;product.clear();product.update(deepcopy(desired))
            reader.save=save
            blobs={r['url']:Path(r['file']).read_bytes() for r in raw}
            reader.fetch_image=lambda url:blobs[url]
            manager=JobManager(Path(root)/'jobs');job=manager.create(1,7,{'ai_requests':40,'full_resolution_images':32,'total_tokens':500000},mode='auto_apply')
            from template_applicability import snapshot
            snapshot(template,manager.directory(job['job_id']))
            with patch('audit_one.audit',auditor),patch('execution_ledger.ExecutionLedger',side_effect=lambda:ExecutionLedger(Path(root)/'execution.sqlite')):
                result=run_automatic(manager,job,AutomationPolicy(CONFIG),writer=reader,judge=judge,quality_gate=CandidateQualityGate(Inspector()))
            self.assertEqual(reader.saves,1,result)
            self.assertIn(result['status'],{'AUTO_VERIFIED','PARTIALLY_AUTO_FIXED'})
            self.assertEqual(judge.calls,1)
            self.assertEqual(product['images']['main'][0],'https://x/b')
            self.assertEqual(product['descriptionJson'],'opaque https://forbidden/description')
            plan=json.loads((manager.directory(job['job_id'])/'plan.v2.json').read_text())
            self.assertIn('full_audit_evidence_manifest.json',{r['path'] for r in plan['evidence_refs']})

    def test_confirmed_identity_mismatch_never_disappears_as_clean(self):
        from auto_workflow import prepare
        with tempfile.TemporaryDirectory() as root:
            product,raw,reader,auditor,judge,template=self.fixture(root)
            product['skus']=[];product['images']['sku']=[]
            key=next(k for k in judge.results if k.startswith('IDENTITY_'))
            for row in judge.results[key]['results']:
                row['decision']='MISMATCH';row['model']='OTHER-01'
                row['observations']['model_identity'].update(value='OTHER-01',decision='MISMATCH')
            report=run_full_audit(Path(root)/'jobs',1,7,reader,judge=judge,auditor=auditor,template_config=template)
            self.assertEqual(report['compliance_status'],'NON_COMPLIANT')
            manager=JobManager(Path(root)/'jobs');job=manager.load(report['job_id']);d=manager.directory(job['job_id'])
            result=prepare(d,job,AutomationPolicy(CONFIG),CandidateQualityGate(Inspector()))
            self.assertEqual(result['status'],'DEFERRED',result)
            self.assertGreater(result['deferred_count'],0)

    def test_direct_compiler_cannot_omit_full_audit_unresolved_items(self):
        from plan_compiler import compile_auto_plan
        with tempfile.TemporaryDirectory() as root:
            d,job,_=self.complete(root,True)
            result=compile_auto_plan(d,job,[],AutomationPolicy(CONFIG))
            self.assertEqual(result['status'],'DEFERRED',result)
            self.assertGreater(result['deferred_count'],0)
