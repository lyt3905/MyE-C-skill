import unittest
from unittest.mock import Mock
from site_client import _SiteTransport
class ScopeWireTests(unittest.TestCase):
 def test_SCOPE_06_original_description_is_transmitted_without_parsing(self):
  for value in [' invalid JSON { ',{'opaque':['https://x/old']},None]:
   with self.subTest(value=value):
    site=object.__new__(_SiteTransport);product={'id':1,'descriptionJson':value,'images':{'main':['https://x/old'],'detail':['https://x/detail'],'sku':[]},'skus':[]}
    site.product=Mock(return_value=product);site.call=Mock(return_value={'success':True})
    site.save(1,images={'main':['https://x/new']})
    body=site.call.call_args.args[1];self.assertEqual(body['descriptionJson'],value);self.assertIs(type(body['descriptionJson']),type(value))
 def test_SCOPE_07_direct_writer_cannot_override_fixed_description(self):
  for arguments in [{'desc':'changed'},{'extra':{'descriptionJson':'changed'}}]:
   with self.subTest(arguments=arguments):
    site=object.__new__(_SiteTransport);site.product=Mock(return_value={'id':1,'descriptionJson':'original','images':{}});site.call=Mock()
    with self.assertRaisesRegex(ValueError,'DESCRIPTION'):site.save(1,**arguments)
    site.call.assert_not_called()
