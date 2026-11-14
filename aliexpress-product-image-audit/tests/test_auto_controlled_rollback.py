import tempfile,unittest,json
from pathlib import Path
import test_auto_workflow_more as helpers
from controlled_rollback import prepare_rollback,apply_rollback,confirmation_for

class ControlledRollbackTests(unittest.TestCase):
    def test_fake_rollback_restores_only_original_fields_with_one_new_save(self):
        with tempfile.TemporaryDirectory() as root:
            result,writer,product=helpers.AdditionalWorkflowTests().execute_case(root,crop=True)
            path=next(Path(root).glob('JOB_*'))
            preview=prepare_rollback(path,writer)
            self.assertEqual(writer.saves,1)
            receipt=apply_rollback(path,writer,confirmation_for(preview))
            self.assertEqual(receipt['status'],'ROLLBACK_MATCHED')
            self.assertEqual((writer.saves,writer.uploads),(2,1))
            self.assertEqual(product['images']['main'],['https://x/bad'])
            self.assertEqual(product['status'],'READY_TO_PUBLISH');self.assertEqual(product['weight'],0.2)
            with self.assertRaises(FileExistsError):apply_rollback(path,writer,confirmation_for(preview))
    def test_unknown_save_and_concurrent_edit_refuse_rollback(self):
        with tempfile.TemporaryDirectory() as root:
            result,writer,product=helpers.AdditionalWorkflowTests().execute_case(root,crop=True)
            path=next(Path(root).glob('JOB_*'))
            preview=prepare_rollback(path,writer)
            product['weight']=99
            with self.assertRaisesRegex(ValueError,'STATE_DRIFT'):apply_rollback(path,writer,confirmation_for(preview))
            self.assertEqual(writer.saves,1)
            journal=json.loads((path/'local_execution.json').read_text());journal['state']='APPLY_UNKNOWN'
            (path/'local_execution.json').write_text(json.dumps(journal))
            with self.assertRaisesRegex(ValueError,'READBACK'):prepare_rollback(path,writer)
