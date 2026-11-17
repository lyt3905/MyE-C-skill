import importlib
import unittest
from unittest.mock import patch
class ExplicitSiteTests(unittest.TestCase):
    def test_import_does_not_discover_credentials(self):
        from mye_c_automation import site_client
        with patch('builtins.open', side_effect=AssertionError('credential read')):
            importlib.reload(site_client)
    def test_explicit_config_no_discovery_and_tls(self):
        from mye_c_automation import site_client
        cfg={'base':'https://example.invalid','user':'u','pwd':'p'}
        with patch.object(site_client,'load_cfg',side_effect=AssertionError('discovery')), patch.object(site_client._SiteTransport,'login'), patch.object(site_client.ssl,'create_default_context',wraps=site_client.ssl.create_default_context) as context:
            site=site_client.Site(cfg=cfg,verify_tls=True)
            self.assertFalse(hasattr(site,'save'))
            self.assertTrue(context.return_value is not None)
        with self.assertRaises(ValueError): site_client.Site(cfg=dict(cfg,base='http://example.invalid'),verify_tls=True)
        with self.assertRaises(ValueError): site_client.Site(cfg=cfg,verify_tls=False)
