import sys
import unittest
from pathlib import Path
from mye_c_automation.final_state import validate_final_snapshot

class RequiredPoolTests(unittest.TestCase):
    def test_missing_required_pools_fail_closed(self):
        for images in (None, {}, {'main':['https://x/a']}, {'main':['https://x/a'],'detail':['https://x/b']}):
            snapshot={'skus':[{'skuImageUrl':'https://x/c'}]}
            if images is not None: snapshot['images']=images
            with self.subTest(images=images):
                self.assertFalse(validate_final_snapshot(snapshot, context={'before':snapshot})['ok'])

    def test_complete_pools_pass(self):
        snapshot={'images':{'main':['https://x/a'],'detail':['https://x/b'],'sku':['https://x/c']},'skus':[{'skuImageUrl':'https://x/c'}]}
        self.assertTrue(validate_final_snapshot(snapshot,context={'before':snapshot})['ok'])
    def test_missing_pool_rejected_before_upload_or_save(self):
        import tempfile
        from unittest.mock import Mock
        from test_local_execution import ApplyTests
        from mye_c_automation.executor.local import LocalExecutor
        for missing in ('main','detail','sku'):
            with self.subTest(missing=missing),tempfile.TemporaryDirectory() as root:
                helper=ApplyTests();writer,plan=helper.fixture(root)
                writer.data['skus']=[{'skuId':1,'skuImageUrl':writer.data['images']['main'][0]}]
                from mye_c_automation.product_state import canonical_state_hash
                plan['precondition']['state_sha256']=canonical_state_hash(writer.data)
                images=dict(writer.data['images']);images.pop(missing,None)
                plan['desired']={'images':images}
                writer.upload=Mock()
                with self.assertRaises(ValueError):LocalExecutor(writer,root).execute(plan,helper.confirm(plan))
                writer.upload.assert_not_called();self.assertEqual(writer.calls,0)
