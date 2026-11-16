"""Synthetic transport and product adapters, never a second business runner."""
import copy
import hashlib
import io
import json
from pathlib import Path
from PIL import Image,ImageDraw
import numpy as np

def observation(item,action,marks):
    return dict(schema_version='image-action-decision.v2',task_type='image_action_decision',item_id=item['id'],image_id=item['id'],
        image_sha256=item['sha256'],image_type=item['image_type'],evidence_ids=item['evidence_ids'],confidence=0.,abstain=False,
        decision=action,visual_class='TOY_PRODUCT',retail_box_status='ABSENT',retail_box_confidence=0.,retail_box_bbox=None,
        box_relation='UNRELATED',toy_present=True,toy_confidence=0.,watermarks=marks,
        product_identity=dict(same_product_as_context='UNKNOWN',model_visible='UNKNOWN',structure_match='UNKNOWN',color_match='UNKNOWN'),
        sku_suitability=dict(is_toy_photo=True,is_retail_box_photo=False,recommended_group='WITHOUT_RETAIL_BOX'),
        subject_complete=True,clear=True,angle='FRONT',background_complexity='SMOOTH',preserve_regions=[],reason='Synthetic fixture observation')

def image_bytes(image):
    buffer=io.BytesIO();image.save(buffer,format='PNG');return buffer.getvalue()

class FakeReader:
    def __init__(self,state,assets,counters):self.state=state;self.assets=assets;self.counters=counters
    def product(self,pid):
        self.counters['independent_reads']+=1
        if self.counters['saves']:self.counters['independent_readbacks']+=1
        return copy.deepcopy(self.state)
    def current_shop(self):return 7
    def account_fingerprint(self):return 'f'*64
    def fetch_image(self,url):return self.assets[url]

class FakeWriter(FakeReader):
    def product(self,pid):
        if self.counters['saves']:return self.readonly_client().product(pid)
        return copy.deepcopy(self.state)
    def readonly_client(self):return FakeReader(self.state,self.assets,self.counters)
    def save(self,pid,desired,**kwargs):
        self.counters['saves']+=1;self.state.clear();self.state.update(copy.deepcopy(desired))
    def upload(self,path):
        self.counters['uploads']+=1;url='https://fake/upload/'+str(self.counters['uploads']);self.assets[url]=Path(path).read_bytes();return url

