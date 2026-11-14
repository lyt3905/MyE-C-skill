"""Task-specific result contracts with strict identity and evidence bindings."""
CLASSES={'official_marketing_text','third_party_store_banner','chinese_promotion_poster','third_party_store_logo','social_account_signature','manufacturer_branding','product_print','marketing_text','photographer_credit','unknown'}
TASKS={'watermark','sku_match','product_identity','title_semantics','remedy_quality','remedy_geometry','deletion_quality'}
def validate_result(result, task, item, evidence=None, *, allow_legacy=True):
    if task not in TASKS or not isinstance(result,dict): raise ValueError('unsupported task/result')
    if task=='product_identity':
        # Shape aliases only: keep original observations and confidence, and
        # reject contradictory fields instead of selecting the convenient one.
        result=dict(result)
        for alias,field in (('observed_model','model'),('observed_color','color')):
            if alias in result:
                if field in result and result[field]!=result[alias]:raise ValueError('ambiguous identity observations')
                result[field]=result[alias]
        if result.get('schema_version')=='product-identity/v3':
            from .identity_contract import validate_identity
            result=validate_identity(result,evidence)
        elif not allow_legacy:raise ValueError('LEGACY_RESULT_NOT_EXHAUSTIVE:product_identity')
    required={'task_type','item_id','confidence','abstain','evidence_ids'}
    required |= ({'classification','owner','location'} if result.get('schema_version')!='watermark/v3' else set()) if task=='watermark' else {'decision'}
    if not required <= set(result) or result['task_type'] != task or result['item_id'] != item: raise ValueError('identity/fields')
    if type(result['confidence']) not in (int,float) or not 0 <= result['confidence'] <= 1 or type(result['abstain']) is not bool: raise ValueError('confidence/abstain')
    refs=result['evidence_ids']
    if not isinstance(refs,list) or not refs or any(type(x) is not str or not x for x in refs): raise ValueError('evidence')
    if evidence is not None and not set(refs) <= set(evidence.get('evidence_ids',[])): raise ValueError('unbound evidence')
    if task=='watermark':
        if result.get('schema_version')=='watermark/v3':
            from .watermark_contract import validate_watermark
            result=validate_watermark(result,evidence)
        else:
            if not allow_legacy:raise ValueError('LEGACY_RESULT_NOT_EXHAUSTIVE:watermark')
            if result.get('schema_version') not in (None,'legacy-watermark/v2'):raise ValueError('unsupported watermark schema')
            if result['classification'] not in CLASSES or any(type(result[k]) is not str or not result[k] for k in ('owner','location')): raise ValueError('classification')
            result=dict(result,coverage_complete=False,legacy_single_mark=True)
    else:
        if result['decision'] not in {'MATCH','MISMATCH','UNCERTAIN'}: raise ValueError('decision')
    if task=='remedy_quality':
        required_checks={'product_identity_match','source_clean','candidate_visual_validation','protected_elements_preserved','residual_pass','subject_bounds_safe'}
        known_checks=required_checks|{'model_match','packaging_match','official_source'}
        top_checks={k:result[k] for k in known_checks if k in result}
        if top_checks:
            if 'checks' in result:raise ValueError('ambiguous quality checks')
            if not required_checks<=set(top_checks) or any(type(v) is not bool for v in top_checks.values()):raise ValueError('quality checks required')
            # Normalize shape only; preserve every decision and boolean, without defaults.
            result={k:v for k,v in result.items() if k not in known_checks}
            result['checks']=top_checks
        checks=result.get('checks')
        if not isinstance(checks,dict) or not required_checks<=set(checks) or any(type(v) is not bool for v in checks.values()): raise ValueError('quality checks required')
    if task=='deletion_quality':
        if any(type(result.get(k)) is not bool for k in ('is_box','is_official','information_preserved')) or result.get('category') not in {'REDUNDANT','DECORATION','STORE_BANNER','PRODUCT','UNCERTAIN'}:raise ValueError('deletion observations required')
    if task=='remedy_geometry' and not result['abstain']:
        for name in ('subject_box','crop_box','erase_box'):
            box=result.get(name)
            if box is not None and (type(box) is not list or len(box)!=4 or any(type(v) is not int or v<0 for v in box)):
                raise ValueError('invalid geometry')
    if task=='sku_match':
        if result.get('image_type') not in (None,'box','product_only','mixed','unknown'): raise ValueError('image_type')
        if result.get('sku_packaging') not in (None,'with_box','without_box','unknown'): raise ValueError('sku_packaging')
        for flag in ('missing_image','shared_across_skus'):
            if flag in result and type(result[flag]) is not bool: raise ValueError('sku flag')
        if not all(type(result.get(k)) is str and result[k] for k in ('sku_id','image_id')): raise ValueError('sku references')
        if evidence and any(result[k] != evidence.get(k) for k in ('sku_id','image_id')): raise ValueError('sku identity mismatch')
    if task=='product_identity' and result.get('model') and not result.get('model_evidence_ids'): raise ValueError('model evidence required')
    if result.get('model_evidence_ids') and not set(result['model_evidence_ids']) <= set(refs): raise ValueError('model evidence unbound')
    return result
