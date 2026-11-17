import io,json,tempfile,unittest,hashlib
from pathlib import Path
from copy import deepcopy
import numpy as np
from PIL import Image,ImageDraw
from mye_c_automation.audit_one import audit
from mye_c_automation.workflow_runner import run_automatic
from mye_c_automation.job_manager import JobManager
from mye_c_automation.automation_policy import AutomationPolicy
from mye_c_automation.candidate_quality import CandidateQualityGate
from test_auto_decision import CONFIG
from test_auto_remedy import Inspector

class RealAuditorWorkflowTests(unittest.TestCase):
    def execute(self,root,mode,shop=7,pid=1,coordination_key=None,shop_context=None,save_timeout=False):
        root=Path(root);blobs={}
        clean=Image.new('RGB',(1000,1000),'white');ImageDraw.Draw(clean).rectangle((300,200,700,700),fill='blue')
        dirty=clean.copy();ImageDraw.Draw(dirty).rectangle((10,10,13,13),fill='red')
        other=Image.fromarray(np.random.default_rng(42).integers(0,256,(1000,1000,3),dtype=np.uint8))
        for url,image in [('https://fake/bad',dirty),('https://fake/other',other)]:
            data=io.BytesIO();image.save(data,format='PNG');blobs[url]=data.getvalue()
        product={'id':pid,'shopId':shop,'status':'READY_TO_PUBLISH','title':'NA-H74 威震天','titleEn':'Hot Sale Transformation NA-H74 NAH74 Megatank Action Figures Collection Gifts','titleTranslationZh':'热销 NA-H74 威震天','brand':'200017853','identityJson':{'logoCode':'keep','modelCode':'NA-H74'},'images':{'main':['https://fake/bad'],'detail':['https://fake/other'],'sku':['https://fake/other']},'skus':[],'descriptionJson':{'blocks':[]}}
        class Site:
            def product(self,pid):return deepcopy(product)
            def current_shop(self):return shop_context['shop'] if shop_context is not None else shop
            def download(self,url,path):Path(path).write_bytes(blobs[url])
        if mode.startswith('delete'):
            data=io.BytesIO();Image.new('RGB',(1000,1000),'red').save(data,format='PNG');blobs['https://fake/bad']=data.getvalue()
            data=io.BytesIO();clean.save(data,format='PNG');blobs['https://fake/body']=data.getvalue()
            product['images']['main'].append('https://fake/body')
            if mode=='delete_seven':product['images']['main']+=['https://fake/body']*5
            product['descriptionJson']={'blocks':[{'type':'image','url':'https://fake/bad'},{'type':'text','text':'keep'}]}
        if mode=='clean':
            data=io.BytesIO();clean.save(data,format='PNG');blobs['https://fake/bad']=data.getvalue();blobs['https://fake/other']=data.getvalue()
        if mode=='disagreement':
            ImageDraw.Draw(other).rectangle((10,10,13,13),fill='red')
            data=io.BytesIO();other.save(data,format='PNG');blobs['https://fake/other']=data.getvalue()
        site=Site()
        class OCR:
            def __call__(self,image):
                red=(image[:,:,2]>240)&(image[:,:,1]<20)&(image[:,:,0]<20)
                return ([[[[10,10],[60,10],[60,30],[10,30]],'Third Party Store',.99]] if red.any() else [],None)
        def auditor(pid,shop,output_dir):
            if shop_context is not None:
                import time
                shop_context['shop']=shop;time.sleep(.03)
            return audit(pid,shop,output_dir=output_dir,site=site,downloader=site.download,ocr_factory=OCR)
        class Judge:
            metrics={'requests':0,'usage_available':False}
            def process_queue(self,queue,context):
                if mode=='disagreement':
                    return {r['id']:{'status':'HIT','results':[{'task_type':'watermark','classification':'third_party_store_logo','confidence':.99,'abstain':False},{'task_type':'watermark','classification':'manufacturer_branding' if r.get('source_url')=='https://fake/other' else 'third_party_store_logo','confidence':.99,'abstain':False}]} for r in queue['items']}
                return {r['id']:{'status':'HIT' if r.get('source_url')=='https://fake/bad' and mode!='clean' else 'CLEAN','results':[{'task_type':'watermark','classification':'third_party_store_logo' if r.get('source_url')=='https://fake/bad' and mode!='clean' else 'manufacturer_branding','confidence':.99,'abstain':False}]*2} for r in queue['items']}
        class Quality(Inspector):
            def inspect(self,*args):
                result=super().inspect(*args)
                if mode=='official_dirty' or mode.startswith('delete'):result['source_clean']=False
                return result
            def inspect_deletion(self,*args,**kwargs):return {'ok':True,'is_box':mode=='delete_box','is_official':False,'category':'STORE_BANNER','information_preserved':True,'evidence_ids':['INDEPENDENT_DELETE']}
            def propose(self,*args):return {'subject_box':[300,200,701,701],'erase_box':[0,0,60,60]} if mode in {'erase','disagreement'} else {}
        class Writer:
            saves=0;uploads=0
            def __init__(self):
                if coordination_key:self.coordination_key=coordination_key
            def product(self,pid):return site.product(pid)
            def current_shop(self):return shop_context['shop'] if shop_context is not None else shop
            def save(self,pid,value,**kwargs):
                if shop_context is not None:
                    assert shop_context['shop']==shop
                    shop_context['saves'].append((pid,shop_context['shop']))
                self.saves+=1;product.clear();product.update(deepcopy(value))
                if save_timeout:raise TimeoutError('Fake commit completed but response lost')
            def upload(self,path):self.uploads+=1;blobs['https://fake/upload']=Path(path).read_bytes();return 'https://fake/upload'
            def fetch_image(self,url):return blobs[url]
        config=dict(CONFIG,shop_allowlist=[4,7],allow_actions=dict(CONFIG['allow_actions'],ERASE_LOCAL=mode in {'erase','disagreement'},REPLACE_LOCAL=True,DELETE_REDUNDANT=mode.startswith('delete')))
        if mode.startswith('official'):
            official=root/'official.png';root.mkdir(parents=True,exist_ok=True);clean.save(official)
            index=root/'official-pool.json';index.write_text(json.dumps({'schema':'official-image-pool/v1','items':[{'file':str(official),'sha256':hashlib.sha256(official.read_bytes()).hexdigest(),'official_source':True,'source_url':'https://maker/official','model':'NA-H74','packaging_type':'FIGURE'}]}),encoding='utf-8')
            config['local_pool_index']=str(index)
        manager=JobManager(root/'jobs');job=manager.create(pid,shop,{'ai_requests':20,'full_resolution_images':20},mode='auto_apply')
        writer=Writer();result=run_automatic(manager,job,AutomationPolicy(config),writer=writer,auditor=auditor,judge=Judge(),quality_gate=CandidateQualityGate(Quality()))
        return result,writer,manager.directory(job['job_id'])
    def test_background_trial_from_real_auditor_to_fake_writer(self):
        with tempfile.TemporaryDirectory() as root:
            result,writer,path=self.execute(root,'erase')
            self.assertEqual(result['status'],'AUTO_VERIFIED',result);self.assertEqual((writer.saves,writer.uploads),(1,1))
            self.assertTrue(json.loads((path/'audit_flags.json').read_text(encoding='utf-8'))['ocr_hits'])
    def test_official_local_pool_from_real_auditor_to_fake_writer(self):
        with tempfile.TemporaryDirectory() as root:
            result,writer,path=self.execute(root,'official')
            self.assertEqual(result['status'],'AUTO_VERIFIED',result);self.assertEqual((writer.saves,writer.uploads),(1,1))

    def test_E33_dirty_official_pool_is_rejected_in_real_auditor_workflow(self):
        with tempfile.TemporaryDirectory() as root:
            result,writer,path=self.execute(root,'official_dirty')
            self.assertEqual(result['status'],'DEFERRED',result)
            self.assertEqual((writer.saves,writer.uploads),(0,0))
            rows=json.loads((path/'mye_c_automation.candidate_quality.json').read_text(encoding='utf-8'))['items']
            self.assertTrue(any(r['action']=='REPLACE_LOCAL' and not r['ok'] for r in rows))
            self.assertEqual(writer.product(1)['images']['main'],['https://fake/bad'])

    def test_safe_deletion_from_real_auditor_preserves_description_structure(self):
        with tempfile.TemporaryDirectory() as root:
            result,writer,path=self.execute(root,'delete')
            self.assertEqual(result['status'],'AUTO_VERIFIED',result)
            self.assertEqual((writer.saves,writer.uploads),(1,0))
            after=writer.product(1)
            self.assertEqual(after['images']['main'],['https://fake/body'])
            self.assertEqual(after['descriptionJson'],{'blocks':[{'type':'image','url':'https://fake/bad'},{'type':'text','text':'keep'}]})  # v1.2: deletion never propagates

    def test_E10_box_deletion_is_deferred_in_real_auditor_workflow(self):
        with tempfile.TemporaryDirectory() as root:
            result,writer,path=self.execute(root,'delete_box')
            self.assertEqual(result['status'],'DEFERRED',result)
            self.assertEqual((writer.saves,writer.uploads),(0,0))
            self.assertIn('https://fake/bad',writer.product(1)['images']['main'])

    def test_E09_seven_main_can_save_only_after_safe_deletion_repairs_count(self):
        with tempfile.TemporaryDirectory() as root:
            result,writer,path=self.execute(root,'delete_seven')
            self.assertEqual(result['status'],'PARTIALLY_AUTO_FIXED',result)
            self.assertEqual(len(writer.product(1)['images']['main']),6)
            self.assertEqual((writer.saves,writer.uploads),(1,0))
            deferred=json.loads((path/'deferred_items.json').read_text(encoding='utf-8'))['items']
            reasons=str([r['reason_codes'] for r in deferred])
            self.assertNotIn('main_count_gt_6',reasons)
            self.assertIn('PHASH_DUPLICATE_UNCONFIRMED',reasons)

    def test_E07_disagreement_preserves_detail_while_independent_main_saves(self):
        with tempfile.TemporaryDirectory() as root:
            result,writer,path=self.execute(root,'disagreement')
            product=writer.product(1)
            self.assertEqual(result['status'],'PARTIALLY_AUTO_FIXED',result)
            self.assertEqual((writer.saves,writer.uploads),(1,1))
            self.assertEqual(product['images']['main'],['https://fake/upload'])
            self.assertEqual(product['images']['detail'],['https://fake/other'])
