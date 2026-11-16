import unittest
from mye_c_automation.audit_one import _image_urls
from mye_c_automation.final_state import simulate_final_snapshot, validate_final_snapshot
class ScopeV12Tests(unittest.TestCase):
 def product(self):
  return {'images':{'main':['https://x/main'],'detail':['https://x/detail'],'sku':['https://x/sku'],'ai':['https://x/ai'],'scene':['https://x/scene']},'skus':[{'skuImageUrl':'https://x/sku'}],'descriptionJson':{'blocks':[{'type':'image','url':'https://x/main'},{'type':'image','url':'https://x/404.jpg'}]}}
 def test_SCOPE_01_02_08_only_three_pools_and_no_description_urls(self):
  rows=_image_urls(self.product())
  self.assertEqual({r['kind'] for r in rows},{'main','detail','sku'})
  self.assertEqual({r['url'] for r in rows},{'https://x/main','https://x/detail','https://x/sku'})
 def test_SCOPE_04_06_upload_preserves_description_type_and_value(self):
  from copy import deepcopy
  for description in ['not json',{'blocks':[{'url':'https://x/main'}]},None]:
   with self.subTest(description=description):
    p=self.product();p['descriptionJson']=description;before=deepcopy(p)
    result=simulate_final_snapshot(p,{'desired':{},'post_actions':{'uploads':[{'pool':'main','index':0}]}},['https://x/new'])
    self.assertEqual(result['descriptionJson'],description)
    self.assertIs(type(result['descriptionJson']),type(description))
    self.assertEqual(result['images']['main'],['https://x/new'])
    self.assertEqual(result['images']['ai'],before['images']['ai'])
 def test_SCOPE_03_invalid_description_is_opaque(self):
  p=self.product();p['descriptionJson']='not JSON { invalid'
  self.assertTrue(validate_final_snapshot(p,context={'before':p})['ok'])

 def test_SCOPE_08_auxiliary_values_are_opaque_but_protected(self):
  from copy import deepcopy
  p=self.product();p['images']['ai']={'vendor':'opaque'};p['images']['scene']='not an image list'
  self.assertTrue(validate_final_snapshot(p,context={'before':p})['ok'])
  changed=deepcopy(p);changed['images']['ai']={}
  self.assertFalse(validate_final_snapshot(changed,context={'before':p})['ok'])
