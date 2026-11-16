import tempfile,unittest,hashlib
from pathlib import Path
from PIL import Image
from unittest.mock import Mock
from mye_c_automation.executor.service import ExecutorService
from mye_c_automation.automation_policy import AutomationPolicy
from test_auto_decision import CONFIG
import test_local_execution as helpers

class UploadReceiptTests(unittest.TestCase):
    def fixture(self,root):
        writer,plan=helpers.ApplyTests().fixture(root)
        writer.data['images']['main']=['a','a2']
        from mye_c_automation.product_state import canonical_state_hash
        plan['precondition']['state_sha256']=canonical_state_hash(writer.data)
        path=Path(root)/'asset.png';Image.new('RGB',(800,800),'white').save(path)
        ref={'path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'pool':'main','index':0}
        plan['desired']={'images':writer.product(1)['images']};plan['post_actions']={'uploads':[ref,dict(ref,index=1)]}
        writer.upload=Mock(return_value='https://fake/upload')
        return writer,plan,path
    def test_identical_asset_is_uploaded_once_for_multiple_targets(self):
        with tempfile.TemporaryDirectory() as root:
            writer,plan,path=self.fixture(root)
            result=ExecutorService(Mock(),writer,root).execute(plan,{},False)
            writer.upload.assert_called_once();self.assertEqual(result['upload_calls'],1)
            self.assertEqual(writer.calls,1)
    def test_automatic_upload_receipt_bytes_must_match_before_save(self):
        with tempfile.TemporaryDirectory() as root:
            writer,plan,path=self.fixture(root)
            policy=AutomationPolicy(CONFIG)
            plan.update(schema='token-opt-plan/v3',automation={'policy_sha256':policy.sha256,'actions':['CROP_BANNER']})
            writer.fetch_image=Mock(return_value=b'wrong uploaded bytes')
            with self.assertRaisesRegex(ValueError,'UPLOAD_HASH_MISMATCH'):
                ExecutorService(Mock(),writer,root,automation_policy=policy).execute(plan,{},False)
            self.assertEqual(writer.calls,0)
    def test_empty_upload_url_never_fetches_or_saves_and_records_failure(self):
        with tempfile.TemporaryDirectory() as root:
            writer,plan,path=self.fixture(root)
            policy=AutomationPolicy(CONFIG)
            plan.update(schema='token-opt-plan/v3',automation={'policy_sha256':policy.sha256,'actions':['CROP_BANNER']})
            writer.upload=Mock(return_value='')
            writer.fetch_image=Mock(return_value=path.read_bytes())
            with self.assertRaisesRegex(ValueError,'UPLOAD_URL_EMPTY'):
                ExecutorService(Mock(),writer,root,automation_policy=policy).execute(plan,{},False)
            writer.fetch_image.assert_not_called()
            self.assertEqual(writer.calls,0)
            import json
            receipt=json.loads((Path(root)/'upload_receipts.json').read_text())
            self.assertEqual(receipt['state'],'UPLOAD_UNKNOWN')
            self.assertEqual(receipt['upload_calls'],1)
            self.assertIn('UPLOAD_URL_EMPTY',receipt['error'])
