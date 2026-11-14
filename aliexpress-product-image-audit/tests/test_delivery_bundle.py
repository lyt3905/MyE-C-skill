import unittest,tempfile,zipfile
from pathlib import Path
from build_sync_bundle import bundle
class DeliveryBundleTests(unittest.TestCase):
 def test_runtime_docs_requirements_and_windows_runner_included_without_local_data(self):
  with tempfile.TemporaryDirectory() as root,tempfile.TemporaryDirectory() as out:
   root=Path(root)
   for name in ['scripts/run_auto_tests.ps1','references/SOP.md','requirements-auto.txt','SKILL.md','README.md','scripts/.cache/private.json','local/site.json','work/job.json']:
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture')
   bundle(root,out)
   with zipfile.ZipFile(Path(out)/'workflow-sync-review.zip') as z:
    names=z.namelist()
   for name in ['scripts/run_auto_tests.ps1','references/SOP.md','requirements-auto.txt','SKILL.md','README.md']:self.assertIn(name,names)
   for name in ['scripts/.cache/private.json','local/site.json','work/job.json']:self.assertNotIn(name,names)
