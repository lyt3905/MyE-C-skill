import tempfile
import unittest
from job_manager import JobManager,atomic_json
from automation_policy import AutomationPolicy
from test_auto_decision import CONFIG,remedy
from plan_compiler import compile_auto_plan

class EvidenceBindingTests(unittest.TestCase):
    def test_booleans_and_arbitrary_sha_do_not_authorize_source(self):
        with tempfile.TemporaryDirectory() as root:
            manager=JobManager(root);job=manager.create(1,7,{})
            path=manager.directory(job['job_id'])
            product={'images':{'main':['https://x/a'],'detail':['https://x/b'],'sku':[]}}
            atomic_json(path/'audit_product.json',product)
            row=remedy();row['target']['index']=0
            result=compile_auto_plan(path,job,[row],AutomationPolicy(CONFIG))
            self.assertFalse(result['ok']);self.assertEqual(result['status'],'BLOCKED_FATAL')
    def test_changed_box_evidence_is_rejected_before_any_writer_call(self):
        from pathlib import Path
        import hashlib
        from unittest.mock import Mock
        from test_local_execution import ApplyTests
        from executor.local import LocalExecutor
        with tempfile.TemporaryDirectory() as root:
            helper=ApplyTests();writer,plan=helper.fixture(root)
            proof=Path(root)/'box_validation.json';proof.write_text('{"items":[]}')
            plan['evidence_refs']=[{'path':proof.name,'sha256':hashlib.sha256(proof.read_bytes()).hexdigest()}]
            proof.write_text('{"items":["changed"]}')
            writer.upload=Mock();writer.product=Mock(side_effect=AssertionError('writer must not be contacted'))
            with self.assertRaises(ValueError):LocalExecutor(writer,root).execute(plan,helper.confirm(plan))
            writer.product.assert_not_called();writer.upload.assert_not_called();self.assertEqual(writer.calls,0)
