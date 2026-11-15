"""Automatic remediation after the existing machine audit and candidate pipeline."""
from policy_engine import MODEL_CONFIDENCE_MIN
import json
from pathlib import Path
from candidate_quality import CandidateQualityGate
from remedy_planner import RemedyPlanner
from plan_compiler import compile_auto_plan
from policy_engine import evaluate
from job_manager import atomic_json

def deferral_reasons(item, judgement, disposition):
    """Separate an unresolved judgement from a rejected remediation candidate.

    Reporting only: the policy decision and all execution gates stay unchanged.
    """
    reasons=[]
    if item.get('task_type')=='watermark' and disposition=='NEEDS_REVIEW':
        reasons.append('WATERMARK_OWNERSHIP_UNVERIFIED')
        results=judgement.get('results',[])
        if not results:reasons.append('MODEL_RESULTS_MISSING')
        if any(row.get('confidence',0)<MODEL_CONFIDENCE_MIN for row in results):
            reasons.append('MODEL_CONFIDENCE_BELOW_THRESHOLD')
        if any(row.get('abstain') for row in results):reasons.append('MODEL_ABSTAINED')
        if len({row.get('classification') for row in results})>1:
            reasons.append('MODEL_CLASSIFICATIONS_DIFFER')
        if len(reasons)==1:reasons.append('POLICY_REQUIRES_REVIEW')
    if item.get('reference_only'):reasons.append('SKU_REFERENCE_ONLY_NO_POOL_TARGET')
    return reasons or ['NO_VERIFIED_REMEDY']

