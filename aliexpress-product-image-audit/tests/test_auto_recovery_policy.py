import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from automation_policy import AutomationPolicy
from test_auto_decision import CONFIG
from job_manager import JobManager,atomic_json
from workflow_runner import run_automatic

class RecoveryPolicyTests(unittest.TestCase):
    def test_policy_edit_invalidates_loaded_authority(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'policy.json';atomic_json(path,CONFIG)
            policy=AutomationPolicy.load(path)
            atomic_json(path,dict(CONFIG,enabled=False))
            with self.assertRaisesRegex(ValueError,'POLICY_CHANGED'):
                policy.authorize(1,7,[])
    def test_finished_job_returns_persisted_result_without_reauditing(self):
        with tempfile.TemporaryDirectory() as root:
            manager=JobManager(root);job=manager.create(1,7,{},mode='auto_apply')
            path=manager.directory(job['job_id'])
            result={'status':'AUTO_VERIFIED','site_save_calls':1}
            atomic_json(path/'state.json',{'state':'AUTO_VERIFIED','automatic':True})
            atomic_json(path/'automatic_result.json',result)
            audit=Mock(side_effect=AssertionError('must not re-audit'))
            self.assertEqual(run_automatic(manager,job,AutomationPolicy(CONFIG),auditor=audit),result)
            audit.assert_not_called()
    def test_unknown_job_never_reopens_apply(self):
        with tempfile.TemporaryDirectory() as root:
            manager=JobManager(root);job=manager.create(1,7,{},mode='auto_apply')
            path=manager.directory(job['job_id'])
            atomic_json(path/'state.json',{'state':'APPLY_UNKNOWN','automatic':True})
            writer=Mock()
            result=run_automatic(manager,job,AutomationPolicy(CONFIG),writer=writer)
            self.assertEqual(result['status'],'APPLY_UNKNOWN')
            writer.save.assert_not_called()
