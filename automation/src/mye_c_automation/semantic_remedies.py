"""Connect deterministic title/SKU rules to independently observed evidence."""
from pathlib import Path
from mye_c_automation.product_state import canonical_state_hash
from mye_c_automation.sku_assignment import packaging, plan_assignments
from mye_c_automation.title_rewrite import rewrite_title

def build(product,flags,queue,images,inspector,shop,generated_remedies=(),allow_snapshot_rows=False,allowed_actions=None,verified_sku_rows=None):
    candidates=[];handled=set();resolved_items=set()
    def base(item,action,evidence):
        return {'remedy_id':'REM_'+item,'item_id':item,'action':action,'source':{'type':'product_snapshot','sha256':canonical_state_hash(product)},
                'candidate_asset':None,'evidence_ids':evidence,'checks':{k:True for k in ('product_identity_match','source_clean','candidate_visual_validation','protected_elements_preserved','source_bound')},'reason_codes':['DETERMINISTIC_RULES_AND_INDEPENDENT_REVIEW']}
    title_anomalies={'title_prefix','title_length','modelCode_missing','modelCode_title_inclusion','titleTranslationZh_missing'}
    triggers={a.get('type') for a in flags.get('anomalies',[]) if isinstance(a,dict)}
    title_items={r['id'] for r in queue if r['task_type']=='title_semantics'}
    approved={}
    if allowed_actions is not None and 'TITLE_REWRITE' not in allowed_actions:
        handled.update(title_anomalies)
    if (allowed_actions is None or 'TITLE_REWRITE' in allowed_actions) and (triggers&title_anomalies or title_items):
        generated=rewrite_title(product,shop)
        try:approved=inspector.validate_title(product,generated) if generated.get('ok') and inspector and callable(getattr(inspector,'validate_title',None)) else {}
        except Exception as exc:
            approved={}
            candidates.append(dict(remedy_id='TITLE_DEFER',item_id='TITLE_DEFER',action='WEB_DEFER',target={},source={},checks={},evidence_ids=['audit_product.json'],reason_codes=['TITLE_VALIDATOR_UNAVAILABLE',type(exc).__name__]))
        if generated.get('ok') and approved.get('ok') is True and approved.get('evidence_ids'):
            row=base('TITLE_AUTO','TITLE_REWRITE',approved['evidence_ids'])
            row.update(target={'field':'titleEn'},titleEn=generated['titleEn'],modelCode=generated.get('modelCode'))
            row['checks'].update(title_rules_pass=True,field_provenance=True,translation_once_policy=True)
            row.update(title_review_status='NOT_REVIEWED',translation_policy='ONCE_NO_AUTOMATIC_RETRY')
            row['reason_codes']=['SOP_RULES_WITH_SINGLE_TRANSLATION_NO_TITLE_MODEL_REVIEW']
            candidates.append(row);handled.update(title_anomalies);resolved_items.update(title_items)
    if allowed_actions is not None and 'BRAND_CODE' not in allowed_actions:handled.add('brand_rule')
    if 'brand_rule' in triggers and (allowed_actions is None or 'BRAND_CODE' in allowed_actions):
        generated=rewrite_title(product,shop)
        current=product.get('brandId')
        # Only the explicit integer code field is supported. A separate brand alias is ambiguous.
        field_known=type(current) is int and current in {200017853,200014695} and not product.get('brand')
        if field_known and generated.get('ok'):
            try:
                validator=getattr(inspector,'validate_brand',None)
                approved=validator(product,generated) if callable(validator) else {}
            except Exception:approved={}
            if approved.get('ok') is True and approved.get('evidence_ids'):
                if current!=generated['brandCode']:
                    row=base('BRAND_AUTO','BRAND_CODE',approved['evidence_ids'])
                    row.update(target={'field':'brandId'},brandId=generated['brandCode'],brand_field_verified=True)
                    row['checks'].update(field_provenance=True,brand_mapping_verified=True)
                    candidates.append(row)
                handled.add('brand_rule')
    sku_rows=product.get('skus') or []
    references=[r.get('skuImageUrl') or r.get('imageUrl') or r.get('image') for r in sku_rows]
    sku_items=[r for r in queue if r['task_type']=='sku_match']
    needs_sku=bool(sku_items) or len(references)!=len(set(references)) or any(packaging(r.get('skuName',r.get('name','')))!='unknown' for r in sku_rows)
    if sku_rows and verified_sku_rows is not None and set(verified_sku_rows)==set(range(len(sku_rows))):
        # The complete audit already verified each existing reference. No new
        # assignment is needed merely because the API omits database SKU IDs.
        resolved_items.update(item['id'] for item in sku_items)
        needs_sku=False
    if needs_sku:
        # An unaddressable SKU cannot be assigned regardless of visual quality.
        # Reuse the assignment validator before paying for image observations.
        identity_check=plan_assignments(product,[],allow_snapshot_rows=allow_snapshot_rows)
        identity_unverified='SKU_IDENTIFIER_UNVERIFIED' in identity_check.get('deferred_reasons',{}).values()
        observations=[]
        if not identity_unverified and inspector and callable(getattr(inspector,'observe_image',None)):
            for image in images:
                if image.get('error'):continue
                path=Path(image['file'])
                if not path.is_absolute():path=Path(__file__).parent/path
                try:observed=inspector.observe_image(path,product)
                except Exception as exc:observed={'verified':False,'clean':False,'reason':type(exc).__name__}
                observations.append(dict(observed,url=image['url']))
        dependencies={}
        for remedy in (() if identity_unverified else generated_remedies):
            if remedy.get('action') not in {'CROP_BANNER','BOX_NORMALIZE','ERASE_LOCAL','REPLACE_LOCAL'}:continue
            asset=remedy.get('candidate_asset') or {};target=remedy.get('target') or {}
            try:
                import hashlib
                path=Path(asset['path'])
                if not path.is_absolute():continue
                if hashlib.sha256(path.read_bytes()).hexdigest()!=asset['sha256']:continue
                observed=inspector.observe_image(path,product)
                if observed.get('sha256')!=asset['sha256']:continue
                url=product['images'][target['pool']][target['index']]
                observations=[r for r in observations if r['url']!=url]
                observations.append(dict(observed,url=url))
                dependencies[url]=remedy['remedy_id']
            except Exception:continue
        result=plan_assignments(product,observations,allow_snapshot_rows=allow_snapshot_rows)
        if result['assignments']:
            row=base('SKU_AUTO','SKU_ASSIGN',result['evidence_ids'])
            row.update(target={'sku_ids':list(result['assignments'])},assignments=result['assignments'])
            row['assignment_evidence']={sku_id:next(observation for observation in observations if observation['url']==url) for sku_id,url in result['assignments'].items()}
            row['requires_remedy_ids']=sorted({dependencies[url] for url in result['assignments'].values() if url in dependencies})
            row['checks'].update(sku_assignment_unique=True,packaging_match=True,model_match=True)
            candidates.append(row)
        if result.get('row_assignments'):
            assignments=result['row_assignments']
            row=base('SKU_SNAPSHOT_AUTO','SKU_ASSIGN',result['evidence_ids'])
            row.update(target={'sku_row_indices':[entry['index'] for entry in assignments]},row_assignments=assignments)
            row['row_assignment_evidence']={str(entry['index']):next(observation for observation in observations if observation['url']==entry['url']) for entry in assignments}
            row['requires_remedy_ids']=sorted({dependencies[entry['url']] for entry in assignments if entry['url'] in dependencies})
            row['checks'].update(sku_assignment_unique=True,packaging_match=True,model_match=True,snapshot_rows_bound=True)
            candidates.append(row)
        if 'deferred_rows' in result:
            deferred_indices={entry['index'] for entry in result['deferred_rows']}
            for item in sku_items:
                if type(item.get('sku_row_index')) is int and item['sku_row_index'] not in deferred_indices:
                    resolved_items.add(item['id'])
            for entry in result['deferred_rows']:
                item_id='SKU_SNAPSHOT_DEFER_ROW_'+str(entry['index'])
                candidates.append(dict(remedy_id=item_id,item_id=item_id,action='WEB_DEFER',
                                       target={'sku_row_index':entry['index']},source={},checks={},
                                       evidence_ids=['audit_product.json'],reason_codes=[entry['reason']]))
            return candidates,handled,resolved_items
        for item in sku_items:
            if item.get('sku_id') not in result['deferred']:resolved_items.add(item['id'])
        reported_rows=set()
        for sku_id in result['deferred']:
            row_index=next((i for i,sku in enumerate(sku_rows) if i not in reported_rows and str(sku.get('skuId',sku.get('id','')))==sku_id),None)
            if row_index is not None:reported_rows.add(row_index)
            reason=result.get('deferred_reasons',{}).get(sku_id,'SKU_ASSIGNMENT_UNCERTAIN')
            # Row locators are reporting-only; never invent an assignable SKU ID.
            suffix='_ROW_'+str(row_index) if reason=='SKU_IDENTIFIER_UNVERIFIED' else ''
            item_id='SKU_DEFER_'+sku_id+suffix
            candidates.append(dict(remedy_id=item_id,item_id=item_id,action='WEB_DEFER',
                target={'sku_row_index':row_index},source={},checks={},evidence_ids=['audit_product.json'],reason_codes=[reason]))
    return candidates,handled,resolved_items
