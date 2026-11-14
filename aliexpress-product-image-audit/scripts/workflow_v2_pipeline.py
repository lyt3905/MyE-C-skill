"""Machine candidate queue and conservative read-only review integration."""
import json
import time
import hashlib
from pathlib import Path
from ai_judge import JudgeClient
from budget_manager import BudgetManager
from job_manager import atomic_json

def image_candidate(row):
    """Bind a machine candidate to its original business target and bytes."""
    pool, index = row['kind'], row['index']
    if pool not in {'main','detail','sku'}:raise ValueError('OUT_OF_SCOPE_IMAGE_POOL')
    local = Path(row['file'])
    if not local.is_absolute(): local = Path(__file__).parent / local
    digest = hashlib.sha256(local.read_bytes()).hexdigest()
    if row.get('content_sha256') not in (None, digest):
        raise ValueError('source image changed')
    image_id = pool.upper() + '_' + str(index).zfill(3)
    item_id = 'WM_' + image_id
    return dict(id=item_id, item_id=item_id, task_type='watermark', image_id=image_id,
                kind=pool, pool=pool, index=index, source_url=row.get('url'),
                source_sha256=digest, sha256=digest, local=str(local),
                reference_only=row.get('source')=='skus',
                source_field=row.get('source','images'),source_index=row.get('source_index',index),
                reason='MACHINE_CANDIDATE', evidence_ids=[item_id])

