"""Deterministic conservative compiler; AI opinions never become write operations."""
import hashlib
import json
from pathlib import Path
from mye_c_automation.job_manager import atomic_json
from mye_c_automation.plan_v2 import validate_plan, plan_hash, planned_upload_count
from mye_c_automation.policy_engine import evaluate
from mye_c_automation.product_state import canonical_state_hash


def _reviewed_sku_records(source,product):
    from mye_c_automation.v2_remediation import verify_audit
    source=Path(source).resolve();job=json.loads((source/'job.json').read_text(encoding='utf-8'))
    inventory,judgements=verify_audit(source,job)
    known={u for pool in ('main','detail','sku') for u in (product.get('images') or {}).get(pool,[])}
    records=[]
    for digest,content in inventory['contents'].items():
        url=next((u for u in content['urls'] if u in known),None)
        if url is None:continue
        if hashlib.sha256(Path(content['file']).read_bytes()).hexdigest()!=digest:raise ValueError('SKU_SOURCE_IMAGE_CHANGED')
        result=judgements[digest]
        records.append(dict(sha256=digest,url=url,image_id=content['occurrence_ids'][0],observation=result.get('observation'),decision=result['decision'],width=content['width'],height=content['height']))
    return job,records


def verify_reviewed_sku_source(directory):
    """Recheck archived source references and repeat selection before a SKU-only save."""
    from mye_c_automation import sku_assignment
    root=Path(directory);read=lambda n:json.loads((root/n).read_text(encoding='utf-8'))
    binding=read('sku_source_binding.json');source=Path(binding['source_directory']).resolve()
    for name,digest in binding['source_files'].items():
        path=(source/name).resolve()
        if not path.is_relative_to(source) or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('SKU_SOURCE_EVIDENCE_CHANGED')
    product=read('audit_product.json');job,records=_reviewed_sku_records(source,product);current=read('job.json')
    if (job['pid'],str(job['shop_id']),job.get('account_fingerprint'))!=(current['pid'],str(current['shop_id']),current.get('account_fingerprint')):raise ValueError('SKU_SOURCE_CONTEXT_MISMATCH')
    if binding['selection_implementation_sha256']!=hashlib.sha256(Path(sku_assignment.__file__).read_bytes()).hexdigest():raise ValueError('SKU_SELECTION_IMPLEMENTATION_CHANGED')
    selection=sku_assignment.select_v2(product,records,allow_snapshot_rows=binding['allow_snapshot_rows'])
    if selection!=read('v2_sku_selection.json') or selection['reason_codes']:raise ValueError('SKU_SELECTION_CHANGED_OR_INCOMPLETE')
    for row in selection['selected_sku_images']:
        if hashlib.sha256((root/'sku_verified_images'/(row['sha256']+'.bin')).read_bytes()).hexdigest()!=row['sha256']:raise ValueError('SKU_VERIFIED_BYTES_CHANGED')
    return selection


