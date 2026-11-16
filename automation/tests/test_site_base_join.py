"""Accept the trailing slash normally copied from a browser address bar."""
import json
import unittest
from unittest.mock import MagicMock
from mye_c_automation.site_client import _SiteTransport


class SiteBaseJoinTests(unittest.TestCase):
    def test_trailing_slash_does_not_duplicate_api_separator(self):
        for base, expected in (
            ('https://example.invalid/', 'https://example.invalid/api/auth/login'),
            ('https://example.invalid/app/', 'https://example.invalid/app/api/auth/login'),
            ('https://example.invalid', 'https://example.invalid/api/auth/login'),
        ):
            with self.subTest(base=base):
                transport = object.__new__(_SiteTransport)
                transport.cfg = {'base': base}
                transport.op = MagicMock()
                transport.op.open.return_value.__enter__.return_value.read.return_value = b'{}'
                transport.call('/api/auth/login', {'username': 'fake', 'password': 'fake'})
                request = transport.op.open.call_args.args[0]
                self.assertEqual(request.full_url, expected)
                self.assertEqual(request.get_method(), 'POST')
                self.assertEqual(json.loads(request.data), {'username': 'fake', 'password': 'fake'})
