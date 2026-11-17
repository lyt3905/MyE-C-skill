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

class AutoWorkflowTests(unittest.TestCase):
    def test_real_queue_twin_to_fake_executor_and_readback(self):
        with tempfile.TemporaryDirectory() as root:
            manager=JobManager(root);job=manager.create(1,7,{'ai_requests':10,'full_resolution_images':10},mode='auto_apply')
            product={'id':1,'shopId':7,'status':'READY_TO_PUBLISH','price':20,'weight':0.2,'images':{'main':['https://x/bad'],'detail':['https://x/clean'],'sku':['https://x/bad']},'skus':[{'skuId':1,'skuImageUrl':'https://x/bad','price':10}]}
            def auditor(pid,shop,output_dir):
                image=Image.new('RGB',(1000,1000),'white');ImageDraw.Draw(image).rectangle((300,200,700,700),fill='blue')
                rows=[]
                for kind,url in [('main','https://x/bad'),('detail','https://x/clean')]:
                    path=output_dir/(kind+'.png');image.save(path)
                    rows.append({'file':str(path),'kind':kind,'index':0,'url':url})
                atomic_json(output_dir/'audit_product.json',product)
                atomic_json(output_dir/'audit_raw.json',{'pid':pid,'images':rows})
                atomic_json(output_dir/'audit_flags.json',{'pid':pid,'summary':{'ocr_enabled':True},'ocr_hits':[{'image':rows[0]['file']}]})
            class Judge:
                metrics={'requests':2,'usage_available':False}
                def process_queue(self,queue,context):
                    return {row['id']:{'status':'HIT','results':[{'task_type':'watermark','classification':'third_party_store_logo','abstain':False,'confidence':0.99}]*2} for row in queue['items']}
            class Writer:
                saves=0;uploads=0
                def product(self,pid): return deepcopy(product)
                def current_shop(self):return 7
                def save(self,pid,desired,**kwargs):self.saves+=1;product.clear();product.update(deepcopy(desired))
                def upload(self,path):self.uploads+=1;return 'https://x/upload'
                def fetch_image(self,url):return (manager.directory(job['job_id'])/'detail.png').read_bytes()
            writer=Writer()
            result=run_automatic(manager,job,AutomationPolicy(CONFIG),writer=writer,auditor=auditor,judge=Judge(),quality_gate=CandidateQualityGate(Inspector()))
            self.assertEqual(result['status'],'AUTO_VERIFIED')
            self.assertEqual(writer.saves,1);self.assertEqual(writer.uploads,0)
            self.assertEqual(product['images']['main'],['https://x/clean'])
            self.assertEqual(product['skus'][0]['skuImageUrl'],'https://x/clean')
            self.assertEqual(product['status'],'READY_TO_PUBLISH');self.assertEqual(product['weight'],0.2)
