import unittest,tempfile
from budget_manager import BudgetManager
class Round2BudgetTests(unittest.TestCase):
 def test_zero_and_unknown(self):
  b=BudgetManager({'total_tokens':100})
  self.assertEqual(b.snapshot()['token_status'],'NOT_CALLED')
  b.reserve_tokens(10);b.settle_tokens(10,0)
  self.assertEqual(b.snapshot()['token_status'],'ACTUAL_ZERO')
  b.reserve_tokens(10);b.settle_tokens(10,None)
  self.assertEqual(b.snapshot()['token_status'],'UNKNOWN')
  b.close()
 def test_block_no_retry(self):
  from ai_judge.client import JudgeClient
  calls=[]
  with tempfile.TemporaryDirectory() as root:
   b=BudgetManager({'ai_requests':0})
   c=JudgeClient(b,root,transport=lambda *args:calls.append(args))
   result=c.classify('watermark',{'id':'a','evidence_ids':[],'dimensions':[800,800]},{})
   self.assertEqual(result['error'],'BUDGET_EXCEEDED')
   self.assertEqual(calls,[]);self.assertEqual(c.metrics['retries'],0)
   b.close()

 def test_unused_token_reservation_released(self):
  from ai_judge.client import JudgeClient
  with tempfile.TemporaryDirectory() as root:
   b=BudgetManager({'ai_requests':0,'total_tokens':10000})
   c=JudgeClient(b,root,transport=lambda *args:self.fail('must not call'))
   c.classify('watermark',{'id':'x','evidence_ids':[],'dimensions':[800,800]},{})
   self.assertEqual(b.snapshot()['used']['total_tokens'],0)
   self.assertEqual(c.metrics['requests'],0)
   b.close()
 def test_sku_unknown_image_rejected(self):
  from ai_judge.schemas import validate_result
  result={'task_type':'sku_match','item_id':'x','confidence':1,'abstain':False,'evidence_ids':['x'],'decision':'MATCH','sku_id':'s','image_id':'unknown'}
  with self.assertRaises(ValueError):
   validate_result(result,'sku_match','x',{'sku_id':'s','image_id':'known','evidence_ids':['x']})

 def test_template_source_bound_in_manifest(self):
  import json,hashlib,numpy as np
  from pathlib import Path
  from evidence_builder import build
  with tempfile.TemporaryDirectory() as root:
   root=Path(root); source=root/'template.npy'
   np.save(source,np.zeros((2,2),dtype=np.float32))
   build(root,[],templates=[{'path':str(source),'shop_id':7}],shop_id=7)
   manifest=json.loads((root/'evidence_manifest.json').read_text())
   template=next(row for row in manifest['sources'] if row.get('kind')=='template')
   self.assertEqual(template['source'],str(source.resolve()))
   self.assertEqual(template['sha256'],hashlib.sha256(source.read_bytes()).hexdigest())
   source.write_bytes(b'changed')
   self.assertNotEqual(template['sha256'],hashlib.sha256(source.read_bytes()).hexdigest())
