"""Observed real-server side effects, reproduced at the Fake transport boundary."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import test_v13_account_cli as cli
from mye_c_automation.automation_policy import AutomationPolicy
from mye_c_automation.executor.local import LocalExecutor
from mye_c_automation.executor.site_write_client import SiteWriteClient
from mye_c_automation.job_manager import JobManager
from mye_c_automation.workflow_runner import run_automatic


class BackendSaveContractTests(unittest.TestCase):
    def test_acknowledged_save_with_protected_drift_is_not_verified_or_retried(self):
        for suffix in ('description','both'):
            with self.subTest(server_mutation=suffix),tempfile.TemporaryDirectory() as temp:
                transport,path,_,error=cli.AccountCliTests().execute(temp,case='backend_drift_'+suffix)
                self.assertIsNotNone(error)
                self.assertIn('post-write verification failed',str(error))
                self.assertEqual((transport.saves,transport.uploads,transport.translations),(1,0,0))

                read=lambda name:json.loads((path/name).read_text(encoding='utf-8'))
                self.assertEqual(read('state.json')['state'],'APPLY_UNKNOWN')
                self.assertEqual(read('save_attempt.json')['state'],'SAVED_RESPONSE_RECEIVED')
                self.assertFalse((path/'apply_receipt.json').exists())
                plan=read('plan.v2.json');before=read('before.json');expected=read('expected_after.json')
                self.assertEqual(set(plan['desired']),{'titleEn'})
                for field in ('descriptionJson','skus','price','weight','status'):
                    self.assertEqual(expected[field],before[field])
                writer=SiteWriteClient(transport)
                for _ in range(2):
                    recovery=LocalExecutor(writer,path).recover_readback(plan)
                    self.assertEqual(recovery['write_outcome'],'DRIFT')
                    self.assertFalse(recovery['retry_save_allowed'])
                manager=JobManager(path.parent);job=manager.load(path.name)
                audit=Mock(side_effect=AssertionError('must not re-audit a started write'))
                resumed=run_automatic(manager,job,AutomationPolicy.load(Path(temp)/'policy.json'),writer=writer,auditor=audit)
                self.assertEqual(resumed['write_outcome'],'DRIFT')
                audit.assert_not_called()
                self.assertEqual((transport.saves,transport.uploads,transport.translations),(1,0,0))

    def test_server_derived_amounts_do_not_fail_title_readback_or_trigger_second_save(self):
        with tempfile.TemporaryDirectory() as temp:
            transport,path,_,error=cli.AccountCliTests().execute(temp,case='backend_drift_skus')
            self.assertIsNone(error,repr(error))
            self.assertEqual((transport.saves,transport.uploads,transport.translations),(1,0,1))
            read=lambda name:json.loads((path/name).read_text(encoding='utf-8'))
            self.assertIn(read('state.json')['state'],{'AUTO_VERIFIED','PARTIALLY_AUTO_FIXED'})
            before=read('before.json');after=read('after.json');expected=read('expected_after.json')
            self.assertEqual(expected['skus'],before['skus'])
            self.assertNotEqual(after['skus'][0]['discountPrice'],before['skus'][0]['discountPrice'])
            self.assertEqual(after['descriptionJson'],before['descriptionJson'])
            writer=SiteWriteClient(transport)
            self.assertEqual(LocalExecutor(writer,path).recover_readback(read('plan.v2.json'))['write_outcome'],'MATCHED')
            from mye_c_automation.check import check_saved_job
            self.assertTrue(check_saved_job(path)['ok'])
