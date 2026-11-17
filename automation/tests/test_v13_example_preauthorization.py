import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mye_c_automation.automation_policy import AutomationPolicy
from mye_c_automation import workflow_runner


EXAMPLE = __import__('mye_c_automation.resources',fromlist=['resource_path']).resource_path('config/automation.v1.example.json')


class ExamplePreauthorizationTests(unittest.TestCase):
    def test_shipped_example_allows_preview_but_not_execution(self):
        policy = AutomationPolicy.load(EXAMPLE)
        actions = [name for name, allowed in policy.config['allow_actions'].items() if allowed]
        self.assertTrue(actions)
        self.assertEqual(policy.authorize(3527, 7, actions, execution=False), policy.sha256)
        with self.assertRaisesRegex(ValueError, '^AUTO_APPLY_DISABLED$'):
            policy.authorize(3527, 7, actions)

    def test_standard_cli_refuses_copied_example_before_site_client(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            copied = root / 'automation.json'
            copied.write_bytes(EXAMPLE.read_bytes())
            site = root / 'site.json'
            site.write_text('{}', encoding='utf-8')
            argv = ['workflow_runner', '--root', str(root / 'jobs'), 'run',
                    '--pid', '3527', '--shop', '7', '--mode', 'auto_apply',
                    '--automation-config', str(copied), '--site-config', str(site)]
            with patch('sys.argv', argv), patch('mye_c_automation.site_client._SiteTransport') as transport:
                with self.assertRaisesRegex(ValueError, '^AUTO_APPLY_DISABLED$'):
                    workflow_runner.main()
                transport.assert_not_called()
            self.assertEqual(list((root / 'jobs').glob('JOB_*')), [])
