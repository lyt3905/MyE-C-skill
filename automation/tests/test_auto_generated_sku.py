import unittest,tempfile,hashlib
from pathlib import Path
from PIL import Image
from mye_c_automation.semantic_remedies import build
class GeneratedSkuCandidateTests(unittest.TestCase):
 def test_independently_observed_crop_can_supply_without_box_assignment(self):
  with tempfile.TemporaryDirectory() as root:
   path=Path(root)/'crop.png';Image.new('RGB',(800,800),'green').save(path)
   digest=hashlib.sha256(path.read_bytes()).hexdigest()
   product={'identityJson':{'modelCode':'NA-H74'},'images':{'main':['https://x/dirty'],'sku':['https://x/box']},'skus':[{'skuId':1,'skuName':'without box','skuImageUrl':'https://x/box'}]}
   class Inspector:
    def observe_image(self,path,context):return dict(clean=True,verified=True,image_type='FIGURE',model='NA-H74',sha256=digest,evidence_ids=['CROP_INDEPENDENT'])
   generated=[{'remedy_id':'CROP_BANNER:main:0','action':'CROP_BANNER','target':{'pool':'main','index':0},'candidate_asset':{'path':str(path),'sha256':digest}}]
   candidates,_,_=build(product,{'anomalies':[]},[],[],Inspector(),7,generated_remedies=generated)
   sku=next(r for r in candidates if r['action']=='SKU_ASSIGN')
   self.assertEqual(sku['assignments'],{'1':'https://x/dirty'})
   self.assertEqual(sku['assignment_evidence']['1']['sha256'],digest)
   self.assertEqual(sku['requires_remedy_ids'],['CROP_BANNER:main:0'])
 def test_sku_is_deferred_when_generated_remedy_not_authorized(self):
     from mye_c_automation.auto_decision import decide
     from mye_c_automation.automation_policy import AutomationPolicy
     from test_auto_decision import CONFIG,remedy
     row=remedy();row['requires_remedy_ids']=['MISSING_CROP']
     result=decide([row],AutomationPolicy(CONFIG),pid=1,shop=7)
     self.assertEqual(result[0]['decision'],'DEFERRED')
     self.assertIn('REMEDY_DEPENDENCY_NOT_AUTHORIZED',result[0]['reason_codes'])
 def test_missing_generated_file_cannot_supply_sku(self):
     product={'identityJson':{'modelCode':'NA-H74'},'images':{'main':['https://x/dirty']},'skus':[{'skuId':1,'skuName':'without box','skuImageUrl':'https://x/box'}]}
     class Inspector:
         def observe_image(self,*args):raise AssertionError('missing bytes must never be judged')
     generated=[{'remedy_id':'crop','action':'CROP_BANNER','target':{'pool':'main','index':0},'candidate_asset':{'path':'Z:/missing/file.png','sha256':'a'*64}}]
     candidates,_,_=build(product,{'anomalies':[]},[],[],Inspector(),7,generated_remedies=generated)
     self.assertFalse(any(r['action']=='SKU_ASSIGN' for r in candidates))
 def test_upload_budget_rejection_defers_dependent_sku(self):
     from mye_c_automation.auto_decision import decide
     from mye_c_automation.automation_policy import AutomationPolicy
     from test_auto_decision import CONFIG,remedy
     from test_auto_upload_budget_allocation import UploadBudgetAllocationTests
     crop=UploadBudgetAllocationTests().candidate(0,'a'*64)
     sku=remedy();sku.update(action='SKU_ASSIGN',remedy_id='SKU',requires_remedy_ids=[crop['remedy_id']])
     sku['checks'].update(sku_assignment_unique=True,packaging_match=True,model_match=True)
     config=dict(CONFIG,max_uploads_per_job=0,allow_actions=dict(CONFIG['allow_actions'],SKU_ASSIGN=True))
     rows=decide([crop,sku],AutomationPolicy(config),pid=1,shop=7)
     self.assertEqual([r['decision'] for r in rows],['DEFERRED','DEFERRED'])
     self.assertIn('REMEDY_DEPENDENCY_NOT_AUTHORIZED',rows[1]['reason_codes'])

 def test_generated_validator_runtime_failure_defers_sku_without_crashing(self):
  with tempfile.TemporaryDirectory() as root:
   path=Path(root)/'crop.png';Image.new('RGB',(800,800)).save(path)
   product={'identityJson':{'modelCode':'NA-H74'},'images':{'main':['https://x/a']},'skus':[{'skuId':1,'skuName':'without box','skuImageUrl':'https://x/box'}]}
   class Inspector:
    def observe_image(self,*args):raise RuntimeError('gateway budget unavailable')
   generated=[{'remedy_id':'crop','action':'CROP_BANNER','target':{'pool':'main','index':0},'candidate_asset':{'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}]
   candidates,_,_=build(product,{'anomalies':[]},[],[],Inspector(),7,generated_remedies=generated)
   self.assertFalse(any(r['action']=='SKU_ASSIGN' for r in candidates))