def product_context(product, job, flags):
    return {'pid':job['pid'],'shop':job['shop_id'],'product_sha256':hashlib.sha256(json.dumps(product,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
            'title':product.get('title'),'titleEn':product.get('titleEn'),'brand':product.get('brand'),'brandId':product.get('brandId'),
            'identityJson':product.get('identityJson'),'product_type':product.get('productType',product.get('categoryId')),
            'skus':product.get('skus'),'product_checks':flags.get('product_checks',{})}

def pipeline(directory, job, judge=None):
    started=time.perf_counter()
    directory=Path(directory)
    flags_path=directory/'audit_flags.json'
    raw_path=directory/'audit_raw.json'
    if not flags_path.exists() or not raw_path.exists():
        return {'status':'NEEDS_REVIEW','reason':'audit evidence missing'}
    flags=json.loads(flags_path.read_text(encoding='utf-8'))
    raw=json.loads(raw_path.read_text(encoding='utf-8'))
    if flags.get('pid') != job['pid'] or raw.get('pid') != job['pid']:
        raise ValueError('audit PID mismatch')
    raw['images']=[row for row in raw.get('images',[]) if row.get('kind') in {'main','detail','sku'}]
    from evidence_builder import build
    from policy_engine import evaluate
    build(directory,raw.get('images',[]),shop_id=job['shop_id'],templates_required=job.get('templates_required',False))
    candidates={row['image'] for key in ('ocr_hits','border_candidates','residual_candidates') for row in flags.get(key,[])}
    template_status=json.loads((directory/'template_scan.json').read_text(encoding='utf-8'))
    required_templates=job.get('templates_required',False)
    if template_status.get('status')=='REQUIRED_TEMPLATE_MISSING' or required_templates and template_status.get('status') not in {'COMPLETE','NO_APPLICABLE_TEMPLATE'}:
        flags.setdefault('anomalies',[]).append({'type':'REQUIRED_TEMPLATES_NOT_CONFIGURED'})
        atomic_json(flags_path,flags)
        # This machine stage has just added the template-configuration finding.
        # Finalize only its own flags file before plan compilation; do not rehash
        # unrelated sources or relax the later evidence/tamper checks.
        manifest_path=directory/'evidence_manifest.json'
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        flags_ref=next(ref for ref in manifest['files'] if ref['path']=='audit_flags.json')
        flags_ref['sha256']=hashlib.sha256(flags_path.read_bytes()).hexdigest()
        atomic_json(manifest_path,manifest)
    template_rows=json.loads((directory/'template_scan.json').read_text(encoding='utf-8')).get('items',[])
    template_sources={str(Path(row['image']).resolve()) for row in template_rows if row['status'] in {'HIT','SUSPECT','UNKNOWN'}}
    for row in raw.get('images',[]):
        local=Path(row['file'])
        if not local.is_absolute(): local=Path(__file__).parent/local
        if str(local.resolve()) in template_sources: candidates.add(row['file'])
    items=[]
    for row in raw.get('images',[]):
        if row.get('file') not in candidates: continue
        local=Path(row['file'])
        if not local.is_absolute(): local=Path(__file__).parent/local
        item_id='WATERMARK_'+str(len(items)+1).zfill(3)
        items.append(image_candidate(row))
    product=json.loads((directory/'audit_product.json').read_text(encoding='utf-8')) if (directory/'audit_product.json').exists() else {}
    items.extend(semantic_candidates(product, flags, raw.get('images',[])))
    queue={'schema':'ai-queue/v2','pid':job['pid'],'items':items}
    atomic_json(directory/'ai_queue.json',queue)
    budget=BudgetManager(job['budget'],directory/'budget.sqlite')
    try:
        model_options={'config':job['model_config']} if 'model_config' in job else {}
        judge=judge or JudgeClient(budget,directory/'judge_cache',**model_options)
        product=json.loads((directory/'audit_product.json').read_text(encoding='utf-8')) if (directory/'audit_product.json').exists() else {}
        from product_state import canonical_state_hash
        state_digest = canonical_state_hash(product)
        if job.get('input_state_sha256') not in (None, state_digest):
            raise ValueError('STATE_DRIFT')
        ai_started=time.perf_counter()
        results=judge.process_queue(queue,product_context(product,job,flags))
        ai_ms=round((time.perf_counter()-ai_started)*1000,3)
        atomic_json(directory/'ai_judgements.json',results)
        # No semantic absence or model opinion constitutes permission to mutate.
        review={'status':'NEEDS_REVIEW','reason':'read-only audit; actions require validated plan and independent executor authorization','judgements':results,'machine_anomalies':flags.get('anomalies',[]),'budget':budget.snapshot()}
        policies={key:evaluate(value) for key,value in results.items()}
        review['policies']=policies
        if (directory/'audit_product.json').exists() and not items and not flags.get('anomalies') and not flags.get('uncertain_refs') and not flags.get('summary',{}).get('image_errors') and flags.get('summary',{}).get('ocr_enabled') is True:
            review['status']='READ_ONLY_COMPLETE'
            review['reason']='No candidate actions; no mutations performed'
        plan_started=time.perf_counter()
        from plan_compiler import compile_plan
        compiled=compile_plan(directory,job)
        plan_ms=round((time.perf_counter()-plan_started)*1000,3)
        review['plan_validation']=compiled
        if not compiled['ok']:
            review['status']='NEEDS_REVIEW'
        elif review['status'] != 'READ_ONLY_COMPLETE':
            review['status']='PLAN_READY'
        atomic_json(directory/'review.json',review)
        (directory/'report.md').write_text('# Audit '+str(job['pid'])+'\nStatus: '+review['status']+'\nAI requests: '+str(judge.metrics['requests'])+'\nNo product writes performed.\n',encoding='utf-8')
        atomic_json(directory/'ai_metrics.json',judge.metrics)
        old=json.loads((directory/'run_metrics.json').read_text(encoding='utf-8')) if (directory/'run_metrics.json').exists() else {}
        atomic_json(directory/'audit_metrics.v1.json',old)
        used=budget.snapshot()['used']
        metrics={'schema':'token-opt-metrics/v2','workflow_version':'token-opt-v2','job_id':job['job_id'],'pid':job['pid'],
          'timing':{'total_ms':round((time.perf_counter()-started)*1000,3)+(old.get('elapsed_seconds',0)*1000),'audit_ms':old.get('elapsed_seconds')*1000 if isinstance(old.get('elapsed_seconds'),(float,int)) else None,'pipeline_ms':round((time.perf_counter()-started)*1000,3),'download_ms':None,'cv_ms':None,'ocr_ms':None,'ai_ms':ai_ms,'plan_ms':plan_ms,'residual_ms':json.loads((directory/'residual_manifest.json').read_text(encoding='utf-8'))['elapsed_ms'],'dry_run_ms':None,'apply_ms':None,'verify_ms':None},
          'downloads':old.get('downloads',{}),'ocr':{'image_count':old.get('ocr',{}).get('image_executions'),'execution_count':None,'cache_hits':old.get('ocr',{}).get('cache_reuses')},
          'ai':judge.metrics,'executor':{'site_get_calls':None,'upload_calls':0,'site_save_calls':0,'translate_calls':0,'status_calls':0,'verification_ok':None},
          'budget':{'token_status':budget.snapshot()['token_status'],'actual_tokens':budget.snapshot()['actual_tokens'],'status':'UNKNOWN' if not judge.metrics['usage_available'] else 'WITHIN_REQUEST_LIMITS','ai_requests_used':used.get('ai_requests'),'ai_requests_limit':job['budget'].get('ai_requests'),'full_resolution_images_used':used.get('full_resolution_images'),'full_resolution_images_limit':job['budget'].get('full_resolution_images')}}
        atomic_json(directory/'run_metrics.json',metrics)
        from render_token_report import render
        (directory/'report.md').write_text(render(directory,job['pid']),encoding='utf-8')
        return review
    finally:
        budget.close()


def semantic_candidates(product, flags, images):
    """Queue only explicit machine semantic uncertainties; bind SKU references."""
    items=[]
    for index, sku in enumerate(product.get('skus') or []):
        if not isinstance(sku,dict): continue
        url=sku.get('skuImageUrl') or sku.get('imageUrl') or sku.get('image')
        image=next((row for row in images if row.get('url') == url), None)
        # Strong explicit model-code contradiction only; color words alone are ambiguous.
        import re
        name=str(sku.get('skuName') or sku.get('name') or '')
        name_codes=set(re.findall(r'\b[A-Za-z]{1,6}-?\d{2,6}\b',name.upper()))
        ocr_text=' '.join(str(row.get('text','')) for row in (image or {}).get('ocr',[]) if float(row.get('score',0)) >= .9)
        image_codes=set(re.findall(r'\b[A-Za-z]{1,6}-?\d{2,6}\b',ocr_text.upper()))
        contradiction=bool(name_codes and image_codes and name_codes.isdisjoint(image_codes))
        if image and not (sku.get('semanticReviewRequired') or sku.get('imageNameMismatch') or contradiction): continue
        url=sku.get('skuImageUrl') or sku.get('imageUrl') or sku.get('image')
        image=next((row for row in images if row.get('url') == url), None)
        if not image:
            items.append({'id':'SKU_MISSING_'+str(index).zfill(3),'task_type':'sku_match','sku_row_index':index,'sku_id':str(sku.get('skuId') or sku.get('id') or index),'reason':'MISSING_IMAGE','evidence_ids':[]})
            continue
        identity=str(sku.get('skuId') or sku.get('id') or index)
        item_id='SKU_MATCH_'+str(index).zfill(3)
        local=Path(image['file'])
        if not local.is_absolute(): local=Path(__file__).parent/local
        pool=image.get('kind','sku');image_index=image.get('index',index)
        image_id=pool.upper()+'_'+str(image_index).zfill(3)
        items.append({'id':item_id,'task_type':'sku_match','sku_id':identity,'sku_row_index':index,'image_id':image_id,
                      'pool':pool,'kind':pool,'index':image_index,'source_url':image.get('url'),'source_sha256':image.get('content_sha256'),
                      'local':str(local),'sha256':image.get('content_sha256'),'sku_name':sku.get('skuName',sku.get('name')),'sku_specification':sku,
                      'reason':'IMAGE_NAME_MISMATCH','evidence_ids':[item_id]})
    # Title model review is disabled by the current user scope. Deterministic
    # source/SOP checks and one translation remain in the title action path.
    if product.get('identityReviewRequired') or flags.get('product_checks',{}).get('identity_review_required'):
        image=next((row for row in images if row.get('kind')=='main' and not row.get('error')),None)
        item={'id':'PRODUCT_IDENTITY_001','task_type':'product_identity','reason':'IDENTITY_UNCERTAIN','evidence_ids':['PRODUCT_IDENTITY_001']}
        if image:
            local=Path(image['file'])
            if not local.is_absolute(): local=Path(__file__).parent/local
            pool=image.get('kind','main');image_index=image.get('index',0)
            item.update(local=str(local),sha256=image.get('content_sha256'),image_id=pool.upper()+'_'+str(image_index).zfill(3),pool=pool,index=image_index,source_url=image.get('url'))
        items.append(item)
    return items
