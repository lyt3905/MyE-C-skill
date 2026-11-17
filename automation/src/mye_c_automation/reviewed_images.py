"""Bound user-reviewed blank-pixel deletions; no model or general audit override."""
from copy import deepcopy
import hashlib,json
from pathlib import Path
from PIL import Image
from mye_c_automation.job_manager import atomic_json

FIELD='reviewed_detail_deletions'


def validate_targets(targets):
    if type(targets) is not list or not targets:raise ValueError('REVIEWED_DETAIL_TARGETS_REQUIRED')
    seen=set()
    for row in targets:
        if (type(row) is not dict or set(row)!={'index','url','sha256'} or type(row['index']) is not int or row['index']<0
            or row['index'] in seen or not isinstance(row['url'],str) or not row['url'].startswith(('https://','http://'))
            or not isinstance(row['sha256'],str) or len(row['sha256'])!=64 or any(c not in '0123456789abcdef' for c in row['sha256'])):raise ValueError('INVALID_REVIEWED_DETAIL_TARGET')
        seen.add(row['index'])
    return targets


def scoped_detail_change(before,plan):
    """Pure scope check: no changes beyond exactly the reviewed detail slots."""
    post=plan.get('post_actions') or {}
    if FIELD not in post:return False
    try:
        if (set(post)!={FIELD} or plan.get('automation',{}).get('actions')!=['DELETE'] or
            set(plan.get('desired',{}))!={'images'}):return False
        expected=deepcopy(before['images']);targets=validate_targets(post[FIELD])
        for row in sorted(targets,key=lambda r:r['index'],reverse=True):
            if expected['detail'][row['index']]!=row['url']:return False
            expected['detail'].pop(row['index'])
        return expected==plan['desired']['images']
    except (ValueError,KeyError,IndexError,TypeError):return False


def verify_reviewed_evidence(directory,plan):
    root=Path(directory).resolve();read=lambda n:json.loads((root/n).read_text(encoding='utf-8'))
    proof=read('reviewed_images.json');before=read('audit_product.json')
    from mye_c_automation.product_state import canonical_state_hash
    if (proof.get('schema')!='user-reviewed-blank-deletion/v1' or
        (proof.get('job_id'),proof.get('pid'),proof.get('shop'),proof.get('account_fingerprint'),proof.get('before_sha256'))!=
        (plan['job_id'],plan['pid'],plan['shop'],plan['precondition'].get('account_fingerprint'),plan['precondition']['state_sha256']) or
        canonical_state_hash(before)!=proof['before_sha256'] or not scoped_detail_change(before,plan) or
        proof.get('targets')!=plan['post_actions'][FIELD]):raise ValueError('REVIEWED_IMAGE_SCOPE_MISMATCH')
    review=proof.get('authorization') or {}
    if review.get('source')!='EXPLICIT_USER_REVIEW' or review.get('authorized_actions')!=['DELETE'] or not isinstance(review.get('statement'),str) or not review['statement'].strip():raise ValueError('USER_DELETION_REVIEW_REQUIRED')
    bound={r['path'].replace('\\','/'):r['sha256'] for r in plan['evidence_refs']}
    for name in ('audit_product.json','reviewed_images.json'):
        if bound.get(name)!=hashlib.sha256((root/name).read_bytes()).hexdigest():raise ValueError('REVIEWED_EVIDENCE_NOT_BOUND')
    for row in proof['targets']:
        name='reviewed_images/'+row['sha256']+'.bin';path=root/name
        if bound.get(name)!=row['sha256'] or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('REVIEWED_PIXEL_BYTES_CHANGED')
        with Image.open(path) as image:
            image.load()
            if image.size!=(1,1) or image.format!='GIF':raise ValueError('REVIEWED_TARGET_NOT_BLANK_GIF_PIXEL')
    return proof


