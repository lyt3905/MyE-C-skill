import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from mye_c_automation import automatic_report
from mye_c_automation.ai_judge import JudgeClient
from mye_c_automation.budget_manager import BudgetManager
import test_v13_image_observations as responses


class RecoveryMetricsTests(unittest.TestCase):
    def baseline(self, root):
        (root/'ai_metrics.json').write_text(json.dumps({
            'requests':0,'cache_hits':0,'total_tokens':0,'usage_available':True,'calls':[]}),encoding='utf-8')

    def emit(self, root, judge, phase, run):
        return automatic_report.write(root,{'pid':1,'shop_id':7,'job_id':'JOB_FAKE'},
            'CONTENT_REVIEW_REQUIRED',{'run_id':run,'total_elapsed_ms':10},
            inspector=SimpleNamespace(judge=judge,metrics_phase=phase))

    def client(self, root, budget, transport):
        return JudgeClient(budget,root/'cache',models=('glm','kimi'),transport=transport,retries=0)

    def test_recovery_cache_retains_previous_usage_and_report_refresh_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.baseline(root)
            budget=BudgetManager({'ai_requests':4,'full_resolution_images':0,'total_tokens':100000},root/'budget.sqlite')
            try:
                sample=responses.ImageObservationTests();calls=[]
                def transport(*args):calls.append(args[0]);return sample.response()
                first=self.client(root,budget,transport)
                first.classify('watermark',sample.evidence(),{})
                self.emit(root,first,'initial','run1')
                recovered=self.client(root,budget,lambda *args:self.fail('recovery must use cache'))
                recovered.classify('watermark',sample.evidence(),{})
                self.emit(root,recovered,'recovery','run2')
                result=self.emit(root,recovered,'recovery','run2')
                self.assertEqual(calls,['glm','kimi'])
                self.assertEqual(result['ai']['reported_requests'],2)
                self.assertEqual(result['ai']['actual_tokens'],100)
                self.assertEqual(result['ai']['cache_hits'],2)
                self.assertEqual(result['ai']['metrics_completeness'],'VERIFIED')
                self.assertEqual(result['timing_ms']['total_ms'],20)
                phases=json.loads((root/'quality_metrics.json').read_text(encoding='utf-8'))['phases']
                self.assertEqual(len(phases),2)
                self.assertEqual([e['usage_status'] for e in phases['recovery']['calls']],['NOT_CALLED']*2)
            finally:budget.close()

    def test_missing_precrash_metrics_cannot_be_reported_as_actual_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.baseline(root)
            budget=BudgetManager({'ai_requests':4,'full_resolution_images':0,'total_tokens':100000},root/'budget.sqlite')
            try:
                sample=responses.ImageObservationTests();first=self.client(root,budget,lambda *args:sample.response())
                first.classify('watermark',sample.evidence(),{})
                # The process died after a charged response/cache write, before reporting.
                recovered=self.client(root,budget,lambda *args:self.fail('cache expected'))
                recovered.classify('watermark',sample.evidence(),{})
                result=self.emit(root,recovered,'recovery','run2')
                self.assertEqual(result['ai']['admitted_requests'],2)
                self.assertEqual(result['ai']['reported_requests'],0)
                self.assertIsNone(result['ai']['actual_tokens'])
                self.assertEqual(result['ai']['token_status'],'UNKNOWN')
                self.assertEqual(result['ai']['metrics_completeness'],'INCOMPLETE')
                self.assertIn('MODEL_METRICS_INCOMPLETE',result['unverified_items'])
            finally:budget.close()

    def test_second_transport_phase_adds_usage_and_prior_unknown_stays_unknown(self):
        for known in (True,False):
            with self.subTest(first_usage_known=known),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);self.baseline(root)
                budget=BudgetManager({'ai_requests':4,'full_resolution_images':0},root/'budget.sqlite')
                try:
                    sample=responses.ImageObservationTests()
                    first=self.client(root,budget,lambda *args:sample.response(usage=known))
                    first.classify('watermark',sample.evidence(),{})
                    self.emit(root,first,'initial','run1')
                    second=self.client(root,budget,lambda *args:sample.response())
                    second.classify('watermark',sample.evidence(),{'title':'Changed verification context'})
                    result=self.emit(root,second,'recovery','run2')
                    self.assertEqual(result['ai']['reported_requests'],4)
                    self.assertEqual(result['ai']['metrics_completeness'],'VERIFIED')
                    self.assertEqual(result['ai']['actual_tokens'],200 if known else None)
                    self.assertEqual(result['ai']['token_status'],'ACTUAL_REPORTED' if known else 'UNKNOWN')
                finally:budget.close()
