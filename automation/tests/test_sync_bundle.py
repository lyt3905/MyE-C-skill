import tempfile,unittest,json,zipfile,hashlib
from pathlib import Path
from mye_c_automation.build_sync_bundle import bundle
class SyncBundleTests(unittest.TestCase):
 def test_review_bundle_consistency_and_no_runtime_copy(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)/'source';output=Path(temp)/'output'
   (root/'scripts').mkdir(parents=True);(root/'scripts'/'x.py').write_text('x=1')
   (root/'scripts'/'work').mkdir();(root/'scripts'/'work'/'secret.json').write_text('{}')
   manifest=bundle(root,output)
   self.assertEqual([r['path'] for r in manifest],['scripts/x.py'])
   with zipfile.ZipFile(output/'workflow-sync-review.zip') as z:
    self.assertEqual(hashlib.sha256(z.read('scripts/x.py')).hexdigest(),manifest[0]['sha256'])
