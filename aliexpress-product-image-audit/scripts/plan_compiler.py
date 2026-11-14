"""Deterministic conservative compiler; AI opinions never become write operations."""
import hashlib
import json
from pathlib import Path
from job_manager import atomic_json
from plan_v2 import validate_plan, plan_hash,planned_upload_count
from policy_engine import evaluate
from product_state import canonical_state_hash

def compile_auto_plan(directory, job, candidates, policy):
    """Compile verified independent actions without fabricating a manual review."""
    from copy import deepcopy
    from auto_decision import decide
    from final_state import pre_apply_validate
    root=Path(directory)
    product=json.loads((root/'audit_product.json').read_text(encoding='utf-8'))
    execution=job.get('mode') not in {'audit','dry_run'}
    rows=decide(candidates,policy,pid=job['pid'],shop=job['shop_id'],execution=execution)
    conditional_path=root/'conditional_decisions.json'
    if conditional_path.exists():
        transitions=json.loads(conditional_path.read_text(encoding='utf-8'))
        for row in rows:
            if any(event['item_id']==row['item_id'] and event['action']==row['action'] for event in transitions['items']):
                transitions['items'].append({'item_id':row['item_id'],'action':row['action'],'decision':row['decision'],'stage':'action_validation_and_local_authorization','reason_codes':row.get('reason_codes',[])})
        atomic_json(conditional_path,transitions)
    atomic_json(root/'remedy_candidates.json',{'items':candidates})
    atomic_json(root/'auto_decisions.json',{'policy_sha256':policy.sha256,'items':rows})
    deferred=[r for r in rows if r['decision'] not in {'AUTO_SAFE','KEEP'}]
    atomic_json(root/'deferred_items.json',{'items':deferred})
    safe=[r for r in rows if r['decision']=='AUTO_SAFE']
    plan=dict(schema='token-opt-plan/v3',job_id=job['job_id'],pid=job['pid'],shop=job['shop_id'],
              workflow_version='token-opt-v2',policy_version=job['policy_version'],
              precondition={'state_sha256':canonical_state_hash(product)},evidence_refs=[],ai_judgement_refs=[],
              desired={},post_actions={},review={'status':'RESOLVED'},
              automation={'policy_sha256':policy.sha256,'actions':[r['action'] for r in safe]})
    if job.get('account_fingerprint'):plan['precondition']['account_fingerprint']=job['account_fingerprint']
    images=deepcopy(product.get('images') or {})
    protected_urls=set()
    for row in deferred:
        target=row.get('target',{});pool=target.get('pool');index=target.get('index')
        if pool in images and type(index) is int and 0<=index<len(images[pool]):protected_urls.add(images[pool][index])
    used=set();mappings={};uploads=[];deletions=[]
    try:
        for row in safe:
            from remedy_binding import verify as verify_binding
            verify_binding(root,row,product)
            action=row['action']; target=row['target']
            if action in {'REPLACE_TWIN','REPLACE_LOCAL','CROP_BANNER','BOX_NORMALIZE','ERASE_LOCAL'}:
                pool,index=target['pool'],target['index']
                if type(index) is not int or index<0 or pool not in images or index>=len(images[pool]) or (pool,index) in used:
                    raise ValueError('INVALID_OR_DUPLICATE_TARGET')
                used.add((pool,index))
                if target.get('image_id')!=pool.upper()+'_'+str(index).zfill(3): raise ValueError('IMAGE_ID_MISMATCH')
                if action=='REPLACE_TWIN':
                    url=row['source']['url']
                    if not any(url in urls for urls in images.values()): raise ValueError('SOURCE_NOT_IN_PRODUCT_POOL')
                    original_url=images[pool][index]
                    images[pool][index]=url
                    if original_url not in protected_urls:mappings[original_url]=url
                else:
                    asset=row.get('candidate_asset') or {}
                    if (asset.get('pool'),asset.get('index'))!=(pool,index): raise ValueError('ASSET_TARGET_MISMATCH')
                    path=(root/asset['path']).resolve()
                    if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=asset['sha256']:
                        raise ValueError('ASSET_HASH_MISMATCH')
                    uploads.append({k:asset[k] for k in ('path','sha256','pool','index')})
            elif action=='DELETE_REDUNDANT':
                pool,index=target['pool'],target['index']
                if pool not in {'main','detail'} or type(index) is not int or not 0<=index<len(images.get(pool,[])) or (pool,index) in used or target.get('image_id')!=pool.upper()+'_'+str(index).zfill(3):raise ValueError('INVALID_DELETION_TARGET')
                used.add((pool,index));deletions.append((pool,index,product['images'][pool][index]))
            elif action=='SKU_ASSIGN':
                if row.get('row_assignments'):
                    from snapshot_sku import validate_assignments
                    assignments=validate_assignments(product,row['row_assignments'])
                    if (not policy.config.get('allow_snapshot_sku_rows') or row.get('assignments') or
                            row.get('checks',{}).get('snapshot_rows_bound') is not True or
                            target.get('sku_row_indices')!=[entry['index'] for entry in assignments] or
                            plan['post_actions'].get('sku_row_assignments') or plan['post_actions'].get('sku_assignments')):
                        raise ValueError('SNAPSHOT_SKU_ASSIGNMENT_NOT_AUTHORIZED')
                    plan['post_actions']['sku_row_assignments']=deepcopy(assignments)
                    continue
                assignments=row['assignments']
                known={str(s.get('skuId',s.get('id',''))) for s in product.get('skus',[])}
                if not assignments or not set(assignments)<=known or set(assignments)!=set(target['sku_ids']):
                    raise ValueError('UNKNOWN_SKU_ASSIGNMENT')
                if any(not any(url in pool for pool in images.values()) for url in assignments.values()):
                    raise ValueError('SKU_SOURCE_NOT_IN_PRODUCT')
                if set(assignments)&set(plan['post_actions'].get('sku_assignments',{})): raise ValueError('DUPLICATE_SKU_ASSIGNMENT')
                plan['post_actions'].setdefault('sku_assignments',{}).update(assignments)
            elif action=='TITLE_REWRITE':
                from title_rewrite import rewrite_title
                generated=rewrite_title(product,job['shop_id'])
                if not generated['ok'] or generated['titleEn']!=row['titleEn'] or generated.get('modelCode')!=row.get('modelCode'):
                    raise ValueError('TITLE_DOES_NOT_MATCH_SOP')
                if product.get('titleEn')!=row['titleEn']:
                    plan['desired']['titleEn']=row['titleEn']
                    plan['post_actions']['translate_title']=True
                if row.get('modelCode'):
                    from product_state import identity_object
                    identity=identity_object(product.get('identityJson') or {})
                    if identity.get('modelCode')!=row['modelCode']:
                        identity['modelCode']=row['modelCode']
                        plan['desired']['identityJson']=json.dumps(identity,ensure_ascii=False)
            elif action=='BRAND_CODE':
                from title_rewrite import rewrite_title
                brand_rule=rewrite_title(product,job['shop_id'])
                if row.get('brand_field_verified') is not True or row.get('brandId') not in {200017853,200014695}:
                    raise ValueError('BRAND_FIELD_MAPPING_UNVERIFIED')
                if type(product.get('brandId')) is not int or product['brandId'] not in {200017853,200014695} or product.get('brand') or not brand_rule.get('ok') or row['brandId']!=brand_rule.get('brandCode'):
                    raise ValueError('BRAND_FIELD_ALIAS_OR_RULE_CONFLICT')
                if product.get('brandId')!=row['brandId']:plan['desired']['brandId']=row['brandId']
            else:
                raise ValueError('ACTION_COMPILER_NOT_IMPLEMENTED: '+action)
        def remap(value):
            if isinstance(value,str): return mappings.get(value,value)
            if isinstance(value,list): return [remap(v) for v in value]
            if isinstance(value,dict): return {k:remap(v) for k,v in value.items()}
            return value
        if deletions:
            for pool,index,url in sorted(deletions,key=lambda row:(row[0],-row[1])):del images[pool][index]
            for upload in uploads:upload['index']-=sum(pool==upload['pool'] and index<upload['index'] for pool,index,url in deletions)
            positions={}
            for row in safe:
                target=row['target'];pool,index=target.get('pool'),target.get('index')
                if pool is not None and row['action']!='DELETE_REDUNDANT':
                    positions[target['image_id']]={'pool':pool,'index':index-sum(p==pool and i<index for p,i,url in deletions)}
            if positions:plan['post_actions']['target_positions']=positions
        if mappings or uploads or images!=product.get('images',{}):
            plan['desired']['images']={pool:remap(urls) if pool in {'main','detail','sku'} else urls for pool,urls in images.items()}
        # SKU linkage is handled in the common simulator, including existing-pool twins.
        if mappings: plan['post_actions']['url_replacements']=mappings
        if uploads: plan['post_actions']['uploads']=uploads
        if uploads and protected_urls:plan['post_actions']['preserve_reference_urls']=sorted(protected_urls)
        policy.authorize(job['pid'],job['shop_id'],plan['automation']['actions'],uploads=planned_upload_count(plan),execution=execution)
        validation=pre_apply_validate(product,plan)
        if not validation['ok'] and (plan['desired'] or plan['post_actions'] or not deferred):
            raise ValueError('INVALID_FINAL_STATE: '+repr(validation['errors']))
        from final_state import simulate_final_snapshot
        if not uploads and canonical_state_hash(simulate_final_snapshot(product,plan))==canonical_state_hash(product):
            plan['desired']={};plan['post_actions']={}
        # Bind every decision and input file; executor verifies these before any I/O.
        names=['audit_product.json','remedy_candidates.json','auto_decisions.json','deferred_items.json']
        names += [n for n in ('audit_account.json','conditional_decisions.json','candidate_quality.json','box_validation.json','deletion_validation.json','main_cleanup.json','audit_coverage.json','semantic_validation.json','ai_queue.json','ai_judgements.json','audit_flags.json','audit_raw.json','evidence_manifest.json') if (root/n).exists()]
        names += [str(p.relative_to(root)) for p in sorted((root/'quality_evidence').glob('*')) if p.is_file()]
        manifest_path=root/'evidence_manifest.json'
        if manifest_path.exists():
            for ref in json.loads(manifest_path.read_text(encoding='utf-8')).get('files',[]):
                path=(root/ref['path']).resolve()
                if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=ref['sha256']:
                    raise ValueError('EVIDENCE_MANIFEST_FILE_CHANGED')
                if ref['path'] not in names:names.append(ref['path'])
        plan['evidence_refs']=[dict(path=n,sha256=hashlib.sha256((root/n).read_bytes()).hexdigest()) for n in names]
        validate_plan(plan)
        atomic_json(root/'plan.v2.json',plan)
        changed=bool(plan['desired'] or plan['post_actions'])
        result=dict(ok=True,status='AUTO_READY' if changed else 'DEFERRED' if deferred else 'CLEAN',
                    plan_sha256=plan_hash(plan),deferred_count=len(deferred),read_only=not bool(plan['desired'] or plan['post_actions']),
                    existing_state_findings=validation['errors'] if not validation['ok'] else [])
        atomic_json(root/'compiled_plan.json',dict(result,plan=plan))
    except (ValueError,KeyError,TypeError,OSError) as exc:
        (root/'plan.v2.json').unlink(missing_ok=True)
        result=dict(ok=False,status='BLOCKED_FATAL',error_codes=[str(exc)])
    atomic_json(root/'plan_validation.json',result)
    return result

