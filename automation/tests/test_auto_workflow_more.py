import tempfile
import unittest
from pathlib import Path
from copy import deepcopy
from PIL import Image,ImageDraw
from mye_c_automation.job_manager import JobManager, atomic_json
from mye_c_automation.automation_policy import AutomationPolicy
from test_auto_decision import CONFIG
from test_auto_remedy import Inspector
from mye_c_automation.candidate_quality import CandidateQualityGate
from mye_c_automation.workflow_runner import run_automatic

class AdditionalWorkflowTests(unittest.TestCase):
    def execute_case(self,root,crop=False,partial=False,pid=1,generated_sku=False,account=None,audit_account=None):
        manager=JobManager(root);job=manager.create(pid,7,{'ai_requests':30,'full_resolution_images':20},mode='auto_apply')
        product={'id':pid,'shopId':7,'status':'READY_TO_PUBLISH','price':20,'weight':0.2,'images':{'main':['https://x/bad'],'detail':['https://x/dirty','https://x/clean'],'sku':['https://x/bad']},'skus':[{'skuId':1,'skuImageUrl':'https://x/bad','price':10}]}
        if generated_sku:
            product['identityJson']={'modelCode':'NA-H74'}
            product['skus'][0].update(skuName='without box',skuImageUrl='https://x/dirty')
        def auditor(pid,shop,output_dir):
            import numpy as np
            image=Image.new('RGB',(1000,1000),'white');ImageDraw.Draw(image).rectangle((300,200,700,700),fill='blue')
            random=Image.fromarray(np.random.default_rng(42).integers(0,256,(1000,1000,3),dtype=np.uint8))
            rows=[]
            for kind,index,url in [('main',0,'https://x/bad'),('detail',0,'https://x/dirty'),('detail',1,'https://x/clean')]:
                path=output_dir/(kind+str(index)+'.png');(random if kind=='detail' and (index==0 or crop) else image).save(path)
                rows.append({'file':str(path),'kind':kind,'index':index,'url':url})
            if account is not None:atomic_json(output_dir/'audit_account.json',{'account_fingerprint':audit_account or account})
            atomic_json(output_dir/'audit_product.json',product)
            atomic_json(output_dir/'audit_raw.json',{'pid':pid,'images':rows})
            atomic_json(output_dir/'audit_flags.json',{'pid':pid,'summary':{'ocr_enabled':True},'ocr_hits':[{'image':r['file']} for r in rows if r['kind']=='main' or partial and r['index']==0]})
        class Judge:
            metrics={'requests':2,'usage_available':False}
            def process_queue(self,queue,context):
                return {r['id']:({'status':'NEEDS_REVIEW','results':[]} if r['pool']=='detail' else {'status':'HIT','results':[{'task_type':'watermark','classification':'third_party_store_logo','abstain':False,'confidence':0.99}]*2}) for r in queue['items']}
        class Quality(Inspector):
            def observe_image(self,path,context):
                import hashlib
                name=Path(path).name
                clean=name.startswith(('crop_','readback_'))
                return {'verified':True,'clean':clean,'image_type':'FIGURE' if clean else 'BOX','model':'NA-H74','sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'evidence_ids':['GENERATED_DUAL']}

            def propose(self,source,context):return {'crop_box':[0,0,1000,900],'subject_box':[300,200,701,701]} if crop else {}
        class Writer:
            saves=0;uploads=0;uploaded=None
            def product(self,pid):return deepcopy(product)
            def current_shop(self):return 7
            def save(self,pid,desired,**kwargs):self.saves+=1;product.clear();product.update(deepcopy(desired))
            def upload(self,path):self.uploads+=1;self.uploaded=Path(path).read_bytes();return 'https://x/upload'
            def fetch_image(self,url):return self.uploaded if url=='https://x/upload' else (manager.directory(job['job_id'])/'detail1.png').read_bytes()
        if account is not None:Writer.account_fingerprint=lambda self:account
        writer=Writer()
        result=run_automatic(manager,job,AutomationPolicy(dict(CONFIG,allow_actions=dict(CONFIG['allow_actions'],SKU_ASSIGN=generated_sku))),writer=writer,auditor=auditor,judge=Judge(),quality_gate=CandidateQualityGate(Quality()))
        return result,writer,product
    def test_crop_upload_save_and_byte_readback(self):
        with tempfile.TemporaryDirectory() as root:
            result,writer,product=self.execute_case(root,crop=True)
            self.assertEqual(result['status'],'AUTO_VERIFIED',result)
            self.assertEqual((writer.saves,writer.uploads),(1,1))
            self.assertEqual(product['images']['main'],['https://x/upload'])
            import json
            states=json.loads(next(Path(root).glob('JOB_*/conditional_decisions.json')).read_text())['items']
            self.assertEqual(states[-1]['decision'],'AUTO_SAFE')
    def test_deferred_detail_preserved_while_main_fixed(self):
        with tempfile.TemporaryDirectory() as root:
            result,writer,product=self.execute_case(root,partial=True)
            self.assertEqual(result['status'],'PARTIALLY_AUTO_FIXED',result)
            self.assertEqual(writer.saves,1)
            self.assertEqual(product['images']['detail'][0],'https://x/dirty')
            self.assertEqual(product['images']['main'],['https://x/clean'])

    def test_generated_crop_is_assigned_to_sku_and_verified_after_upload(self):
        with tempfile.TemporaryDirectory() as root:
            result,writer,product=self.execute_case(root,crop=True,generated_sku=True)
            self.assertEqual(result['status'],'AUTO_VERIFIED',result)
            self.assertEqual((writer.saves,writer.uploads),(1,1))
            self.assertEqual(product['skus'][0]['skuImageUrl'],'https://x/upload')
