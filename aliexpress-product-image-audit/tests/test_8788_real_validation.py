"""Offline validation-runner tests. All provider responses are synthetic."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_8788_real_validation as rv


def response(item, model, tokens=100):
    refs = item['evidence_ids'][:1]
    row = dict(task_type=item['task_type'], item_id=item['id'], confidence=.95,
               abstain=False, evidence_ids=refs)
    if item['task_type'] == 'watermark':
        row.update(schema_version='watermark/v3', image_size=item['dimensions'],
                   coverage_complete=True, no_marks_detected=True, marks=[], unresolved_items=[])
    else:
        values = dict(product_subject='toy', image_type='FIGURE', model_identity='DW-ES09T',
                      color='red', packaging='UNBOXED')
        row.update(schema_version='product-identity/v3', decision='MATCH', observations={
            k: dict(value=v, decision='MATCH', confidence=.95, abstain=False, evidence_ids=refs,
                    **({'visibility': 'VISIBLE'} if k == 'model_identity' else {}))
            for k, v in values.items()})
    return dict(model=model, usage=dict(prompt_tokens=tokens-10, completion_tokens=10, total_tokens=tokens),
                choices=[dict(message=dict(content=json.dumps(row)))])


class BudgetTests(unittest.TestCase):
    def test_reserve_before_send_settle_and_count_failure(self):
        b = rv.HardBudget()
        b.reserve(12000); b.settle(dict(prompt_tokens=90, completion_tokens=10, total_tokens=100))
        self.assertEqual((b.requests, b.known_tokens), (1, 100))
        b.reserve(12000); b.fail('TIMEOUT')
        self.assertEqual(b.requests, 2)
        with self.assertRaisesRegex(rv.Blocked, 'TIMEOUT'): b.reserve(12000)

    def test_25th_request_blocked(self):
        b = rv.HardBudget()
        for _ in range(24):
            b.reserve(100); b.settle(dict(prompt_tokens=90, completion_tokens=10, total_tokens=100))
        with self.assertRaisesRegex(rv.Blocked, 'REQUEST_LIMIT'): b.reserve(100)

    def test_next_worst_case_cannot_exceed_remaining_budget(self):
        b = rv.HardBudget()
        b.reserve(290000); b.settle(dict(prompt_tokens=289990, completion_tokens=10, total_tokens=290000))
        with self.assertRaisesRegex(rv.Blocked, 'TOKEN_LIMIT'): b.reserve(10001)
        self.assertEqual(b.requests, 1)

    def test_missing_or_inconsistent_usage_stops_and_never_zeroes(self):
        for usage in (None, {}, dict(prompt_tokens=90, completion_tokens=10, total_tokens=99),
                      dict(prompt_tokens=True, completion_tokens=0, total_tokens=1)):
            b = rv.HardBudget(); b.reserve(100)
            with self.assertRaisesRegex(rv.Blocked, 'USAGE_UNKNOWN'): b.settle(usage)
            self.assertIsNone(b.snapshot()['total_tokens'])
            with self.assertRaises(rv.Blocked): b.reserve(100)

    def test_unknown_input_ceiling_blocks_before_request(self):
        b = rv.HardBudget()
        with self.assertRaisesRegex(rv.Blocked, 'TOKEN_CEILING_UNVERIFIED'): b.reserve(None)
        self.assertEqual(b.requests, 0)

    def test_supplier_exceeding_reserved_ceiling_latches_stop(self):
        b = rv.HardBudget(); b.reserve(100)
        with self.assertRaisesRegex(rv.Blocked, 'PROVIDER_BOUND_BREACH'):
            b.settle(dict(prompt_tokens=100, completion_tokens=10, total_tokens=110))
        self.assertEqual(b.known_tokens, 110)


class RealValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = rv.DEFAULT_SOURCE
        cls.inputs = rv.build_inputs(cls.source)

    def test_full_sha_six_images_16_positions_no_extra_sku_tasks(self):
        self.assertEqual(len(self.inputs['images']), 6)
        self.assertEqual(len(self.inputs['occurrences']), 16)
        self.assertEqual(len(self.inputs['tasks']), 12)
        self.assertEqual(set(x['sha256'] for x in self.inputs['images']), set(rv.EXPECTED))
        for item in self.inputs['tasks']:
            self.assertEqual(len(item['sha256']), 64)
            self.assertIn(item['task_type'], ('watermark', 'product_identity'))
            self.assertEqual(set(item['evidence_ids']), {item['id']} | {x['image_id'] for x in item.get('extra_images', [])})

    def test_preflight_no_network_no_judge_no_writer_default_blocked_budget(self):
        with tempfile.TemporaryDirectory() as tmp, patch('urllib.request.urlopen', side_effect=AssertionError('NETWORK')), \
                patch('ai_judge.client.JudgeClient.__init__', side_effect=AssertionError('JUDGE')):
            out = rv.prepare(self.source, self.inputs, Path(tmp), rv.DEFAULT_CONFIG)
            result = json.loads((out/'8788-real-validation-final-verification.json').read_text())
            self.assertEqual(result['state'], 'PREFLIGHT_BLOCKED')
            self.assertIn('TOKEN_CEILING_UNVERIFIED', result['blockers'])
            self.assertEqual(result['actual_provider_requests'], 0)
            self.assertFalse(result['real_execution_authorized'])
            for name in rv.ARTIFACTS: self.assertTrue((out/name).exists(), name)

    def test_default_cli_never_executes_and_modes_exclusive(self):
        parser = rv.parser()
        self.assertFalse(parser.parse_args([]).execute_real_models)
        with self.assertRaises(SystemExit): parser.parse_args(['--preflight-only', '--execute-real-models'])

    def test_isolation_rejects_old_job_and_its_ancestors(self):
        for path in (self.source, self.source/'new', self.source.parent):
            with self.assertRaisesRegex(rv.Blocked, 'OUTPUT_ISOLATION'):
                rv.validate_output(path, self.source)

    def test_fake_entry_cannot_write_start_marker_into_historical_job(self):
        real_open = Path.open
        def guarded_open(path, mode='r', *args, **kwargs):
            if mode == 'x': raise AssertionError('Attempt to mutate historical Job blocked by test')
            return real_open(path, mode, *args, **kwargs)
        with patch.object(Path, 'open', guarded_open):
            with self.assertRaisesRegex(rv.Blocked, 'OUTPUT_ISOLATION'):
                rv.run_fake(self.source, lambda *args: self.fail('provider called'), per_request_ceiling=100)

    def test_contract_change_after_preflight_stops_before_first_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = rv.prepare(self.source, self.inputs, Path(tmp), rv.DEFAULT_CONFIG)
            versions = rv.source_versions(); versions['confidence_min'] = .80
            with patch.object(rv, 'source_versions', return_value=versions):
                result = rv.run_fake(job, lambda *args: self.fail('provider called'), per_request_ceiling=100)
            self.assertEqual(result['simulated_requests'], 0)
            self.assertIn('SOURCE_VERSION_CHANGED', result['blockers'])

    def test_manifest_sha_dimensions_binding_and_scope_tamper_blocked(self):
        for mutation in ('sha', 'dimensions', 'refs', 'mapping', 'task', 'context'):
            bad = copy.deepcopy(self.inputs)
            if mutation == 'sha': bad['images'][0]['sha256'] = '0'*64
            elif mutation == 'dimensions': bad['tasks'][0]['dimensions'] = [1, 1]
            elif mutation == 'refs': bad['tasks'][0]['evidence_ids'].append('FOREIGN')
            elif mutation == 'mapping': bad['occurrences'].pop()
            elif mutation == 'task': bad['tasks'][0]['task_type'] = 'sku_match'
            else: bad['context']['unexpected_product_field'] = 'forbidden'
            with self.assertRaisesRegex(rv.Blocked, 'INPUT_MANIFEST_CHANGED'):
                rv.verify_inputs(self.source, bad)

    def test_24_fake_calls_partial_reports_mapping_and_source_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = rv.prepare(self.source, self.inputs, Path(tmp), rv.DEFAULT_CONFIG)
            calls = []
            def fake(model, item, context):
                calls.append((item['id'], model)); return response(item, model)
            result = rv.run_fake(job, fake, per_request_ceiling=12000)
            self.assertEqual(len(calls), 24)
            self.assertEqual(len(set(calls)), 24)
            self.assertEqual(result['state'], 'FAKE_COMPLETED')
            self.assertEqual(result['actual_provider_requests'], 0)
            self.assertEqual(result['simulated_requests'], 24)
            self.assertEqual(result['source_evidence_unchanged'], True)
            self.assertEqual(len(json.loads((job/'8788-real-validation-watermark.json').read_text())['positions']), 16)

    def test_all_failures_stop_without_retry_preserve_raw_and_usage(self):
        for failure in ('timeout', 'schema', 'usage', 'model'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                job = rv.prepare(self.source, self.inputs, Path(tmp), rv.DEFAULT_CONFIG)
                calls = []
                def fake(model, item, context):
                    calls.append(1)
                    if failure == 'timeout': raise TimeoutError()
                    raw = response(item, model)
                    if failure == 'schema': raw['choices'][0]['message']['content'] = '{}'
                    elif failure == 'usage': raw.pop('usage')
                    elif failure == 'model': raw['model'] = 'unapproved-model'
                    return raw
                result = rv.run_fake(job, fake, per_request_ceiling=12000)
                self.assertEqual(len(calls), 1)
                self.assertEqual(result['state'], 'FAKE_STOPPED')
                self.assertEqual(len((job/'8788-real-validation-requests.jsonl').read_text().splitlines()), 2)
                if failure != 'timeout': self.assertEqual(len(list((job/'raw').glob('*.json'))), 1)

    def test_used_job_never_restarts_or_reuses_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = rv.prepare(self.source, self.inputs, Path(tmp), rv.DEFAULT_CONFIG)
            rv.run_fake(job, lambda m, i, c: response(i, m), per_request_ceiling=12000)
            with self.assertRaisesRegex(rv.Blocked, 'JOB_ALREADY_STARTED'):
                rv.run_fake(job, lambda *a: self.fail('called'), per_request_ceiling=12000)

    def test_source_modified_midrun_stops_before_next_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = rv.prepare(self.source, self.inputs, Path(tmp), rv.DEFAULT_CONFIG)
            count = []
            def seal(*args):
                count.append(1)
                if len(count) > 1: raise rv.Blocked('HISTORICAL_EVIDENCE_CHANGED')
            with patch.object(rv, 'verify_seal', side_effect=seal):
                result = rv.run_fake(job, lambda m, i, c: response(i, m), per_request_ceiling=12000)
            self.assertEqual(result['simulated_requests'], 1)
            self.assertEqual(result['state'], 'FAKE_STOPPED')

    def test_overlay_includes_matched_and_unmatched_region_boxes(self):
        item = self.inputs['tasks'][0]
        mark = dict(mark_id='M1', classification='third_party_store_banner', owner='Example Store',
                    location='top', bbox_xyxy=[100, 100, 200, 200], confidence=.95,
                    abstain=False, evidence_ids=item['evidence_ids'][:1])
        analysis = dict(regions=[dict(model_a_observation=mark, model_b_observation=None, status='UNKNOWN')],
                        confirmed_findings=[], unresolved_items=[])
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp); (job/'8788-real-validation-overlay').mkdir()
            rv.overlay(job, item, [dict(marks=[mark])], analysis, True)
            from PIL import Image
            with Image.open(job/'8788-real-validation-overlay'/(item['sha256']+'.png')) as image:
                # Combined panel at x=800,y=830 plus original-pixel coordinates.
                self.assertEqual(image.getpixel((900, 960)), (255, 165, 0))

    def test_no_unsafe_cli_flags_and_fixed_caps(self):
        for args in (['--max-provider-requests', '25'], ['--max-total-tokens', '500000'], ['--retry'], ['--allow-budget-bypass']):
            with self.assertRaises(SystemExit): rv.parser().parse_args(args)

    def test_schema_failure_records_actual_per_request_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = rv.prepare(self.source, self.inputs, Path(tmp), rv.DEFAULT_CONFIG)
            def fake(model, item, context):
                raw = response(item, model); raw['choices'][0]['message']['content'] = '{}'; return raw
            rv.run_fake(job, fake, per_request_ceiling=12000)
            last = json.loads((job/'8788-real-validation-requests.jsonl').read_text().splitlines()[-1])
            self.assertEqual(last['provider_usage']['total_tokens'], 100)


if __name__ == '__main__': unittest.main()
