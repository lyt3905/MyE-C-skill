from current_source_fixtures import freeze_current_source
"""Observed mode defers token verification, never schema/evidence verification."""
import json
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import observed_audit as oa
import run_8788_real_validation as rv
from test_8788_real_validation import response


class ObservedAuditTests(unittest.TestCase):
    def setUp(self):freeze_current_source(self)

    def prepare(self, directory):
        return oa.prepare(Path(directory), user_statement='先不管预算，先把程序跑通',
                          authorize_real=False)

    def test_default_cli_is_offline(self):
        self.assertFalse(oa.parser().parse_args([]).execute_observed_models)

    def test_low_reasoning_generation_is_in_plan_and_real_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = self.prepare(tmp)
            options = rv.read(job/'generation-options.json')
            self.assertEqual(options, dict(reasoning_effort='low', max_output_tokens=16384))
            inputs = rv.read(job/'inputs.json'); model = rv.read(job/'model-profile.json')['models'][0]
            body, _ = oa.body_for(model, inputs['tasks'][0], inputs['context'], options)
            self.assertEqual(body['max_tokens'], 16384)
            self.assertEqual(body['reasoning_effort'], 'low')
            self.assertEqual(rv.canonical(body), rv.read(job/'request-plan.json')[0]['body_sha256'])

    def test_legacy_http_cannot_bypass_budget_with_prepared_generation_options(self):
        captured=[]
        def send(request, timeout):
            captured.append(json.loads(request.data)); return io.BytesIO(b'{"ok":true}')
        config=rv.load_config(rv.DEFAULT_CONFIG)
        prepared=dict(model=config['models'][0],messages=[],max_tokens=16384,reasoning_effort='low')
        with patch.dict('os.environ',{'VLM_API_KEY':'FAKE_TEST_ONLY'}), \
                patch('urllib.request.build_opener',return_value=SimpleNamespace(open=send)):
            with self.assertRaisesRegex(rv.Blocked,'LEGACY_MODEL_ENTRY_DISABLED'):
                rv._http_transport(config,config['models'][0],{}, {},body=prepared)
        self.assertEqual(captured,[])

    def test_empty_output_length_is_diagnosed_and_not_used_as_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = self.prepare(tmp)
            def fake(model,item,context):
                raw=response(item,model); raw['choices'][0]['message']['content']=''
                raw['choices'][0]['finish_reason']='length'
                return raw
            result=oa.run(job,transport=fake,fake=True)
            self.assertEqual(result['stop_reason'], 'OUTPUT_LIMIT_EXHAUSTED')
            self.assertEqual(result['normalized_response_count'], 0)

    def test_24_fake_calls_complete_with_no_budget_guarantee(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = self.prepare(tmp); calls = []
            def fake(model, item, context):
                calls.append((model, item['id'])); return response(item, model)
            report = oa.run(job, transport=fake, fake=True)
            self.assertEqual(len(calls), 24)
            self.assertEqual(len(set(calls)), 24)
            self.assertEqual(report['state'], 'FAKE_PIPELINE_COMPLETED')
            self.assertEqual(len(report['occurrences']), 16)
            self.assertFalse(report['HARD_CAP_GUARANTEED'])
            self.assertEqual(report['actual_provider_requests'], 0)
            self.assertEqual(report['usage']['gateway_reported_known_tokens'], 2400)
            self.assertIsNone(report['usage']['verified_actual_tokens'])

    def test_missing_usage_does_not_stop_audit_or_become_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = self.prepare(tmp)
            def fake(model, item, context):
                raw = response(item, model); raw.pop('usage'); return raw
            report = oa.run(job, transport=fake, fake=True)
            self.assertEqual(report['request_count'], 24)
            self.assertEqual(report['state'], 'FAKE_PIPELINE_COMPLETED')
            self.assertEqual(report['usage']['unknown_usage_requests'], 24)
            self.assertIsNone(report['usage']['gateway_reported_total_tokens'])

    def test_bad_schema_or_timeout_stops_after_one_attempt(self):
        for reason in ('schema', 'timeout', 'model'):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as tmp:
                job = self.prepare(tmp); calls = []
                def fake(model, item, context):
                    calls.append(1)
                    if reason == 'timeout': raise TimeoutError()
                    raw = response(item, model)
                    if reason == 'schema': raw['choices'][0]['message']['content'] = '{}'
                    else: raw['model'] = 'wrong-model'
                    return raw
                report = oa.run(job, transport=fake, fake=True)
                self.assertEqual(len(calls), 1)
                self.assertEqual(report['state'], 'FAKE_PIPELINE_STOPPED')
                self.assertEqual(report['request_count'], 1)

    def test_attempt_is_durable_before_sender_and_raw_is_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = self.prepare(tmp)
            def fake(model, item, context):
                journal = oa.Journal(job/'observed-requests.sqlite', job.name, create=False)
                self.assertEqual(journal.rows()[-1]['status'], 'DISPATCHED')
                return response(item, model)
            oa.run(job, transport=fake, fake=True)
            self.assertEqual(len(list((job/'observed-raw').glob('*.json'))), 24)

    def test_no_real_authorization_rejects_before_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = self.prepare(tmp)
            with self.assertRaisesRegex(rv.Blocked, 'REAL_AUTHORIZATION_REQUIRED'):
                oa.run(job, transport=lambda *args: self.fail('sent'), fake=False)

    def test_cannot_restart_completed_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = self.prepare(tmp); oa.run(job, transport=lambda m,i,c:response(i,m), fake=True)
            with self.assertRaisesRegex(rv.Blocked, 'JOB_ALREADY_STARTED'):
                oa.run(job, transport=lambda *args:self.fail('sent'), fake=True)

    def test_source_changed_before_start_never_sends(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = self.prepare(tmp)
            with patch.object(rv, 'verify_seal', side_effect=rv.Blocked('HISTORICAL_EVIDENCE_CHANGED')):
                with self.assertRaises(rv.Blocked):
                    oa.run(job, transport=lambda *args:self.fail('sent'), fake=True)

    def test_request_limit_is_24_without_token_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = oa.Journal(Path(tmp)/'requests.sqlite', 'job', create=True)
            for i in range(24):
                journal.dispatch('task'+str(i), 'model', 'a'*64)
                journal.complete(i+1, 'SUCCESS', {'prompt_tokens':1000000, 'completion_tokens':10, 'total_tokens':1000010}, None)
            with self.assertRaisesRegex(rv.Blocked, 'REQUEST_LIMIT'):
                journal.dispatch('task25', 'model', 'a'*64)
            self.assertEqual(len(journal.rows()), 24)

    def test_unknown_result_never_promoted_to_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = self.prepare(tmp)
            def fake(model, item, context):
                raw = response(item, model); row = json.loads(raw['choices'][0]['message']['content'])
                row['confidence'] = .5; row['abstain'] = True
                raw['choices'][0]['message']['content'] = json.dumps(row); return raw
            report = oa.run(job, transport=fake, fake=True)
            self.assertEqual(report['state'], 'FAKE_PIPELINE_COMPLETED')
            self.assertFalse(report['all_image_checks_conclusive'])

    def test_dispatch_failure_does_not_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = self.prepare(tmp)
            with patch.object(oa.Journal, 'dispatch', side_effect=rv.Blocked('JOURNAL_IO_FAILURE')):
                report = oa.run(job, transport=lambda *args:self.fail('sent'), fake=True)
            self.assertEqual(report['request_count'], 0)
            self.assertEqual(report['state'], 'FAKE_PIPELINE_STOPPED')

    def test_historical_job_cannot_be_run_or_written(self):
        with self.assertRaisesRegex(rv.Blocked, 'OUTPUT_ISOLATION'):
            oa.run(rv.DEFAULT_SOURCE, transport=lambda *args:self.fail('sent'), fake=True)


if __name__ == '__main__': unittest.main()
