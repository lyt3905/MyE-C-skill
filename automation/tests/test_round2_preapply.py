import unittest
import tempfile
from test_local_execution import ApplyTests
from mye_c_automation.executor.local import LocalExecutor

class PreApplyRegression(unittest.TestCase):
 def test_seven_images_rejected_before_save(self):
  with tempfile.TemporaryDirectory() as root:
   helper=ApplyTests(); w,p=helper.fixture(root)
   p['desired']={'images':dict(w.data['images'],main=['a']*7)}
   try: LocalExecutor(w,root).execute(p,helper.confirm(p))
   except ValueError: pass
   assert w.calls == 0

class MorePreApply(unittest.TestCase):
 def test_protected_field(self):
  from mye_c_automation.final_state import validate_final_snapshot
  result=validate_final_snapshot({'weight':2},context={'before':{'weight':1}})
  self.assertFalse(result['ok']);self.assertEqual(result['errors'][0]['field'],'weight')
 def test_identity_and_post_upload_drift(self):
  from PIL import Image
  from pathlib import Path
  import hashlib
  for failure in ('shop','pid','drift','empty'):
   with self.subTest(failure=failure),tempfile.TemporaryDirectory() as root:
    helper=ApplyTests(); w,p=helper.fixture(root)
    w.data=dict(w.data,id=1,shopId=7)
    from mye_c_automation.product_state import canonical_state_hash
    p['precondition']['state_sha256']=canonical_state_hash(w.data)
    if failure in ('shop','pid'):
     w.data['shopId' if failure=='shop' else 'id']=99
    else:
     asset=Path(root)/'replacement.png';Image.new('RGB',(800,800)).save(asset)
     p['desired']={'images':dict(w.data['images'])}
     p['post_actions']={'uploads':[dict(path=asset.name,sha256=hashlib.sha256(asset.read_bytes()).hexdigest(),pool='main',index=0)]}
     def upload(path):
      w.uploads+=1
      if failure=='drift':w.data['weight']=99
      return '' if failure=='empty' else 'https://example.test/new.png'
     w.upload=upload
    with self.assertRaises(ValueError):LocalExecutor(w,root).execute(p,helper.confirm(p))
    self.assertEqual(w.calls,0)
 def test_valid_upload(self):
  from PIL import Image
  from pathlib import Path
  import hashlib
  with tempfile.TemporaryDirectory() as root:
   helper=ApplyTests();w,p=helper.fixture(root)
   asset=Path(root)/'replacement.png';Image.new('RGB',(800,800)).save(asset)
   p['desired']={'images':dict(w.data['images'])}
   p['post_actions']={'uploads':[dict(path=asset.name,sha256=hashlib.sha256(asset.read_bytes()).hexdigest(),pool='main',index=0)]}
   def upload(path):w.uploads+=1;return 'https://example.test/new.png'
   w.upload=upload
   result=LocalExecutor(w,root).execute(p,helper.confirm(p))
   self.assertEqual(w.calls,1);self.assertEqual(w.uploads,1)
   self.assertEqual(w.data['images']['main'],['https://example.test/new.png'])
   self.assertEqual(result['content_review_status'],'NOT_VERIFIED')
 def test_sku_upload_preserves_other_skus(self):
  from PIL import Image
  from pathlib import Path
  import hashlib
  from mye_c_automation.product_state import canonical_state_hash
  with tempfile.TemporaryDirectory() as root:
   helper=ApplyTests();w,p=helper.fixture(root)
   w.data=dict(w.data,skus=[{'id':1,'skuImageUrl':'c','price':10},{'id':2,'skuImageUrl':'other','price':20}],images=dict(w.data['images'],sku=['c','other']))
   p['precondition']['state_sha256']=canonical_state_hash(w.data)
   asset=Path(root)/'replacement.png';Image.new('RGB',(800,800)).save(asset)
   p['desired']={'images':dict(w.data['images'])}
   p['post_actions']={'uploads':[dict(path=asset.name,sha256=hashlib.sha256(asset.read_bytes()).hexdigest(),pool='sku',index=0)]}
   w.upload=lambda path:'https://example.test/new.png'
   LocalExecutor(w,root).execute(p,helper.confirm(p))
   self.assertEqual(w.data['skus'],[{'id':1,'skuImageUrl':'https://example.test/new.png','price':10},{'id':2,'skuImageUrl':'other','price':20}])
 def test_missing_identity_and_small_upload_fail_closed(self):
  from PIL import Image
  from pathlib import Path
  import hashlib
  for failure in ('identity','small'):
   with self.subTest(failure=failure),tempfile.TemporaryDirectory() as root:
    helper=ApplyTests();w,p=helper.fixture(root)
    if failure=='identity':w.data.pop('shopId');w.data.pop('id')
    else:
     asset=Path(root)/'small.png';Image.new('RGB',(799,800)).save(asset)
     p['desired']={'images':dict(w.data['images'])}
     p['post_actions']={'uploads':[dict(path=asset.name,sha256=hashlib.sha256(asset.read_bytes()).hexdigest(),pool='main',index=0)]}
    with self.assertRaises(ValueError):LocalExecutor(w,root).execute(p,helper.confirm(p))
    self.assertEqual(w.calls,0);self.assertEqual(w.uploads,0)
