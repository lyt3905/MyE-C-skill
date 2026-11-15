"""Full-workflow regressions: production contracts, no external requests."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_v2_vision as vision
from test_v2_vision import observation


class CoordinationTests(unittest.TestCase):
    setUp = vision.VisionTests.setUp
    client = vision.VisionTests.client
    decide = vision.VisionTests.decide

    def test_deepseek_alone_reviews_keep(self):
        client, calls = self.client(lambda m, i: observation(i, confidence=.8))
        result = self.decide(client)
        self.assertEqual(result['decision'], 'KEEP')
        self.assertEqual([c[0] for c in calls], list(client.models))
        self.assertNotIn('primary_result', calls[0][1])
        self.assertEqual(len(calls),1)
        self.assertFalse(result['second_model_called'])

    def test_secondary_sku_suitability_is_not_requested(self):
        def reply(model, item):
            row = observation(item)
            if model == 'mimo-v2.6-pro':
                row['sku_suitability']['recommended_group'] = 'UNKNOWN'
            return row
        client, calls = self.client(reply)
        client.models=('deepseek-v4.1-flash','mimo-v2.6-pro')
        result=self.decide(client)
        self.assertEqual(result['decision'], 'KEEP')
        self.assertFalse(result['field_differences'])
        self.assertTrue(all(c[0]=='deepseek-v4.1-flash' for c in calls))

    def test_single_model_regions_preserved_without_synthetic_merge(self):
        def reply(model, item):
            offset = .01 if model == 'mimo-v2.6-pro' else 0
            return observation(item, 'REMOVE_TEXT',
                watermarks=[dict(kind='STORE_WATERMARK', bbox=[.02+offset,.8,.12+offset,.9], confidence=.8, preserve_overlap_risk='LOW')],
                preserve_regions=[dict(kind='toy_structure', bbox=[.2+offset,.2,.8,.7])])
        client, calls = self.client(reply)
        result = self.decide(client)
        self.assertEqual(result['decision'], 'REMOVE_TEXT')
        self.assertEqual(result['observation']['watermarks'][0]['bbox'], [.02,.8,.12,.9])
        self.assertEqual(result['observation']['preserve_regions'],[dict(kind='toy_structure',bbox=[.2,.2,.8,.7])])
        self.assertFalse(result['geometry_differences'])
        self.assertEqual(len(calls),1)

    def test_disabled_reviewer_cannot_change_removal_regions(self):
        def reply(model, item):
            box=[.02,.8,.12,.9] if model==client.models[0] else [.8,.02,.9,.12]
            return observation(item,'REMOVE_TEXT',watermarks=[dict(kind='STORE_WATERMARK',bbox=box,confidence=.9,preserve_overlap_risk='LOW')])
        client, _ = self.client(reply)
        result=self.decide(client)
        self.assertEqual(result['decision'], 'REMOVE_TEXT')
        self.assertEqual(result['observation']['watermarks'][0]['bbox'],[.02,.8,.12,.9])
        self.assertFalse(result['second_model_called'])

    def test_only_deepseek_ownership_is_recorded(self):
        def reply(model,item):
            return observation(item,watermarks=[dict(kind='PROMOTIONAL_TEXT',owner='MANUFACTURER' if model==client.models[0] else 'THIRD_PARTY_STORE',bbox=[.02,.8,.12,.9],confidence=.9,preserve_overlap_risk='LOW')])
        client, _ = self.client(reply)
        result=self.decide(client)
        self.assertEqual(result['decision'], 'KEEP')
        self.assertEqual(result['observation']['watermarks'][0]['owner'],'MANUFACTURER')
        self.assertEqual(len(result['results']),1)

    def test_factory_model_text_is_protected_and_sku_eligible(self):
        from sku_assignment import select_v2
        mark=dict(kind='PROMOTIONAL_TEXT',owner='MANUFACTURER',bbox=[.02,.8,.12,.9],confidence=.8,preserve_overlap_risk='LOW')
        client, _ = self.client(lambda m,i:observation(i,watermarks=[mark]))
        result=self.decide(client)
        self.assertEqual(result['decision'],'KEEP')
        records=[dict(sha256=str(n)*64,url='https://fake/'+str(n),image_id=str(n),observation=result['observation'],decision='KEEP',width=800,height=800) for n in (1,2)]
        product=dict(skus=[dict(skuId='real',skuName='Without Box',skuImageUrl='https://fake/1')])
        selection=select_v2(product,records)
        self.assertEqual(len(selection['selected_sku_images']),2)
        self.assertEqual(selection['assignments'],{'real':'https://fake/1'})

    def test_factory_promotion_cannot_be_removed(self):
        from ai_judge.image_action_decision import validate
        mark=dict(kind='PROMOTIONAL_TEXT',owner='MANUFACTURER',bbox=[.02,.8,.12,.9],confidence=.9,preserve_overlap_risk='LOW')
        with self.assertRaises(ValueError):
            validate(observation(self.item,'REMOVE_TEXT',watermarks=[mark]),self.item)

    def test_low_field_confidence_is_recorded_without_deferral(self):
        client, _ = self.client(lambda m,i:observation(i,field_confidences={'visual_class':.79,'product_identity':.9,'box_relation':.9,'watermark_ownership':.9,'sku_suitability':.9}))
        result=self.decide(client)
        self.assertEqual(result['decision'],'KEEP')
        self.assertFalse(result['reason_codes'])
        self.assertEqual(result['observation']['field_confidences']['visual_class'],.79)


class EntryTests(unittest.TestCase):
    def test_pre_audit_cli_defaults_to_v2_instead_of_ocr(self):
        import audit_one
        with patch('workflow_runner.main') as routed,patch('audit_one.audit',side_effect=AssertionError('legacy forbidden')):
            self.assertEqual(audit_one.main(['1','--shop','7','--site-config','fake-site.json']),0)
        self.assertIn('read_only',routed.call_args.args[0])

    def test_direct_full_audit_defaults_to_v2_and_record_only(self):
        from full_product_audit import run_full_audit
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as root:
            reader=Mock();reader.current_shop.return_value=7;reader.account_fingerprint.return_value='a'*64
            with patch('full_product_audit.run_unified_audit',return_value={'audit_complete':True}) as audited:
                run_full_audit(root,1,7,reader)
            job=audited.call_args.args[1]
            self.assertEqual(job['image_workflow'],'v2')
            self.assertEqual(job['model_budget']['mode'],'RECORD_ONLY')

    def test_readonly_cli_uses_the_same_unified_audit(self):
        from workflow_runner import main
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);site=root/'site.json';site.write_text('{}')
            argv=['workflow_runner','run','--pid','1','--shop','7','--mode','read_only','--root',str(root/'jobs'),'--site-config',str(site)]
            with patch('sys.argv',argv),patch('site_client.ReadOnlySiteClient') as reader,patch('full_product_audit.run_full_audit',return_value={'audit_complete':True}) as audited,patch('workflow_runner.run',side_effect=AssertionError('legacy forbidden')):
                main()
            self.assertEqual(audited.call_count,1)
            job=audited.call_args.kwargs['job']
            self.assertEqual(job['image_workflow'],'v2')
            self.assertEqual(job['mode'],'read_only')
            self.assertEqual(job['model_budget']['mode'],'RECORD_ONLY')

    def test_run_apply_uses_the_existing_authorized_automatic_executor(self):
        from workflow_runner import main
        from test_auto_decision import CONFIG
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);site=root/'site.json';site.write_text('{}')
            policy=root/'policy.json';policy.write_text(json.dumps(CONFIG))
            argv=['workflow_runner','run','--pid','1','--shop','7','--mode','apply','--root',str(root/'jobs'),'--site-config',str(site),'--automation-config',str(policy)]
            with patch('sys.argv',argv),patch('site_client._SiteTransport'),patch('executor.site_write_client.SiteWriteClient'),patch('workflow_runner.run_automatic',return_value={'status':'AUTO_VERIFIED'}) as execute,patch('workflow_runner.run',side_effect=AssertionError('legacy forbidden')):
                main()
            self.assertEqual(execute.call_count,1)
            self.assertEqual(execute.call_args.args[1]['image_workflow'],'v2')
            self.assertEqual(execute.call_args.args[1]['mode'],'auto_apply')


class RepairAndReadbackTests(unittest.TestCase):
    def scenario(self, root, actions, **kwargs):
        from test_v2_workflow import V2WorkflowTests
        return V2WorkflowTests.scenario(self, root, actions, **kwargs)

    def test_local_failure_falls_back_once_to_configured_image_editor(self):
        with tempfile.TemporaryDirectory() as root, patch('image_repairs_v2.remove_text',side_effect=RuntimeError('local inpaint failed')):
            s=self.scenario(root,['REMOVE_TEXT','KEEP'],edit_backend=True)
            self.assertEqual(s['writer'].uploads,1)
            self.assertEqual(s['writer'].saves,1)
            self.assertTrue(s['result']['content_validation']['ok'])
            quality=json.loads((s['root']/'v2_quality.json').read_text(encoding='utf-8'))['items']
            self.assertTrue(any(r.get('action')=='AI_REGENERATE' and r.get('ok') for r in quality))
            self.assertTrue(any(r.get('error_type')=='RuntimeError' for r in quality))

    def test_local_failure_without_editor_keeps_original(self):
        with tempfile.TemporaryDirectory() as root, patch('image_repairs_v2.remove_text',side_effect=RuntimeError('local inpaint failed')):
            s=self.scenario(root,['REMOVE_TEXT','KEEP'])
            self.assertEqual(s['writer'].uploads,0)
            self.assertEqual(s['product']['images']['main'],s['original']['images']['main'])

    def test_editor_failure_never_uploads(self):
        with tempfile.TemporaryDirectory() as root, patch('ai_judge.client.JudgeClient.invoke_image_adapter',side_effect=TimeoutError('fake edit timeout')):
            s=self.scenario(root,['AI_REGENERATE','KEEP'],edit_backend=True)
            self.assertEqual(s['writer'].uploads,0)

    def test_editor_missing_usage_is_recorded_null_and_does_not_block(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['AI_REGENERATE','KEEP'],edit_backend='unknown_usage')
            self.assertEqual(s['writer'].uploads,1)
            self.assertEqual(s['writer'].saves,1)
            report=json.loads((s['root']/'report_data.json').read_text(encoding='utf-8'))
            self.assertIsNone(report['ai']['actual_tokens'])
            self.assertEqual(report['ai']['by_model']['deepseek-v4.1-flash']['unknown_usage_calls'],1)

    def test_faint_watermark_still_runs_the_full_repair_chain(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['REMOVE_TEXT','KEEP'],watermark_color=(245,245,245))
            self.assertEqual(s['writer'].uploads,1)
            self.assertTrue(s['result']['content_validation']['ok'])

    def test_failed_lama_backend_preserves_original(self):
        def complex_image(item,action='KEEP',**changes):
            return observation(item,action,background_complexity='COMPLEX',**changes)
        with tempfile.TemporaryDirectory() as root,patch('test_v2_workflow.observation',side_effect=complex_image),patch('image_repairs_v2.lama_torchscript',side_effect=RuntimeError('fake LaMa load failure')):
            s=self.scenario(root,['REMOVE_TEXT','KEEP'],image_options={'lama_model_path':str(Path(root)/'fake-lama.pt')})
            self.assertEqual(s['writer'].uploads,0)
            self.assertEqual(s['product']['images']['main'],s['original']['images']['main'])

    def test_failed_upload_never_saves(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['REMOVE_TEXT','KEEP'],upload_fail=True)
            self.assertEqual(s['writer'].uploads,1)
            self.assertEqual(s['writer'].saves,0)
            self.assertEqual(s['product'],s['original'])

    def test_save_applied_but_timed_out_recovers_by_reading_without_resend(self):
        from workflow_runner import resume_verification
        from execution_ledger import ExecutionLedger
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['REMOVE_TEXT','KEEP'],save_timeout='after')
            self.assertEqual(s['result']['status'],'APPLY_UNKNOWN')
            recovery=json.loads((s['root']/'recovery_readback.json').read_text(encoding='utf-8'))
            self.assertEqual(recovery['write_outcome'],'MATCHED')
            with patch('execution_ledger.ExecutionLedger',side_effect=lambda:ExecutionLedger(Path(root)/'fake-ledger.sqlite')):
                checked=resume_verification(s['manager'],s['root'].name,s['writer'])
            self.assertTrue(checked['content_validation']['ok'])
            self.assertEqual(s['writer'].saves,1)

    def test_explicit_review_preserves_original_but_low_score_allows_repair(self):
        for mode in ('review','low_confidence'):
            def reply(item,action='KEEP',**changes):
                if mode=='low_confidence':changes['confidence']=.79
                else:action='REVIEW'
                return observation(item,action,**changes)
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as root,patch('test_v2_workflow.observation',side_effect=reply):
                s=self.scenario(root,['REMOVE_TEXT','KEEP'])
                if mode=='review':
                    self.assertEqual(s['writer'].uploads,0)
                    self.assertEqual(s['writer'].saves,0)
                    self.assertEqual(s['product'],s['original'])
                else:
                    self.assertEqual(s['writer'].uploads,1)
                    self.assertEqual(s['writer'].saves,1)
                    self.assertTrue(s['result']['content_validation']['ok'])
                    observations=json.loads((s['root']/'full_ai_judgements.json').read_text())
                    self.assertTrue(all(row['observation']['confidence']==.79 for row in observations.values()))

    def test_sku_url_unchanged_but_image_bytes_changed_fails_readback(self):
        from v2_remediation import verify_content
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['KEEP','KEEP'])
            plan=json.loads((s['root']/'plan.v2.json').read_text(encoding='utf-8'))
            with patch.object(s['writer'],'fetch_image',return_value=b'changed bytes at same URL'):
                result=verify_content(s['root'],plan,s['writer'])
            self.assertFalse(result['ok'])
            self.assertTrue(result['image_readback'])

    def test_all_kept_pools_are_checked_by_bytes(self):
        from v2_remediation import verify_content
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['REMOVE_TEXT','KEEP'])
            plan=json.loads((s['root']/'plan.v2.json').read_text(encoding='utf-8'))
            checked=verify_content(s['root'],plan,s['writer'])
            self.assertTrue(checked['ok'])
            self.assertEqual({row['pool'] for row in checked['image_readback']},{'main','detail','sku','sku_reference'})
            self.assertTrue(all(row['expected_sha256']==row['observed_sha256'] for row in checked['image_readback']))

    def test_report_counts_unique_actions_and_pool_references(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['REMOVE_TEXT','KEEP'])
            report=json.loads((s['root']/'report_data.json').read_text(encoding='utf-8'))
            flow=report['v2_workflow']
            self.assertEqual(flow['unique_images'],2)
            self.assertEqual(flow['audit_actions'],{'REMOVE_TEXT':1,'KEEP':1})
            self.assertEqual(flow['pools'],{'main':2,'detail':2,'sku':1})
            self.assertEqual(flow['sku_references'],1)
            self.assertGreater(flow['duplicate_references'],0)
            self.assertTrue(flow['readback']['description_exact'])

    def test_confirmed_apply_performs_v2_byte_verification(self):
        from workflow_runner import local_apply
        from plan_v2 import plan_hash
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['REMOVE_TEXT','KEEP'],mode='dry_run')
            plan=json.loads((s['root']/'plan.v2.json').read_text(encoding='utf-8'))
            confirmation=dict(confirmed=True,job_id=plan['job_id'],pid=plan['pid'],shop=plan['shop'],plan_sha256=plan_hash(plan))
            result=local_apply(s['manager'],plan['job_id'],s['writer'],confirmation)
            self.assertEqual(s['writer'].saves,1)
            self.assertTrue(result['content_validation']['ok'])
            self.assertTrue(result['content_validation']['protected_fields_exact'])

    def test_full_cli_from_shop_pid_to_save_and_independent_readback(self):
        import io
        from contextlib import redirect_stdout
        from ai_judge.client import JudgeClient
        from execution_ledger import ExecutionLedger
        from workflow_runner import main
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);seed=self.scenario(root/'seed',['REMOVE_TEXT','KEEP'],mode='audit')
            site=root/'site.json';site.write_text('{}')
            policy=root/'policy.json';policy.write_text(json.dumps(seed['policy'].config))
            options=root/'options.json';options.write_text(json.dumps({'rights':'OWNED_OR_LICENSED'}))
            cli_root=root/'cli-jobs'
            argv=['workflow_runner','run','--shop','7','--pid','1','--mode','auto_apply','--root',str(cli_root),'--site-config',str(site),'--automation-config',str(policy),'--image-options',str(options)]
            def client(budget,cache,**kwargs):
                kwargs.pop('retries',None)
                return JudgeClient(budget,cache,transport=seed['transport'],retries=0,**kwargs)
            with patch('sys.argv',argv),patch('site_client._SiteTransport'),patch('executor.site_write_client.SiteWriteClient',return_value=seed['writer']),patch.object(type(seed['writer']),'readonly_client',return_value=seed['writer'],create=True),patch('ai_judge.JudgeClient',side_effect=client),patch('full_product_audit.download_only',side_effect=seed['auditor']),patch('execution_ledger.ExecutionLedger',side_effect=lambda:ExecutionLedger(root/'ledger.sqlite')),patch('audit_one.audit',side_effect=AssertionError('legacy forbidden')),redirect_stdout(io.StringIO()):
                main()
            jobs=[p for p in cli_root.iterdir() if p.is_dir() and p.name.startswith('JOB_')]
            self.assertEqual(len(jobs),1)
            report=json.loads((jobs[0]/'report_data.json').read_text(encoding='utf-8'))
            self.assertEqual(seed['writer'].saves,1)
            self.assertEqual(seed['writer'].uploads,1)
            self.assertTrue(report['v2_workflow']['readback']['ok'])
            self.assertEqual(report['v2_workflow']['unique_images'],2)
            self.assertEqual(report['ai']['by_model']['deepseek-v4.1-flash']['requests'],3)
