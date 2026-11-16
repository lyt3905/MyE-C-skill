from watermark_fixtures import exhaustive
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from mye_c_automation.ai_judge import JudgeClient
from mye_c_automation.budget_manager import BudgetManager
from mye_c_automation import automatic_report
import test_v13_account_cli


class ImageObservationTests(unittest.TestCase):
    def evidence(self):return {'id':'WM_MAIN_000','task_type':'watermark','sha256':'a'*64,'evidence_ids':['WM_MAIN_000'],'dimensions':[800,800]}
    def response(self,usage=True,valid=True):
        result={'task_type':'watermark','item_id':'WM_MAIN_000','classification':'manufacturer_branding',
                'owner':'factory','location':'box','confidence':.95,'abstain':False,'evidence_ids':['WM_MAIN_000']}
        result=exhaustive(result)
        response={'choices':[{'message':{'content':json.dumps(result) if valid else 'not JSON'}}]}
        if usage:response['usage']={'prompt_tokens':40,'completion_tokens':10,'total_tokens':50}
        return response

    def test_real_call_and_cache_observations_keep_provider_and_usage_distinct(self):
        with tempfile.TemporaryDirectory() as root:
            budget=BudgetManager({'ai_requests':4,'full_resolution_images':0})
            try:
                client=JudgeClient(budget,root,models=('glm','kimi'),transport=lambda *args:self.response())
                client.classify('watermark',self.evidence(),{})
                events=client.metrics['calls']
                self.assertEqual([(e['model'],e['usage_status'],e['total_tokens']) for e in events],
                                 [('glm','ACTUAL_REPORTED',50),('kimi','ACTUAL_REPORTED',50)])
                self.assertTrue(all(e['elapsed_ms']>=0 for e in events))
                client.classify('watermark',self.evidence(),{})
                self.assertEqual(client.metrics['requests'],2)
                self.assertEqual([(e['status'],e['usage_status'],e['total_tokens']) for e in client.metrics['calls'][2:]],
                                 [('CACHE_HIT','NOT_CALLED',None)]*2)
            finally:budget.close()

    def test_invalid_json_still_accounts_actual_usage_and_missing_usage_is_unknown(self):
        for usage,valid,want in [(True,False,'ACTUAL_REPORTED'),(False,True,'UNKNOWN')]:
            with self.subTest(usage=usage),tempfile.TemporaryDirectory() as root:
                budget=BudgetManager({'ai_requests':1,'full_resolution_images':0})
                try:
                    client=JudgeClient(budget,root,models=('glm',),transport=lambda *args:self.response(usage,valid),retries=0)
                    result=client.classify('watermark',self.evidence(),{})
                    event=client.metrics['calls'][0]
                    self.assertEqual(event['usage_status'],want)
                    self.assertEqual(event['total_tokens'],50 if usage else None)
                    if not valid:self.assertEqual(result['status'],'NEEDS_REVIEW')
                finally:budget.close()

    def test_budget_blocked_is_not_a_zero_token_provider_call(self):
        with tempfile.TemporaryDirectory() as root:
            budget=BudgetManager({'ai_requests':0,'full_resolution_images':0})
            try:
                client=JudgeClient(budget,root,models=('glm','kimi'),transport=lambda *args:self.fail('must not call'))
                client.classify('watermark',self.evidence(),{})
                event=client.metrics['calls'][0]
                self.assertEqual((event['usage_status'],event['called'],event['total_tokens']),('BUDGET_BLOCKED',False,None))
                self.assertEqual(client.metrics['models'],['glm','kimi'])
            finally:budget.close()

    def test_negative_provider_usage_is_unknown_in_both_events_and_aggregate(self):
        with tempfile.TemporaryDirectory() as root:
            budget=BudgetManager({'ai_requests':1,'full_resolution_images':0})
            try:
                response=self.response();response['usage']['total_tokens']=-1
                client=JudgeClient(budget,root,models=('glm',),transport=lambda *args:response)
                client.classify('watermark',self.evidence(),{})
                self.assertFalse(client.metrics['usage_available'])
                self.assertIsNone(client.metrics['total_tokens'])
                self.assertEqual(client.metrics['calls'][0]['usage_status'],'UNKNOWN')
                self.assertIsNone(client.metrics['calls'][0]['total_tokens'])
            finally:budget.close()

    def test_standard_cli_exports_each_image_with_independent_signals_and_no_description(self):
        with tempfile.TemporaryDirectory() as root:
            writer,path,_,error=test_v13_account_cli.AccountCliTests().execute(root)
            self.assertIsNone(error,repr(error))
            report=json.loads((path/'image_observations.json').read_text(encoding='utf-8'))
            self.assertEqual(report['image_count'],2)
            self.assertEqual({r['image_id'] for r in report['images']},{'MAIN_000','DETAIL_000'})
            main=next(r for r in report['images'] if r['pool']=='main')
            self.assertTrue(main['signals']['ocr']['hits'])
            self.assertIn('template',main['signals'])
            self.assertIn('residual',main['signals'])
            self.assertGreaterEqual(main['timing_ms']['download'],0)
            self.assertIn(main['processing_status']['cv'],{'EXECUTED','CACHE_HIT'})
            self.assertGreaterEqual(main['timing_ms']['ocr'],0)
            self.assertGreaterEqual(main['timing_ms']['residual'],0)
            self.assertGreaterEqual(main['timing_ms']['highpass'],0)
            self.assertIsNone(main['models']['actual_tokens'])
            self.assertNotIn('description',json.dumps(report).lower())
            self.assertEqual((writer.uploads,writer.saves),(1,1))

    def test_download_elapsed_is_measured_per_unique_url(self):
        from mye_c_automation.download_manager import download_unique
        with tempfile.TemporaryDirectory() as root:
            def download(url,path):Image.new('RGB',(20,20),'blue').save(path,format='PNG')
            with patch('mye_c_automation.download_manager.time.perf_counter',side_effect=[10.,10.5]):
                result=download_unique(['https://fake/a','https://fake/a'],root,downloader=download,workers=1)
            self.assertEqual(len(result),1)
            self.assertEqual(result['https://fake/a']['elapsed_ms'],500.)

    def test_export_names_all_uncalled_models_including_budget_blocked_and_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            files={'audit_raw.json':{'pid':1,'images':[{'kind':'main','index':0,'url':'https://fake/a'}]},
                   'ai_queue.json':{'items':[{'id':'WM_MAIN_000','task_type':'watermark','pool':'main','index':0,'source_url':'https://fake/a'}]}}
            for name,data in files.items():(root/name).write_text(json.dumps(data),encoding='utf-8')
            for event_status,usage_status in [('BUDGET_BLOCKED','BUDGET_BLOCKED'),('CACHE_HIT','NOT_CALLED')]:
                metrics={'models':['glm','kimi'],'calls':[{'item_id':'WM_MAIN_000','model':'glm','called':False,
                         'status':event_status,'usage_status':usage_status,'total_tokens':None,'elapsed_ms':1.}]}
                (root/'ai_metrics.json').write_text(json.dumps(metrics),encoding='utf-8')
                models=automatic_report.image_observations(root)['images'][0]['models']
                self.assertEqual(models['not_called_models'],['glm','kimi'])
                self.assertEqual(models['token_status'],usage_status)
            (root/'ai_metrics.json').write_text(json.dumps({'models':['glm','kimi'],'calls':[]}),encoding='utf-8')
            self.assertEqual(automatic_report.image_observations(root)['images'][0]['models']['token_status'],'NOT_CALLED')
