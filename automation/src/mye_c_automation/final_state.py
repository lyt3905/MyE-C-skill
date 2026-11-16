"""Deterministic pre-write simulation; never performs I/O."""
from copy import deepcopy
import json

def upload_placeholders(plan,prefix='https://pending.invalid/validated-upload/'):
 identifiers={};tokens=[]
 for index,row in enumerate((plan.get('post_actions') or {}).get('uploads',[])):
  key=row.get('sha256','target:'+str(index))
  if key not in identifiers:identifiers[key]=len(identifiers)
  tokens.append(prefix+str(identifiers[key]).zfill(3))
 return tokens

def simulate_final_snapshot(before_snapshot, plan, uploaded_urls=None):
 if 'descriptionJson' in plan.get('desired',{}):raise ValueError('DESCRIPTION_MUTATION_FORBIDDEN')
 result=deepcopy(before_snapshot)
 result.update(deepcopy(plan['desired']))
 row_assignments=(plan.get('post_actions') or {}).get('sku_row_assignments',[])
 if row_assignments:
  from mye_c_automation.snapshot_sku import validate_assignments
  validate_assignments(before_snapshot,row_assignments)
  for assignment in row_assignments:
   sku=result['skus'][assignment['index']];url=assignment['url']
   sku['skuImageUrl']=url
   for field in ('imageUrl','image'):
    if field in sku:sku[field]=url
   pool=result.setdefault('images',{}).setdefault('sku',[])
   if url not in pool:pool.append(url)
 assignments=(plan.get('post_actions') or {}).get('sku_assignments',{})
 for sku in result.get('skus') or []:
  sku_id=str(sku.get('skuId',sku.get('id','')))
  if sku_id in assignments:
   sku['skuImageUrl']=assignments[sku_id]
   for field in ('imageUrl','image'):
    if field in sku: sku[field]=assignments[sku_id]
   pool=result.setdefault('images',{}).setdefault('sku',[])
   if assignments[sku_id] not in pool:pool.append(assignments[sku_id])
 mappings=(plan.get('post_actions') or {}).get('url_replacements',{})
 def replace_known(value):
  if isinstance(value,str): return mappings.get(value,value)
  if isinstance(value,list): return [replace_known(v) for v in value]
  if isinstance(value,dict): return {k:replace_known(v) for k,v in value.items()}
  return value
 if mappings:
  result['images']={pool:replace_known(urls) if pool in {'main','detail','sku'} else urls for pool,urls in result.get('images',{}).items()}
  for sku in result.get('skus') or []:
   for field in ('skuImageUrl','imageUrl','image'):
    if field in sku: sku[field]=replace_known(sku[field])
 for ref,url in zip((plan.get('post_actions') or {}).get('uploads',[]),uploaded_urls or []):
  if ref['pool']=='description':continue
  old=result['images'][ref['pool']][ref['index']]
  if old in (plan.get('post_actions') or {}).get('preserve_reference_urls',[]):
   result['images'][ref['pool']][ref['index']]=url
   continue
  def remap(value):
   if isinstance(value,str): return url if value==old else value
   if isinstance(value,list): return [remap(v) for v in value]
   if isinstance(value,dict): return {k:remap(v) for k,v in value.items()}
   return value
  result['images']={pool:remap(urls) if pool in {'main','detail','sku'} else urls for pool,urls in result['images'].items()}
  for sku in result.get('skus') or []:
   for field in ('skuImageUrl','imageUrl','image'):
    if sku.get(field)==old: sku[field]=url
 if (plan.get('post_actions') or {}).get('content_groups'):
  from mye_c_automation.image_content_plan import apply_groups
  result=apply_groups(before_snapshot,result,plan,uploaded_urls)
 return result

