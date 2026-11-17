import tempfile,json,hashlib,unittest
from pathlib import Path
from PIL import Image
import test_v21_compiler
from mye_c_automation.job_manager import atomic_json
from mye_c_automation.manual_review import evidence_hash
from mye_c_automation.plan_compiler import compile_plan
class AuthorizationTests(unittest.TestCase):
 def setup_case(self,root,decision='KEEP'):
  m,j,p=test_v21_compiler.CompilerReviewTests().fixture(root)
  product={'images':{'main':['https://old/a','https://old/b'],'detail':['https://old/d'],'sku':[]}}
  atomic_json(p/'audit_product.json',product)
  atomic_json(p/'ai_queue.json',{'items':[{'id':'X','kind':'main','index':0,'evidence_ids':['X']}]})
  r={'schema':'manual-review/v1','job_id':j['job_id'],'pid':1,'shop_id':7,'evidence_sha256':evidence_hash(p),'items':[{'item_id':'X','decision':decision,'authorized_actions':['DELETE','REPLACE_LOCAL'],'reviewed_at':'now','reviewer':'user','reason':'test','evidence_ids':['X']}],'changes':[{'field':'images','action':'DELETE','target':{'pool':'main','index':0},'value':{'main':['https://old/b'],'detail':['https://old/d'],'sku':[]},'item_ids':['X']}]}
  return j,p,r,product
 def test_keep_delete_and_replace_rejected(self):
  for action in ['DELETE','REPLACE_LOCAL']:
   with tempfile.TemporaryDirectory() as root:
    j,p,r,_=self.setup_case(root);r['changes'][0]['action']=action
    self.assertIn('ACTION_NOT_AUTHORIZED',compile_plan(p,j,r)['error_codes'])
 def test_replace_asset_and_missing_hash(self):
  with tempfile.TemporaryDirectory() as root:
   j,p,r,product=self.setup_case(root,'REPLACE_LOCAL');Image.new('RGB',(800,800)).save(p/'replacement.jpg')
   change=r['changes'][0];change.update(action='REPLACE_LOCAL',value=product['images'],asset={'path':'replacement.jpg','sha256':hashlib.sha256((p/'replacement.jpg').read_bytes()).hexdigest(),'pool':'main','index':0})
   r['items'][0]['asset']=dict(change['asset'])
   self.assertTrue(compile_plan(p,j,r)['ok']);plan=json.loads((p/'plan.v2.json').read_text());self.assertEqual(plan['post_actions']['uploads'][0]['index'],0)
   del change['asset']['sha256'];r['items'][0]['asset']=dict(change['asset'])
   with self.assertRaisesRegex(ValueError,'asset'):compile_plan(p,j,r)
 def test_manifest_dynamic_change_invalidates_review(self):
  with tempfile.TemporaryDirectory() as root:
   j,p,r,_=self.setup_case(root)
   atomic_json(p/'template_scan.json',{'status':'CLEAN'})
   atomic_json(p/'evidence_manifest.json',{'schema':'evidence-manifest/v1','files':[{'path':'template_scan.json'}],'sources':[]})
   r['evidence_sha256']=evidence_hash(p)
   atomic_json(p/'template_scan.json',{'status':'HIT'})
   with self.assertRaisesRegex(ValueError,'evidence changed'):compile_plan(p,j,r)


 def test_legacy_review_without_manifest_rejected(self):
  with tempfile.TemporaryDirectory() as root:
   j,p,r,_=self.setup_case(root)
   (p/'evidence_manifest.json').unlink()
   r['evidence_sha256']=evidence_hash(p)
   with self.assertRaisesRegex(ValueError,'EVIDENCE_MANIFEST_REQUIRED'):compile_plan(p,j,r)
 def test_description_exact_url_mapping_only(self):
  with tempfile.TemporaryDirectory() as root:
   j,p,r,product=self.setup_case(root,'REMOVE_CANDIDATE_CONFIRMED')
   old='https://old.example/path/a.jpg';new='https://new.example/path/a.jpg'
   product['descriptionJson']={'blocks':[{'url':old,'text':'keep'},{'url':'https://other.example/a.jpg'}]}
   atomic_json(p/'audit_product.json',product);r['evidence_sha256']=evidence_hash(p)
   r['items'][0].update(authorized_actions=['REPLACE_DESCRIPTION_URL'],url_replacements={old:new})
   desired={'blocks':[{'url':new,'text':'keep'},{'url':'https://other.example/a.jpg'}]}
   r['changes']=[{'field':'descriptionJson','action':'REPLACE_DESCRIPTION_URL','item_ids':['X'],'url_replacements':{old:new},'value':desired}]
   with self.assertRaisesRegex(ValueError,'forbidden'):compile_plan(p,j,r)
   desired['blocks'][0]['text']='deleted content'
   with self.assertRaisesRegex(ValueError,'forbidden'):compile_plan(p,j,r)
   desired['blocks'][0]['text']='keep'
   r['items'][0]['url_replacements']=r['changes'][0]['url_replacements']={'a.jpg':new}
   with self.assertRaisesRegex(ValueError,'forbidden'):compile_plan(p,j,r)