def compile_plan(directory, job, review=None):
    root=Path(directory)
    read=lambda name: json.loads((root/name).read_text(encoding='utf-8'))
    product=read('audit_product.json'); flags=read('audit_flags.json')
    judgements=read('ai_judgements.json')
    policies={key:evaluate(value) for key,value in sorted(judgements.items())}
    unresolved=[key for key,value in policies.items() if value != 'KEEP']
    if flags.get('summary',{}).get('ocr_enabled') is False or flags.get('anomalies') or flags.get('uncertain_refs') or flags.get('summary',{}).get('image_errors'):
        unresolved.append('MACHINE_ANOMALIES')
    if review:
        from manual_review import validate_review
        decisions=validate_review(root,job,review)
        actionable={key for change in review.get('changes',[]) if change.get('action') for key in change.get('item_ids',[])}
        unresolved=[key for key in unresolved if decisions.get(key) not in {'KEEP','WEB_DEFER'} and not (key in actionable and decisions.get(key) in {'REMOVE_CANDIDATE','REMOVE_CANDIDATE_CONFIRMED','REPLACE_LOCAL','CROP_BANNER','SKU_ASSIGN_CONFIRMED'})]
    atomic_json(root/'policy_decisions.json',{'policies':policies,'unresolved':unresolved})
    atomic_json(root/'decision_plan.json',{'status':'NEEDS_REVIEW' if unresolved else 'RESOLVED','unresolved':unresolved})
    if unresolved:
        result={'ok':False,'status':'NEEDS_REVIEW','unresolved':unresolved,'policies':policies}
        atomic_json(root/'plan_validation.json',result)
        return result
    names=['audit_product.json','audit_flags.json','audit_raw.json']
    if (root/'audit_account.json').exists():names.append('audit_account.json')
    if (root/'evidence_manifest.json').exists():
        manifest=read('evidence_manifest.json')
        names+=['evidence_manifest.json','ai_queue.json']+[r['path'] for r in manifest.get('files',[])]
    refs=[{'path':name,'sha256':hashlib.sha256((root/name).read_bytes()).hexdigest()} for name in names]
    plan={'schema':'token-opt-plan/v2','job_id':job['job_id'],'pid':job['pid'],'shop':job['shop_id'],'workflow_version':'token-opt-v2','policy_version':job['policy_version'],'precondition':{'state_sha256':canonical_state_hash(product)},'evidence_refs':refs,'ai_judgement_refs':[{'path':'ai_judgements.json','sha256':hashlib.sha256((root/'ai_judgements.json').read_bytes()).hexdigest()}],'desired':{},'post_actions':{},'review':{'status':'RESOLVED'}}
    if job.get('account_fingerprint'):plan['precondition']['account_fingerprint']=job['account_fingerprint']
    if review and review.get('changes'):
        queue={row['id']:row for row in read('ai_queue.json')['items']}
        desired={}
        review_rows={row['item_id']:row for row in review['items']}
        uploads=[]
        from approved_deletions import validate_batch
        batch_urls=set()
        for candidate in review['changes']:
            if candidate.get('field')=='images' and candidate.get('action')=='DELETE_BATCH':
                batch_urls.update(validate_batch(product,read('audit_raw.json'),queue,review_rows,candidate))
        for change in review['changes']:
            field=change.get('field')
            if field not in {'titleEn','images','brandId'} or field in desired:
                raise ValueError('forbidden or duplicate change')
            ids=change.get('item_ids',[])
            if not ids or any(key not in decisions or key not in queue for key in ids):
                raise ValueError('unreviewed change')
            for key in ids:
                row=review_rows[key]
                if row['decision'] in {'KEEP','WEB_DEFER','NEEDS_MORE_EVIDENCE','NEEDS_REVIEW'}:
                    result={'ok':False,'status':'NEEDS_REVIEW','error_codes':['ACTION_NOT_AUTHORIZED']}
                    atomic_json(root/'plan_validation.json',result)
                    return result
                action=change.get('action')
                checked_action='DELETE' if action=='DELETE_BATCH' else action
                allowed={'REMOVE_CANDIDATE':{'DELETE','CROP_BANNER','REPLACE_LOCAL'},'REMOVE_CANDIDATE_CONFIRMED':{'DELETE','CROP_BANNER','REPLACE_LOCAL','UPDATE_TITLE'},'REPLACE_LOCAL':{'REPLACE_LOCAL'},'CROP_BANNER':{'CROP_BANNER'},'SKU_ASSIGN_CONFIRMED':{'SKU_ASSIGN'}}
                if checked_action not in allowed.get(row['decision'],set()):
                    raise ValueError('ACTION_NOT_AUTHORIZED')
                if action=='REPLACE_LOCAL' and row.get('asset') != change.get('asset'):
                    raise ValueError('review asset mismatch')
                if not action or checked_action not in row.get('authorized_actions',[]):
                    raise ValueError('ACTION_NOT_AUTHORIZED')
                if row['decision']=='REPLACE_LOCAL' and action!='REPLACE_LOCAL':
                    raise ValueError('ACTION_NOT_AUTHORIZED')
                item=queue[key]
                target=change.get('target',{})
                if field=='images' and action!='DELETE_BATCH':
                    if target.get('pool')!=item.get('kind') or target.get('index')!=item.get('index'):
                        raise ValueError('review target mismatch')
                    proposed=change['value']; original=product.get('images',{})
                    pool=target['pool']; index=target['index']
                    if type(index) is not int or pool not in original or not 0<=index<len(original[pool]):
                        raise ValueError('review target missing')
                    expected={k:list(v) for k,v in original.items()}
                    if change.get('action')=='DELETE': del expected[pool][index]
                    elif change.get('action')!='REPLACE_LOCAL': raise ValueError('unsupported image action')
                    if proposed!=expected: raise ValueError('unreviewed image target changed')
                if item.get('local'):
                    source=Path(item['local'])
                    if hashlib.sha256(source.read_bytes()).hexdigest()!=item.get('sha256'):
                        raise ValueError('original image changed')
            if field=='images':
                original=product.get('images',{})
                proposed=change['value']
                raw=read('audit_raw.json')
                protected=set()
                for row in raw.get('images',[]):
                    if row.get('image_type') in {'box','packaging'} or row.get('is_box') is True:
                        protected.add(row.get('url'))
                for judgement in judgements.values():
                    for result in judgement.get('results',[]):
                        if result.get('image_type') in {'box','packaging'}:
                            image_id=result.get('image_id')
                            protected.update(row.get('url') for row in raw.get('images',[]) if row.get('file')==image_id or row.get('id')==image_id)
                for pool,urls in original.items():
                    if any(url in protected and url not in proposed.get(pool,[]) for url in urls):
                        raise ValueError('box image deletion forbidden')
                if change.get('action')=='REPLACE_LOCAL':
                    from PIL import Image
                    asset=change.get('asset',{})
                    source=(root/asset.get('path','')).resolve()
                    if not source.is_relative_to(root.resolve()) or not source.is_file() or not asset.get('sha256') or hashlib.sha256(source.read_bytes()).hexdigest()!=asset['sha256']:
                        raise ValueError('invalid replacement asset')
                    with Image.open(source) as image:
                        image.verify()
                    pool=asset.get('pool'); index=asset.get('index')
                    if {'pool':pool,'index':index} != change.get('target'):
                        raise ValueError('replacement target mismatch')
                    if pool not in original or type(index) is not int or not 0<=index<len(original[pool]):
                        raise ValueError('invalid replacement target')
                    if proposed!=original:
                        raise ValueError('replacement must preserve original URLs until upload')
                    uploads.append({k:asset[k] for k in ('path','sha256','pool','index')})
                known_sku_refs=set()
                if change.get('action')=='DELETE_BATCH' and change.get('preserve_existing_sku_refs') is True:
                    known_sku_refs={s.get('skuImageUrl') or s.get('imageUrl') or s.get('image') for s in product.get('skus') or []}
                if any(url not in original.get(pool,[]) and not (pool=='sku' and url in known_sku_refs) for pool,urls in proposed.items() for url in urls):
                    raise ValueError('unverified image URL')
            desired[field]=change['value']
        plan['desired']=desired
        if uploads: plan['post_actions']={'uploads':uploads}
    validate_plan(plan)
    atomic_json(root/'plan.v2.json',plan)
    result={'ok':True,'plan_sha256':plan_hash(plan),'operations':[{'field':key,'value':value} for key,value in sorted(plan['desired'].items())],'read_only':not bool(plan['desired'])}
    atomic_json(root/'compiled_plan.json',dict(result,plan=plan)); atomic_json(root/'plan_validation.json',result)
    return result