def prepare(directory,job,policy,quality_gate=None):
    if job.get('image_workflow')=='v2':
        from v2_remediation import prepare as prepare_v2
        return prepare_v2(directory,job,policy,quality_gate)
    root=Path(directory)
    read=lambda name:json.loads((root/name).read_text(encoding='utf-8'))
    product=read('audit_product.json')
    full_deferred=[]
    if job.get('audit_scope')=='full' or (root/'full_audit_report.json').exists() or (root/'full_audit_evidence_manifest.json').exists():
        from full_product_audit import remediation_inputs
        queue,judgements,full_deferred=remediation_inputs(root,job)
    else:
        queue=read('ai_queue.json')['items'];judgements=read('ai_judgements.json')
    images=read('audit_raw.json')['images']
    images=[r for r in images if r.get('kind') in {'main','detail','sku'}]
    queue=[r for r in queue if r.get('task_type')!='watermark' or r.get('pool') in {'main','detail','sku'}]
    from automation_policy import ACTIONS
    planner=RemedyPlanner(root,quality_gate or CandidateQualityGate(),allowed_actions={a for a in ACTIONS if policy.permits(a)})
    local_pool=[]
    if policy.config.get('local_pool_index'):
        from local_image_pool import load_official_pool
        index=Path(policy.config['local_pool_index'])
        if not index.is_absolute():index=getattr(policy,'path',root/'policy.json').parent/index
        local_pool=load_official_pool(index)
    candidates=[];pending=[]
    if policy.permits('DELETE_REDUNDANT') and policy.config.get('delete_decorated_composites') is True:
        from auto_deletions import plan_decorated_cleanup
        candidates.extend(plan_decorated_cleanup(root,product,images,planner.quality_gate.inspector))
    composite_targets={(r['target']['pool'],r['target']['index']) for r in candidates if r.get('validation_scope',{}).get('type')=='AUTHORIZED_DECORATED_COMPOSITE_REMOVAL'}
    for item in queue:
        if (item.get('pool'),item.get('index')) in composite_targets:continue
        judgement=judgements.get(item['id'],{})
        disposition=evaluate(judgement)
        if item.get('full_confirmed_findings') and item.get('full_identity_status')!='FAIL' and item['task_type']=='watermark':
            disposition='REMOVE_CANDIDATE'
        if disposition=='KEEP': continue
        candidate=None
        if item['task_type']=='watermark' and disposition=='REMOVE_CANDIDATE' and not item.get('reference_only') and item.get('pool') in {'main','detail','sku'}:
            from full_product_audit import confirmed_edge_proposal
            proposal=confirmed_edge_proposal(item) if policy.permits('CROP_BANNER') else {}
            inspector=planner.quality_gate.inspector
            if not proposal and (policy.permits('CROP_BANNER') or policy.permits('ERASE_LOCAL')) and inspector and callable(getattr(inspector,'propose',None)):
                try:proposal=inspector.propose(Path(item['local']),product) or {}
                except Exception:proposal={}
            candidate=planner.plan(item,images,product,crop_box=proposal.get('crop_box'),subject_box=proposal.get('subject_box'),erase_box=proposal.get('erase_box'),local_pool=local_pool)
            if candidate is None and policy.permits('DELETE_REDUNDANT'):
                from auto_deletions import plan_deletion
                candidate=plan_deletion(root,item,product,images,inspector)
        if candidate: candidates.append(candidate)
        else:
            reasons=deferral_reasons(item,judgement,disposition)
            candidates.append(dict(remedy_id='DEFER_'+item['id'],item_id=item['id'],action='WEB_DEFER',
                                   target={'image_id':item.get('image_id'),'pool':item.get('pool'),'index':item.get('index')},source={},candidate_asset=None,
                                   checks={},evidence_ids=item.get('evidence_ids',[]),reason_codes=reasons))
            pending.append({'item_id':item['id'],'source_url':item.get('source_url'),'reason':reasons[0],'reason_codes':reasons})
    flags=read('audit_flags.json')
    # A low-resolution main/SKU image needs the existing HD-source search even
    # when its watermark ownership result is KEEP. Reuse the same independent
    # identity/packaging/content gate; pHash merely proposes candidates.
    if policy.permits('REPLACE_TWIN') or policy.permits('REPLACE_LOCAL'):
        from PIL import Image
        from workflow_v2_pipeline import image_candidate
        occupied={(r.get('target',{}).get('pool'),r.get('target',{}).get('index')) for r in candidates if r['action']!='WEB_DEFER'}
        for image in images:
            pool,index=image.get('kind'),image.get('index')
            if pool not in {'main','sku'} or image.get('error') or image.get('source')=='skus' or (pool,index) in occupied:continue
            try:
                with Image.open(planner._path(image)) as decoded:
                    if min(decoded.size)>=800:continue
                item=image_candidate(image)
                item.update(id='HD_'+item['image_id'],item_id='HD_'+item['image_id'],evidence_ids=['audit_raw.json'])
                candidate=planner.plan(item,images,product,local_pool=local_pool)
                if candidate:
                    candidate['reason_codes'].append('LOW_RESOLUTION_EXISTING_HD_VERIFIED')
                    candidates.append(candidate);occupied.add((pool,index))
            except (OSError,ValueError,KeyError,TypeError):continue
    if policy.permits('BOX_NORMALIZE'):
        from PIL import Image
        occupied={(r.get('target',{}).get('pool'),r.get('target',{}).get('index')) for r in candidates if r['action']!='WEB_DEFER'}
        for image in images:
            if image.get('source')=='skus':continue
            pool,index=image.get('kind'),image.get('index')
            if pool not in {'main','detail','sku'} or (pool,index) in occupied:continue
            try:
                with Image.open(planner._path(image)) as decoded:
                    if min(decoded.size)>=800:continue
                item=dict(image,id='BOX_'+pool.upper()+'_'+str(index).zfill(3),image_id=pool.upper()+'_'+str(index).zfill(3),pool=pool,evidence_ids=['audit_raw.json'])
                candidate=planner.plan_box(item,product)
                if candidate:
                    candidates.append(candidate);occupied.add((pool,index))
            except (OSError,ValueError,TypeError):continue
    from semantic_remedies import build as build_semantic
    from copy import deepcopy
    generated=deepcopy(candidates)
    for row in generated:
        if row.get('candidate_asset'):
            row['candidate_asset']['path']=str((root/row['candidate_asset']['path']).resolve())
    verified_sku_rows=None
    if (root/'full_audit_report.json').is_file():
        full=read('full_audit_report.json')
        verified_sku_rows={row['sku_row_index']:row.get('evidence_ids',[]) for row in full['occurrences']
                           if row['target_type']=='sku_reference' and row.get('checks',{}).get('sku_packaging')=='PASS'}
    semantic,handled,resolved=build_semantic(product,flags,queue,images,planner.quality_gate.inspector,job['shop_id'],generated_remedies=generated,
                                          allow_snapshot_rows=policy.config.get('allow_snapshot_sku_rows') is True and policy.permits('SKU_ASSIGN'),
                                          allowed_actions={action for action in ACTIONS if policy.permits(action)},verified_sku_rows=verified_sku_rows)
    from product_state import canonical_state_hash
    atomic_json(root/'semantic_validation.json',{'source_product_sha256':canonical_state_hash(product),'candidates':semantic})
    candidates=[r for r in candidates if r['item_id'] not in resolved]+semantic
    from auto_deletions import plan_main_cleanup
    candidates=plan_main_cleanup(root,product,images,planner.quality_gate.inspector,candidates,enabled=policy.permits('DELETE_REDUNDANT'))
    pending=[r for r in pending if r['item_id'] not in resolved]
    deleted={r['target']['index'] for r in candidates if r['action']=='DELETE_REDUNDANT' and r['target']['pool']=='main'}
    if deleted and 1<=len(product.get('images',{}).get('main',[]))-len(deleted)<=6:handled.add('main_count_gt_6')
    for pair in flags.get('duplicates',[]):
        if pair.get('a') in deleted or pair.get('b') in deleted:continue
        item_id='DUP_MAIN_'+str(pair.get('a'))+'_'+str(pair.get('b'))
        candidates.append(dict(remedy_id=item_id,item_id=item_id,action='WEB_DEFER',target={'pool':'main','index':pair.get('b')},source={},checks={},evidence_ids=['audit_flags.json'],reason_codes=['PHASH_DUPLICATE_UNCONFIRMED']))
    for index,anomaly in enumerate(flags.get('anomalies',[])):
        if isinstance(anomaly,dict) and anomaly.get('type') in handled:continue
        if isinstance(anomaly,dict) and anomaly.get('type')=='short_side_lt_800' and any(
            row['action'] in {'REPLACE_TWIN','REPLACE_LOCAL','CROP_BANNER','BOX_NORMALIZE'} and
            (row['target'].get('pool'),row['target'].get('index'))==(anomaly.get('kind'),anomaly.get('index'))
            for row in candidates):continue
        candidates.append(dict(remedy_id='ANOMALY_'+str(index),item_id='ANOMALY_'+str(index),action='WEB_DEFER',target={},source={},checks={},evidence_ids=['audit_flags.json'],reason_codes=[str(anomaly)]))
    summary=flags.get('summary',{})
    if summary.get('ocr_enabled') is not True or summary.get('image_errors') or flags.get('uncertain_refs'):
        candidates.append(dict(remedy_id='AUDIT_INCOMPLETE',item_id='AUDIT_INCOMPLETE',action='WEB_DEFER',target={},source={},checks={},evidence_ids=['audit_flags.json'],reason_codes=['AUDIT_INCOMPLETE']))
    from audit_coverage import verify_sources
    coverage=verify_sources(root,product,images)
    # Keep the original low-size finding visible. It is not a missing download
    # once a verified replacement candidate covers that exact source URL. Every
    # other coverage/hash/decode error remains unresolved; final content must
    # still pass the ordinary saved-image verification.
    fixed_urls=set()
    for row in candidates:
        target=row.get('target',{})
        if row['action'] in {'REPLACE_TWIN','REPLACE_LOCAL','CROP_BANNER','BOX_NORMALIZE'}:
            try:fixed_urls.add(product['images'][target['pool']][target['index']])
            except (KeyError,IndexError,TypeError):pass
    unresolved_missing=set(coverage['missing_urls'])-fixed_urls
    unresolved_errors=[error for error in coverage['errors']
                       if error.get('reason')!='ValueError: LEGACY_SMALL_IMAGE' or error.get('url') not in fixed_urls]
    if fixed_urls:
        coverage['quality_findings_with_replacement_candidates']=sorted(
            {error['url'] for error in coverage['errors'] if error.get('reason')=='ValueError: LEGACY_SMALL_IMAGE'}&fixed_urls)
        atomic_json(root/'audit_coverage.json',coverage)
    if not coverage['ok'] and (unresolved_missing or unresolved_errors):
        candidates.append(dict(remedy_id='AUDIT_COVERAGE_INCOMPLETE',item_id='AUDIT_COVERAGE_INCOMPLETE',action='WEB_DEFER',target={},source={},checks={},evidence_ids=['audit_coverage.json'],reason_codes=['AUDIT_COVERAGE_INCOMPLETE']))
    atomic_json(root/'web_pending.json',{'items':pending,'external_search_enabled':False})
    atomic_json(root/'before.json',product)
    atomic_json(root/'automation_policy_summary.json',{'sha256':policy.sha256,'config':policy.config})
    if full_deferred:
        full_deferred=[r for r in full_deferred if (r.get('target',{}).get('pool'),r.get('target',{}).get('index')) not in composite_targets]
        blocked={r['item_id'] for r in full_deferred}
        targets={(r['target'].get('pool'),r['target'].get('index')) for r in full_deferred if r['target']}
        sku_unknown=any(r['item_id'].startswith('FULL_SKU_ROW_') for r in full_deferred)
        from full_product_audit import localized_confirmed_repair
        from auto_deletions import validated_composite_deletion
        candidates=[r for r in candidates if validated_composite_deletion(root,r) or localized_confirmed_repair(root,r) or (not (sku_unknown and r['action']=='SKU_ASSIGN') and r['item_id'] not in blocked and
                    (r.get('target',{}).get('pool'),r.get('target',{}).get('index')) not in targets)]+full_deferred
    return compile_auto_plan(root,job,candidates,policy)

