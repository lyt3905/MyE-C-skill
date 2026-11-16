import unittest
from unittest.mock import patch
from pathlib import Path
from mye_c_automation.site_client import Site, load_cfg, _SiteTransport
from mye_c_automation.apply_token_plan import execute_plan, ApplyError
class SecurityV21(unittest.TestCase):
 def test_old_apply_denied_before_access(self):
  with self.assertRaisesRegex(ApplyError,'Legacy writes disabled'): execute_plan(None,{},Path('unused'),apply=True)
 def test_no_automatic_secrets(self):
  with self.assertRaises(RuntimeError): load_cfg()
  with self.assertRaises(RuntimeError): Site()
 def test_read_only_surface(self):
  for name in ('save','upload','status','replace_links'): self.assertFalse(hasattr(Site,name))
  with patch('mye_c_automation.site_client._SiteTransport'):
   client=Site({})
   with self.assertRaises(PermissionError): client.call('/api/admin/shops/current',{'shopId':1},method='PUT')
 def test_tls_cannot_disable(self):
  with self.assertRaises(ValueError): Site({'base':'https://example.test','user':'test','pwd':'test'},verify_tls=False)
