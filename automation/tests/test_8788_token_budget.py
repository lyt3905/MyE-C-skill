from current_source_fixtures import freeze_current_source
"""Synthetic provider capability and durable ledger tests; no inference."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import mye_c_automation.token_budget as tb


def proof(value, status='DOCUMENTED_UPPER_BOUND'):
    return dict(value=value, status=status, source='fake://provider/spec-v1')


def capability():
    return dict(provider='FAKE', model_id='fake-model', api='fake-v1', document_version='fake-v1',
                valid_until='2099-01-01', route_verified=True, usage_verified=True,
                text=proof(100), image_per_input=proof(1000), other_input=proof(0),
                output=proof(8192, 'DOCUMENTED_HARD_LIMIT'), overhead=proof(10), fake=True)


def metadata():
    return dict(provider='FAKE', model_id='fake-model', task_type='watermark', image_sha256='a'*64,
                prompt_version='fake-prompt-v1', schema_version='watermark/v3',
                request_body_sha256='b'*64, input_text_upper_bound=100,
                image_input_upper_bound=1000, other_input_upper_bound=0,
                output_token_hard_limit=8192, provider_overhead_upper_bound=10,
                upper_bound_status='DOCUMENTED_UPPER_BOUND', proof_source='fake://provider/spec-v1')


def usage(n=100):
    return dict(prompt_tokens=n-10, completion_tokens=10, total_tokens=n)


class CapabilityTests(unittest.TestCase):
    def test_documented_parts_sum_without_double_counting_images(self):
        result = tb.request_upper_bound(capability(), image_count=2, mode='FAKE')
        self.assertEqual(result['request_upper_bound'], 10302)

    def test_unknown_images_not_zero(self):
        cap = capability(); cap['image_per_input'] = proof(None, 'UNKNOWN')
        result = tb.request_upper_bound(cap, image_count=2, mode='FAKE')
        self.assertIsNone(result['request_upper_bound'])
        self.assertIsNone(result['image_input_upper_bound'])

    def test_average_percentile_cannot_prove_upper_bound(self):
        for status in ('ESTIMATE_ONLY', 'P95', 'NOT_SUPPORTED', 'UNKNOWN'):
            cap = capability(); cap['image_per_input'] = proof(100, status)
            self.assertIsNone(tb.request_upper_bound(cap, image_count=1, mode='FAKE')['request_upper_bound'])

    def test_unknown_provider_model_and_current_gateway_are_blocked(self):
        for model in ('nonexistent-model', 'deepseek-v4.1-flash', 'mimo-v2.6-pro'):
            cap = tb.provider_capability('http://127.0.0.1:8788/v1', model)
            bound = tb.request_upper_bound(cap, image_count=2)
            self.assertIsNone(bound['request_upper_bound'])
            self.assertFalse(cap['route_verified'])

    def test_expired_document_missing_version_and_fake_in_strict_mode_block(self):
        for key, value in (('valid_until', '2000-01-01'), ('document_version', ''), ('api', '')):
            cap = capability(); cap[key] = value
            self.assertIsNone(tb.request_upper_bound(cap, image_count=1, mode='FAKE')['request_upper_bound'])
        self.assertIsNone(tb.request_upper_bound(capability(), image_count=1)['request_upper_bound'])

    def test_24_request_plan_requires_all_bounds_and_total_cap(self):
        known = dict(request_upper_bound=12000, blockers=[])
        self.assertEqual(tb.plan_budget([known]*24)['state'], 'PREFLIGHT_PASS')
        self.assertEqual(tb.plan_budget([dict(request_upper_bound=13000, blockers=[])]*24)['state'], 'PREFLIGHT_BLOCKED')
        result = tb.plan_budget([known]*23+[dict(request_upper_bound=None, blockers=['IMAGE_BOUND_UNKNOWN'])])
        self.assertIsNone(result['worst_case_total_tokens'])
        self.assertFalse(result['TOKEN_CAP_PROVEN'])

    def test_provider_specific_usage_no_cache_or_reasoning_double_count(self):
        deepseek = dict(usage(), prompt_cache_hit_tokens=30, prompt_cache_miss_tokens=60,
                        prompt_tokens_details=dict(cached_tokens=30),
                        completion_tokens_details=dict(reasoning_tokens=8))
        kimi = dict(usage(), prompt_tokens_details=dict(cached_tokens=30, cache_write_tokens=20),
                    completion_tokens_details=dict(reasoning_tokens=8))
        self.assertEqual(tb.parse_usage('deepseek-direct', deepseek)['total_tokens'], 100)
        self.assertEqual(tb.parse_usage('kimi-direct', kimi)['total_tokens'], 100)
        with self.assertRaises(tb.BudgetError): tb.parse_usage('deepseek-direct', kimi)

    def test_untagged_gateway_usage_is_not_proven_provider_usage(self):
        for model in ('deepseek-v4.1-flash', 'mimo-v2.6-pro'):
            with self.assertRaisesRegex(tb.BudgetError, 'USAGE_PROVENANCE_UNVERIFIED'):
                tb.parse_usage('workbuddy:'+model, usage())

    def test_unknown_extra_usage_and_total_mismatch_stop(self):
        for raw in (dict(usage(), new_billable_tokens=9), dict(usage(), total_tokens=99),
                    dict(usage(), image_tokens=100), dict(usage(), credit=.01)):
            with self.assertRaises(tb.BudgetError): tb.parse_usage('fake-chat', raw)

    def test_missing_partial_negative_bool_and_renamed_usage_rejected(self):
        for raw in (None, {}, dict(total_tokens=100), dict(usage(), prompt_tokens=-1),
                    dict(usage(), total_tokens=True), dict(input_tokens=90, output_tokens=10, total_tokens=100)):
            with self.assertRaises(tb.BudgetError): tb.parse_usage('fake-chat', raw)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.path = Path(self.tmp.name)/'ledger.sqlite'
        self.ledger = tb.TokenLedger.create(self.path, 'fake-job', mode='FAKE')

    def tearDown(self): self.tmp.cleanup()

    def reserve(self, request_id='R1', bound=12000):
        self.ledger.reserve(request_id, bound, metadata())

    def test_reservation_is_committed_and_persisted_before_send(self):
        self.reserve()
        state = self.ledger.snapshot()
        self.assertEqual(state['reserved_tokens'], 12000)
        self.assertEqual(state['remaining_tokens'], 288000)
        self.assertIsNone(state['total_tokens'])
        self.assertEqual(state['usage_status'], 'PENDING')
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT request_upper_bound FROM requests').fetchone()[0], 12000)

    def test_success_replaces_reservation_with_actual_full_usage(self):
        self.reserve(); self.ledger.mark_sent('R1'); self.ledger.settle('R1', usage(), 'fake-chat')
        snap = self.ledger.snapshot()
        self.assertEqual((snap['actual_tokens'], snap['reserved_tokens']), (100, 0))
        self.assertEqual(self.ledger.records()[0]['actual_usage'], usage())

    def test_timeout_and_missing_usage_retain_unknown_committed(self):
        for reason in ('TIMEOUT', 'SERVER_ERROR', 'RESPONSE_PARSE_ERROR'):
            with self.subTest(reason=reason):
                ledger = tb.TokenLedger.create(Path(self.tmp.name)/(reason+'.sqlite'), reason, mode='FAKE')
                ledger.reserve('R', 12000, metadata()); ledger.mark_sent('R'); ledger.mark_unknown('R', reason)
                snap = ledger.snapshot()
                self.assertEqual(snap['unknown_committed_tokens'], 12000)
                self.assertIsNone(snap['total_tokens'])
                with self.assertRaises(tb.BudgetError): ledger.reserve('NEXT', 12000, metadata())
                with self.assertRaises(tb.BudgetError): ledger.release('R', 'LOCAL_NOT_SENT')

    def test_missing_usage_keeps_reservation_and_stops(self):
        self.reserve(); self.ledger.mark_sent('R1')
        with self.assertRaisesRegex(tb.BudgetError, 'USAGE_UNKNOWN'):
            self.ledger.settle('R1', None, 'fake-chat')
        self.assertEqual(self.ledger.snapshot()['unknown_committed_tokens'], 12000)

    def test_actual_over_bound_is_persistent_breach(self):
        self.reserve(bound=100); self.ledger.mark_sent('R1')
        with self.assertRaisesRegex(tb.BudgetError, 'BUDGET_GUARD_BREACH'):
            self.ledger.settle('R1', usage(110), 'fake-chat')
        state = tb.TokenLedger.open(self.path, 'fake-job').snapshot()
        self.assertEqual(state['status'], 'BUDGET_GUARD_BREACH')
        self.assertEqual(state['actual_tokens'], 110)

    def test_actual_plus_reserved_cannot_exceed_300000(self):
        self.reserve(bound=290000); self.ledger.mark_sent('R1'); self.ledger.settle('R1', usage(290000), 'fake-chat')
        with self.assertRaisesRegex(tb.BudgetError, 'TOKEN_LIMIT'): self.reserve('R2', 10001)

    def test_25th_request_rejected_even_when_first_24_failed_before_send(self):
        for i in range(24):
            self.reserve(str(i), 100); self.ledger.release(str(i), 'LOCAL_NOT_SENT')
        with self.assertRaisesRegex(tb.BudgetError, 'REQUEST_LIMIT'): self.reserve('25', 100)

    def test_corrupt_missing_and_version_mismatch_fail_closed(self):
        bad = Path(self.tmp.name)/'bad.sqlite'; bad.write_bytes(b'not sqlite')
        for path in (bad, Path(self.tmp.name)/'missing.sqlite'):
            with self.assertRaises(tb.BudgetError): tb.TokenLedger.open(path, 'fake-job')
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db: db.execute("UPDATE meta SET version='wrong'")
        with self.assertRaises(tb.BudgetError): tb.TokenLedger.open(self.path, 'fake-job')

    def test_write_failure_poisoned_process_and_restart_fail_closed(self):
        self.reserve(); self.ledger.mark_sent('R1')
        with patch.object(self.ledger, '_commit', side_effect=sqlite3.OperationalError('disk full')):
            with self.assertRaises(tb.BudgetError): self.ledger.settle('R1', usage(), 'fake-chat')
        with self.assertRaises(tb.BudgetError): self.reserve('R2')
        with self.assertRaises(tb.BudgetError): tb.TokenLedger.open(self.path, 'fake-job')

    def test_restart_of_inflight_preserves_reservation_stops_and_never_releases(self):
        self.reserve(); self.ledger.mark_sent('R1')
        reopened = tb.TokenLedger.open(self.path, 'fake-job')
        self.assertEqual(reopened.snapshot()['unknown_committed_tokens'], 12000)
        self.assertEqual(reopened.snapshot()['status'], 'UNKNOWN_COMMITTED')
        with self.assertRaises(tb.BudgetError): reopened.release('R1', 'LOCAL_NOT_SENT')

    def test_restart_settled_does_not_double_charge(self):
        self.reserve(); self.ledger.mark_sent('R1'); self.ledger.settle('R1', usage(), 'fake-chat')
        reopened = tb.TokenLedger.open(self.path, 'fake-job')
        self.assertEqual(reopened.snapshot()['actual_tokens'], 100)
        with self.assertRaises(tb.BudgetError): reopened.settle('R1', usage(), 'fake-chat')
        with self.assertRaises(tb.BudgetError): reopened.reserve('R1', 12000, metadata())
        self.assertEqual(reopened.snapshot()['actual_tokens'], 100)

    def test_duplicate_reservation_and_simultaneous_inflight_rejected(self):
        self.reserve()
        with self.assertRaises(tb.BudgetError): self.reserve()
        with self.assertRaisesRegex(tb.BudgetError, 'CONCURRENT_REQUEST_FORBIDDEN'): self.reserve('R2')

    def test_two_concurrent_reservations_admit_one(self):
        def submit(i):
            try: self.ledger.reserve(str(i), 200000, metadata()); return True
            except tb.BudgetError: return False
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(submit, range(2)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(self.ledger.snapshot()['committed_tokens'], 200000)

    def test_release_only_verified_not_sent_never_refunds_request_count(self):
        self.reserve(); self.ledger.release('R1', 'LOCAL_NOT_SENT')
        self.assertEqual(self.ledger.snapshot()['request_count'], 1)
        self.assertEqual(self.ledger.snapshot()['committed_tokens'], 0)
        with self.assertRaises(tb.BudgetError): self.ledger.release('R1', 'LOCAL_NOT_SENT')

    def test_ledger_cannot_be_recreated_reset_or_moved_to_other_job(self):
        with self.assertRaises(tb.BudgetError): tb.TokenLedger.create(self.path, 'fake-job', mode='FAKE')
        with self.assertRaises(tb.BudgetError): tb.TokenLedger.open(self.path, 'another-job')

    def test_unknown_bounds_and_unaudited_strict_profile_refused(self):
        with self.assertRaisesRegex(tb.BudgetError, 'TOKEN_CEILING_UNVERIFIED'): self.reserve(bound=None)
        strict = tb.TokenLedger.create(Path(self.tmp.name)/'strict.sqlite', 'strict-job', mode='STRICT')
        self.assertEqual(strict.snapshot()['status'], 'PREFLIGHT_BLOCKED')
        with self.assertRaisesRegex(tb.BudgetError, 'PROVIDER_CAPABILITY_UNVERIFIED'):
            strict.reserve('R', 12000, metadata())

    def test_settled_amount_corruption_cannot_create_fake_balance(self):
        self.reserve(); self.ledger.mark_sent('R1'); self.ledger.settle('R1', usage(), 'fake-chat')
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
            db.execute('UPDATE requests SET actual_tokens=0')
        with self.assertRaises(tb.BudgetError): tb.TokenLedger.open(self.path, 'fake-job')

    def test_pending_upper_bound_corruption_cannot_create_fake_balance(self):
        self.reserve()
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
            db.execute('UPDATE requests SET request_upper_bound=-1')
        with self.assertRaises(tb.BudgetError): self.ledger.snapshot()

    def test_mark_sent_twice_is_rejected_without_new_attempt(self):
        self.reserve(); self.ledger.mark_sent('R1')
        with self.assertRaises(tb.BudgetError): self.ledger.mark_sent('R1')
        self.assertEqual(self.ledger.snapshot()['request_count'], 1)

    def test_corrupt_active_flag_cannot_resume_unknown_charge(self):
        self.reserve(); self.ledger.mark_sent('R1'); self.ledger.mark_unknown('R1', 'TIMEOUT')
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
            db.execute("UPDATE meta SET status='ACTIVE'")
        with self.assertRaises(tb.BudgetError): self.reserve('R2')


class RunnerBudgetIntegrationTests(unittest.TestCase):
    def setUp(self):freeze_current_source(self)

    def test_fake_runner_uses_durable_reservation_before_transport(self):
        import mye_c_automation.run_8788_real_validation as rv
        from test_8788_real_validation import response
        with tempfile.TemporaryDirectory() as tmp:
            job = rv.prepare(rv.DEFAULT_SOURCE, rv.build_inputs(rv.DEFAULT_SOURCE), Path(tmp), rv.DEFAULT_CONFIG)
            observed = []
            def fake(model, item, context):
                with closing(sqlite3.connect(job/'token-budget.fake.sqlite')) as db:
                    observed.append(db.execute("SELECT count(*) FROM requests WHERE reservation_status='DISPATCHED'").fetchone()[0])
                return response(item, model)
            result = rv.run_fake(job, fake, per_request_ceiling=12000)
            self.assertEqual(result['simulated_requests'], 24)
            self.assertEqual(observed, [1]*24)
            ledger = tb.TokenLedger.open(job/'token-budget.fake.sqlite', job.name)
            self.assertEqual(ledger.snapshot()['actual_tokens'], 2400)
            self.assertEqual(len(ledger.records()), 24)

    def test_preflight_records_unknown_bounds_and_unused_strict_ledger(self):
        import mye_c_automation.run_8788_real_validation as rv
        with tempfile.TemporaryDirectory() as tmp, patch('urllib.request.urlopen', side_effect=AssertionError('NETWORK')):
            job = rv.prepare(rv.DEFAULT_SOURCE, rv.build_inputs(rv.DEFAULT_SOURCE), Path(tmp), rv.DEFAULT_CONFIG)
            plan = json.loads((job/'token-budget-plan.json').read_text())
            self.assertFalse(plan['TOKEN_CAP_PROVEN'])
            self.assertIsNone(plan['worst_case_total_tokens'])
            ledger = tb.TokenLedger.open(job/'token-budget.sqlite', job.name)
            self.assertEqual(ledger.snapshot()['request_count'], 0)
            self.assertEqual(ledger.snapshot()['mode'], 'STRICT')

    def test_reservation_disk_failure_stops_before_transport(self):
        import mye_c_automation.run_8788_real_validation as rv
        with tempfile.TemporaryDirectory() as tmp:
            job = rv.prepare(rv.DEFAULT_SOURCE, rv.build_inputs(rv.DEFAULT_SOURCE), Path(tmp), rv.DEFAULT_CONFIG)
            with patch.object(tb.TokenLedger, 'reserve', side_effect=tb.BudgetError('LEDGER_IO_FAILURE')):
                result = rv.run_fake(job, lambda *args: self.fail('sent'), per_request_ceiling=12000)
            self.assertEqual(result['state'], 'FAKE_STOPPED')
            self.assertEqual(result['simulated_requests'], 0)

    def test_settlement_disk_failure_never_sends_next_request(self):
        import mye_c_automation.run_8788_real_validation as rv
        from test_8788_real_validation import response
        with tempfile.TemporaryDirectory() as tmp:
            job = rv.prepare(rv.DEFAULT_SOURCE, rv.build_inputs(rv.DEFAULT_SOURCE), Path(tmp), rv.DEFAULT_CONFIG)
            calls = []
            def fake(model, item, context):
                calls.append(1); return response(item, model)
            with patch.object(tb.TokenLedger, 'settle', side_effect=tb.BudgetError('LEDGER_IO_FAILURE')):
                result = rv.run_fake(job, fake, per_request_ceiling=12000)
            self.assertEqual(len(calls), 1)
            self.assertEqual(result['state'], 'FAKE_STOPPED')


if __name__ == '__main__': unittest.main()
