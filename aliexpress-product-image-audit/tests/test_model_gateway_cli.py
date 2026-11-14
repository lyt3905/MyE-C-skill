from watermark_fixtures import exhaustive
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from ai_judge import JudgeClient
from budget_manager import BudgetManager
from job_manager import JobManager, atomic_json
import test_v13_account_cli

PROFILE={'schema':'model-gateway/v1','base_url':'http://127.0.0.1:3425/v1',
         'models':['workbuddy/deepseek-v4.1-flash','workbuddy/kimi-k3-1'],
         'max_output_tokens':4096,'retries':0,'timeout':90}


def response(item,classification='product_print'):
    return {'choices':[{'message':{'content':json.dumps(exhaustive({'task_type':'watermark','item_id':item['id'],
        'classification':classification,'owner':'factory','location':'center','confidence':.99,
        'abstain':False,'evidence_ids':item['evidence_ids']}))}}],
        'usage':{'prompt_tokens':2,'completion_tokens':2,'total_tokens':4}}


class ModelGatewayCliTests(unittest.TestCase):
    def test_profile_controls_wire_both_models_and_output_over_environment(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ,
                {'VLM_API_KEY':'fake-key','VLM_BASE':'http://wrong','VLM_MAX_OUTPUT_TOKENS':'99'}):
            budget=BudgetManager({'ai_requests':2,'total_tokens':20000})
            try:
                client=JudgeClient(budget,root,config=PROFILE)
                requests=[]
                def send(req,timeout):
                    requests.append((req.full_url,json.loads(req.data),timeout))
                    return io.BytesIO(json.dumps(response({'id':'A','evidence_ids':['A'],'dimensions':[800,800]})).encode())
                with patch('urllib.request.urlopen',side_effect=send):
                    result=client.classify('watermark',{'id':'A','task_type':'watermark','evidence_ids':['A'],'dimensions':[800,800]},{})
                self.assertEqual(result['status'],'CLEAN',result)
                self.assertEqual([r[1]['model'] for r in requests],PROFILE['models'])
                self.assertTrue(all(r[0]==PROFILE['base_url']+'/chat/completions' and r[1]['max_tokens']==4096 and r[2]==90 for r in requests))
                self.assertEqual(budget.snapshot()['actual_tokens'],8)
            finally:budget.close()

    def test_profile_separates_provider_caches(self):
        with tempfile.TemporaryDirectory() as root:
            calls=[]
            def send(model,item,context):calls.append(model);return response(item)
            for base in ('http://127.0.0.1:3425/v1','http://localhost:3425/v1'):
                budget=BudgetManager({'ai_requests':2})
                try:
                    client=JudgeClient(budget,root,config=dict(PROFILE,base_url=base),transport=send)
                    self.assertEqual(client.classify('watermark',{'id':'A','evidence_ids':['A'],'dimensions':[800,800]},{})['status'],'CLEAN')
                finally:budget.close()
            self.assertEqual(len(calls),4)

    def test_job_binds_profile_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as root:
            manager=JobManager(root);original=copy.deepcopy(PROFILE)
            job=manager.create(1,7,{},model_config=original);original['models'][0]='other'
            self.assertEqual(job['model_config'],PROFILE)
            manager.bind_input(job['job_id'],{'id':1});manager.bind_account(job['job_id'],'a'*64)
            self.assertEqual(manager.load(job['job_id'])['model_config'],PROFILE)
            changed=manager.load(job['job_id']);changed['model_config']['max_output_tokens']=8192
            atomic_json(manager.directory(job['job_id'])/'job.json',changed)
            with self.assertRaises(ValueError):manager.load(job['job_id'])

    def test_quality_stage_uses_frozen_profile(self):
        from visual_quality import VisualQualityInspector
        with tempfile.TemporaryDirectory() as root:
            with patch('ai_judge.JudgeClient') as constructor:
                inspector=VisualQualityInspector(root,{'budget':{'ai_requests':2},'model_config':PROFILE})
                try:self.assertEqual(constructor.call_args.kwargs['config'],PROFILE)
                finally:inspector.close()

    def test_invalid_profile_is_rejected_before_site_login(self):
        import workflow_runner
        with tempfile.TemporaryDirectory() as root:
            profile=Path(root)/'models.json';atomic_json(profile,dict(PROFILE,api_key='do-not-log'))
            argv=['workflow_runner.py','run','--pending','1','--shop','7','--mode','dry_run',
                  '--site-config','does-not-exist.json','--model-config',str(profile),'--root',str(Path(root)/'jobs')]
            with patch('sys.argv',argv),patch('site_client.ReadOnlySiteClient') as site:
                with self.assertRaisesRegex(ValueError,'INVALID_MODEL_CONFIG:fields') as caught:workflow_runner.main()
                site.assert_not_called()
                self.assertNotIn('do-not-log',str(caught.exception))

    def test_cli_profile_preserves_fake_execution_and_main_stage_binding(self):
        class Queue:
            metrics={'requests':0,'usage_available':False}
            def process_queue(self,queue,context):
                from workflow_v2_pipeline import JudgeClient as constructor
                if constructor.call_args.kwargs.get('config')!=PROFILE:raise AssertionError('profile not sent to main judge')
                return {}
        with tempfile.TemporaryDirectory() as root:
            profile=Path(root)/'models.json';atomic_json(profile,PROFILE)
            writer,directory,_,error=test_v13_account_cli.AccountCliTests().execute(root,case='lowres',model_profile=profile,queue_judge=Queue())
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.saves,writer.uploads),(1,0))
            self.assertEqual(json.loads((directory/'job.json').read_text())['model_config'],PROFILE)
            self.assertEqual(json.loads((directory/'state.json').read_text())['state'],'AUTO_VERIFIED')

    def test_cli_provider_failure_and_model_conflict_never_write(self):
        for failure in ('http','conflict'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as root:
                profile=Path(root)/'models.json';atomic_json(profile,PROFILE)
                budget=BudgetManager({'ai_requests':4,'total_tokens':50000,'full_resolution_images':4})
                def send(model,item,context):
                    if failure=='http':raise urllib.error.HTTPError('http://local',502,'error',{},io.BytesIO(b'{}'))
                    return response(item,'third_party_store_banner' if model==PROFILE['models'][0] else 'product_print')
                try:
                    queue=JudgeClient(budget,Path(root)/'judge',config=PROFILE,transport=send)
                    writer,directory,_,error=test_v13_account_cli.AccountCliTests().execute(root,model_profile=profile,queue_judge=queue)
                    self.assertIsNone(error,repr(error))
                    self.assertEqual((writer.saves,writer.uploads),(0,0))
                    self.assertEqual(json.loads((directory/'state.json').read_text())['state'],'DEFERRED')
                finally:budget.close()

    def test_cli_profile_keeps_packaging_protection(self):
        with tempfile.TemporaryDirectory() as root:
            profile=Path(root)/'models.json';atomic_json(profile,PROFILE)
            writer,directory,_,error=test_v13_account_cli.AccountCliTests().execute(root,case='cleanup_box',model_profile=profile)
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.saves,writer.uploads),(0,0))


if __name__=='__main__':unittest.main()
