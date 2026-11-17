"""User selected CLI delivery; desktop draft remains out of active runtime."""
import json,subprocess,sys,tempfile,unittest
from pathlib import Path

class CliDeliveryScopeTests(unittest.TestCase):
    def test_active_help_has_setup_and_workflow_but_no_desktop_command(self):
        p=subprocess.run([sys.executable,'-m','mye_c_automation','--help'],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('configure',p.stdout);self.assertIn('workflow',p.stdout)
        self.assertNotIn(' ui ',p.stdout)
        p=subprocess.run([sys.executable,'-m','mye_c_automation','ui','--help'],capture_output=True,text=True)
        self.assertEqual(p.returncode,2)

    def test_desktop_module_is_not_in_active_package(self):
        import mye_c_automation
        root=Path(mye_c_automation.__file__).parent
        self.assertFalse((root/'desktop.py').exists())
        self.assertFalse((root/'desktop_data.py').exists())
