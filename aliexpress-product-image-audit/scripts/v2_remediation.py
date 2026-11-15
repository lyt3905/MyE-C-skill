"""V2 candidate strategy for the existing prepare/compiler/binding interfaces."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import cv2
from candidate_quality import sha256
from job_manager import atomic_json
from product_state import canonical_state_hash

def verify_audit(root,job):
    root=Path(root);read=lambda n:json.loads((root/n).read_text(encoding='utf-8'))
    manifest=read('full_audit_evidence_manifest.json')
    for ref in manifest['files']:
        path=(root/ref['path']).resolve()
        if not path.is_relative_to(root.resolve()) or sha256(path)!=ref['sha256']:raise ValueError('FULL_AUDIT_EVIDENCE_CHANGED')
    if canonical_state_hash(read('audit_product.json'))!=job['input_state_sha256']:raise ValueError('V2_SOURCE_CHANGED')
    return read('full_inventory.json'),read('full_ai_judgements.json')

def prepare(directory,job,policy,gate):
    from image_repairs_v2 import remove_text,lama_torchscript
    from sku_assignment import select_v2
    from plan_compiler import compile_auto_plan
    root=Path(directory).resolve();inventory,judgements=verify_audit(root,job)
    product=json.loads((root/'audit_product.json').read_text(encoding='utf-8'))
    options=job['image_options'];candidates=[];quality=[];proofs=[];records=[]
    next_sku_index=len((product.get('images') or {}).get('sku',[]))
    sku_ids=[row.get('skuId',row.get('id')) for row in product.get('skus',[])]
    invalid_sku_rows={index for index,value in enumerate(sku_ids) if type(value) not in (str,int) or not str(value).strip() or sum(str(other)==str(value) for other in sku_ids)!=1}
    unresolved_reference_urls={row.get('skuImageUrl') or row.get('imageUrl') or row.get('image') for index,row in enumerate(product.get('skus',[])) if index in invalid_sku_rows}
    inspector=getattr(gate,'inspector',None)
    for digest,content in inventory['contents'].items():
        result=judgements[digest];action=result['decision'];o=result.get('observation');reason=None;asset=None;retained=[]
        if action in {'REMOVE_TEXT','AI_REGENERATE'}:
            try:
                if not policy.permits(action):raise ValueError('ACTION_NOT_AUTHORIZED')
                if options['rights']!='OWNED_OR_LICENSED':raise ValueError('RIGHTS_NOT_AUTHORIZED')
                if inspector is None:raise ValueError('CONTENT_VALIDATOR_UNAVAILABLE')
                for attempt in range(2 if action=='REMOVE_TEXT' else 1):
                    dest=root/'v2_candidates'/digest/str(attempt);dest.mkdir(parents=True,exist_ok=True)
                    if action=='REMOVE_TEXT':
                        lama=getattr(inspector,'lama_backend',None)
                        if lama is None and options.get('lama_model_path'):lama=lama_torchscript(options['lama_model_path'],options.get('lama_model_sha256'))
                        repair=remove_text(content['file'],o,dest,rights=options['rights'],algorithm='OPENCV_NS' if attempt else None,lama=lama,max_area=options['max_mask_area'])
                    else:
                        backend=getattr(inspector,'image_edit_backend',None)
                        model=getattr(inspector,'image_edit_model',None)
                        if backend is None and options.get('image_edit'):
                            from image_repairs_v2 import configured_image_edit
                            config=options['image_edit'];model=config['model']
                            backend=lambda source,context,observation,dest:configured_image_edit(config,source,context,observation,dest)
                        if backend is None:raise ValueError('IMAGE_EDIT_BACKEND_UNAVAILABLE')
                        # The configured adapter must return a budgeted model response,
                        # including actual usage and a candidate path (no fake estimates).
                        from ai_judge.client import safe_payload
                        from model_config import require_enabled_model
                        require_enabled_model(model)
                        context=safe_payload({},product)['context']
                        constraints=(Path(__file__).resolve().parents[1]/'prompts/image_edit.v2.md').read_text(encoding='utf-8')
                        context.update(pid=job['pid'],_image_edit_constraints=constraints)
                        raw=inspector.judge.invoke_image_adapter(model,{'id':digest,'sha256':digest,'prompt_sha256':hashlib.sha256(constraints.encode()).hexdigest()},context,
                            lambda:backend(content['file'],context,o,dest))
                        path=Path(raw['candidate_path']).resolve()
                        if not path.is_relative_to(dest.resolve()) or path==Path(content['file']).resolve():raise ValueError('IMAGE_EDIT_OUTPUT_UNBOUND')
                        repair=dict(input_path=content['file'],input_sha256=digest,output_path=str(path),output_sha256=sha256(path),algorithm='CONFIGURED_IMAGE_EDIT',mask_path=None)
                        atomic_json(dest/'edit.json',repair)
                    checked=inspector.inspect_v2(content['file'],repair['output_path'],product,action,repair.get('mask_path'))
                    quality.append(dict(checked,repair=repair,source_sha256=digest,action=action,attempt=attempt+1))
                    if checked.get('ok'):
                        asset=dict(path=str(Path(repair['output_path']).relative_to(root)),sha256=repair['output_sha256']);break
                    if checked.get('quality_status') not in {'FAIL_RETRYABLE','FAIL_WATERMARK_REMAINS'}:break
                    # Only one alternate local algorithm. LaMa failure does not
                    # silently become an unsuitable OpenCV repair.
                    if repair['algorithm']=='LAMA_INPAINT':break
                if asset is None:raise ValueError('V2_QUALITY_REJECTED')
            except (ValueError,OSError,ImportError,KeyError,TypeError,RuntimeError,cv2.error) as exc:reason=str(exc);action='REVIEW'
        if action=='DELETE':
            if o and o['retail_box_status']=='PRESENT' and o['box_relation']=='SAME_PRODUCT':
                for other_digest,other in judgements.items():
                    observed=other.get('observation') or {}
                    if (other_digest==digest or other['decision']=='DELETE' or observed.get('retail_box_status')!='PRESENT' or
                        observed.get('box_relation')!='SAME_PRODUCT' or observed.get('retail_box_confidence',0)<.8 or
                        observed.get('product_identity',{}).get('same_product_as_context')!='YES'):continue
                    retained=[{k:r[k] for k in ('pool','index','url','sha256')} for r in inventory['occurrences'] if r['sha256']==other_digest and r['target_type']=='image_slot'][:1]
                    if retained:break
                if not retained:action='REVIEW';reason='LAST_RETAIL_BOX_EVIDENCE'
        positions=[r for r in inventory['occurrences'] if r['sha256']==digest and r['target_type']=='image_slot']
        references=[r for r in inventory['occurrences'] if r['sha256']==digest and r['target_type']=='sku_reference']
        if positions:
            for reference in references:
                if reference['sku_row_index'] in invalid_sku_rows:
                    candidates.append(dict(remedy_id='V2_REF_'+reference['id'],item_id='V2_REF_'+reference['id'],action='WEB_DEFER',
                        target={'sku_row_index':reference['sku_row_index'],'source_occurrence_id':reference['id']},
                        source={'type':'V2_VISION','sha256':digest,'url':reference['url']},checks={},evidence_ids=['full_ai_judgements.json'],reason_codes=['SKU_MAPPING_UNRESOLVED']))
        if not positions and references:
            if asset and any(r['sku_row_index'] in invalid_sku_rows for r in references):
                action='REVIEW';reason='SKU_MAPPING_UNRESOLVED';asset=None
            if asset:
                for url in dict.fromkeys(r['url'] for r in references):
                    reference=next(r for r in references if r['url']==url)
                    positions.append(dict(id='SKU_'+str(next_sku_index).zfill(3),pool='sku',index=next_sku_index,
                        url=url,v2_append_sku=True,v2_source_occurrence_id=reference['id']))
                    next_sku_index+=1
            elif action!='KEEP':
                for reference in references:
                    candidates.append(dict(remedy_id='V2_REF_'+reference['id'],item_id='V2_REF_'+reference['id'],action='WEB_DEFER',
                        target={'sku_row_index':reference['sku_row_index'],'source_occurrence_id':reference['id']},
                        source={'type':'V2_VISION','sha256':digest,'url':reference['url']},checks={},evidence_ids=['full_ai_judgements.json'],
                        reason_codes=[reason] if reason else result['reason_codes'] or ['SKU_REFERENCE_UNRESOLVED']))
        for occurrence in positions:
            target={k:occurrence[k] for k in ('pool','index')};target['image_id']=occurrence['id']
            deferred_reference=bool(asset) and target['pool']=='sku' and occurrence['url'] in unresolved_reference_urls
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
            if row['action'] not in {'KEEP','WEB_DEFER'}:
                row['checks']={'vision_bound':True,'rights_authorized':options['rights']=='OWNED_OR_LICENSED','quality_passed':bool(asset) if action!='DELETE' else len(result['models'])==2}
                proofs.append(deepcopy(row))
            candidates.append(row)
        selected_observation=deepcopy(o)
        if asset and action in {'REMOVE_TEXT','AI_REGENERATE'}:
            selected_observation['watermarks']=[m for m in selected_observation['watermarks'] if m['kind'] not in {'STORE_WATERMARK','PROMOTIONAL_TEXT'}]
        records.append(dict(sha256=asset['sha256'] if asset else digest,url=content['urls'][0],image_id=content['occurrence_ids'][0],observation=selected_observation,decision='KEEP' if asset and action in {'REMOVE_TEXT','AI_REGENERATE'} else action,width=content['width'],height=content['height']))
    for occurrence in inventory['occurrences']:
        if occurrence['sha256'] is None:
            records.append(dict(sha256='MISSING_'+occurrence['id'],url=occurrence.get('url'),image_id=occurrence['id'],observation=None,decision='REVIEW',width=0,height=0))
            candidates.append(dict(remedy_id='V2_MISSING_'+occurrence['id'],item_id='V2_MISSING_'+occurrence['id'],action='WEB_DEFER',target={'image_id':occurrence['id'],'pool':occurrence.get('pool'),'index':occurrence.get('index')},source={},checks={},evidence_ids=['full_inventory.json'],reason_codes=['SOURCE_UNAVAILABLE']))
    selection=select_v2(product,records);atomic_json(root/'v2_sku_selection.json',selection)
    sku_candidate=None
    if selection['assignments']:
        row=dict(remedy_id='V2_SKU',item_id='V2_SKU',action='SKU_ASSIGN',target={'sku_ids':list(selection['assignments'])},source={'type':'V2_SKU','sha256':canonical_state_hash(product)},checks={'vision_bound':True,'quality_passed':True},evidence_ids=['v2_sku_selection.json'],assignments=selection['assignments'],sku_pool_urls=[r['url'] for r in selection['selected_sku_images']],v2_contract=True)
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
        unresolved.append(row)
    candidates=unresolved
    for pool in ('main','detail','sku'):
        deletions=[r for r in candidates if r['action']=='DELETE' and r['target']['pool']==pool]
        if pool=='sku' and selection['assignments'] and policy.permits('SKU_ASSIGN'):continue
        if deletions and len(deletions)>=len(product.get('images',{}).get(pool,[])):
            for row in deletions:
                row.update(action='WEB_DEFER',reason_codes=['DELETE_WOULD_EMPTY_POOL'])
            proofs=[r for r in proofs if r['remedy_id'] not in {d['remedy_id'] for d in deletions}]
    proofs=[deepcopy(row) for row in candidates if row.get('v2_contract') and row['action'] not in {'KEEP','WEB_DEFER'}]
    atomic_json(root/'v2_quality.json',{'items':quality})
    atomic_json(root/'v2_action_proofs.json',{'source_product_sha256':canonical_state_hash(product),'candidates':proofs})
    return compile_auto_plan(root,job,candidates,policy)

def validate_candidate(row):
    checks=row.get('checks',{})
    if row['action'] not in {'DELETE','REMOVE_TEXT','AI_REGENERATE','SKU_ASSIGN'}:raise ValueError('V2_ACTION')
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
        if row.get('sku_pool_urls')!=[r['url'] for r in read('v2_sku_selection.json')['selected_sku_images']]:raise ValueError('V2_SKU_POOL_UNBOUND')
        for deletion in row['source'].get('reference_deletions',[]):
            occurrence=next((r for r in inventory['occurrences'] if r['id']==deletion['source_occurrence_id'] and r['target_type']=='sku_reference'),None)
            sku=product['skus'][deletion['sku_row_index']]
            if (not occurrence or occurrence['sha256']!=deletion['source_sha256'] or occurrence['url']!=deletion['source_url'] or
                str(sku.get('skuId',sku.get('id')))!=deletion['sku_id'] or results[occurrence['sha256']]['decision']!='DELETE'):
                raise ValueError('V2_REFERENCE_DELETION_UNBOUND')
        return
    target=row['target']
    if row.get('v2_append_sku'):
        occ=next((r for r in inventory['occurrences'] if r['id']==row.get('v2_source_occurrence_id') and r['target_type']=='sku_reference' and r['url']==row['source']['url']),None)
        if target.get('pool')!='sku':raise ValueError('V2_REFERENCE_POOL_INVALID')
    else:occ=next((r for r in inventory['occurrences'] if r['id']==target['image_id'] and r.get('pool')==target['pool'] and r.get('index')==target['index']),None)
    if not occ or results[occ['sha256']]['decision']!=row['action']:raise ValueError('V2_DECISION_UNBOUND')
    source=inventory['contents'][occ['sha256']]
    if sha256(source['file'])!=occ['sha256']:raise ValueError('V2_ORIGINAL_CHANGED')
    if row['action']=='DELETE' and row['source'].get('sku_replacements'):
        assignments=read('v2_sku_selection.json')['assignments']
        if any(assignments.get(key)!=url for key,url in row['source']['sku_replacements'].items()):raise ValueError('V2_DELETE_SKU_REPLACEMENT_UNBOUND')
    if row['action']!='DELETE':
        asset=row['candidate_asset'];path=(root/asset['path']).resolve()
        if not path.is_relative_to(root.resolve()) or sha256(path)!=asset['sha256']:raise ValueError('V2_ASSET_CHANGED')
        checked=next((q for q in read('v2_quality.json')['items'] if q.get('ok') is True and q['source_sha256']==occ['sha256'] and q['candidate_sha256']==asset['sha256']),None)
        if not checked:raise ValueError('V2_QUALITY_UNBOUND')
        repair=checked['repair']
        if repair.get('mask_path') and sha256(repair['mask_path'])!=repair['mask_sha256']:raise ValueError('V2_MASK_CHANGED')


def verify_content(directory,plan,writer):
    """Read back approved bytes and all protected fields; no OCR or new edits."""
    from final_state import validate_final_snapshot
    root=Path(directory);read=lambda n:json.loads((root/n).read_text(encoding='utf-8'))
    before=read('audit_product.json');after=writer.product(plan['pid']);expected=read('expected_after.json')
    structural=validate_final_snapshot(after,context={'before':before,'plan':plan,'saved_readback':True})
    items=[];decisions=read('auto_decisions.json')['items']
    for row in decisions:
        if row.get('decision')!='AUTO_SAFE':continue
        observed=[]
        try:
            target=row['target'];action=row['action']
            if action in {'REMOVE_TEXT','AI_REGENERATE'}:
                position=plan['post_actions'].get('target_positions',{}).get(target['image_id'],target)
                url=after['images'][position['pool']][position['index']]
                data=writer.fetch_image(url);digest=hashlib.sha256(data).hexdigest()
                ok=digest==row['candidate_asset']['sha256']
                observed.append(dict(url=url,observed_sha256=digest,expected_sha256=row['candidate_asset']['sha256']))
            elif action=='DELETE':
                ok=after['images'][target['pool']]==expected['images'][target['pool']]
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
            else:ok=False
            items.append({'remedy_id':row['remedy_id'],'ok':ok,'scope':'V2_APPROVED_BYTES_AND_REFERENCE_READBACK','readback':observed})
        except (KeyError,IndexError,OSError,ValueError):items.append({'remedy_id':row['remedy_id'],'ok':False,'readback':observed})
    description_ok=('descriptionJson' in before)==('descriptionJson' in after) and type(before.get('descriptionJson')) is type(after.get('descriptionJson')) and before.get('descriptionJson')==after.get('descriptionJson')
    result=dict(ok=structural['ok'] and description_ok and after.get('images')==expected.get('images') and all(i['ok'] for i in items),items=items,structure=structural,description_exact=description_ok)
    atomic_json(root/'content_validation.json',result);return result