def compile_reviewed_sku_plan(directory,job,product,policy,source_directory,*,fetch_image):
    """Compile a fresh SKU-only plan from sealed observations; no model or old Job replay."""
    from copy import deepcopy
    from mye_c_automation import sku_assignment
    from mye_c_automation.final_state import pre_apply_validate
    policy.authorize(job['pid'],job['shop_id'],['SKU_ASSIGN'],execution=True)
    root=Path(directory).resolve();source=Path(source_directory).resolve()
    if root==source or root.is_relative_to(source) or source.is_relative_to(root):raise ValueError('SKU_SOURCE_MUST_REMAIN_SEPARATE')
    if job.get('input_state_sha256')!=canonical_state_hash(product):raise ValueError('SKU_CURRENT_INPUT_MISMATCH')
    source_job,records=_reviewed_sku_records(source,product)
    if (source_job['pid'],str(source_job['shop_id']),source_job.get('account_fingerprint'))!=(job['pid'],str(job['shop_id']),job.get('account_fingerprint')):raise ValueError('SKU_SOURCE_CONTEXT_MISMATCH')
    selection=sku_assignment.select_v2(product,records,allow_snapshot_rows=policy.config.get('allow_snapshot_sku_rows') is True)
    if selection['reason_codes'] or not (selection['assignments'] or selection['row_assignments']):raise ValueError('SKU_SELECTION_INCOMPLETE:'+repr(selection['reason_codes']))
    names=[r['path'] for r in json.loads((source/'full_audit_evidence_manifest.json').read_text(encoding='utf-8'))['files']]
    names+=['job.json','full_audit_evidence_manifest.json']
    if (source/'v2_policy_reassessment.json').exists():names.append('v2_policy_reassessment.json')
    binding=dict(source_directory=str(source),source_files={n:hashlib.sha256((source/n).read_bytes()).hexdigest() for n in names},allow_snapshot_rows=policy.config.get('allow_snapshot_sku_rows') is True,selection_implementation_sha256=hashlib.sha256(Path(sku_assignment.__file__).read_bytes()).hexdigest(),model_requests=0,scope='FRESH_SNAPSHOT_SKU_ONLY_FROM_READONLY_ARCHIVED_OBSERVATIONS')
    verified=root/'sku_verified_images';verified.mkdir()
    for row in selection['selected_sku_images']:
        data=fetch_image(row['url'])
        if hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('SKU_CURRENT_IMAGE_BYTES_CHANGED')
        (verified/(row['sha256']+'.bin')).write_bytes(data)
    atomic_json(root/'audit_account.json',dict(account_fingerprint=job['account_fingerprint'],status='VERIFIED'))
    atomic_json(root/'audit_product.json',product);atomic_json(root/'sku_source_binding.json',binding);atomic_json(root/'v2_sku_selection.json',selection)
    post={}
    if selection['assignments']:post['sku_assignments']=selection['assignments']
    if selection['row_assignments']:post['sku_row_assignments']=selection['row_assignments']
    images=deepcopy(product['images']);images['sku']=[r['url'] for r in selection['selected_sku_images']]
    names=['job.json','audit_account.json','audit_product.json','sku_source_binding.json','v2_sku_selection.json']+[p.relative_to(root).as_posix() for p in sorted(verified.iterdir())]
    plan=dict(schema='token-opt-plan/v3',job_id=job['job_id'],pid=job['pid'],shop=job['shop_id'],workflow_version='token-opt-v2',policy_version=job['policy_version'],precondition=dict(state_sha256=canonical_state_hash(product),account_fingerprint=job['account_fingerprint']),evidence_refs=[dict(path=n,sha256=hashlib.sha256((root/n).read_bytes()).hexdigest()) for n in names],ai_judgement_refs=[],desired={'images':images},post_actions=post,review={'status':'RESOLVED'},automation={'policy_sha256':policy.sha256,'actions':['SKU_ASSIGN']})
    plan=validate_plan(plan);checked=pre_apply_validate(product,plan)
    if not checked['ok']:raise ValueError('SKU_FINAL_STATE:'+repr(checked['errors']))
    verify_reviewed_sku_source(root)
    compiled=dict(ok=True,status='PLAN_READY',read_only=False,plan_sha256=plan_hash(plan),stage='SKU_ONLY_CORRECTION_FROM_SEALED_OBSERVATIONS')
    atomic_json(root/'plan.v2.json',plan);atomic_json(root/'compiled_plan.json',compiled)
    return plan,compiled


