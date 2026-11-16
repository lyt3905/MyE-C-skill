from mye_c_automation.resources import resource_path
"""Legacy injected-auditor CLI regressions; full default has separate bridge tests."""
import unittest,tempfile,json,io
from pathlib import Path
from copy import deepcopy
from contextlib import ExitStack,redirect_stdout
from unittest.mock import patch
from PIL import Image,ImageDraw
import numpy as np
from mye_c_automation import workflow_runner
from mye_c_automation.job_manager import atomic_json
from mye_c_automation.execution_ledger import ExecutionLedger
from test_auto_remedy import Inspector
class AccountCliTests(unittest.TestCase):
 def execute(self,root,after_preview=None,mode='auto_apply',missing_principal=False,case='crop',title_validator=None,template_projection='gray',queue_judge=None,model_profile=None):
  from mye_c_automation.audit_one import audit as actual_audit
  root=Path(root);jobs=root/'jobs';blobs={};seen=[]
  main=Image.new('RGB',(1000,1000),'white');ImageDraw.Draw(main).rectangle((300,200,700,700),fill='blue');ImageDraw.Draw(main).rectangle((0,920,999,999),fill='red')
  if case!='crop':ImageDraw.Draw(main).rectangle((0,920,999,999),fill='white')
  if case=='center_watermark':ImageDraw.Draw(main).rectangle((300,460,700,480),fill='red')
  detail=Image.fromarray(np.random.default_rng(45).integers(0,256,(1000,1000,3),dtype=np.uint8))
  if case.startswith('lowres'):
   detail=main.copy();main=main.resize((500,500))
   if case=='lowres_no_hd':detail=detail.resize((700,700))
  official=detail.copy() if case.startswith('lowres_local') else None
  if official is not None:detail=Image.fromarray(np.random.default_rng(48).integers(0,256,(1000,1000,3),dtype=np.uint8))
  if case.startswith('lowres_local_letterbox'):
   official=Image.fromarray(np.random.default_rng(445).integers(0,256,(1667,1000,3),dtype=np.uint8))
   main=Image.new('RGB',(500,500),'white');main.paste(official.resize((300,500)),(100,0))
  for url,image in [('https://fake/main',main),('https://fake/detail',detail)]:
   b=io.BytesIO();image.save(b,format='PNG');blobs[url]=b.getvalue()
  product={'id':1,'status':'PENDING','title':'NA-H74 威震天','titleEn':'Hot Sale Transformation NA-H74 NAH74 Megatank Action Figures Collection Gifts','identityJson':{'modelCode':'NA-H74','logoCode':'keep'},'brandId':200017853,'titleTranslationZh':'热销 NA-H74 威震天','price':20,'weight':.2,'images':{'main':['https://fake/main'],'detail':['https://fake/detail'],'sku':[]},'skus':[],'descriptionJson':'opaque invalid JSON { https://fake/main'}
  if case=='lowres_legacy_sku':
   extra=io.BytesIO();Image.new('RGB',(1000,1000),'green').save(extra,format='PNG');blobs['https://fake/sku_existing']=extra.getvalue()
   product['images']['sku']=['https://fake/sku_existing'];product['skus']=[{'skuId':1,'skuName':'without box','skuImageUrl':'https://fake/detail','price':10}]
  if case.startswith('cleanup'):
   count=8 if case=='cleanup_insufficient' else 7
   urls=[]
   for index in range(count-1):
    url='https://fake/main_'+str(index);urls.append(url)
    image=Image.fromarray(np.random.default_rng(810+index).integers(0,256,(800,800,3),dtype=np.uint8))
    buffer=io.BytesIO();image.save(buffer,format='PNG');blobs[url]=buffer.getvalue()
   duplicate=blobs[urls[0]]
   if case=='cleanup_phash_only':
    image=Image.open(io.BytesIO(duplicate));image.putpixel((0,0),(0,0,0));buffer=io.BytesIO();image.save(buffer,format='PNG');duplicate=buffer.getvalue()
   blobs['https://fake/copy']=duplicate;urls.append('https://fake/copy');product['images']['main']=urls
   if case=='cleanup_sku_reference':
    product['images']['sku']=['https://fake/copy']
    product['skus']=[{'skuId':1,'skuName':'without box','skuImageUrl':'https://fake/copy','price':10}]
  if case in {'title','title_translate_error'} or case.startswith(('backend_drift_','backend_header')):product['titleEn']='Old title'
  if case=='title_small_scale':product.update(title='NA-H74 小比例 威震天 变形玩具',titleEn='Old title')
  if case.startswith('backend_header'):
   product['descriptionJson']=json.dumps([{'type':'text','texts':[{'class':'title','content':product['titleEn']}]},
                                         {'type':'text','texts':[{'content':'Collected body'}]},
                                         {'type':'image','url':'https://forbidden/description-not-audited'}])
  if case.startswith('backend_drift_'):
   product['images']['sku']=['https://fake/main']
   product['skus']=[{'skuId':1,'skuName':'with box','skuImageUrl':'https://fake/main','discountPrice':33.74,'shippingFee':10.02},
                    {'skuId':2,'skuName':'with box','skuImageUrl':'https://fake/main','discountPrice':34.76,'shippingFee':10.02}]
  if case in {'brand','brand_alias'}:product['brandId']=200014695
  if case=='brand_alias':product['brand']='Unverified Alias'
  if case=='lowres_sku':
   product['images']['main']=['https://fake/detail'];product['images']['sku']=['https://fake/main']
   product['skus']=[{'skuId':1,'skuName':'without box','skuImageUrl':'https://fake/main','price':10}]
  if case=='lowres_shared':product['images']['sku']=['https://fake/main']
  if case=='lowres_other_missing':product['images']['detail'].append('https://fake/missing')
  if case=='title_conflict':
   product.update(title='Transformers MPM-09 Jazz Optimus Prime',titleEn='Old title',identityJson={'modelCode':'MPM-09','logoCode':'keep'})
  if case.startswith('sku'):
   product['images']['sku']=['https://fake/main']
   product['skus']=[{'skuId':1,'skuName':'without box','skuImageUrl':'https://fake/main','price':10},
                    {'skuId':2,'skuName':'with box','skuImageUrl':'https://fake/main','price':12}]
   if case=='sku_color_conflict':product['skus'][0]['color']='red'
   if case=='sku_model_conflict':product['skus'][0]['modelCode']='MS-01'
   if case.startswith('sku_bundle'):
    product['skus'][0]['skuName']={'sku_bundle':'combo bundle without box','sku_bundle_count':'2pcs without box','sku_bundle_pack':'without box 2-pack','sku_bundle_accessory':'accessory pack without box'}.get(case,'combo bundle without box')
    if case=='sku_bundle_partial':product['skus'][1]['skuName']='without box'
   if case in {'sku_multicolor','sku_multicolor_conflict'}:
    red=detail.copy();red.putpixel((0,0),(255,0,0));buffer=io.BytesIO();red.save(buffer,format='PNG');blobs['https://fake/red_body']=buffer.getvalue()
    product['images']['detail'].append('https://fake/red_body')
    product['skus'][0]['color']='red';product['skus'][1].update(skuName='without box',color='blue')
    if case=='sku_multicolor_conflict':product['skus'][0]['modelCode']='MS-01'
   if case=='sku_missing_ids':
    for sku in product['skus']:sku.pop('skuId');sku['id']=None
   if case in {'sku_reference_only','sku_reference_lowres'}:
    reference=main.copy();ImageDraw.Draw(reference).rectangle((0,920,999,999),fill='red')
    if case=='sku_reference_lowres':reference=reference.resize((500,500))
    b=io.BytesIO();reference.save(b,format='PNG');blobs['https://fake/reference']=b.getvalue()
    product['skus'][0]['skuImageUrl']='https://fake/reference'
  class Transport:
   cfg={'base':'https://fake.test','user':'fake','pwd':'fake'}
   account='a'*64;saves=0;uploads=0;translations=0
   def account_fingerprint(self):
    if missing_principal:raise ValueError('ACCOUNT_PRINCIPAL_UNVERIFIED')
    return self.account
   def current_shop(self):return 7
   def call(self,path,data=None,**kwargs):
    if path=='/api/auth/me':return {'data':{'id':101 if self.account=='a'*64 else 102,'selectedShopId':7}}
    if path=='/api/admin/products/1/translate-title':
     self.translations+=1
     if case=='title_translate_error':raise TimeoutError('FAKE_TRANSLATION_TIMEOUT')
     product['titleTranslationZh']='热销 NA-H74 威震天';return {'ok':True}
    raise AssertionError('unexpected API call')
   def product(self,pid):return deepcopy(product)
   def download(self,url,path):
    if case=='lowres_download_error' and url=='https://fake/detail':raise OSError('FAKE_DOWNLOAD_FAILED')
    Path(path).write_bytes(b'not an image' if case=='lowres_corrupt_hd' and url=='https://fake/detail' else blobs[url])
   def upload(self,path):self.uploads+=1;blobs['https://fake/upload']=Path(path).read_bytes();return 'https://fake/upload'
   def save(self,pid,images=None,desc=None,extra=None,expected_state_hash=None):
    self.saves+=1;product['images']=deepcopy(images);product.update(deepcopy(extra or {}))
    if case.startswith('backend_header'):
     description=json.loads(product['descriptionJson']);description[0]['texts'][0]['content']=product['titleEn']
     if case=='backend_header_body':description[1]['texts'][0]['content']='SERVER_CHANGED_BODY'
     if case=='backend_header_image':description[2]['url']='https://forbidden/changed-image'
     product['descriptionJson']=json.dumps(description)
    if case in {'backend_drift_description','backend_drift_both'}:product['descriptionJson']+=' SERVER_REWROTE_OPAQUE_VALUE'
    if case in {'backend_drift_skus','backend_drift_both'}:
     for row,discount in zip(product['skus'],(34.24,35.27)):row.update(discountPrice=discount,shippingFee=10.17)
  transport=Transport();transport.image_bytes=blobs;config=root/'site.json';atomic_json(config,transport.cfg)
  policy=json.loads(resource_path('config/automation.v1.example.json').read_text(encoding='utf-8'));policy.update(enabled=True,shop_allowlist=[7],pid_allowlist=[1]);policy['allow_actions']['REPLACE_TWIN']=False
  if case=='lowres_legacy_sku':policy['allow_actions']={key:key=='REPLACE_TWIN' for key in policy['allow_actions']}
  if case.startswith(('backend_drift_','backend_header')):
   policy['allow_actions']={key:key=='TITLE_REWRITE' for key in policy['allow_actions']};policy['max_uploads_per_job']=0
  if case.startswith('lowres'):policy['allow_actions']['REPLACE_TWIN']=True
  if official is not None:
   import hashlib
   official_path=root/'official.png';official.save(official_path)
   source={'file':str(official_path),'sha256':hashlib.sha256(official_path.read_bytes()).hexdigest(),
           'source_url':'https://maker.example/NA-H74.png','official_source':True,'model':'NA-H74','packaging_type':'FIGURE'}
   if case=='lowres_local_bad_hash':source['sha256']='0'*64
   if case=='lowres_local_unverified':source['official_source']=False
   if case=='lowres_local_wrong_model':source['model']='MS-01'
   atomic_json(root/'official_pool.json',{'schema':'official-image-pool/v1','items':[source]})
   policy['local_pool_index']=str(root/'official_pool.json');policy['allow_actions']['REPLACE_TWIN']=False
  if case.startswith('cleanup'):policy['allow_actions']['DELETE_REDUNDANT']=True
  if case in {'sku_reference_only','sku_reference_lowres'}:policy['allow_actions']['SKU_ASSIGN']=False
  if case=='sku_reference_lowres':policy['allow_actions']['REPLACE_TWIN']=True
  atomic_json(root/'policy.json',policy);atomic_json(root/'templates.json',{'templates':[],'no_applicable_shop_ids':[7]})
  if case=='template_localization':
   import cv2
   gray=cv2.cvtColor(np.array(detail),cv2.COLOR_RGB2GRAY).astype(np.float32)
   if template_projection=='red_excess':
    rgb=np.array(detail).astype(np.float32);gray=np.maximum(0,rgb[:,:,0]-np.maximum(rgb[:,:,1],rgb[:,:,2]))
   template=gray-cv2.GaussianBlur(gray,(0,0),25)
   np.save(root/'template.npy',template[300:316,200:216])
   atomic_json(root/'templates.json',{'templates':[{'shop_id':7,'path':str(root/'template.npy'),'projection':template_projection}],'required_shop_ids':[7]})
  class OCR:
   def __call__(self,image):
    red=(image[:,:,2]>240)&(image[:,:,1]<20)&(image[:,:,0]<20)
    if case=='center_watermark':
     if red.mean()<=.01:return [],None
     ys,xs=np.where(red)
     return [[[[int(xs.min()),int(ys.min())],[int(xs.max()+1),int(ys.min())],[int(xs.max()+1),int(ys.max()+1)],[int(xs.min()),int(ys.max()+1)]],'GenuineProductsStore',.99]],None
    return ([[[[10,930],[300,930],[300,960],[10,960]],'Third Party Store',.99]] if red.mean()>.01 else [],None)
  def audit(pid,shop,output_dir,site):
   seen.append(site);result=actual_audit(pid,shop,output_dir=output_dir,site=site,downloader=site.download,ocr_factory=OCR)
   if case=='lowres_bad_sha':
    raw=json.loads((output_dir/'audit_raw.json').read_text(encoding='utf-8'))
    next(r for r in raw['images'] if r['kind']=='detail')['content_sha256']='0'*64
    atomic_json(output_dir/'audit_raw.json',raw)
   return result
  class Judge:
   metrics={'requests':0,'usage_available':False}
   def process_queue(self,queue,context):return {r['id']:{'status':'HIT','results':[{'task_type':'watermark','classification':'third_party_store_banner' if (case=='crop' and r.get('source_url')=='https://fake/main') or r.get('source_url')=='https://fake/reference' else 'manufacturer_branding','confidence':.99,'abstain':False}]*2} for r in queue['items']}
  class Quality(Inspector):
   def inspect(self,*args):
    result=super().inspect(*args)
    if case in {'lowres_mismatch','lowres_local_letterbox_mismatch'}:result.update(product_identity_match=False,model_match=False)
    return result
   def propose(self,*args):return {'crop_box':[0,0,1000,900],'subject_box':[300,200,701,701]}
   def validate_title(self,current,generated):
    if title_validator is not None:return title_validator(current,generated)
    return {'ok':True,'evidence_ids':['FAKE_INDEPENDENT_TITLE_REVIEW']}
   def validate_brand(self,current,generated):return {'ok':True,'evidence_ids':['FAKE_INDEPENDENT_BRAND_REVIEW']}
   def inspect_deletion(self,source,context,comparison=None):
    import hashlib
    return {'ok':case!='cleanup_disagreement','is_box':case=='cleanup_box','is_official':case=='cleanup_official',
            'category':'REDUNDANT','information_preserved':True,'reference_sha256':hashlib.sha256(Path(comparison).read_bytes()).hexdigest() if comparison else None,
            'evidence_ids':['FAKE_INDEPENDENT_DUPLICATE_COMPARISON']}
   def observe_image(self,path,context):
    import hashlib
    data=Path(path).read_bytes();known=data in blobs.values()
    return {'clean':known,'verified':known,'image_type':'BOX' if not case.startswith('lowres') and data==blobs['https://fake/main'] else 'FIGURE',
            'model':'NA-H74','color':'red' if data==blobs.get('https://fake/red_body') else 'blue','sha256':hashlib.sha256(data).hexdigest(),'evidence_ids':['FAKE_MODEL_AND_PACKAGING']}
   def close(self):pass
  original_run=workflow_runner.run_automatic
  def injected_legacy_run(manager,job,policy,**kwargs):
   writer=kwargs['writer'];reader=writer.readonly_client()
   def injected_audit(pid,shop,output_dir):
    before=None
    try:before=reader.account_fingerprint()
    except ValueError:
     if job['mode']!='audit':raise
    result=audit(pid,shop,output_dir,reader)
    after=None
    try:after=reader.account_fingerprint()
    except ValueError:
     if job['mode']!='audit':raise
    if before!=after:raise ValueError('ACCOUNT_CONTEXT_CHANGED')
    atomic_json(output_dir/'audit_account.json',{'account_fingerprint':before,'status':'VERIFIED' if before else 'UNVERIFIED'})
    return result
   return original_run(manager,job,policy,auditor=injected_audit,**kwargs)
  original_preview=workflow_runner.live_dry_run
  def preview(*args):
   result=original_preview(*args)
   if after_preview:after_preview(transport,Path(args[0].directory(args[1])))
   return result
  argv=['mye_c_automation.workflow_runner.py','run','--image-workflow','legacy','--pid','1','--shop','7','--mode',mode,'--site-config',str(config),'--automation-config',str(root/'policy.json'),'--template-config',str(root/'templates.json'),'--root',str(jobs)]
  if model_profile is not None:argv.extend(['--model-config',str(model_profile)])
  if case=='missing_template':
   position=argv.index('--template-config');del argv[position:position+2]
  with ExitStack() as stack:
   stack.enter_context(patch('mye_c_automation.workflow_runner.run_automatic',side_effect=injected_legacy_run))
   stack.enter_context(patch('sys.argv',argv));stack.enter_context(patch('mye_c_automation.site_client._SiteTransport',return_value=transport))
   stack.enter_context(patch('mye_c_automation.audit_one.audit',audit));stack.enter_context(patch('mye_c_automation.workflow_v2_pipeline.JudgeClient',return_value=queue_judge if queue_judge is not None else Judge()))
   stack.enter_context(patch('mye_c_automation.visual_quality.VisualQualityInspector',return_value=Quality()))
   stack.enter_context(patch('mye_c_automation.execution_ledger.ExecutionLedger',side_effect=lambda:ExecutionLedger(root/'ledger.sqlite')))
   stack.enter_context(patch('mye_c_automation.executor.site_write_client.SiteWriteClient.fetch_image',side_effect=lambda url:blobs[url]))
   stack.enter_context(patch('mye_c_automation.workflow_runner.live_dry_run',preview));stack.enter_context(redirect_stdout(io.StringIO()))
   error=None
   try:workflow_runner.main()
   except Exception as exc:error=exc
  return transport,next(jobs.glob('JOB_*')),seen,error
 def test_A_standard_cli_same_session_audit_to_fake_save_and_readback(self):
  with tempfile.TemporaryDirectory() as root:
   transport,path,seen,error=self.execute(root)
   self.assertIsNone(error,repr(error));self.assertEqual((transport.uploads,transport.saves),(1,1))
   self.assertEqual(seen[0].account_fingerprint(),transport.account_fingerprint())
   for name in ['job.json','audit_account.json']:
    self.assertEqual(json.loads((path/name).read_text())['account_fingerprint'],'a'*64)
   plan=json.loads((path/'plan.v2.json').read_text());self.assertEqual(plan['precondition']['account_fingerprint'],'a'*64)
   self.assertIn('audit_account.json',{r['path'] for r in plan['evidence_refs']})
   self.assertEqual(json.loads((path/'state.json').read_text())['state'],'AUTO_VERIFIED')
   for name in ('dry_run.json','apply_receipt.json'):
    self.assertEqual(json.loads((path/name).read_text())['account_fingerprint'],'a'*64)
   manifest=json.loads((path/'evidence_manifest.json').read_text())
   self.assertIn('audit_account.json',{r['path'] for r in manifest['files']})
   import sqlite3
   from contextlib import closing
   with closing(sqlite3.connect(Path(root)/'ledger.sqlite')) as connection:self.assertEqual(connection.execute('SELECT account FROM executions').fetchone()[0],'a'*64)
 def test_B_account_switch_after_live_preview_blocks_before_first_upload(self):
  with tempfile.TemporaryDirectory() as root:
   transport,path,_,error=self.execute(root,after_preview=lambda transport,path:setattr(transport,'account','b'*64))
   self.assertIsNotNone(error);self.assertIn('ACCOUNT_MISMATCH',str(error))
   self.assertEqual((transport.uploads,transport.saves),(0,0))
   self.assertTrue((path/'dry_run.json').is_file())

 def test_C_preview_receipt_account_tamper_blocks_zero_writes(self):
  def tamper(transport,path):
   receipt=json.loads((path/'dry_run.json').read_text());receipt['account_fingerprint']='b'*64;atomic_json(path/'dry_run.json',receipt)
  with tempfile.TemporaryDirectory() as root:
   transport,path,_,error=self.execute(root,after_preview=tamper)
   self.assertIsNotNone(error);self.assertIn('ACCOUNT',str(error))
   self.assertEqual((transport.uploads,transport.saves),(0,0))
 def test_D_plan_account_changed_to_match_new_client_still_rejected_by_job(self):
  def tamper(transport,path):
   transport.account='b'*64
   plan=json.loads((path/'plan.v2.json').read_text());plan['precondition']['account_fingerprint']='b'*64;atomic_json(path/'plan.v2.json',plan)
  with tempfile.TemporaryDirectory() as root:
   transport,path,_,error=self.execute(root,after_preview=tamper)
   self.assertIsNotNone(error);self.assertIn('ACCOUNT',str(error))
   self.assertEqual((transport.uploads,transport.saves),(0,0))

 def test_E_audit_evidence_fingerprint_tamper_blocks_zero_writes(self):
  def tamper(transport,path):atomic_json(path/'audit_account.json',{'account_fingerprint':'b'*64})
  with tempfile.TemporaryDirectory() as root:
   transport,path,_,error=self.execute(root,after_preview=tamper)
   self.assertIsNotNone(error);self.assertIn('ACCOUNT',str(error))
   self.assertEqual((transport.uploads,transport.saves),(0,0))

 def test_F_missing_principal_allows_readonly_audit_but_blocks_auto_apply(self):
  for mode in ('audit','auto_apply'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as root:
    transport,path,seen,error=self.execute(root,mode=mode,missing_principal=True)
    self.assertEqual((transport.uploads,transport.saves),(0,0))
    if mode=='audit':
     self.assertIsNone(error,repr(error));self.assertTrue(seen)
     self.assertEqual(json.loads((path/'audit_account.json').read_text())['status'],'UNVERIFIED')
    else:
     self.assertIsNotNone(error);self.assertIn('ACCOUNT_PRINCIPAL_UNVERIFIED',str(error))

 def test_G_unverified_readonly_plan_cannot_be_promoted_to_auto_execution(self):
  from mye_c_automation.executor.site_write_client import SiteWriteClient
  from mye_c_automation.executor.local import LocalExecutor
  from mye_c_automation.automation_policy import AutomationPolicy
  with tempfile.TemporaryDirectory() as root:
   transport,path,_,error=self.execute(root,mode='audit',missing_principal=True)
   self.assertIsNone(error,repr(error))
   plan=json.loads((path/'plan.v2.json').read_text());policy=AutomationPolicy.load(Path(root)/'policy.json')
   asset=path/plan['post_actions']['uploads'][0]['path']
   with patch('mye_c_automation.executor.site_write_client.SiteWriteClient.fetch_image',return_value=asset.read_bytes()),self.assertRaisesRegex(ValueError,'ACCOUNT_BINDING_REQUIRED'):
    LocalExecutor(SiteWriteClient(transport),path).execute_auto(plan,policy)
   self.assertEqual((transport.uploads,transport.saves),(0,0))