def verify_content(root,plan,writer,gate):
    job_path=Path(root)/'job.json'
    if job_path.is_file() and json.loads(job_path.read_text(encoding='utf-8')).get('image_workflow')=='v2':
        from v2_remediation import verify_content as verify_v2
        return verify_v2(root,plan,writer)
    """Fetch saved bytes and independently inspect every changed image."""
    root=Path(root)
    rows=json.loads((root/'auto_decisions.json').read_text(encoding='utf-8'))['items']
    after=writer.product(plan['pid'])
    items=[]
    for row in rows:
        if row.get('decision')!='AUTO_SAFE': continue
        target=row['target'];pool,index=target.get('pool'),target.get('index')
        if row['action']=='DELETE_REDUNDANT':
            before=json.loads((root/'before.json').read_text(encoding='utf-8'))
            expected=json.loads((root/'expected_after.json').read_text(encoding='utf-8'))
            count=sum(r.get('decision')=='AUTO_SAFE' and r['action']=='DELETE_REDUNDANT' and r['target'].get('pool')==pool for r in rows)
            valid=after['images'][pool]==expected['images'][pool] and len(after['images'][pool])==len(before['images'][pool])-count
            reference=row['source'].get('reference')
            scope='deletion_readback_and_bound_original_quality'
            retained=row['source'].get('retained_references',[])
            if retained:
                from candidate_quality import sha256
                try:
                    for number,ref in enumerate(retained):
                        path=root/('readback_retained_'+row['target']['image_id']+'_'+str(number)+'.img')
                        path.write_bytes(writer.fetch_image(ref['url']))
                        valid=valid and ref['url'] in after['images'][ref['pool']] and sha256(path)==ref['sha256']
                except Exception:valid=False
                scope='composite_removed_and_retained_material_byte_readback'
            if reference:
                from candidate_quality import sha256
                try:
                    path=root/('readback_duplicate_'+row['target']['image_id']+'.img')
                    path.write_bytes(writer.fetch_image(reference['url']))
                    valid=valid and reference['url'] in after['images'][reference['pool']] and sha256(path)==reference['sha256']
                except Exception:valid=False
                scope='duplicate_retained_reference_byte_readback'
            items.append({'remedy_id':row['remedy_id'],'ok':valid,'scope':scope})
            continue
        position=(plan.get('post_actions') or {}).get('target_positions',{}).get(target.get('image_id'))
        if position:pool,index=position['pool'],position['index']
        if row['action']=='BRAND_CODE':
            from title_rewrite import rewrite_title
            expected=rewrite_title(after,plan['shop'])
            valid=row.get('brand_field_verified') is True and expected.get('ok') is True and after.get('brandId')==row.get('brandId')==expected.get('brandCode')
            items.append({'remedy_id':row['remedy_id'],'ok':valid,'scope':'brandId_readback_and_SOP_mapping'})
            continue
        if row['action']=='TITLE_REWRITE':
            inspector=gate.inspector
            generated={'ok':True,'titleEn':row['titleEn'],'modelCode':row.get('modelCode'),'verify_translation':True}
            checked=inspector.validate_title(after,generated) if inspector and callable(getattr(inspector,'validate_title',None)) else {'ok':False}
            checked['ok']=checked.get('ok') is True and after.get('titleEn')==row['titleEn'] and bool(after.get('titleTranslationZh'))
            items.append(dict(remedy_id=row['remedy_id'],**checked));continue
        if row['action']=='SKU_ASSIGN':
            from sku_assignment import packaging
            raw=json.loads((root/'audit_raw.json').read_text(encoding='utf-8'))['images']
            row_assignments=row.get('row_assignments',[])
            if row_assignments:
                from snapshot_sku import validate_assignments
                validate_assignments(json.loads((root/'before.json').read_text(encoding='utf-8')),row_assignments)
            tasks=[(sku_id,url,None) for sku_id,url in row.get('assignments',{}).items()]
            tasks += [('SNAPSHOT_ROW_'+str(entry['index']),entry['url'],entry['index']) for entry in row_assignments]
            for sku_id,url,row_index in tasks:
                locator={'sku_row_index':row_index} if row_index is not None else {'sku_id':sku_id}
                try:
                    if row.get('requires_remedy_ids') or row_index is not None:
                        expected_snapshot=json.loads((root/'expected_after.json').read_text(encoding='utf-8'))
                        expected_sku=(expected_snapshot['skus'][row_index] if row_index is not None else
                                      next(s for s in expected_snapshot['skus'] if str(s.get('skuId',s.get('id','')))==sku_id))
                        url=expected_sku.get('skuImageUrl') or expected_sku.get('imageUrl') or expected_sku.get('image')
                        if not url:raise ValueError('EXPECTED_SKU_URL_MISSING')
                    sku=(after['skus'][row_index] if row_index is not None else
                         next(s for s in after['skus'] if str(s.get('skuId',s.get('id','')))==sku_id))
                    if row_index is not None:
                        from product_state import SERVER_DERIVED_SKU_FIELDS
                        ignored={'skuImageUrl','imageUrl','image'}|set(SERVER_DERIVED_SKU_FIELDS)
                        if {k:v for k,v in sku.items() if k not in ignored}!={k:v for k,v in expected_sku.items() if k not in ignored}:
                            raise ValueError('SNAPSHOT_SKU_READBACK_ROW_CHANGED')
                    import hashlib
                    path=root/('readback_SKU_'+hashlib.sha256(sku_id.encode()).hexdigest()[:16]+'.img');path.write_bytes(writer.fetch_image(url))
                    observed=gate.inspector.observe_image(path,after)
                    valid=observed.get('verified') is True and observed.get('clean') is True and (sku.get('skuImageUrl') or sku.get('imageUrl'))==url
                    from candidate_quality import sha256
                    expected=(row.get('row_assignment_evidence',{}).get(str(row_index),{}) if row_index is not None else
                              row.get('assignment_evidence',{}).get(sku_id,{}))
                    valid=valid and bool(expected.get('model')) and observed.get('model')==expected['model'] and sha256(path)==expected.get('sha256')
                    if sku.get('color'):valid=valid and observed.get('color')==sku['color']==expected.get('color')
                    valid=valid and observed.get('image_type') in ({'FIGURE'} if packaging(sku.get('skuName',sku.get('name','')))=='without_box' else {'FIGURE','BOX'})
                    items.append(dict(remedy_id=row['remedy_id'],ok=valid,url=url,**locator))
                except Exception as exc:items.append(dict(remedy_id=row['remedy_id'],ok=False,reason=str(exc),**locator))
            continue
        if pool is None: continue
        url=after['images'][pool][index]
        try:
            data=writer.fetch_image(url)
            path=root/('readback_'+row['remedy_id']+'.img');path.write_bytes(data)
            source=row.get('candidate_asset')
            if source: expected=root/source['path']
            else:
                raw=json.loads((root/'audit_raw.json').read_text(encoding='utf-8'))['images']
                expected=Path(next(r['file'] for r in raw if r['url']==row['source']['url']))
                if not expected.is_absolute(): expected=Path(__file__).parent/expected
            approved=None
            if row.get('validation_scope',{}).get('type')=='CONFIRMED_MARK_REPAIR' and source:
                from candidate_quality import sha256
                from remedy_schema import COMMON_CHECKS,ACTION_CHECKS
                quality_path=root/'candidate_quality.json'
                ref=next((v for v in plan.get('evidence_refs',[]) if v['path']=='candidate_quality.json'),None)
                if ref and sha256(quality_path)==ref['sha256'] and sha256(expected)==sha256(path)==row['source']['sha256']:
                    required=COMMON_CHECKS|ACTION_CHECKS.get(row['action'],set())
                    proofs=json.loads(quality_path.read_text(encoding='utf-8')).get('items',[])
                    approved=next((v for v in proofs if v.get('item_id')==row['item_id'] and v.get('action')==row['action'] and v.get('ok') is True
                        and v.get('candidate_sha256')==row['source']['sha256'] and v.get('source_sha256')==row['source'].get('original_sha256')
                        and all(v.get('checks',{}).get(k) is True for k in required) and v.get('evidence_ids')),None)
            if approved:
                checked={'ok':True,'source_sha256':row['source']['sha256'],'candidate_sha256':row['source']['sha256'],
                         'evidence_ids':approved['evidence_ids'],'checks':approved['checks'],
                         'scope':'BYTE_EXACT_READBACK_OF_QUALITY_APPROVED_CANDIDATE','validation_scope':row['validation_scope'],
                         'model_recheck':'NOT_REQUIRED_IDENTICAL_CONTENT'}
            else:
                validation_context=dict(after,_image_repair=dict(row['validation_scope'],phase='POST_WRITE_READBACK')) if row.get('validation_scope') else after
                checked=gate.validate(expected,path,validation_context,expected_sha256=row['source']['sha256'])
        except Exception as exc: checked={'ok':False,'reason':str(exc)}
        items.append(dict(remedy_id=row['remedy_id'],url=url,**checked))
    result={'ok':bool(items) and all(i['ok'] for i in items),'items':items,'scope':'saved_image_bytes'}
    atomic_json(root/'content_validation.json',result)
    atomic_json(root/'after.json',after)
    return result

def report(root,job,status,result,writer=None,inspector=None):
    root=Path(root)
    atomic_json(root/'automatic_result.json',dict(result,status=status))
    from automatic_report import write
    return write(root,job,status,result,writer,inspector)