def compile_main_count_preflight(directory,job,product,policy):
    """Compile the explicit user count rule, without inventing an AI judgement."""
    from copy import deepcopy
    from mye_c_automation.final_state import pre_apply_validate
    if policy.config.get('trim_seven_main_before_audit') is not True:raise ValueError('MAIN_PREFLIGHT_NOT_AUTHORIZED')
    policy.authorize(job['pid'],job['shop_id'],['DELETE'],execution=True)
    images=deepcopy(product.get('images') or {})
    if len(images.get('main') or [])!=7:raise ValueError('MAIN_PREFLIGHT_REQUIRES_EXACT_SEVEN')
    removed=images['main'].pop(0);root=Path(directory)
    proof=dict(rule='USER_MAIN_COUNT_EXACT_SEVEN',source='EXPLICIT_USER_POLICY',removed_pool='main',removed_index=0,
        removed_url=removed,before_count=7,after_count=6,state_sha256=canonical_state_hash(product),
        policy_sha256=policy.sha256,model_requests=0,scope='main reference only; preserve detail/body/SKU')
    atomic_json(root/'main_count_user_rule.json',proof);atomic_json(root/'audit_product.json',product)
    refs=[dict(path=name,sha256=hashlib.sha256((root/name).read_bytes()).hexdigest()) for name in ('main_count_user_rule.json','audit_product.json')]
    plan=dict(schema='token-opt-plan/v3',job_id=job['job_id'],pid=job['pid'],shop=job['shop_id'],
        workflow_version=job['workflow_version'],policy_version=job['policy_version'],
        precondition=dict(state_sha256=canonical_state_hash(product),account_fingerprint=job['account_fingerprint']),
        evidence_refs=refs,ai_judgement_refs=[],desired={'images':images},post_actions={},review={'status':'RESOLVED'},
        automation={'policy_sha256':policy.sha256,'actions':['DELETE']})
    plan=validate_plan(plan);checked=pre_apply_validate(product,plan)
    if not checked['ok']:raise ValueError('MAIN_PREFLIGHT_FINAL_STATE:'+repr(checked['errors']))
    compiled=dict(ok=True,status='PLAN_READY',read_only=False,plan_sha256=plan_hash(plan),stage='BEFORE_MODEL_MAIN_COUNT_RULE')
    atomic_json(root/'plan.v2.json',plan);atomic_json(root/'compiled_plan.json',compiled)
    return plan,compiled

