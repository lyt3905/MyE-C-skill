import unittest
from unittest.mock import patch

import sys
from pathlib import Path
from mye_c_automation.site_client import ReadOnlySiteClient


class CurrentShopAdapterTests(unittest.TestCase):
    def test_current_shop_uses_auth_me_selected_shop(self):
        client = object.__new__(ReadOnlySiteClient)
        with patch.object(client, 'call', return_value={'success': True, 'data': {'selectedShopId': 7, 'selectedShopName': 'shana1'}}) as call:
            self.assertEqual(client.current_shop(), 7)
        call.assert_called_once_with('/api/auth/me')

    def test_current_shop_fails_closed_when_selection_missing(self):
        client = object.__new__(ReadOnlySiteClient)
        with patch.object(client, 'call', return_value={'success': True, 'data': {}}):
            with self.assertRaisesRegex(ValueError, 'SHOP_CONTEXT_UNVERIFIED'):
                client.current_shop()


if __name__ == '__main__':
    unittest.main()