def validate_final_snapshot(final_snapshot, policy=None, context=None):
 context=context or {}; before=context.get('before',{}); errors=[]; checked=[]; warnings=[]
 def check(rule,path,actual,expected,ok):
  checked.append(rule)
  if not ok: errors.append(dict(rule_id=rule,field=path,actual=actual,expected=expected))
 images=final_snapshot.get('images') or {}
 check('IMAGES_REQUIRED','images',final_snapshot.get('images'),'mapping',isinstance(final_snapshot.get('images'),dict))
 if not isinstance(images,dict): images={}
 for pool in ('main','detail') + (('sku',) if final_snapshot.get('skus') else ()):
  urls=images.get(pool)
  check('REQUIRED_POOL','images.'+pool,urls,'nonempty list',isinstance(urls,list) and bool(urls))
 if images:
  for pool,urls in (before.get('images') or {}).items():
   if pool not in {'main','detail','sku'}:check('PROTECTED_IMAGE_POOL','images.'+pool,images.get(pool),urls,images.get(pool)==urls)
  from mye_c_automation.reviewed_images import scoped_detail_change,FIELD
  reviewed=scoped_detail_change(before,context.get('plan',{}))
  if FIELD in (context.get('plan',{}).get('post_actions') or {}):check('REVIEWED_DETAIL_SCOPE','images',None,'exact user-reviewed detail removal',reviewed)
  prior_count=len((before.get('images') or {}).get('main',[]))
  unchanged_count=reviewed and prior_count>6 and images.get('main')==(before.get('images') or {}).get('main')
  if unchanged_count:warnings.append(dict(rule_id='EXISTING_MAIN_COUNT_UNCHANGED',actual=prior_count,scope='USER_REVIEWED_DETAIL_DELETION_ONLY',whole_product_verified=False))
  check('MAIN_COUNT','images.main',len(images.get('main',[])),'1..6; unchanged existing excess only for bound reviewed detail deletion',1<=len(images.get('main',[]))<=6 or unchanged_count)
  for pool,urls in images.items():
   if pool not in {'main','detail','sku'}:continue
   if pool=='main' or (before.get('images') or {}).get(pool):
    check('POOL_NOT_EMPTY','images.'+pool,len(urls),'>0',bool(urls))
   for i,url in enumerate(urls):
    existing=url in (before.get('images') or {}).get(pool,[])
    check('VALID_URL',f'images.{pool}.{i}',url,'existing reference or https URL',isinstance(url,str) and bool(url.strip()) and (existing or url.startswith(('https://','http://'))))
 for sku_index,sku in enumerate(final_snapshot.get('skus') or []):
  reference=sku.get('skuImageUrl') or sku.get('imageUrl') or sku.get('image')
  prior_rows=before.get('skus') or []
  prior=prior_rows[sku_index] if sku_index<len(prior_rows) else {}
  prior_ref=prior.get('skuImageUrl') or prior.get('imageUrl') or prior.get('image')
  legacy_unchanged=bool(reference) and reference==prior_ref and reference not in (before.get('images') or {}).get('sku',[])
  if legacy_unchanged and reference not in images.get('sku',[]):
   warnings.append(dict(rule_id='LEGACY_SKU_REFERENCE_UNCHANGED',field='skus.'+str(sku_index),reference=reference))
  check('SKU_REFERENCE','skus.'+str(sku_index),reference,'image in SKU pool or unchanged legacy SKU reference',reference in images.get('sku',[]) or legacy_unchanged)
 actions=set(context.get('plan',{}).get('automation',{}).get('actions',[]))
 for field in ('status','price','weight','identityJson','titleTranslationZh','title','shippingFee'):
  if field=='identityJson' and final_snapshot.get(field) is not None and before.get(field) is not None:
   from mye_c_automation.product_state import identity_object
   try:
    old_identity=identity_object(before.get(field) or {});new_identity=identity_object(final_snapshot.get(field) or {})
    if 'TITLE_REWRITE' in actions:
     old_identity.pop('modelCode',None);new_identity.pop('modelCode',None)
    check('PROTECTED_FIELD',field,new_identity,old_identity,new_identity==old_identity)
   except ValueError: check('PROTECTED_FIELD',field,'invalid','valid identity',False)
   continue
  check('PROTECTED_FIELD',field,final_snapshot.get(field),before.get(field),final_snapshot.get(field)==before.get(field))
 old_skus=deepcopy(before.get('skus') or [])
 new_skus=deepcopy(final_snapshot.get('skus') or [])
 for rows in (old_skus,new_skus):
  for sku in rows:
   for field in ('skuImageUrl','imageUrl','image'): sku.pop(field,None)
   if context.get('saved_readback') is True:
    from mye_c_automation.product_state import SERVER_DERIVED_SKU_FIELDS
    for field in SERVER_DERIVED_SKU_FIELDS:sku.pop(field,None)
 check('SKU_PROTECTED_FIELDS','skus',new_skus,old_skus,new_skus==old_skus)
 if 'before' in context:
  from mye_c_automation.product_state import description_content_preserved
  description_ok=(type(final_snapshot.get('descriptionJson')) is type(before.get('descriptionJson')) and final_snapshot.get('descriptionJson')==before.get('descriptionJson'))
  if context.get('saved_readback') is True:
   description_ok=description_content_preserved(before.get('descriptionJson'),final_snapshot.get('descriptionJson'),source_title=before.get('titleEn'),saved_title=final_snapshot.get('titleEn'))
  if (context.get('plan',{}).get('post_actions') or {}).get('content_groups'):
   from mye_c_automation.image_content_plan import uploaded_from_snapshot
   try:
    expected=simulate_final_snapshot(before,context['plan'],uploaded_from_snapshot(before,context['plan'],final_snapshot))
    description_ok=type(final_snapshot.get('descriptionJson')) is type(expected.get('descriptionJson')) and final_snapshot.get('descriptionJson')==expected.get('descriptionJson')
    check('CONTENT_ALIAS_SYNC','images',final_snapshot.get('images'),expected.get('images'),final_snapshot.get('images')==expected.get('images'))
   except (KeyError,IndexError,ValueError,TypeError):description_ok=False
  check('PROTECTED_FIELD','descriptionJson',final_snapshot.get('descriptionJson'),before.get('descriptionJson'),
        ('descriptionJson' in final_snapshot)==('descriptionJson' in before) and description_ok)
 errors.sort(key=lambda error: 0 if error['rule_id']=='PROTECTED_FIELD' else 1)
 return dict(ok=not errors,errors=errors,warnings=warnings,checked_rules=checked)

def pre_apply_validate(before_snapshot,plan,context=None):
 final=simulate_final_snapshot(before_snapshot,plan,upload_placeholders(plan))
 return validate_final_snapshot(final,context=dict(context or {},before=before_snapshot,plan=plan))