def compile_auto_plan(directory, job, candidates, policy):
    """Compile verified independent actions without fabricating a manual review."""
    from copy import deepcopy
    from mye_c_automation.auto_decision import decide
    from mye_c_automation.final_state import pre_apply_validate
    root=Path(directory)
    product=json.loads((root/'audit_product.json').read_text(encoding='utf-8'))
    if job.get('image_workflow')!='v2' and (job.get('audit_scope')=='full' or (root/'full_audit_report.json').exists() or (root/'full_audit_evidence_manifest.json').exists()):
        from mye_c_automation.full_product_audit import remediation_inputs, localized_confirmed_repair
        _,_,mandatory=remediation_inputs(root,job)
        candidates=list(candidates)
        from mye_c_automation.auto_deletions import validated_composite_deletion
        resolved_deletions={(r.get('target',{}).get('pool'),r.get('target',{}).get('index')) for r in candidates if validated_composite_deletion(root,r)}
        mandatory=[r for r in mandatory if (r.get('target',{}).get('pool'),r.get('target',{}).get('index')) not in resolved_deletions]
        blocked={(r['target'].get('pool'),r['target'].get('index')) for r in mandatory if r['target']}
        if any(r.get('action')!='WEB_DEFER' and (r.get('target',{}).get('pool'),r.get('target',{}).get('index')) in blocked and not localized_confirmed_repair(root,r) for r in candidates):
            raise ValueError('FULL_AUDIT_UNRESOLVED_TARGET')
        full=json.loads((root/'full_audit_report.json').read_text(encoding='utf-8'))
        # A direct compiler caller cannot drop a confirmed full-audit problem.
        # Unrepaired findings remain visible even if the caller supplies no rows.
        for item in full['occurrences']:
            if not (item.get('verdict')=='FAIL' or item.get('confirmed_findings')):continue
            target={'image_id':item['id'],'pool':item.get('pool'),'index':item.get('index')}
            covered=any(row.get('target',{}).get('pool')==target['pool'] and row.get('target',{}).get('index')==target['index'] for row in candidates+mandatory)
            if not covered:
                mandatory.append(dict(remedy_id='FULL_UNREPAIRED_'+item['id'],item_id='FULL_'+item['id'],action='WEB_DEFER',
                    target=target,source={},checks={},evidence_ids=item.get('evidence_ids',[]),reason_codes=['FULL_AUDIT_CONFIRMED_PROBLEM_UNREPAIRED']))
        candidates += [row for row in mandatory if row not in candidates]
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
        if job.get('image_workflow')=='v2' and type(target.get('sku_row_index')) is int:
            sku=product['skus'][target['sku_row_index']]
            url=sku.get('skuImageUrl') or sku.get('imageUrl') or sku.get('image')
            if isinstance(url,str):protected_urls.add(url)
    if job.get('audit_scope')=='full' and job.get('image_workflow')!='v2':
        # Shared SKU references may follow the same verified local image repair
        # when every source-pool occurrence is explicitly included in this plan.
        full=json.loads((root/'full_audit_report.json').read_text(encoding='utf-8'))
        local_targets={(r['target'].get('pool'),r['target'].get('index')) for r in safe if localized_confirmed_repair(root,r)}
        for url in list(protected_urls):
            positions={(r.get('pool'),r.get('index')) for r in full['occurrences'] if r['target_type']=='image_slot' and r.get('url')==url}
            if positions and positions<=local_targets:protected_urls.remove(url)
    used=set();mappings={};uploads=[];deletions=[]
    try:
        for row in safe:
            from mye_c_automation.remedy_binding import verify as verify_binding
            verify_binding(root,row,product)
            action=row['action']; target=row['target']
            if row.get('v2_contract') and target.get('pool')=='description' and action in {'DELETE','REMOVE_TEXT','AI_REGENERATE','REPLACE_TWIN'}:
                from mye_c_automation.description_images import body_image_nodes
                index=target['index'];body={r['index']:r['url'] for r in body_image_nodes(product.get('descriptionJson'))}
                if index not in body or body[index]!=row['source'].get('original_url',row['source']['url']) or ('description',index) in used:raise ValueError('INVALID_DESCRIPTION_TARGET')
                used.add(('description',index))
                if action not in {'DELETE','REPLACE_TWIN'}:
                    asset=row['candidate_asset'];path=(root/asset['path']).resolve()
                    if (asset['pool'],asset['index'])!=('description',index) or not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=asset['sha256']:raise ValueError('ASSET_HASH_MISMATCH')
                    uploads.append({k:asset[k] for k in ('path','sha256','pool','index')})
                continue
            if action in {'REPLACE_TWIN','REPLACE_LOCAL','CROP_BANNER','BOX_NORMALIZE','ERASE_LOCAL','REMOVE_TEXT','AI_REGENERATE'}:
                pool,index=target['pool'],target['index']
                if row.get('v2_append_sku'):
                    if not row.get('v2_contract') or pool!='sku' or index!=len(images.get('sku',[])):raise ValueError('INVALID_SKU_APPEND_TARGET')
                    images.setdefault('sku',[]).append(row['source']['url'])
                if type(index) is not int or index<0 or pool not in images or index>=len(images[pool]) or (pool,index) in used:
                    raise ValueError('INVALID_OR_DUPLICATE_TARGET')
                used.add((pool,index))
                if target.get('image_id')!=pool.upper()+'_'+str(index).zfill(3): raise ValueError('IMAGE_ID_MISMATCH')
                if action=='REPLACE_TWIN':
                    url=row['source']['url']
                    from mye_c_automation.description_images import body_image_nodes
                    known={u for urls in images.values() if isinstance(urls,list) for u in urls}
                    if row.get('v2_contract'):
                        known.update(r['url'] for r in body_image_nodes(product.get('descriptionJson')))
                        known.update(s.get('skuImageUrl') or s.get('imageUrl') or s.get('image') for s in product.get('skus',[]))
                    if url not in known: raise ValueError('SOURCE_NOT_IN_PRODUCT_POOL')
                    original_url=row['source'].get('original_url',images[pool][index])
                    images[pool][index]=url
                    if original_url not in protected_urls:mappings[original_url]=url
                else:
                    asset=row.get('candidate_asset') or {}
                    if (asset.get('pool'),asset.get('index'))!=(pool,index): raise ValueError('ASSET_TARGET_MISMATCH')
                    path=(root/asset['path']).resolve()
                    if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=asset['sha256']:
                        raise ValueError('ASSET_HASH_MISMATCH')
                    uploads.append({k:asset[k] for k in ('path','sha256','pool','index')})
            elif action in {'DELETE_REDUNDANT','DELETE'}:
                pool,index=target['pool'],target['index']
                if pool not in ({'main','detail','sku'} if action=='DELETE' else {'main','detail'}) or type(index) is not int or not 0<=index<len(images.get(pool,[])) or (pool,index) in used or target.get('image_id')!=pool.upper()+'_'+str(index).zfill(3):raise ValueError('INVALID_DELETION_TARGET')
                used.add((pool,index));deletions.append((pool,index,product['images'][pool][index]))
            elif action=='SKU_ASSIGN':
                if row.get('v2_contract') and (row['source'].get('reference_deletions') or row['source'].get('snapshot_reference_deletions')):
                    policy.authorize(job['pid'],job['shop_id'],['DELETE'],execution=execution)
                    if 'DELETE' not in plan['automation']['actions']:plan['automation']['actions'].append('DELETE')
                if row.get('v2_contract') and row.get('sku_pool_urls'):
                    # images.sku is an existing supported list; this does not
                    # invent a second image field on an individual SKU row.
                    allowed_urls={url for urls in (product.get('images') or {}).values() if isinstance(urls,list) for url in urls}
                    allowed_urls.update(s.get('skuImageUrl') or s.get('imageUrl') or s.get('image') for s in product.get('skus',[]))
                    if row.get('v2_contract'):
                        from mye_c_automation.description_images import body_image_nodes
                        allowed_urls.update(r['url'] for r in body_image_nodes(product.get('descriptionJson')))
                    if any(url not in allowed_urls for url in row['sku_pool_urls']):raise ValueError('SKU_POOL_SOURCE_NOT_IN_PRODUCT')
                    for url in row['sku_pool_urls']:
                        if url not in images.setdefault('sku',[]):images['sku'].append(url)
                if row.get('row_assignments'):
                    from mye_c_automation.snapshot_sku import validate_assignments
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
                from mye_c_automation.title_rewrite import rewrite_title
                generated=rewrite_title(product,job['shop_id'])
                if not generated['ok'] or generated['titleEn']!=row['titleEn'] or generated.get('modelCode')!=row.get('modelCode'):
                    raise ValueError('TITLE_DOES_NOT_MATCH_SOP')
                if product.get('titleEn')!=row['titleEn']:
                    plan['desired']['titleEn']=row['titleEn']
                    plan['post_actions']['translate_title']=True
                if row.get('modelCode'):
                    from mye_c_automation.product_state import identity_object
                    identity=identity_object(product.get('identityJson') or {})
                    if identity.get('modelCode')!=row['modelCode']:
                        identity['modelCode']=row['modelCode']
                        plan['desired']['identityJson']=json.dumps(identity,ensure_ascii=False)
            elif action=='BRAND_CODE':
                from mye_c_automation.title_rewrite import rewrite_title
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
            deleted_positions={(pool,index) for pool,index,url in deletions}
            for row in safe:
                if row.get('v2_contract') and row['action']=='DELETE':
                    for sku_id,url in row['source'].get('sku_replacements',{}).items():
                        if plan['post_actions'].get('sku_assignments',{}).get(sku_id)!=url:raise ValueError('V2_DELETE_SKU_REPLACEMENT_NOT_IN_PLAN')
                    for bound in row['source'].get('snapshot_sku_replacements',[]):
                        if bound not in plan['post_actions'].get('sku_row_assignments',[]):raise ValueError('V2_DELETE_SKU_REPLACEMENT_NOT_IN_PLAN')
                for reference in row.get('source',{}).get('retained_references',[]):
                    if (reference['pool'],reference['index']) in deleted_positions:raise ValueError('COMPOSITE_REFERENCE_MUST_REMAIN')
            for pool,index,url in sorted(deletions,key=lambda row:(row[0],-row[1])):del images[pool][index]
            for upload in uploads:upload['index']-=sum(pool==upload['pool'] and index<upload['index'] for pool,index,url in deletions)
            positions={}
            for row in safe:
                target=row['target'];pool,index=target.get('pool'),target.get('index')
                if pool is not None and pool!='description' and row['action'] not in {'DELETE_REDUNDANT','DELETE'}:
                    positions[target['image_id']]={'pool':pool,'index':index-sum(p==pool and i<index for p,i,url in deletions)}
            if positions:plan['post_actions']['target_positions']=positions
        if mappings or uploads or images!=product.get('images',{}):
            plan['desired']['images']={pool:remap(urls) if pool in {'main','detail','sku'} else urls for pool,urls in images.items()}
        # SKU linkage is handled in the common simulator, including existing-pool twins.
        if mappings: plan['post_actions']['url_replacements']=mappings
        if uploads: plan['post_actions']['uploads']=uploads
        if (uploads or any(r['action']=='REPLACE_TWIN' for r in safe)) and protected_urls:plan['post_actions']['preserve_reference_urls']=sorted(protected_urls)
        if job.get('image_workflow')=='v2':
            from mye_c_automation.image_content_plan import compile_groups
            inventory=json.loads((root/'full_inventory.json').read_text(encoding='utf-8'))
            groups=compile_groups(inventory,safe,rows)
            if groups:plan['post_actions']['content_groups']=groups
        policy.authorize(job['pid'],job['shop_id'],plan['automation']['actions'],uploads=planned_upload_count(plan),execution=execution)
        validation=pre_apply_validate(product,plan)
        if not validation['ok'] and (plan['desired'] or plan['post_actions'] or not deferred):
            raise ValueError('INVALID_FINAL_STATE: '+repr(validation['errors']))
        from mye_c_automation.final_state import simulate_final_snapshot
        if not uploads and canonical_state_hash(simulate_final_snapshot(product,plan))==canonical_state_hash(product):
            plan['desired']={};plan['post_actions']={}
        # Bind every decision and input file; executor verifies these before any I/O.
        names=['audit_product.json','remedy_candidates.json','auto_decisions.json','deferred_items.json']
        if job.get('image_workflow')=='v2':
            names += ['job.json','v2_action_proofs.json','v2_quality.json','v2_sku_selection.json']
            names += ['full_visual_versions.json']
            if (root/'v2_policy_reassessment.json').is_file():names.append('v2_policy_reassessment.json')
            names += [str(p.relative_to(root)) for p in sorted((root/'v2_candidates').rglob('*')) if p.is_file()]
        names += [n for n in ('full_audit_evidence_manifest.json','full_audit_report.json','full_inventory.json','full_ai_queue.json','full_ai_judgements.json','full_audit_protocol.json','coverage_matrix.json','audit_account.json','conditional_decisions.json','mye_c_automation.candidate_quality.json','box_validation.json','deletion_validation.json','main_cleanup.json','mye_c_automation.audit_coverage.json','semantic_validation.json','ai_queue.json','ai_judgements.json','audit_flags.json','audit_raw.json','evidence_manifest.json') if (root/n).exists()]
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
        from mye_c_automation.manual_review import validate_review
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
        from mye_c_automation.approved_deletions import validate_batch
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