def run_fake(root,scenario='twin'):
    from mye_c_automation.job_manager import JobManager,atomic_json
    from mye_c_automation.budget_manager import BudgetManager
    from mye_c_automation.ai_judge.client import JudgeClient
    from mye_c_automation.automation_policy import AutomationPolicy
    from mye_c_automation.full_product_audit import download_only
    from mye_c_automation.workflow_runner import run_automatic
    from mye_c_automation.visual_quality import VisualQualityInspector
    from mye_c_automation.candidate_quality import CandidateQualityGate
    root=Path(root)
    # Original procedural image; the second seed is a geometrically unrelated photo.
    rng=np.random.default_rng(68)
    clean=Image.fromarray(rng.integers(20,235,(1000,1000,3),dtype=np.uint8))
    draw=ImageDraw.Draw(clean)
    for i in range(45):
        x,y=rng.integers(160,760,2);draw.rectangle((x,y,x+45,y+65),outline=(250,250,250),width=4)
    other=Image.fromarray(np.random.default_rng(169).integers(20,235,(1000,1000,3),dtype=np.uint8))
    source=clean.copy();draw=ImageDraw.Draw(source)
    if scenario in {'twin','frame'}:
        draw.rectangle((0,875,1000,1000),fill='red');draw.rectangle((0,0,180,120),fill='red');draw.rectangle((790,0,1000,110),fill='red')
    elif scenario=='repair':
        source=Image.new('RGB',(1000,1000),'white');ImageDraw.Draw(source).rectangle((300,200,700,700),fill='blue')
        ImageDraw.Draw(source).text((20,940),'STORE',fill='red')
    assets={'https://fake/source':image_bytes(source),'https://fake/clean':image_bytes(clean if scenario=='twin' else other)}
    assets['https://fake/spare']=image_bytes(other if scenario=='twin' else Image.fromarray(np.random.default_rng(170).integers(20,235,(1000,1000,3),dtype=np.uint8)))
    # One SHA under an alias URL plus all five business-reference sources.
    assets['https://fake/alias']=assets['https://fake/source']
    product=dict(id=1,shopId=7,status='READY_TO_PUBLISH',price=20,weight=.2,presale=True,title='Synthetic product',
        images=dict(main=['https://fake/source','https://fake/clean','https://fake/spare'],detail=['https://fake/alias','https://fake/clean'],sku=['https://fake/source','https://fake/clean','https://fake/spare']),
        skus=[dict(skuId='real1',skuName='Without Box',skuImageUrl='https://fake/source',price=10),dict(skuId='real2',skuName='With Box',skuImageUrl='https://fake/clean',originalBox=True,price=20)],
        descriptionJson=json.dumps([dict(type='text',text='Preserve text',style={'color':'red'}),dict(type='image',url='https://fake/alias'),dict(type='text',shopFooter=True,text='Preserve footer'),dict(type='image',url='https://never-fetch/footer')]))
    counters=dict(saves=0,uploads=0,independent_reads=0,independent_readbacks=0,model_calls=0)
    writer=FakeWriter(product,assets,counters);reader=writer.readonly_client()
    manager=JobManager(root/'jobs');job=manager.create(1,7,dict(ai_requests=80,full_resolution_images=40),mode='auto_apply',image_workflow='v2',image_options=dict(rights='OWNED_OR_LICENSED'),model_budget=dict(mode='RECORD_ONLY',usage_source='FAKE_TRANSPORT'))
    directory=manager.directory(job['job_id']);budget=BudgetManager(job['budget'],directory/'budget.sqlite')
    source_sha=hashlib.sha256(assets['https://fake/source']).hexdigest()
    def transport(model,item,context):
        if model!='deepseek-v4.1-flash':raise AssertionError('Unexpected model')
        if 'descriptionJson' in context:raise AssertionError('Body text leaked')
        counters['model_calls']+=1
        if item['task_type']=='image_quality_v2':
            value=dict(task_type=item['task_type'],item_id=item['id'],confidence=0.,abstain=False,decision='MATCH',evidence_ids=item['evidence_ids'],checks={k:True for k in ('identity_preserved','packaging_preserved','protected_print_preserved','overlay_removed','no_new_artifacts')})
        else:
            dirty=item['sha256']==source_sha and scenario!='keep'
            boxes=[[0,0,.18,.12],[.79,0,1,.11],[0,.875,1,1]] if scenario in {'twin','frame'} else [[.01,.93,.15,.97]]
            marks=[dict(kind='STORE_WATERMARK',owner='UNKNOWN',overlay_role='ADDED_WATERMARK',bbox=b,confidence=0.,preserve_overlap_risk='LOW') for b in boxes] if dirty else []
            value=observation(item,'REMOVE_TEXT' if dirty else 'KEEP',marks)
        return dict(choices=[dict(message=dict(content=json.dumps(value)))]) # usage unknown, intentionally null
    judge=JudgeClient(budget,directory/'judge_cache',transport=transport,retries=0)
    def download(url,path):Path(path).write_bytes(assets[url])
    def auditor(pid,shop,output_dir,site):return download_only(pid,shop,output_dir=output_dir,site=site,downloader=download)
    policy=AutomationPolicy(dict(schema='automation-policy/v1',enabled=True,mode='auto_apply',shop_allowlist=[7],pid_allowlist=[1],max_products_per_run=1,max_site_save_per_job=1,max_uploads_per_job=12,max_ai_requests_per_job=80,allow_actions={k:True for k in ('REPLACE_TWIN','DELETE','REMOVE_TEXT','SKU_ASSIGN')},preserve_product_status=True,require_live_dry_run=True,require_post_write_readback=True,require_content_validation=True,halt_batch_after_unknown_write=True,stop_on_global_integrity_error=True))
    try:
        result=run_automatic(manager,job,policy,writer=writer,auditor=auditor,full_audit_reader=reader,judge=judge,quality_gate=CandidateQualityGate(VisualQualityInspector(directory,job,judge=judge)))
    finally:budget.close()
    out=dict(status=result['status'],job_id=job['job_id'],scenario=scenario,**counters,real_model_calls=0,site_reads=0,production_writes=0,report=str(directory/'report_data.json'))
    atomic_json(directory/'fake_summary.json',out)
    with (root/'logs/fake.jsonl').open('a',encoding='utf-8') as log:log.write(json.dumps(out)+'\n')
    return out