def compile_blank_deletions(directory,job,product,policy,targets,review,*,fetch_image,inventory=None):
    """Compile only a user's exact blank-detail deletions into the existing V3 plan."""
    from mye_c_automation.product_state import canonical_state_hash
    from mye_c_automation.plan_v2 import validate_plan,plan_hash
    from mye_c_automation.final_state import pre_apply_validate
    policy.authorize(job['pid'],job['shop_id'],['DELETE'],execution=True)
    targets=deepcopy(validate_targets(targets));root=Path(directory).resolve()
    if job['input_state_sha256']!=canonical_state_hash(product):raise ValueError('REVIEWED_CURRENT_STATE_MISMATCH')
    if review.get('source')!='EXPLICIT_USER_REVIEW' or review.get('authorized_actions')!=['DELETE'] or not isinstance(review.get('statement'),str) or not review['statement'].strip():raise ValueError('USER_DELETION_REVIEW_REQUIRED')
    images=deepcopy(product['images']);folder=root/'reviewed_images';folder.mkdir()
    for row in sorted(targets,key=lambda r:r['index'],reverse=True):
        if images['detail'][row['index']]!=row['url']:raise ValueError('REVIEWED_DETAIL_URL_CHANGED')
        data=fetch_image(row['url'])
        if hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('REVIEWED_DETAIL_BYTES_CHANGED')
        path=folder/(row['sha256']+'.bin');path.write_bytes(data)
        with Image.open(path) as image:
            image.load()
            if image.size!=(1,1) or image.format!='GIF':raise ValueError('REVIEWED_TARGET_NOT_BLANK_GIF_PIXEL')
        images['detail'].pop(row['index'])
    atomic_json(root/'audit_product.json',product);atomic_json(root/'audit_account.json',dict(account_fingerprint=job['account_fingerprint'],status='VERIFIED'))
    atomic_json(root/'reviewed_images.json',dict(schema='user-reviewed-blank-deletion/v1',job_id=job['job_id'],pid=job['pid'],shop=job['shop_id'],account_fingerprint=job['account_fingerprint'],before_sha256=job['input_state_sha256'],authorization=review,targets=targets))
    names=['job.json','audit_product.json','audit_account.json','reviewed_images.json']+['reviewed_images/'+r['sha256']+'.bin' for r in targets]
    if inventory is not None:atomic_json(root/'full_inventory.json',inventory);names.append('full_inventory.json')
    atomic_json(root/'auto_decisions.json',dict(policy_sha256=policy.sha256,items=[dict(action='DELETE',decision='AUTO_SAFE',remedy_id='USER_DETAIL_'+str(r['index']),item_id='USER_DETAIL_'+str(r['index']),target=dict(pool='detail',index=r['index']),source=dict(type='EXPLICIT_USER_REVIEW',sha256=r['sha256'],original_sha256=r['sha256'],url=r['url']),reason_codes=['EXPLICIT_USER_REVIEW_BLANK_PIXEL'],evidence_ids=['reviewed_images.json'],checks=dict(user_review_bound=True,blank_pixel_bytes_verified=True)) for r in targets]));names.append('auto_decisions.json')
    plan=dict(schema='token-opt-plan/v3',job_id=job['job_id'],pid=job['pid'],shop=job['shop_id'],workflow_version=job['workflow_version'],policy_version=job['policy_version'],precondition=dict(state_sha256=job['input_state_sha256'],account_fingerprint=job['account_fingerprint']),evidence_refs=[dict(path=n,sha256=hashlib.sha256((root/n).read_bytes()).hexdigest()) for n in dict.fromkeys(names)],ai_judgement_refs=[],desired={'images':images},post_actions={FIELD:targets},review={'status':'RESOLVED'},automation=dict(policy_sha256=policy.sha256,actions=['DELETE']))
    plan=validate_plan(plan);verify_reviewed_evidence(root,plan);checked=pre_apply_validate(product,plan)
    if not checked['ok']:raise ValueError('REVIEWED_FINAL_STATE_INVALID:'+repr(checked['errors']))
    compiled=dict(ok=True,status='AUTO_READY',read_only=False,plan_sha256=plan_hash(plan),scope='USER_REVIEWED_BLANK_DETAIL_DELETION_ONLY',whole_product_verified=False,existing_state_findings=checked['warnings'])
    atomic_json(root/'plan.v2.json',plan);atomic_json(root/'compiled_plan.json',compiled);atomic_json(root/'plan_validation.json',compiled)
    return plan,compiled


def verify_reviewed_snapshot(directory,plan,observed):
    from mye_c_automation.final_state import simulate_final_snapshot,validate_final_snapshot
    from mye_c_automation.product_state import saved_state_matches
    root=Path(directory);verify_reviewed_evidence(root,plan);before=json.loads((root/'audit_product.json').read_text(encoding='utf-8'))
    expected=simulate_final_snapshot(before,plan);checked=validate_final_snapshot(observed,context={'before':before,'plan':plan,'saved_readback':True})
    return dict(ok=checked['ok'] and saved_state_matches(expected,observed,source=before),validation=checked,existing_state_findings=checked['warnings'],whole_product_verified=False,scope='USER_REVIEWED_BLANK_DETAIL_DELETION_ONLY')
