"""Explicit restoration exception. Preview is read-only; apply is one bound save."""
from copy import deepcopy
import hashlib,json,uuid
from pathlib import Path
from mye_c_automation.job_manager import JobManager, atomic_json
from mye_c_automation.plan_v2 import plan_hash, validate_plan
from mye_c_automation.product_state import canonical_state_hash, canonical_json, diff_state
from mye_c_automation.final_state import validate_final_snapshot
from mye_c_automation.executor.service import ExecutorService
from mye_c_automation.account_coordination import account_lock, account_key

RESTORABLE={'titleEn','identityJson','brandId','images','skus'}

def _hash(preview):
    return hashlib.sha256(canonical_json({k:v for k,v in preview.items() if k!='preview_sha256'}).encode()).hexdigest()

def _source(root):
    read=lambda name:json.loads((root/name).read_text(encoding='utf-8'))
    job=JobManager(root.parent).load(root.name);plan=validate_plan(read('plan.v2.json'))
    if (plan['job_id'],plan['pid'],plan['shop'])!=(job['job_id'],job['pid'],job['shop_id']):raise ValueError('ROLLBACK_BINDING_MISMATCH')
    journal=read('local_execution.json')
    if journal.get('plan_sha256')!=plan_hash(plan):raise ValueError('ROLLBACK_BINDING_MISMATCH')
    recovery=read('recovery_readback.json') if (root/'recovery_readback.json').exists() else {}
    if journal.get('state')=='APPLY_UNKNOWN' and recovery.get('write_outcome')!='MATCHED':raise ValueError('UNKNOWN_WRITE_REQUIRES_READBACK')
    before=read('before.json')
    after=read('after.json') if (root/'after.json').exists() else read('recovery_after.json')
    if canonical_state_hash(before)!=plan['precondition']['state_sha256']:raise ValueError('ROLLBACK_SOURCE_CHANGED')
    changed=set(diff_state(before,after))-{'titleTranslationZh'}
    if changed-RESTORABLE:raise ValueError('ROLLBACK_PROTECTED_FIELD_CONFLICT')
    return job,plan,before,after,changed

def _target(current,before,after,changed,plan):
    if canonical_state_hash(current)!=canonical_state_hash(after):raise ValueError('STATE_DRIFT_BEFORE_ROLLBACK')
    target=deepcopy(current)
    for field in changed:
        if field in before:target[field]=deepcopy(before[field])
        else:target.pop(field,None)
    validation=validate_final_snapshot(target,context={'before':current,'plan':{'automation':{'actions':['TITLE_REWRITE']}}})
    if not validation['ok']:raise ValueError('ROLLBACK_TARGET_INVALID: '+repr(validation['errors']))
    return target

def confirmation_for(preview):
    return {'confirmed':True,'rollback_id':preview['rollback_id'],'pid':preview['pid'],'shop':preview['shop'],'preview_sha256':preview['preview_sha256']}

def prepare_rollback(directory,reader):
    root=Path(directory);job,plan,before,after,changed=_source(root)
    with account_lock(account_key(reader,root.parent)):
        current=reader.product(job['pid']);ExecutorService(None,reader,root)._identity(current,plan)
        target=_target(current,before,after,changed,plan)
        preview={'schema':'controlled-rollback/v1','rollback_id':'ROLLBACK_'+uuid.uuid4().hex,'source_job_id':job['job_id'],'pid':job['pid'],'shop':job['shop_id'],'source_plan_sha256':plan_hash(plan),'precondition_state_sha256':canonical_state_hash(current),'target_state_sha256':canonical_state_hash(target),'restore_fields':sorted(changed),'changes':diff_state(current,target),'read_only':True,'site_save_calls':0,'upload_calls':0,'status_calls':0,'content_status':'ORIGINAL_CONTENT_MAY_CONTAIN_REPORTED_ANOMALIES'}
        preview['preview_sha256']=_hash(preview)
        atomic_json(root/'rollback.preview.json',preview)
        atomic_json(root/'rollback.confirmation.example.json',dict(confirmation_for(preview),confirmed=False))
        return preview

