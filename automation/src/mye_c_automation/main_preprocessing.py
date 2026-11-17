"""Bounded first-main reference deletion; pure transforms, no model/site I/O."""
from copy import deepcopy
from pathlib import Path
import json

FIELD='main_reference_cleanup'


def validate_receipt(value):
    if (not isinstance(value,dict) or set(value)!={'job_id','main_count'} or
        not isinstance(value['job_id'],str) or not value['job_id'].startswith('JOB_') or
        any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' for c in value['job_id']) or
        type(value['main_count']) is not int or value['main_count']<1):
        raise ValueError('INVALID_MAIN_PREFLIGHT_RECEIPT')
    return value


def count_exception(before,plan):
    from mye_c_automation.product_state import canonical_state_hash
    pre=plan.get('precondition') or {};value=pre.get('main_count_preflight')
    if not value:return False
    validate_receipt(value)
    return (plan.get('schema')=='token-opt-plan/v3' and
        pre.get('state_sha256')==canonical_state_hash(before) and
        value['main_count']==len((before.get('images') or {}).get('main') or []))


def verify_receipt(directory,plan):
    """Bind the continuation to a completed independent preflight readback."""
    from mye_c_automation.product_state import canonical_state_hash
    root=Path(directory);value=validate_receipt(plan['precondition']['main_count_preflight'])
    prior=root.parent/value['job_id']
    def read(name):return json.loads((prior/name).read_text(encoding='utf-8'))
    job=read('job.json');proof=read('main_count_user_rule.json');source=read('audit_product.json')
    expected_after=read('expected_after.json')
    if (prior/'independent_preflight_verification.json').is_file():
        verified=read('independent_preflight_verification.json').get('ok') is True
        observed=read('independent_after.json')
    else:
        recovery=read('preflight_recovery_verification.json')
        verified=(recovery.get('status')=='AUTO_VERIFIED' and recovery.get('write_outcome')=='MATCHED' and
            recovery.get('job_id')==value['job_id'] and recovery.get('retry_save_allowed') is False)
        observed=read('recovery_after.json')
    before=json.loads((root/'audit_product.json').read_text(encoding='utf-8'))
    derived=transformed(source,proof['recipe'])
    expected_after.pop('updatedAt',None);observed.pop('updatedAt',None);current=deepcopy(before);current.pop('updatedAt',None);derived.pop('updatedAt',None)
    if (job['pid']!=plan['pid'] or job['shop_id']!=plan['shop'] or
        job.get('account_fingerprint')!=plan['precondition'].get('account_fingerprint') or
        not verified or
        proof.get('policy_sha256')!=plan['automation']['policy_sha256'] or
        proof.get('state_sha256')!=canonical_state_hash(source) or
        derived!=expected_after or
        expected_after!=observed or observed!=current or not count_exception(before,plan)):
        raise ValueError('MAIN_PREFLIGHT_RECEIPT_MISMATCH')


def validate_recipe(value):
    if (not isinstance(value,dict) or set(value)!={'schema','removed_url','before_count','after_count'} or
        value.get('schema')!='main-reference-cleanup/v1' or not isinstance(value.get('removed_url'),str) or
        not value['removed_url'] or type(value.get('before_count')) is not int or value['before_count']<=6 or
        type(value.get('after_count')) is not int or not 0<value['after_count']<value['before_count']):
        raise ValueError('INVALID_MAIN_REFERENCE_CLEANUP')
    return value


def recipe(before):
    urls=(before.get('images') or {}).get('main') or []
    if len(urls)<=6:raise ValueError('MAIN_PREFLIGHT_REQUIRES_OVER_SIX')
    return validate_recipe(dict(schema='main-reference-cleanup/v1',removed_url=urls[0],
        before_count=len(urls),after_count=sum(u!=urls[0] for u in urls)))


def transformed(before,value):
    from mye_c_automation.description_images import body_image_nodes,delete_body_images
    validate_recipe(value)
    urls=(before.get('images') or {}).get('main') or []
    if len(urls)!=value['before_count'] or not urls or urls[0]!=value['removed_url']:
        raise ValueError('MAIN_REFERENCE_SOURCE_MISMATCH')
    result=deepcopy(before);target=value['removed_url']
    for pool in ('main','detail','sku'):
        if pool in result['images']:result['images'][pool]=[u for u in result['images'][pool] if u!=target]
    if len(result['images']['main'])!=value['after_count']:raise ValueError('MAIN_REFERENCE_COUNT_MISMATCH')
    for sku in result.get('skus') or []:
        for field in ('skuImageUrl','imageUrl','image'):
            if sku.get(field)==target:sku[field]=None
    if any(row['url']==target for row in body_image_nodes(before.get('descriptionJson'))):
        result['descriptionJson']=delete_body_images(before['descriptionJson'],[target])
    return result


def expected(before,plan):
    post=plan.get('post_actions') or {}
    if (set(post)!={FIELD} or plan.get('automation',{}).get('actions')!=['DELETE'] or
        set(plan.get('desired',{}))!={'images'}):raise ValueError('MAIN_REFERENCE_SCOPE_ONLY')
    result=transformed(before,post[FIELD])
    if result['images']!=plan['desired']['images']:raise ValueError('MAIN_REFERENCE_IMAGES_MISMATCH')
    return result


def verify_snapshot(before,plan,after):
    wanted=expected(before,plan);actual=deepcopy(after)
    wanted.pop('updatedAt',None);actual.pop('updatedAt',None)
    from mye_c_automation.product_state import canonical_state_hash
    ok=canonical_state_hash(actual)==canonical_state_hash(wanted)
    return dict(ok=ok,errors=[] if ok else [dict(rule_id='MAIN_REFERENCE_CLEANUP_SCOPE')],
        checks=['MAIN_REFERENCE_CLEANUP_SCOPE'],warnings=[])


def verify_evidence(directory,plan):
    from mye_c_automation.product_state import canonical_state_hash
    root=Path(directory);before=json.loads((root/'audit_product.json').read_text(encoding='utf-8'))
    proof=json.loads((root/'main_count_user_rule.json').read_text(encoding='utf-8'))
    if (proof.get('recipe')!=(plan.get('post_actions') or {}).get(FIELD) or
        proof.get('state_sha256')!=canonical_state_hash(before) or
        proof.get('policy_sha256')!=plan.get('automation',{}).get('policy_sha256')):
        raise ValueError('MAIN_REFERENCE_EVIDENCE_MISMATCH')
    expected(before,plan)
