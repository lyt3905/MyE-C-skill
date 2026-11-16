"""Acceptance contracts introduced by extraction; no original directory access."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

class IndependentSoftwareTests(unittest.TestCase):
    def test_installed_cli_runs_outside_project(self):
        with tempfile.TemporaryDirectory() as cwd:
            p=subprocess.run([sys.executable,'-m','mye_c_automation','--help'],cwd=cwd,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertIn('fake',p.stdout)

    def test_resources_and_record_only_model_initialization(self):
        from mye_c_automation.resources import resource_path
        from mye_c_automation.ai_judge.image_action_decision import CONFIDENCE_POLICY,PROMPT
        from mye_c_automation.model_config import review_models
        self.assertEqual(CONFIDENCE_POLICY,'RECORD_ONLY')
        self.assertTrue(PROMPT)
        self.assertEqual(tuple(review_models(('deepseek-v4.1-flash','mimo-v2.6-pro'))),('deepseek-v4.1-flash',))
        self.assertTrue(resource_path('config/schemas/image-action-decision.v2.schema.json').is_file())

    def test_fake_twin_cli_saves_without_upload_and_independently_reads(self):
        with tempfile.TemporaryDirectory() as root:
            p=subprocess.run([sys.executable,'-m','mye_c_automation','fake','--scenario','twin','--data-root',root],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            out=json.loads(p.stdout)
            self.assertEqual(out['status'],'AUTO_VERIFIED')
            self.assertEqual(out['uploads'],0)
            self.assertEqual(out['saves'],1)
            self.assertGreater(out['independent_reads'],0)
            self.assertGreater(out['independent_readbacks'],0)
            self.assertTrue(Path(out['report']).is_relative_to(Path(root)))
            job=Path(out['report']).parent
            self.assertTrue((job/'full_visual_versions.json').is_file())
            self.assertTrue((job/'budget.sqlite').is_file())

    def test_frame_demo_has_no_twin_and_deletes_without_upload(self):
        with tempfile.TemporaryDirectory() as root:
            p=subprocess.run([sys.executable,'-m','mye_c_automation','fake','--scenario','frame','--data-root',root],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            out=json.loads(p.stdout);job=Path(out['report']).parent
            self.assertEqual(out['status'],'AUTO_VERIFIED')
            self.assertEqual((out['saves'],out['uploads']),(1,0))
            self.assertFalse(json.loads((job/'full_visual_versions.json').read_text())['matches'])
            decisions=json.loads((job/'auto_decisions.json').read_text())['items']
            self.assertTrue(any(r['action']=='DELETE' and r['decision']=='AUTO_SAFE' for r in decisions))

    def test_repair_demo_uploads_once_and_verifies_protected_fields(self):
        with tempfile.TemporaryDirectory() as root:
            p=subprocess.run([sys.executable,'-m','mye_c_automation','fake','--scenario','repair','--data-root',root],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            out=json.loads(p.stdout);job=Path(out['report']).parent
            self.assertEqual(out['status'],'AUTO_VERIFIED')
            self.assertEqual((out['saves'],out['uploads']),(1,1))
            checked=json.loads((job/'content_validation.json').read_text())
            self.assertTrue(checked['ok'])
            self.assertTrue(checked['protected_fields_exact'])

    def test_data_defaults_never_use_package_install_directory(self):
        from mye_c_automation.paths import data_root
        from mye_c_automation import __file__ as package_file
        self.assertFalse(data_root().is_relative_to(Path(package_file).parent))

if __name__=='__main__':unittest.main()