def apply_rollback(directory,writer,confirmation):
    root=Path(directory);preview=json.loads((root/'rollback.preview.json').read_text(encoding='utf-8'))
    if preview.get('schema')!='controlled-rollback/v1' or preview.get('preview_sha256')!=_hash(preview) or confirmation!=confirmation_for(preview):raise ValueError('BOUND_ROLLBACK_CONFIRMATION_REQUIRED')
    job,plan,before,after,changed=_source(root)
    if (preview['source_job_id'],preview['pid'],preview['shop'],preview['source_plan_sha256'])!=(job['job_id'],job['pid'],job['shop_id'],plan_hash(plan)):raise ValueError('ROLLBACK_BINDING_MISMATCH')
    with account_lock(account_key(writer,root.parent)):
        if (root/'rollback_execution.json').exists():raise FileExistsError('ROLLBACK_ALREADY_ATTEMPTED')
        current=writer.product(job['pid']);ExecutorService(None,writer,root)._identity(current,plan)
        if canonical_state_hash(current)!=preview['precondition_state_sha256']:raise ValueError('STATE_DRIFT_BEFORE_ROLLBACK')
        target=_target(current,before,after,changed,plan)
        if canonical_state_hash(target)!=preview['target_state_sha256'] or sorted(changed)!=preview['restore_fields']:raise ValueError('ROLLBACK_PREVIEW_CHANGED')
        journal=root/'rollback_execution.json'
        with journal.open('x',encoding='utf-8') as stream:
            json.dump({'preview_sha256':preview['preview_sha256'],'state':'APPLY_UNKNOWN'},stream);stream.flush()
            import os
            os.fsync(stream.fileno())
        atomic_json(root/'rollback_before.json',current);atomic_json(root/'rollback_expected.json',target)
        result={'status':'ROLLBACK_MATCHED','site_save_calls':0,'upload_calls':0,'translate_calls':0,'status_calls':0,'publish_calls':0,'content_status':'RESTORED_ORIGINAL_NOT_REAUDITED'}
        try:
            fresh=writer.product(job['pid']);ExecutorService(None,writer,root)._identity(fresh,plan)
            if canonical_state_hash(fresh)!=preview['precondition_state_sha256']:raise ValueError('STATE_DRIFT_BEFORE_ROLLBACK_SAVE')
            if canonical_state_hash(current)!=canonical_state_hash(target):
                result['site_save_calls']=1
                writer.save(job['pid'],deepcopy(target),expected_state_sha256=preview['precondition_state_sha256'])
            observed=writer.product(job['pid']);ExecutorService(None,writer,root)._identity(observed,plan)
            if canonical_state_hash(observed)!=canonical_state_hash(target):raise ValueError('ROLLBACK_READBACK_MISMATCH')
            if current.get('titleEn')!=target.get('titleEn'):
                try:
                    result['translate_calls']=1;writer.translate(job['pid'],target.get('titleEn',''))
                    observed=writer.product(job['pid']);ExecutorService(None,writer,root)._identity(observed,plan)
                    expected=deepcopy(target);expected['titleTranslationZh']=observed.get('titleTranslationZh')
                    if not observed.get('titleTranslationZh') or canonical_state_hash(observed)!=canonical_state_hash(expected):raise ValueError('ROLLBACK_TRANSLATION_READBACK_FAILED')
                except Exception as exc:result.update(status='TRANSLATION_PENDING',translation_error=type(exc).__name__)
            atomic_json(root/'rollback_after.json',observed)
            atomic_json(journal,dict(result,preview_sha256=preview['preview_sha256'],state=result['status']))
            atomic_json(root/'rollback_receipt.json',result)
            return result
        except Exception as exc:
            atomic_json(journal,{'preview_sha256':preview['preview_sha256'],'state':'APPLY_UNKNOWN','error':type(exc).__name__,'retry_save_allowed':False})
            raise

def rollback_readback(directory,reader):
    root=Path(directory);job,plan,before,after,changed=_source(root)
    expected=json.loads((root/'rollback_expected.json').read_text(encoding='utf-8'))
    with account_lock(account_key(reader,root.parent)):
        current=reader.product(job['pid']);ExecutorService(None,reader,root)._identity(current,plan)
        if expected.get('titleEn')!=after.get('titleEn'):expected['titleTranslationZh']=current.get('titleTranslationZh')
        result={'read_only':True,'write_outcome':'MATCHED' if canonical_state_hash(current)==canonical_state_hash(expected) else 'DRIFT_OR_NOT_OBSERVED','retry_save_allowed':False,'site_save_calls':0,'upload_calls':0,'status_calls':0}
        atomic_json(root/'rollback_readback.json',result)
        return result
