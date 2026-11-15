import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch
from budget_manager import BudgetManager, BudgetExceeded
from ai_judge import JudgeClient


def policy():
    return dict(mode='CONTROLLED_CANARY', enabled=True, authorization_id='FAKE-ONLY',
                max_requests=2, max_products=1, max_images=2, max_images_per_request=1,
                max_output_tokens=100, token_soft_limit=1000, reserve_tokens=200,
                usd_stop='1', models=['a','b'], endpoints=['https://fake/v1'],
                max_in_flight=1, retries=0, usage_source='GATEWAY_REPORTED_UNVERIFIED',
                price=dict(source='fake fixture only', endpoint='https://fake/v1', models=['a','b'],
                    currency='USD', valid_until='2099-01-01', input_per_million='1',
                    output_per_million='2', image_included=True, cache_included=True))

class UnifiedModelBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.b=BudgetManager({'ai_requests':10,'full_resolution_images':10},self.root/'budget.sqlite')
    def tearDown(self):
        self.b.close();self.tmp.cleanup()
    def setup_budget(self,p=None):
        self.b.configure_model_budget(p or policy(),'JOB_fake')
    def send(self,transport=None,usage=None,model='a',images=None):
        transport=transport or (lambda:{'usage':usage if usage is not None else dict(prompt_tokens=20,completion_tokens=10,total_tokens=30)})
        return self.b.model_call(model,'https://fake/v1',1,images or ['a'*64],100,{'task_type':'watermark','request_body_sha256':'x'},transport)
    def test_missing_authorization_never_dispatches(self):
        t=Mock();
        with self.assertRaises(BudgetExceeded):self.send(t)
        t.assert_not_called()
    def test_every_required_parameter_is_fail_closed(self):
        for key in policy():
            with self.subTest(key=key):
                p=policy();p.pop(key)
                with self.assertRaises((ValueError,BudgetExceeded)):self.b.configure_model_budget(p,'JOB_fake')
    def test_invalid_numeric_or_unknown_price_never_dispatches(self):
        for key,value in [('usd_stop',None),('usd_stop','NaN'),('max_requests',0),('max_products',True),('reserve_tokens',None),('max_in_flight',2),('retries',1)]:
            with self.subTest(key=key,value=value):
                p=policy();p[key]=value
                with self.assertRaises((ValueError,BudgetExceeded)):self.b.configure_model_budget(p,'JOB_fake')
    def test_success_records_gateway_provenance_and_cost(self):
        self.setup_budget();self.send()
        s=self.b.model_snapshot();self.assertEqual(s['requests'],1)
        self.assertEqual(s['known_tokens'],30);self.assertEqual(s['usage_source'],'GATEWAY_REPORTED_UNVERIFIED')
        self.assertFalse(s['SPEND_CAP_GUARANTEED']);self.assertGreater(float(s['known_usd']),0)
    def test_missing_usage_preserves_reservation_and_stops(self):
        self.setup_budget()
        with self.assertRaises(BudgetExceeded):self.send(lambda:{})
        s=self.b.model_snapshot();self.assertEqual(s['reserved_tokens'],200);self.assertIsNone(s['total_tokens'])
        t=Mock()
        with self.assertRaises(BudgetExceeded):self.send(t)
        t.assert_not_called()
    def test_timeout_never_retries(self):
        self.setup_budget();t=Mock(side_effect=TimeoutError())
        with self.assertRaises(TimeoutError):self.send(t)
        self.assertEqual(t.call_count,1);self.assertEqual(self.b.model_snapshot()['status'],'UNKNOWN')
    def test_request_limit_before_transport(self):
        self.setup_budget();self.send();self.send(model='b');t=Mock()
        with self.assertRaises(BudgetExceeded):self.send(t)
        t.assert_not_called()
    def test_route_and_model_whitelist(self):
        self.setup_budget();t=Mock()
        with self.assertRaises(BudgetExceeded):self.send(t,model='other')
        t.assert_not_called()
    def test_nested_concurrent_call_blocked(self):
        self.setup_budget()
        def inner():
            with self.assertRaises(BudgetExceeded):self.send()
            return {'usage':dict(prompt_tokens=20,completion_tokens=10,total_tokens=30)}
        self.send(inner);self.assertEqual(self.b.model_snapshot()['requests'],1)
    def test_restart_pending_is_unknown(self):
        self.setup_budget()
        self.b._db.execute("INSERT INTO model_calls VALUES ('crash','DISPATCHED',200,'0.0004',NULL,NULL,NULL,'{}')")
        self.b.close();self.b=BudgetManager({'ai_requests':10,'full_resolution_images':10},self.root/'budget.sqlite')
        self.setup_budget();self.assertEqual(self.b.model_snapshot()['status'],'UNKNOWN')
        with self.assertRaises(BudgetExceeded):self.send()
    def test_changed_job_or_policy_rejected(self):
        self.setup_budget();p=policy();p['max_requests']=3
        with self.assertRaises((ValueError,BudgetExceeded)):self.b.configure_model_budget(p,'JOB_fake')
        with self.assertRaises((ValueError,BudgetExceeded)):self.b.configure_model_budget(policy(),'JOB_other')
    def test_direct_http_request_requires_budget_dispatch(self):
        client=JudgeClient(self.b,self.root/'cache',models=('a','b'))
        with patch('urllib.request.urlopen') as net,patch.dict('os.environ',{'VLM_API_KEY':'fake'}):
            with self.assertRaises(BudgetExceeded):client._request('a',{'task_type':'watermark','id':'x'},{})
            net.assert_not_called()
    def test_strict_never_uses_controlled_bypass(self):
        p=policy();p['mode']='STRICT'
        with self.assertRaises(BudgetExceeded):self.b.configure_model_budget(p,'JOB_fake')
    def test_usd_reservation_blocks_last_request(self):
        p=policy();p['usd_stop']='0.00001';self.setup_budget(p);t=Mock()
        with self.assertRaises(BudgetExceeded):self.send(t)
        t.assert_not_called()
    def test_usage_total_mismatch_stops(self):
        self.setup_budget()
        with self.assertRaises(BudgetExceeded):self.send(usage=dict(prompt_tokens=20,completion_tokens=10,total_tokens=1))
        self.assertEqual(self.b.model_snapshot()['status'],'UNKNOWN')

    def test_image_and_product_scope_are_enforced_before_send(self):
        self.setup_budget();self.send();t=Mock()
        with self.assertRaises(BudgetExceeded):self.b.model_call('a','https://fake/v1',2,['a'*64],100,{},t)
        with self.assertRaises(BudgetExceeded):self.send(t,images=['a'*64,'a'*64])
        t.assert_not_called()
    def test_legacy_direct_senders_are_closed(self):
        import vlmcheck,run_8788_real_validation as legacy
        with patch('urllib.request.urlopen') as net,patch('urllib.request.build_opener') as opener:
            with self.assertRaises(BudgetExceeded):vlmcheck.call('a','not-an-image')
            with self.assertRaises(legacy.Blocked):legacy._http_transport({},'a',{}, {})
            net.assert_not_called();opener.assert_not_called()
    def test_ledger_write_failure_never_sends(self):
        import sqlite3
        self.setup_budget();t=Mock()
        with patch.object(self.b,'_transaction',side_effect=sqlite3.OperationalError('fake disk failure')):
            with self.assertRaises(BudgetExceeded):self.send(t)
        with self.assertRaises(BudgetExceeded):self.send(t)
        t.assert_not_called()
    def test_soft_reservation_breach_stops_even_with_small_reported_total(self):
        self.setup_budget()
        with self.assertRaises(BudgetExceeded):self.send(usage=dict(prompt_tokens=200,completion_tokens=10,total_tokens=210))
        self.assertEqual(self.b.model_snapshot()['known_tokens'],210)
        t=Mock()
        with self.assertRaises(BudgetExceeded):self.send(t)
        t.assert_not_called()

    def test_corrupt_settled_amount_cannot_create_new_budget(self):
        self.setup_budget();self.send()
        self.b._db.execute("UPDATE model_calls SET actual=0,usd='0' WHERE state='SETTLED'")
        t=Mock()
        with self.assertRaises(BudgetExceeded):self.send(t)
        t.assert_not_called()
    def test_disk_failure_latch_survives_restart(self):
        import sqlite3
        self.setup_budget()
        with patch.object(self.b,'_transaction',side_effect=sqlite3.OperationalError('disk')):
            with self.assertRaises(BudgetExceeded):self.send(Mock())
        self.b.close();self.b=BudgetManager({'ai_requests':10,'full_resolution_images':10},self.root/'budget.sqlite')
        self.setup_budget();t=Mock()
        with self.assertRaises(BudgetExceeded):self.send(t)
        t.assert_not_called()

    def test_redirect_and_response_model_change_stop_without_followup(self):
        from ai_judge.client import _NoModelRedirect
        with self.assertRaises(BudgetExceeded):_NoModelRedirect().redirect_request(None,None,302,'',{},'https://other/')
        self.setup_budget()
        with self.assertRaises(BudgetExceeded):self.send(lambda:{'model':'unapproved','usage':dict(prompt_tokens=1,completion_tokens=1,total_tokens=2)})
        self.assertEqual(self.b.model_snapshot()['status'],'UNKNOWN')
