import tempfile,unittest,json,hashlib
from pathlib import Path
from PIL import Image,ImageDraw
from mye_c_automation.job_manager import JobManager, atomic_json
from mye_c_automation.automation_policy import AutomationPolicy
from test_auto_decision import CONFIG
from test_auto_remedy import Inspector
from mye_c_automation.candidate_quality import CandidateQualityGate
from mye_c_automation.remedy_planner import RemedyPlanner
from mye_c_automation.auto_deletions import plan_deletion
from mye_c_automation.plan_compiler import compile_auto_plan
from mye_c_automation.final_state import simulate_final_snapshot

class DeletionReindexTests(unittest.TestCase):
    def test_delete_before_crop_rebuilds_upload_target_from_stable_id(self):
        with tempfile.TemporaryDirectory() as root:
            manager=JobManager(root);job=manager.create(1,7,{})
            directory=manager.directory(job['job_id']);raw=[]
            product={'images':{'main':['https://x/banner','https://x/dirty','https://x/keep'],'detail':['https://x/detail'],'sku':['https://x/keep']}}
            for pool,urls in product['images'].items():
                for index,url in enumerate(urls):
                    image=Image.new('RGB',(1000,1000),'red' if url.endswith('banner') else 'white')
                    if not url.endswith('banner'):ImageDraw.Draw(image).rectangle((300,200,700,700),fill='blue')
                    path=directory/(pool+str(index)+'.png');image.save(path)
                    raw.append({'kind':pool,'index':index,'url':url,'file':str(path),'content_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
            atomic_json(directory/'audit_product.json',product);atomic_json(directory/'audit_raw.json',{'images':raw})
            def item(index):
                row=raw[index]
                return {'id':'WM_MAIN_'+str(index).zfill(3),'image_id':'MAIN_'+str(index).zfill(3),'pool':'main','kind':'main','index':index,'local':row['file'],'source_url':row['url'],'source_sha256':row['content_sha256'],'evidence_ids':['E'+str(index)]}
            class DeletionInspector:
                def inspect_deletion(self,*args):return {'ok':True,'is_box':False,'is_official':False,'category':'STORE_BANNER','information_preserved':True,'evidence_ids':['DELETE_DUAL']}
            deletion=plan_deletion(directory,item(0),product,raw,DeletionInspector())
            crop=RemedyPlanner(directory,CandidateQualityGate(Inspector())).plan(item(1),[],{},crop_box=[0,0,1000,900],subject_box=[300,200,701,701])
            policy=AutomationPolicy(dict(CONFIG,allow_actions=dict(CONFIG['allow_actions'],DELETE_REDUNDANT=True)))
            result=compile_auto_plan(directory,job,[deletion,crop],policy)
            self.assertTrue(result['ok'],result)
            plan=json.loads((directory/'plan.v2.json').read_text(encoding='utf-8'))
            self.assertEqual(plan['post_actions']['uploads'][0]['index'],0)
            self.assertEqual(plan['post_actions']['target_positions']['MAIN_001'],{'pool':'main','index':0})
            after=simulate_final_snapshot(product,plan,['https://x/cropped'])
            self.assertEqual(after['images']['main'],['https://x/cropped','https://x/keep'])
