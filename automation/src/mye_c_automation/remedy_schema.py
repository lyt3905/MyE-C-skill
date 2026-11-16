"""Typed action contract; observations are never arbitrary save parameters."""
import re
from mye_c_automation.automation_policy import ACTIONS

COMMON_CHECKS = {'product_identity_match','source_clean','candidate_visual_validation',
                 'protected_elements_preserved','source_bound'}
ACTION_CHECKS = {
    'BOX_NORMALIZE': {'model_match','packaging_match','ocr_pass','residual_pass','template_pass'},
    'REPLACE_TWIN': {'model_match','packaging_match'},
    'CROP_BANNER': {'subject_bounds_safe','ocr_pass','residual_pass','template_pass'},
    'ERASE_LOCAL': {'mask_background_only','outside_mask_unchanged','ocr_pass','residual_pass','template_pass'},
    'REPLACE_LOCAL': {'official_source','model_match','packaging_match'},
    'SKU_ASSIGN': {'sku_assignment_unique','packaging_match','model_match'},
    'TITLE_REWRITE': {'title_rules_pass','field_provenance','translation_once_policy'},
    'BRAND_CODE': {'field_provenance','brand_mapping_verified'},
    'DELETE_REDUNDANT': {'non_box_deletion','non_official_deletion','visual_evidence_600px'},
}

def validate_candidate(candidate):
    if isinstance(candidate,dict) and candidate.get('v2_contract'):
        from mye_c_automation.v2_remediation import validate_candidate as validate_v2
        return validate_v2(candidate)
    if type(candidate) is not dict: raise ValueError('INVALID_REMEDY')
    for key in ('remedy_id','item_id','action'):
        if not isinstance(candidate.get(key),str) or not candidate[key]: raise ValueError('MISSING_'+key)
    if candidate['action'] not in ACTIONS-{'WEB_SEARCH'}: raise ValueError('UNKNOWN_REMEDY_ACTION')
    if not isinstance(candidate.get('evidence_ids'),list) or not candidate['evidence_ids']:
        raise ValueError('MISSING_EVIDENCE')
    source=candidate.get('source')
    if not isinstance(source,dict) or not source.get('type') or not re.fullmatch('[a-f0-9]{64}',str(source.get('sha256',''))):
        raise ValueError('UNBOUND_SOURCE')
    if type(candidate.get('target')) is not dict or type(candidate.get('checks')) is not dict:
        raise ValueError('INVALID_REMEDY_TARGET_OR_CHECKS')
    common=COMMON_CHECKS-{'source_clean'} if candidate['action']=='DELETE_REDUNDANT' else COMMON_CHECKS
    required=common|ACTION_CHECKS.get(candidate['action'],set())
    composite=candidate['action']=='DELETE_REDUNDANT' and candidate.get('validation_scope',{}).get('type')=='AUTHORIZED_DECORATED_COMPOSITE_REMOVAL'
    if composite:required=(required-{'non_box_deletion'})|{'decorated_composite','retained_packaging_verified'}
    if any(candidate['checks'].get(k) is not True for k in required): raise ValueError('QUALITY_GATE_INCOMPLETE')
    if candidate['action']=='DELETE_REDUNDANT' and candidate.get('is_box') is not False and not composite:
        raise ValueError('BOX_DELETION_FORBIDDEN')
    return candidate
