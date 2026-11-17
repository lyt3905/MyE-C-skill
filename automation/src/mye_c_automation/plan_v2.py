"""Strict v2 plan envelope; no approval field is trusted."""
import hashlib
import re
from copy import deepcopy
from mye_c_automation.product_state import canonical_json


def plan_hash(plan):
    return hashlib.sha256(canonical_json(plan).encode()).hexdigest()

def planned_upload_count(plan):
    return len({row['sha256'] for row in (plan.get('post_actions') or {}).get('uploads',[])})


def validate_plan(plan):
    required = {'schema','job_id','pid','shop','workflow_version','policy_version','precondition','evidence_refs','ai_judgement_refs','desired','post_actions','review'}
    automatic=isinstance(plan,dict) and plan.get('schema')=='token-opt-plan/v3'
    if automatic: required.add('automation')
    if type(plan) is not dict or set(plan) != required or plan['schema'] not in {'token-opt-plan/v2','token-opt-plan/v3'} or plan['workflow_version'] != 'token-opt-v2':
        raise ValueError('invalid v2 envelope')
    if automatic:
        from mye_c_automation.automation_policy import ACTIONS
        auto=plan['automation']
        if type(auto) is not dict or set(auto)!={'policy_sha256','actions'} or not _digest(auto['policy_sha256']) or type(auto['actions']) is not list or any(a not in ACTIONS for a in auto['actions']):
            raise ValueError('invalid automatic authorization binding')
    if any(type(plan[k]) is not int or plan[k] <= 0 for k in ('pid','shop')):
        raise ValueError('invalid identity')
    if any(type(plan[k]) is not str or not plan[k].strip() or len(plan[k]) > 200 for k in ('job_id','policy_version')):
        raise ValueError('invalid version or job')
    if plan['review'] != {'status': 'RESOLVED'}:
        raise ValueError('NEEDS_REVIEW')
    pre = plan['precondition']
    if type(pre) is not dict or not {'state_sha256'}<=set(pre) or set(pre)-({'state_sha256','account_fingerprint'}|({'main_count_preflight'} if automatic else set())) or not _digest(pre['state_sha256']) or ('account_fingerprint' in pre and not _digest(pre['account_fingerprint'])):
        raise ValueError('invalid state digest')
    if 'main_count_preflight' in pre:
        from mye_c_automation.main_preprocessing import validate_receipt
        validate_receipt(pre['main_count_preflight'])
    desired = plan['desired']
    allowed_desired={'titleEn','images','brandId'}|({'identityJson'} if automatic else set())
    if type(desired) is not dict or set(desired) - allowed_desired:
        raise ValueError('forbidden desired fields')
    if automatic:
        actions=set(plan['automation']['actions'])
        scopes={'titleEn':{'TITLE_REWRITE'},'identityJson':{'TITLE_REWRITE'},'brandId':{'BRAND_CODE'},'images':{'REPLACE_TWIN','REPLACE_LOCAL','CROP_BANNER','BOX_NORMALIZE','ERASE_LOCAL','DELETE_REDUNDANT','SKU_ASSIGN','DELETE','REMOVE_TEXT','AI_REGENERATE'}}
        if any(not actions&scopes[field] for field in desired): raise ValueError('UNAUTHORIZED_FIELD_SCOPE')
        if 'identityJson' in desired:
            from mye_c_automation.product_state import identity_object
            if not isinstance(desired['identityJson'],str): raise ValueError('identityJson must be serialized')
            identity_object(desired['identityJson'])
    if 'titleEn' in desired and (type(desired['titleEn']) is not str or not desired['titleEn'].strip()):
        raise ValueError('invalid title')
    if automatic and len(desired.get('titleEn',''))>120:raise ValueError('title exceeds SOP limit')
    if 'brandId' in desired and (type(desired['brandId']) is not int or desired['brandId'] < 0):
        raise ValueError('invalid brand')
    if 'images' in desired:
        images = desired['images']
        pools={'main','detail','sku'}|({'ai','scene','gallery','attachList'} if automatic else set())
        if type(images) is not dict or set(images) - pools or any(type(pool) is not list or any(type(url) is not str or not url for url in pool) for pool in images.values()):
            raise ValueError('invalid images')
    post = plan['post_actions']
    if post == []:  # Legacy empty representation, accepted only when empty.
        post = {}
    allowed_post={'uploads','translate_title'} | ({'url_replacements','sku_assignments','sku_row_assignments','preserve_reference_urls','target_positions','content_groups','reviewed_detail_deletions','main_reference_cleanup'} if automatic else set())
    if type(post) is not dict or set(post) - allowed_post or type(post.get('translate_title',False)) is not bool or type(post.get('uploads',[])) is not list:
        raise ValueError('invalid post actions')
    if 'reviewed_detail_deletions' in post:
        from mye_c_automation.reviewed_images import validate_targets
        validate_targets(post['reviewed_detail_deletions'])
        if set(post)!={'reviewed_detail_deletions'} or plan['automation']['actions']!=['DELETE'] or set(desired)!={'images'}:raise ValueError('REVIEWED_DELETION_SCOPE_ONLY')
    if 'main_reference_cleanup' in post:
        from mye_c_automation.main_preprocessing import validate_recipe
        validate_recipe(post['main_reference_cleanup'])
        if set(post)!={'main_reference_cleanup'} or plan['automation']['actions']!=['DELETE'] or set(desired)!={'images'}:raise ValueError('MAIN_REFERENCE_SCOPE_ONLY')
    if 'url_replacements' in post:
        if not set(plan['automation']['actions'])&{'REPLACE_TWIN','REPLACE_LOCAL','CROP_BANNER','BOX_NORMALIZE','ERASE_LOCAL'}:
            raise ValueError('UNAUTHORIZED_POST_ACTION_SCOPE')
        from urllib.parse import urlparse
        mapping=post['url_replacements']
        if type(mapping) is not dict or not mapping or any(type(v) is not str or urlparse(v).scheme not in {'http','https'} or not urlparse(v).netloc for pair in mapping.items() for v in pair):
            raise ValueError('invalid URL replacements')
    if 'sku_assignments' in post:
        mapping=post['sku_assignments']
        if 'SKU_ASSIGN' not in plan['automation']['actions'] or type(mapping) is not dict or not mapping or any(type(k) is not str or not k or type(v) is not str or not v.startswith(('http://','https://')) for k,v in mapping.items()):
            raise ValueError('invalid SKU assignments')
    if 'sku_row_assignments' in post:
        rows=post['sku_row_assignments']
        if 'SKU_ASSIGN' not in plan['automation']['actions'] or post.get('sku_assignments') or type(rows) is not list or not rows:
            raise ValueError('invalid snapshot SKU assignments')
        seen=set()
        for row in rows:
            if (type(row) is not dict or set(row)!={'index','source_sha256','url'} or type(row['index']) is not int or
                    row['index']<0 or row['index'] in seen or not _digest(row['source_sha256']) or
                    type(row['url']) is not str or not row['url'].startswith(('http://','https://'))):
                raise ValueError('invalid snapshot SKU locator')
            seen.add(row['index'])
    if 'preserve_reference_urls' in post and (type(post['preserve_reference_urls']) is not list or any(type(url) is not str or not url for url in post['preserve_reference_urls'])):
        raise ValueError('invalid preserved references')
    if 'target_positions' in post:
        if not {'DELETE_REDUNDANT','DELETE'}&set(plan['automation']['actions']) or type(post['target_positions']) is not dict:raise ValueError('invalid target positions')
        for image_id,target in post['target_positions'].items():
            if type(image_id) is not str or type(target) is not dict or set(target)!={'pool','index'} or target['pool'] not in {'main','detail','sku'} or type(target['index']) is not int or target['index']<0 or target['index']>=len(desired.get('images',{}).get(target['pool'],[])):raise ValueError('invalid target position')
    targets = set()
    if 'content_groups' in post:
        groups=post['content_groups'];seen_urls=set();seen_sha=set()
        if not isinstance(groups,list) or not groups:raise ValueError('INVALID_CONTENT_GROUPS')
        for group in groups:
            keys={'source_sha256','urls','action','candidate_sha256'}|({'replacement_url'} if group.get('action')=='REPLACE_TWIN' else set()) if isinstance(group,dict) else set()
            if (not isinstance(group,dict) or set(group)!=keys or not _digest(group['source_sha256']) or
                group['source_sha256'] in seen_sha or group['action'] not in {'DELETE','REMOVE_TEXT','AI_REGENERATE','REPLACE_TWIN'} or group['action'] not in plan['automation']['actions'] or
                not isinstance(group['urls'],list) or not group['urls'] or any(not isinstance(u,str) or not u.startswith(('http://','https://')) or u in seen_urls for u in group['urls'])):raise ValueError('INVALID_CONTENT_GROUP')
            if group['action']=='DELETE':
                if group['candidate_sha256'] is not None:raise ValueError('INVALID_CONTENT_DELETE')
            elif group['action']=='REPLACE_TWIN':
                if not _digest(group['candidate_sha256']) or not isinstance(group['replacement_url'],str) or not group['replacement_url'].startswith(('https://','http://')):raise ValueError('UNBOUND_CONTENT_TWIN')
            elif not _digest(group['candidate_sha256']) or group['candidate_sha256'] not in {r.get('sha256') for r in post.get('uploads',[])}:raise ValueError('UNBOUND_CONTENT_UPLOAD')
            seen_urls.update(group['urls']);seen_sha.add(group['source_sha256'])
    if automatic and post.get('uploads') and not set(plan['automation']['actions'])&{'REPLACE_LOCAL','CROP_BANNER','BOX_NORMALIZE','ERASE_LOCAL','REMOVE_TEXT','AI_REGENERATE'}:
        raise ValueError('UNAUTHORIZED_UPLOAD_SCOPE')
    if automatic and post.get('translate_title') and ('TITLE_REWRITE' not in plan['automation']['actions'] or 'titleEn' not in desired):
        raise ValueError('UNAUTHORIZED_TRANSLATION_SCOPE')
    for upload in post.get('uploads',[]):
        if type(upload) is not dict or set(upload) != {'path','sha256','pool','index'}:
            raise ValueError('invalid upload action')
        _reference({k: upload[k] for k in ('path','sha256')})
        if upload['pool'] not in (('main','detail','sku','description') if automatic and post.get('content_groups') else ('main','detail','sku')) or type(upload['index']) is not int or upload['index'] < 0:
            raise ValueError('invalid upload target')
        target = (upload['pool'], upload['index'])
        if target in targets or (upload['pool']!='description' and upload['index'] >= len(desired.get('images',{}).get(upload['pool'],[]))):
            raise ValueError('duplicate or missing upload target')
        targets.add(target)
    for key in ('evidence_refs','ai_judgement_refs'):
        if type(plan[key]) is not list:
            raise ValueError('invalid references')
        for ref in plan[key]:
            _reference(ref)
    return deepcopy(plan)


def _digest(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _reference(ref):
    if type(ref) is not dict or set(ref) != {'path','sha256'} or not _digest(ref['sha256']) or type(ref['path']) is not str or not ref['path'].strip():
        raise ValueError('invalid evidence reference')
    path = ref['path'].replace('\\','/')
    if path.startswith('/') or ':' in path or any(part in ('..','') for part in path.split('/')):
        raise ValueError('unsafe evidence path')
