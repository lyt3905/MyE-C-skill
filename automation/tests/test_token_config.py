import unittest
from mye_c_automation.workflow_runner import configured_limits

class TokenConfigTests(unittest.TestCase):
    def test_explicit_token_limit_is_enforced_resource(self):
        self.assertEqual(configured_limits({'limits': {'ai_requests': 45}, 'token_limit': 123})['total_tokens'], 123)
        self.assertNotIn('total_tokens', configured_limits({'limits': {}, 'token_limit': None}))
        for invalid in (0, -1, True, '5'):
            with self.assertRaises(ValueError):
                configured_limits({'limits': {}, 'token_limit': invalid})
