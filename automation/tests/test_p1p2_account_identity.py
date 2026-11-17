import unittest
from unittest.mock import Mock
from mye_c_automation.site_client import _SiteTransport, ReadOnlySiteClient
from mye_c_automation.executor.site_write_client import SiteWriteClient
class VerifiedAccountTests(unittest.TestCase):
 def transport(self,principal=101,base='https://example.test'):
  site=object.__new__(_SiteTransport);site.cfg={'base':base,'user':'display-name','pwd':'not-used'}
  site.call=Mock(return_value={'data':{'id':principal,'selectedShopId':7}})
  return site
 def test_P0_ACCOUNT_01_same_server_principal_has_stable_fingerprint(self):
  first=self.transport();second=self.transport();second.cfg['user']='different-display'
  self.assertEqual(first.account_fingerprint(),second.account_fingerprint())
  self.assertEqual(SiteWriteClient(first).account_fingerprint(),first.account_fingerprint())
 def test_P0_ACCOUNT_02_same_shop_or_username_does_not_mask_different_account(self):
  first=self.transport();other=self.transport(102)
  self.assertNotEqual(first.account_fingerprint(),other.account_fingerprint())
  self.assertNotEqual(first.account_fingerprint(),self.transport(base='https://other.test').account_fingerprint())
 def test_missing_or_conflicting_principal_never_uses_username_fallback(self):
  site=self.transport();site.call.return_value={'data':{'selectedShopId':7,'username':'display-name'}}
  with self.assertRaisesRegex(ValueError,'ACCOUNT'):site.account_fingerprint()
  site.call.return_value={'data':{'id':101,'user':{'id':102},'selectedShopId':7}}
  with self.assertRaisesRegex(ValueError,'ACCOUNT'):site.account_fingerprint()
 def test_P0_ACCOUNT_04_missing_current_shop_is_explicit_failure(self):
  client=SiteWriteClient(object())
  with self.assertRaisesRegex(ValueError,'SHOP_CONTEXT_UNVERIFIED'):client.current_shop()
 def test_P0_ACCOUNT_02_plan_binding_rejects_other_account_even_same_pid_shop(self):
  from mye_c_automation.executor.service import ExecutorService
  from pathlib import Path
  class Writer:
   def current_shop(self):return 7
   def account_fingerprint(self):return 'b'*64
  service=ExecutorService(None,Writer(),Path('.'))
  with self.assertRaisesRegex(ValueError,'ACCOUNT_MISMATCH'):
   service._identity({'id':1,'shopId':7},{'pid':1,'shop':7,'precondition':{'account_fingerprint':'a'*64}})
