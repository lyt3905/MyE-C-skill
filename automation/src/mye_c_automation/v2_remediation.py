"""V2 candidate strategy for the existing prepare/compiler/binding interfaces."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import cv2
from mye_c_automation.candidate_quality import sha256
from mye_c_automation.job_manager import atomic_json
from mye_c_automation.product_state import canonical_state_hash

def verify_audit(root,job):
    root=Path(root);read=lambda n:json.loads((root/n).read_text(encoding='utf-8'))
    manifest=read('full_audit_evidence_manifest.json')
    for ref in manifest['files']:
        path=(root/ref['path']).resolve()
        if not path.is_relative_to(root.resolve()) or sha256(path)!=ref['sha256']:raise ValueError('FULL_AUDIT_EVIDENCE_CHANGED')
    if canonical_state_hash(read('audit_product.json'))!=job['input_state_sha256']:raise ValueError('V2_SOURCE_CHANGED')
    results=read('full_ai_judgements.json')
    if (root/'v2_policy_reassessment.json').exists():
        from mye_c_automation.ai_judge import image_action_decision as visual
        from mye_c_automation.automation_policy import AutomationPolicy
        receipt=read('v2_policy_reassessment.json');policy=AutomationPolicy(receipt['policy'])
        if (receipt['source_judgements_sha256']!=sha256(root/'full_ai_judgements.json') or
            receipt['policy_sha256']!=policy.sha256 or policy.config.get('delete_decorated_composites') is not True or not policy.permits('DELETE') or
            receipt['implementation_sha256']!=sha256(visual.__file__)):raise ValueError('V2_REASSESSMENT_UNBOUND')
        expected={digest:visual.reassess_seller_poster(row) for digest,row in results.items()}
        expected={digest:row for digest,row in expected.items() if row!=results[digest] and row['results'][0].get('image_sha256')==digest}
        if receipt['overrides']!=expected:raise ValueError('V2_REASSESSMENT_CHANGED')
        results.update(expected)
    return read('full_inventory.json'),results


def record_seller_reassessment(root,job,policy):
    """Append bound current-policy evidence without touching sealed initial audit files."""
    root=Path(root)
    if policy.config.get('delete_decorated_composites') is not True or not policy.permits('DELETE'):return
    from mye_c_automation.ai_judge import image_action_decision as visual
    _,results=verify_audit(root,job)
    if (root/'v2_policy_reassessment.json').exists():return
    changed={digest:visual.reassess_seller_poster(row) for digest,row in results.items()}
    changed={digest:row for digest,row in changed.items() if row!=results[digest] and row['results'][0].get('image_sha256')==digest}
    if changed:
        atomic_json(root/'v2_policy_reassessment.json',dict(source_judgements_sha256=sha256(root/'full_ai_judgements.json'),policy_sha256=policy.sha256,policy=policy.config,implementation_sha256=sha256(visual.__file__),overrides=changed,model_requests=0))

def prepare(directory,job,policy,gate):
    from mye_c_automation.image_repairs_v2 import remove_text, lama_torchscript
    from mye_c_automation.sku_assignment import select_v2
    from mye_c_automation.plan_compiler import compile_auto_plan
    root=Path(directory).resolve();inventory,judgements=verify_audit(root,job)
    from mye_c_automation.visual_versions import find_versions
    version_path=root/'full_visual_versions.json'
    versions=json.loads(version_path.read_text(encoding='utf-8')) if version_path.exists() else find_versions(inventory,judgements)
    if not version_path.exists():atomic_json(version_path,versions)
    atomic_json(root/'automation_policy_summary.json',dict(sha256=policy.sha256,config=policy.config))
    record_seller_reassessment(root,job,policy)
    inventory,judgements=verify_audit(root,job)
    product=json.loads((root/'audit_product.json').read_text(encoding='utf-8'))
    options=job['image_options'];candidates=[];quality=[];proofs=[];records=[]
    next_sku_index=len((product.get('images') or {}).get('sku',[]))
    sku_ids=[row.get('skuId',row.get('id')) for row in product.get('skus',[])]
    invalid_sku_rows={index for index,value in enumerate(sku_ids) if type(value) not in (str,int) or not str(value).strip() or sum(str(other)==str(value) for other in sku_ids)!=1}
    if policy.config.get('allow_snapshot_sku_rows') is True:
        from mye_c_automation.snapshot_sku import locators
        if locators(product) is not None:invalid_sku_rows=set()
    unresolved_reference_urls={row.get('skuImageUrl') or row.get('imageUrl') or row.get('image') for index,row in enumerate(product.get('skus',[])) if index in invalid_sku_rows}
    inspector=getattr(gate,'inspector',None)
    for digest,content in inventory['contents'].items():
        result=judgements[digest];action=result['decision'];o=result.get('observation');reason=None;asset=None;retained=[]
        twin=versions['matches'].get(digest)
        if twin:
            action='REPLACE_TWIN'
        if action in {'REMOVE_TEXT','AI_REGENERATE'}:
            try:
                if not policy.permits(action):raise ValueError('ACTION_NOT_AUTHORIZED')
                if options['rights']!='OWNED_OR_LICENSED':raise ValueError('RIGHTS_NOT_AUTHORIZED')
                if inspector is None:raise ValueError('CONTENT_VALIDATOR_UNAVAILABLE')
                stages=['REMOVE_TEXT','REMOVE_TEXT'] if action=='REMOVE_TEXT' else ['AI_REGENERATE']
                if action=='REMOVE_TEXT' and policy.permits('AI_REGENERATE') and (getattr(inspector,'image_edit_backend',None) is not None or options.get('image_edit')):
                    stages.append('AI_REGENERATE')
                local_failed=False
                for attempt,attempt_action in enumerate(stages):
                    if attempt_action=='REMOVE_TEXT' and local_failed:continue
                    try:
                        dest=root/'v2_candidates'/digest/str(attempt);dest.mkdir(parents=True,exist_ok=True)
                        if attempt_action=='REMOVE_TEXT':
                            lama=getattr(inspector,'lama_backend',None)
                            if lama is None and options.get('lama_model_path'):lama=lama_torchscript(options['lama_model_path'],options.get('lama_model_sha256'))
                            repair=remove_text(content['file'],o,dest,rights=options['rights'],algorithm='OPENCV_NS' if attempt else None,lama=lama,max_area=options['max_mask_area'])
                        else:
                            backend=getattr(inspector,'image_edit_backend',None)
                            model=getattr(inspector,'image_edit_model',None)
                            if backend is None and options.get('image_edit'):
                                from mye_c_automation.image_repairs_v2 import configured_image_edit
                                config=options['image_edit'];model=config['model']
                                backend=lambda source,context,observation,dest:configured_image_edit(config,source,context,observation,dest)
                            if backend is None:raise ValueError('IMAGE_EDIT_BACKEND_UNAVAILABLE')
                            # The configured adapter must return a budgeted model response,
                            # including actual usage and a candidate path (no fake estimates).
                            from mye_c_automation.ai_judge.client import safe_payload
                            from mye_c_automation.model_config import require_enabled_model
                            require_enabled_model(model)
                            context=safe_payload({},product)['context']
                            constraints=(Path(__file__).resolve().parent/'prompts/image_edit.v2.md').read_text(encoding='utf-8')
                            context.update(pid=job['pid'],_image_edit_constraints=constraints)
                            raw=inspector.judge.invoke_image_adapter(model,{'id':digest,'sha256':digest,'prompt_sha256':hashlib.sha256(constraints.encode()).hexdigest(),'observation_sha256':hashlib.sha256(json.dumps(o,sort_keys=True).encode()).hexdigest()},context,
                                lambda:backend(content['file'],context,o,dest))
                            path=Path(raw['candidate_path']).resolve()
                            if not path.is_relative_to(dest.resolve()) or path==Path(content['file']).resolve():raise ValueError('IMAGE_EDIT_OUTPUT_UNBOUND')
                            repair=dict(input_path=content['file'],input_sha256=digest,output_path=str(path),output_sha256=sha256(path),algorithm='CONFIGURED_IMAGE_EDIT',mask_path=None)
                            atomic_json(dest/'edit.json',repair)
                        checked=inspector.inspect_v2(content['file'],repair['output_path'],product,attempt_action,repair.get('mask_path'))
                        quality.append(dict(checked,repair=repair,source_sha256=digest,action=attempt_action,attempt=attempt+1))
                        if checked.get('ok'):
                            asset=dict(path=str(Path(repair['output_path']).relative_to(root)),sha256=repair['output_sha256']);action=attempt_action;break
                        if checked.get('quality_status') not in {'FAIL_RETRYABLE','FAIL_WATERMARK_REMAINS'}:break
                        # Only one alternate local algorithm. LaMa failure does not
                        # silently become an unsuitable OpenCV repair.
                        if repair['algorithm']=='LAMA_INPAINT':local_failed=True
                    except (ValueError,OSError,ImportError,KeyError,TypeError,RuntimeError,cv2.error) as exc:
                        quality.append(dict(ok=False,source_sha256=digest,action=attempt_action,attempt=attempt+1,error_type=type(exc).__name__,reason=str(exc)))
                        if sha256(content['file'])!=digest:raise ValueError('ORIGINAL_CHANGED') from exc
                        if attempt_action=='AI_REGENERATE':raise
                        local_failed=True
                if asset is None:raise ValueError('V2_QUALITY_REJECTED')
            except (ValueError,OSError,ImportError,KeyError,TypeError,RuntimeError,cv2.error) as exc:reason=str(exc);action='REVIEW'
        if action=='DELETE':
            if o and o['retail_box_status']=='PRESENT':
                for other_digest,other in judgements.items():
                    observed=other.get('observation') or {}
                    if (other_digest==digest or other['decision']!='KEEP' or observed.get('visual_class')=='DECORATED_COMPOSITE' or observed.get('retail_box_status')!='PRESENT'):continue
                    retained=[{k:r[k] for k in ('pool','index','url','sha256')} for r in inventory['occurrences'] if r['sha256']==other_digest and r['target_type']=='image_slot'][:1]
                    if retained:break
                if not retained:action='REVIEW';reason='LAST_RETAIL_BOX_EVIDENCE'
        positions=[r for r in inventory['occurrences'] if r['sha256']==digest and r['target_type']=='image_slot']
        if not positions:
            positions=[r for r in inventory['occurrences'] if r['sha256']==digest and r['target_type']=='description_image']
        references=[r for r in inventory['occurrences'] if r['sha256']==digest and r['target_type']=='sku_reference']
        if positions:
            for reference in references:
                if reference['sku_row_index'] in invalid_sku_rows:
                    candidates.append(dict(remedy_id='V2_REF_'+reference['id'],item_id='V2_REF_'+reference['id'],action='WEB_DEFER',
                        target={'sku_row_index':reference['sku_row_index'],'source_occurrence_id':reference['id']},
                        source={'type':'V2_VISION','sha256':digest,'url':reference['url']},checks={},evidence_ids=['full_ai_judgements.json'],v2_contract=True,reason_codes=['SKU_MAPPING_UNRESOLVED']))
        if not positions and references:
            if (asset or twin) and any(r['sku_row_index'] in invalid_sku_rows for r in references):
                action='REVIEW';reason='SKU_MAPPING_UNRESOLVED';asset=None;twin=None
            if asset or twin:
                for url in dict.fromkeys(r['url'] for r in references):
                    reference=next(r for r in references if r['url']==url)
                    positions.append(dict(id='SKU_'+str(next_sku_index).zfill(3),pool='sku',index=next_sku_index,
                        url=url,v2_append_sku=True,v2_source_occurrence_id=reference['id']))
                    next_sku_index+=1
            elif action!='KEEP':
                for reference in references:
                    candidates.append(dict(remedy_id='V2_REF_'+reference['id'],item_id='V2_REF_'+reference['id'],action='WEB_DEFER',
                        target={'sku_row_index':reference['sku_row_index'],'source_occurrence_id':reference['id']},
                        source={'type':'V2_VISION','sha256':digest,'url':reference['url']},checks={},evidence_ids=['full_ai_judgements.json'],v2_contract=True,
                        reason_codes=[reason] if reason else result['reason_codes'] or ['SKU_REFERENCE_UNRESOLVED']))
        for occurrence in positions:
            target={k:occurrence[k] for k in ('pool','index')};target['image_id']=occurrence['id']
            deferred_reference=bool(asset or twin) and target['pool']=='sku' and occurrence['url'] in unresolved_reference_urls
            row=dict(remedy_id='V2_'+occurrence['id'],item_id='V2_'+occurrence['id'],action='WEB_DEFER' if action=='REVIEW' or deferred_reference else action,
                target=target,source={'type':'V2_VISION','sha256':digest,'url':occurrence['url'],'original_sha256':digest},checks={},
                evidence_ids=['full_ai_judgements.json'],v2_contract=True,reason_codes=[reason] if reason else result['reason_codes'])
            if deferred_reference:row['reason_codes']=['SKU_MAPPING_UNRESOLVED']
            if occurrence.get('v2_append_sku'):
                row.update(v2_append_sku=True,v2_source_occurrence_id=occurrence['v2_source_occurrence_id'])
            if action=='DELETE' and retained:row['source']['retained_references']=deepcopy(retained)
            if asset and not deferred_reference:
                row['candidate_asset']=dict(asset,pool=target['pool'],index=target['index'])
                row['source']['sha256']=asset['sha256']
            if twin and not deferred_reference:
                row['source'].update(type='V2_VISUAL_TWIN',sha256=twin['candidate_sha256'],url=twin['replacement_url'],original_url=occurrence['url'],version_evidence='full_visual_versions.json')
                row['reason_codes']=['EXISTING_CLEAN_VERSION_PRIORITY']
            if row['action'] not in {'KEEP','WEB_DEFER'}:
                from mye_c_automation.model_config import review_models
                row['checks']={'vision_bound':True,'rights_authorized':options['rights']=='OWNED_OR_LICENSED','quality_passed':bool(asset or twin) if action!='DELETE' else len(result['models'])==1 and tuple(result['models'])==review_models(result['models'])}
                proofs.append(deepcopy(row))
            candidates.append(row)
        selected_observation=deepcopy(o)
        if asset and action in {'REMOVE_TEXT','AI_REGENERATE'}:
            from mye_c_automation.ai_judge.image_action_decision import mark_disposition
            selected_observation['watermarks']=[m for m in selected_observation['watermarks'] if mark_disposition(m)!='REMOVABLE']
        chosen=inventory['contents'][twin['candidate_sha256']] if twin else content
        if twin:selected_observation=deepcopy(judgements[twin['candidate_sha256']]['observation'])
        records.append(dict(sha256=twin['candidate_sha256'] if twin else asset['sha256'] if asset else digest,url=twin['replacement_url'] if twin else content['urls'][0],image_id=chosen['occurrence_ids'][0],observation=selected_observation,decision='KEEP' if twin or asset and action in {'REMOVE_TEXT','AI_REGENERATE'} else action,width=chosen['width'],height=chosen['height']))
    for occurrence in inventory['occurrences']:
        if occurrence['sha256'] is None:
            records.append(dict(sha256='MISSING_'+occurrence['id'],url=occurrence.get('url'),image_id=occurrence['id'],observation=None,decision='REVIEW',width=0,height=0))
            candidates.append(dict(remedy_id='V2_MISSING_'+occurrence['id'],item_id='V2_MISSING_'+occurrence['id'],action='WEB_DEFER',target={'image_id':occurrence['id'],'pool':occurrence.get('pool'),'index':occurrence.get('index')},source={},checks={},evidence_ids=['full_inventory.json'],reason_codes=['SOURCE_UNAVAILABLE']))
    selection=select_v2(product,records,allow_snapshot_rows=policy.config.get('allow_snapshot_sku_rows') is True);atomic_json(root/'v2_sku_selection.json',selection)
    sku_candidate=None
    if selection['assignments'] or selection['row_assignments']:
        row=dict(remedy_id='V2_SKU',item_id='V2_SKU',action='SKU_ASSIGN',target={'sku_ids':list(selection['assignments'])},source={'type':'V2_SKU','sha256':canonical_state_hash(product)},checks={'vision_bound':True,'quality_passed':True},evidence_ids=['v2_sku_selection.json'],assignments=selection['assignments'],sku_pool_urls=[r['url'] for r in selection['selected_sku_images']],v2_contract=True)
        if selection['row_assignments']:
            row.update(row_assignments=deepcopy(selection['row_assignments']),target={'sku_row_indices':[r['index'] for r in selection['row_assignments']]})
            row['checks']['snapshot_rows_bound']=True
        candidates.append(row);proofs.append(deepcopy(row))
        sku_candidate=row
    if selection['reason_codes'] and product.get('skus'):
        candidates.append(dict(remedy_id='V2_SKU_DEFER',item_id='V2_SKU_DEFER',action='WEB_DEFER',target={},source={},checks={},evidence_ids=['v2_sku_selection.json'],reason_codes=selection['reason_codes']))
    for row in candidates:
        if row['action']!='DELETE':continue
        references=[r for r in inventory['occurrences'] if r['sha256']==row['source']['sha256'] and r['target_type']=='sku_reference']
        if not references:continue
        ids=[product['skus'][r['sku_row_index']].get('skuId',product['skus'][r['sku_row_index']].get('id')) for r in references]
        if (policy.permits('SKU_ASSIGN') and all(type(value) in (str,int) and str(value).strip() and str(value) in selection['assignments'] for value in ids)):
            row['source']['sku_replacements']={str(value):selection['assignments'][str(value)] for value in ids}
        elif policy.permits('SKU_ASSIGN') and all(any(bound['index']==ref['sku_row_index'] for bound in selection['row_assignments']) for ref in references):
            row['source']['snapshot_sku_replacements']=[deepcopy(bound) for bound in selection['row_assignments'] if any(ref['sku_row_index']==bound['index'] for ref in references)]
        else:row.update(action='WEB_DEFER',reason_codes=['SKU_REFERENCE_REQUIRES_REPLACEMENT'])
    unresolved=[]
    for row in candidates:
        if (sku_candidate and policy.permits('DELETE') and policy.permits('SKU_ASSIGN') and row['action']=='WEB_DEFER' and
            row.get('reason_codes')==['SKU_REFERENCE_UNRESOLVED'] and judgements.get(row.get('source',{}).get('sha256'),{}).get('decision')=='DELETE'):
            index=row['target']['sku_row_index'];sku=product['skus'][index];sku_id=sku.get('skuId',sku.get('id'))
            if type(sku_id) in (str,int) and str(sku_id) in selection['assignments'] and selection['assignments'][str(sku_id)]!=row['source']['url']:
                sku_candidate['source'].setdefault('reference_deletions',[]).append(dict(sku_id=str(sku_id),sku_row_index=index,
                    source_occurrence_id=row['target']['source_occurrence_id'],source_sha256=row['source']['sha256'],source_url=row['source']['url']))
                continue
            bound=next((entry for entry in selection['row_assignments'] if entry['index']==index and entry['url']!=row['source']['url']),None)
            if bound:
                sku_candidate['source'].setdefault('snapshot_reference_deletions',[]).append(dict(sku_row_index=index,source_occurrence_id=row['target']['source_occurrence_id'],source_sha256=row['source']['sha256'],source_url=row['source']['url']))
                continue
        unresolved.append(row)
    candidates=unresolved
    for pool in ('main','detail','sku'):
        deletions=[r for r in candidates if r['action']=='DELETE' and r['target']['pool']==pool]
        if pool=='sku' and (selection['assignments'] or selection['row_assignments']) and policy.permits('SKU_ASSIGN'):continue
        if deletions and len(deletions)>=len(product.get('images',{}).get(pool,[])):
            for row in deletions:
                row.update(action='WEB_DEFER',reason_codes=['DELETE_WOULD_EMPTY_POOL'])
            proofs=[r for r in proofs if r['remedy_id'] not in {d['remedy_id'] for d in deletions}]
    blocked_hashes={r.get('source',{}).get('original_sha256',r.get('source',{}).get('sha256')) for r in candidates if r['action']=='WEB_DEFER' and r.get('v2_contract')}
    for row in candidates:
        if row['action']=='DELETE' and row['source'].get('original_sha256',row['source']['sha256']) in blocked_hashes:
            row.update(action='WEB_DEFER',reason_codes=['CONTENT_GROUP_PARTIALLY_DEFERRED'])
    proofs=[deepcopy(row) for row in candidates if row.get('v2_contract') and row['action'] not in {'KEEP','WEB_DEFER'}]
    atomic_json(root/'v2_quality.json',{'items':quality})
    atomic_json(root/'v2_action_proofs.json',{'source_product_sha256':canonical_state_hash(product),'candidates':proofs})
    return compile_auto_plan(root,job,candidates,policy)

def validate_candidate(row):
    checks=row.get('checks',{})
    if row['action'] not in {'DELETE','REMOVE_TEXT','AI_REGENERATE','SKU_ASSIGN','REPLACE_TWIN'}:raise ValueError('V2_ACTION')
    if not checks.get('vision_bound') or not checks.get('quality_passed'):raise ValueError('V2_PROOF_INCOMPLETE')
    if row['action'] in {'REMOVE_TEXT','AI_REGENERATE'} and not checks.get('rights_authorized'):raise ValueError('RIGHTS_NOT_AUTHORIZED')
    if row['action'] in {'REMOVE_TEXT','AI_REGENERATE'} and not row.get('candidate_asset'):raise ValueError('V2_ASSET_REQUIRED')
    return row

def verify(root,row,product):
    root=Path(root);read=lambda n:json.loads((root/n).read_text(encoding='utf-8'))
    job=read('job.json');inventory,results=verify_audit(root,job);validate_candidate(row)
    proposed={k:v for k,v in row.items() if k not in {'decision','automation_policy_sha256'}}
    proof=read('v2_action_proofs.json')
    if proof['source_product_sha256']!=canonical_state_hash(product) or proposed not in proof['candidates']:raise ValueError('V2_PROOF_UNBOUND')
    if row['action']=='SKU_ASSIGN':
        if row['assignments']!=read('v2_sku_selection.json')['assignments']:raise ValueError('V2_SKU_UNBOUND')
        if row.get('row_assignments',[])!=read('v2_sku_selection.json').get('row_assignments',[]):raise ValueError('V2_SKU_ROWS_UNBOUND')
        if row.get('row_assignments'):
            from mye_c_automation.snapshot_sku import validate_assignments
            validate_assignments(product,row['row_assignments'])
        if row.get('sku_pool_urls')!=[r['url'] for r in read('v2_sku_selection.json')['selected_sku_images']]:raise ValueError('V2_SKU_POOL_UNBOUND')
        for deletion in row['source'].get('reference_deletions',[]):
            occurrence=next((r for r in inventory['occurrences'] if r['id']==deletion['source_occurrence_id'] and r['target_type']=='sku_reference'),None)
            sku=product['skus'][deletion['sku_row_index']]
            if (not occurrence or occurrence['sha256']!=deletion['source_sha256'] or occurrence['url']!=deletion['source_url'] or
                str(sku.get('skuId',sku.get('id')))!=deletion['sku_id'] or results[occurrence['sha256']]['decision']!='DELETE'):
                raise ValueError('V2_REFERENCE_DELETION_UNBOUND')
        for deletion in row['source'].get('snapshot_reference_deletions',[]):
            occurrence=next((r for r in inventory['occurrences'] if r['id']==deletion['source_occurrence_id'] and r['target_type']=='sku_reference' and r['sku_row_index']==deletion['sku_row_index']),None)
            if not occurrence or occurrence['sha256']!=deletion['source_sha256'] or occurrence['url']!=deletion['source_url'] or results[occurrence['sha256']]['decision']!='DELETE' or not any(entry['index']==deletion['sku_row_index'] and entry['url']!=deletion['source_url'] for entry in row.get('row_assignments',[])):raise ValueError('V2_REFERENCE_DELETION_UNBOUND')
        return
    target=row['target']
    if row.get('v2_append_sku'):
        occ=next((r for r in inventory['occurrences'] if r['id']==row.get('v2_source_occurrence_id') and r['target_type']=='sku_reference' and r['url']==row['source'].get('original_url',row['source']['url'])),None)
        if target.get('pool')!='sku':raise ValueError('V2_REFERENCE_POOL_INVALID')
    else:occ=next((r for r in inventory['occurrences'] if r['id']==target['image_id'] and r.get('pool')==target['pool'] and r.get('index')==target['index']),None)
    if not occ:raise ValueError('V2_DECISION_UNBOUND')
    if row['action']=='REPLACE_TWIN':
        from mye_c_automation.visual_versions import compare_versions, clean_candidate, VERSION
        versions=read('full_visual_versions.json');twin=versions['matches'].get(occ['sha256'])
        if (versions.get('schema')!=VERSION or not twin or twin['candidate_sha256']!=row['source']['sha256'] or twin['replacement_url']!=row['source']['url']):raise ValueError('V2_TWIN_UNBOUND')
        source=inventory['contents'][occ['sha256']];candidate=inventory['contents'][twin['candidate_sha256']]
        if sha256(source['file'])!=occ['sha256'] or sha256(candidate['file'])!=twin['candidate_sha256'] or not clean_candidate(results[twin['candidate_sha256']],candidate):raise ValueError('V2_TWIN_SOURCE_CHANGED')
        if not compare_versions(source['file'],candidate['file'],results[occ['sha256']]['observation'])['verified']:raise ValueError('V2_TWIN_ALIGNMENT_FAILED')
        return
    requested=results[occ['sha256']]['decision']
    if requested!=row['action']:
        attempts=read('v2_quality.json')['items']
        fallback=(requested=='REMOVE_TEXT' and row['action']=='AI_REGENERATE' and
            any(q.get('source_sha256')==occ['sha256'] and q.get('action')=='REMOVE_TEXT' and q.get('ok') is False for q in attempts) and
            any(q.get('source_sha256')==occ['sha256'] and q.get('action')=='AI_REGENERATE' and q.get('ok') is True and q.get('candidate_sha256')==row.get('candidate_asset',{}).get('sha256') for q in attempts))
        if not fallback:raise ValueError('V2_DECISION_UNBOUND')
    source=inventory['contents'][occ['sha256']]
    if sha256(source['file'])!=occ['sha256']:raise ValueError('V2_ORIGINAL_CHANGED')
    if row['action']=='DELETE' and row['source'].get('sku_replacements'):
        assignments=read('v2_sku_selection.json')['assignments']
        if any(assignments.get(key)!=url for key,url in row['source']['sku_replacements'].items()):raise ValueError('V2_DELETE_SKU_REPLACEMENT_UNBOUND')
    if row['action']=='DELETE' and row['source'].get('snapshot_sku_replacements'):
        assignments=read('v2_sku_selection.json').get('row_assignments',[])
        if any(entry not in assignments for entry in row['source']['snapshot_sku_replacements']):raise ValueError('V2_DELETE_SKU_REPLACEMENT_UNBOUND')
    if row['action']!='DELETE':
        asset=row['candidate_asset'];path=(root/asset['path']).resolve()
        if not path.is_relative_to(root.resolve()) or sha256(path)!=asset['sha256']:raise ValueError('V2_ASSET_CHANGED')
        checked=next((q for q in read('v2_quality.json')['items'] if q.get('ok') is True and q['source_sha256']==occ['sha256'] and q['candidate_sha256']==asset['sha256']),None)
        if not checked:raise ValueError('V2_QUALITY_UNBOUND')
        repair=checked['repair']
        if repair.get('mask_path') and sha256(repair['mask_path'])!=repair['mask_sha256']:raise ValueError('V2_MASK_CHANGED')


def protected_snapshot(snapshot):
    """Compare all non-image business fields; record server time separately."""
    value=deepcopy(snapshot);value.pop('images',None);value.pop('updatedAt',None)
    for sku in value.get('skus') or []:
        for field in ('skuImageUrl','imageUrl','image'):sku.pop(field,None)
    return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False)


def verify_content(directory,plan,writer):
    """Read back approved bytes and all protected fields; no OCR or new edits."""
    from mye_c_automation.final_state import validate_final_snapshot
    root=Path(directory);read=lambda n:json.loads((root/n).read_text(encoding='utf-8'))
    before=read('audit_product.json');after=writer.product(plan['pid']);expected=read('expected_after.json')
    atomic_json(root/'independent_after.json',after)
    structural=validate_final_snapshot(after,context={'before':before,'plan':plan,'saved_readback':True})
    items=[];decisions=read('auto_decisions.json')['items']
    for row in decisions:
        if row.get('decision')!='AUTO_SAFE':continue
        observed=[]
        try:
            target=row['target'];action=row['action']
            if action in {'REMOVE_TEXT','AI_REGENERATE','REPLACE_TWIN'}:
                position=plan['post_actions'].get('target_positions',{}).get(target['image_id'],target)
                if position['pool']=='description':
                    if action=='REPLACE_TWIN':
                        from mye_c_automation.description_images import body_image_nodes
                        from mye_c_automation.image_content_plan import content_changes
                        deleted,_=content_changes(plan)
                        index=target['index']-sum(r['index']<target['index'] and r['url'] in deleted for r in body_image_nodes(before.get('descriptionJson')))
                        url=next(r['url'] for r in body_image_nodes(after.get('descriptionJson')) if r['index']==index)
                    else:
                        from mye_c_automation.image_content_plan import uploaded_from_snapshot
                        pairs=zip(plan['post_actions'].get('uploads',[]),uploaded_from_snapshot(before,plan,after))
                        url=next(u for ref,u in pairs if ref['pool']=='description' and ref['index']==target['index'])
                else:url=after['images'][position['pool']][position['index']]
                data=writer.fetch_image(url);digest=hashlib.sha256(data).hexdigest()
                approved=row['source']['sha256'] if action=='REPLACE_TWIN' else row['candidate_asset']['sha256']
                ok=digest==approved
                observed.append(dict(url=url,observed_sha256=digest,expected_sha256=approved))
            elif action=='DELETE':
                ok=after.get('descriptionJson')==expected.get('descriptionJson') if target['pool']=='description' else after['images'][target['pool']]==expected['images'][target['pool']]
                for retained in row['source'].get('retained_references',[]):
                    index=retained['index']-sum(r.get('decision')=='AUTO_SAFE' and r['action']=='DELETE' and r['target'].get('pool')==retained['pool'] and r['target'].get('index',-1)<retained['index'] for r in decisions)
                    url=after['images'][retained['pool']][index]
                    approved=next((r['candidate_asset']['sha256'] for r in decisions if r.get('decision')=='AUTO_SAFE' and r['action'] in {'REMOVE_TEXT','AI_REGENERATE'} and r['target'].get('pool')==retained['pool'] and r['target'].get('index')==retained['index']),retained['sha256'])
                    data=writer.fetch_image(url)
                    digest=hashlib.sha256(data).hexdigest()
                    observed.append(dict(url=url,observed_sha256=digest,expected_sha256=approved))
                    ok=ok and digest==approved
            elif action=='SKU_ASSIGN':
                lookup={str(s.get('skuId',s.get('id'))):s for s in after.get('skus',[])}
                resolved={str(s.get('skuId',s.get('id'))):s for s in expected.get('skus',[])}
                reference=lambda s:s.get('skuImageUrl') or s.get('imageUrl') or s.get('image')
                # The approved plan binds source URLs; the executor resolves
                # uploads and replacement mappings before saving the SKU row.
                ok=all(reference(lookup[k])==reference(resolved[k]) for k in row['assignments'])
                if row.get('row_assignments'):
                    ok=ok and all(reference(after['skus'][entry['index']])==reference(expected['skus'][entry['index']]) for entry in row['row_assignments'])
            else:ok=False
            items.append({'remedy_id':row['remedy_id'],'ok':ok,'scope':'V2_APPROVED_BYTES_AND_REFERENCE_READBACK','readback':observed})
        except (KeyError,IndexError,OSError,ValueError):items.append({'remedy_id':row['remedy_id'],'ok':False,'readback':observed})
    description_ok=('descriptionJson' in expected)==('descriptionJson' in after) and type(expected.get('descriptionJson')) is type(after.get('descriptionJson')) and expected.get('descriptionJson')==after.get('descriptionJson')
    protected_after=deepcopy(after)
    if plan.get('post_actions',{}).get('content_groups') and description_ok and 'descriptionJson' in before:protected_after['descriptionJson']=deepcopy(before['descriptionJson'])
    protected_exact=protected_snapshot(before)==protected_snapshot(protected_after)
    metadata_changes=[dict(field='updatedAt',before=before.get('updatedAt'),after=after.get('updatedAt'),before_present='updatedAt' in before,after_present='updatedAt' in after)] if ('updatedAt' in before)!=('updatedAt' in after) or before.get('updatedAt')!=after.get('updatedAt') else []
    def sku_references(snapshot):return [{key:row[key] for key in ('skuImageUrl','imageUrl','image') if key in row} for row in snapshot.get('skus') or []]
    sku_references_exact=sku_references(after)==sku_references(expected)
    inventory=read('full_inventory.json');expected_hashes={url:digest for digest,c in inventory['contents'].items() for url in c['urls']}
    receipts=root/'upload_receipts.json'
    if receipts.exists():
        for receipt in read('upload_receipts.json').get('uploads',[]):expected_hashes[receipt['url']]=receipt['sha256']
    image_readback=[];downloaded={}
    def check_image(pool,index,url,sku_id=None):
        digest=expected_hashes.get(url);observed=None;error=None
        try:
            if url not in downloaded:downloaded[url]=hashlib.sha256(writer.fetch_image(url)).hexdigest()
            observed=downloaded[url]
        except (OSError,ValueError,KeyError,TypeError,RuntimeError) as exc:error=type(exc).__name__
        image_readback.append(dict(pool=pool,index=index,url=url,sku_id=sku_id,expected_sha256=digest,observed_sha256=observed,ok=digest is not None and observed==digest,error=error))
    for pool in ('main','detail','sku'):
        for index,url in enumerate((after.get('images') or {}).get(pool,[])):check_image(pool,index,url)
    if plan.get('post_actions',{}).get('content_groups'):
        from mye_c_automation.description_images import body_image_nodes
        for row in body_image_nodes(after.get('descriptionJson')):check_image('description',row['index'],row['url'])
    for index,sku in enumerate(after.get('skus') or []):
        url=sku.get('skuImageUrl') or sku.get('imageUrl') or sku.get('image')
        if url:check_image('sku_reference',index,url,sku.get('skuId',sku.get('id')))
    byte_ok=all(row['ok'] for row in image_readback)
    result=dict(ok=structural['ok'] and description_ok and protected_exact and sku_references_exact and byte_ok and after.get('images')==expected.get('images') and all(i['ok'] for i in items),items=items,structure=structural,description_exact=description_ok,protected_fields_exact=protected_exact,server_metadata_changes=metadata_changes,sku_references_exact=sku_references_exact,image_readback=image_readback,independent_snapshot_sha256=sha256(root/'independent_after.json'))
    atomic_json(root/'content_validation.json',result);return result
