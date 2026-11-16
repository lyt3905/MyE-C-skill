import tempfile
import unittest
from pathlib import Path
from copy import deepcopy
from PIL import Image
from mye_c_automation.job_manager import JobManager, atomic_json
from mye_c_automation.automation_policy import AutomationPolicy
from test_auto_decision import CONFIG
from test_auto_remedy import Inspector
from mye_c_automation.candidate_quality import CandidateQualityGate
from mye_c_automation.workflow_runner import run_automatic

class SemanticWorkflowTests(unittest.TestCase):
    def execute_case(self,root,kind,snapshot_rows=False,snapshot_readback=None):
        manager=JobManager(root);job=manager.create(1,7,{'ai_requests':30,'full_resolution_images':20},mode='auto_apply')
        product={'id':1,'shopId':7,'status':'PENDING','title':'NA-H74 威震天','titleEn':'Old title','identityJson':{'logoCode':'keep','modelCode':'NA-H74'},'images':{'main':['https://x/box'],'detail':['https://x/body'],'sku':['https://x/box']},'skus':[{'skuId':1,'skuName':'without box','skuImageUrl':'https://x/box','price':10},{'skuId':2,'skuName':'with box','skuImageUrl':'https://x/box','price':12}]}
        if kind in {'title','brand'}:product['skus']=[]
        if kind=='brand':product['brandId']=200014695
        if snapshot_rows:
            for index,sku in enumerate(product['skus']):
                sku.pop('skuId');sku.update(id=None,originalBox=index==1)
        def auditor(pid,shop,output_dir):
            rows=[]
            for pool,url in [('main','https://x/box'),('detail','https://x/body')]:
                path=output_dir/(pool+'.png');Image.new('RGB',(800,800),'blue' if pool=='main' else 'green').save(path)
                rows.append({'file':str(path),'kind':pool,'index':0,'url':url})
            flags={'pid':pid,'summary':{'ocr_enabled':True},'anomalies':[{'type':'title_prefix'}] if kind=='title' else [{'type':'brand_rule'}] if kind=='brand' else [],'product_checks':{'title_identity_brand':{'semantic_review_required':kind=='title'}}}
            atomic_json(output_dir/'audit_product.json',product);atomic_json(output_dir/'audit_raw.json',{'pid':pid,'images':rows});atomic_json(output_dir/'audit_flags.json',flags)
        class Judge:
            metrics={'requests':0,'usage_available':False}
            def process_queue(self,queue,context):return {r['id']:{'status':'NEEDS_REVIEW','results':[]} for r in queue['items']}
        class Quality(Inspector):
            def validate_title(self,product,generated):return {'ok':True,'evidence_ids':['TITLE_DUAL']}
            def validate_brand(self,product,generated):return {'ok':True,'evidence_ids':['BRAND_DUAL']}
            def observe_image(self,path,context):return {'clean':True,'verified':True,'image_type':'BOX' if Path(path).stem=='main' else 'FIGURE','model':'NA-H74','evidence_ids':['DUAL_MODEL'],'sha256':__import__('hashlib').sha256(Path(path).read_bytes()).hexdigest()}
        class Writer:
            saves=0;translations=0
            def product(self,pid):return deepcopy(product)
            def current_shop(self):return 7
            def save(self,pid,desired,**kwargs):
                self.saves+=1;product.clear();product.update(deepcopy(desired))
                if snapshot_readback=='reorder':product['skus'].reverse()
                if snapshot_readback=='price':product['skus'][0]['price']+=1
            def translate(self,pid,title):self.translations+=1;product['titleTranslationZh']='热销 NA-H74 威震天'
            def fetch_image(self,url):return (manager.directory(job['job_id'])/('main.png' if url=='https://x/box' else 'detail.png')).read_bytes()
        writer=Writer();config=dict(CONFIG,allow_actions=dict(CONFIG['allow_actions'],TITLE_REWRITE=True,SKU_ASSIGN=True,BRAND_CODE=True))
        if snapshot_rows:config['allow_snapshot_sku_rows']=True
        result=run_automatic(manager,job,AutomationPolicy(config),writer=writer,auditor=auditor,judge=Judge(),quality_gate=CandidateQualityGate(Quality()))
        return result,writer,product
    def test_title_workflow_saves_once_and_translates_once(self):
        with tempfile.TemporaryDirectory() as root:
            result,writer,product=self.execute_case(root,'title')
            self.assertEqual(result['status'],'AUTO_VERIFIED',result)
            self.assertEqual((writer.saves,writer.translations),(1,1))
            self.assertIn('Megatank',product['titleEn']);self.assertEqual(product['title'],'NA-H74 威震天')
    def test_sku_workflow_repairs_shared_box(self):
        with tempfile.TemporaryDirectory() as root:
            result,writer,product=self.execute_case(root,'sku')
            self.assertEqual(result['status'],'AUTO_VERIFIED',result)
            self.assertEqual(writer.saves,1);self.assertEqual(writer.translations,0)
            self.assertEqual(product['skus'][0]['skuImageUrl'],'https://x/body')
            self.assertEqual(product['skus'][1]['skuImageUrl'],'https://x/box')
