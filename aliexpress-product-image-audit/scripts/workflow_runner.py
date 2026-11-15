"""v2 read-only workflow. Unresolved judgement always stops for review."""
import argparse
import os
import json
from pathlib import Path
from job_manager import JobManager, atomic_json

BUDGET_CONFIG = json.loads((Path(__file__).parent / 'config' / 'budget.v2.json').read_text(encoding='utf-8-sig'))
def configured_limits(config):
    limits = dict(config['limits'])
    token_limit = config.get('token_limit')
    if token_limit is not None:
        if type(token_limit) is not int or token_limit <= 0:
            raise ValueError('positive token_limit required')
        limits['total_tokens'] = token_limit
    return limits

LIMITS = configured_limits(BUDGET_CONFIG)

def resume_verification(manager,job_id,reader,quality_gate=None):
    """Re-read and recheck a saved job. Never upload, save or translate."""
    from executor.local import LocalExecutor
    from account_coordination import account_lock,account_key
    from auto_workflow import verify_content,report
    from candidate_quality import CandidateQualityGate
    from execution_ledger import ExecutionLedger
    import time,uuid
    started=time.perf_counter()
    root=manager.directory(job_id);job=manager.load(job_id)
    plan=json.loads((root/'plan.v2.json').read_text(encoding='utf-8'))
    if (plan['job_id'],plan['pid'],plan['shop'])!=(job_id,job['pid'],job['shop_id']):raise ValueError('RECOVERY_BINDING_MISMATCH')
    owned=None;account=account_key(reader,manager.root)
    with account_lock(account):
        observed=LocalExecutor(reader,root).recover_readback(plan)
        if observed['write_outcome']!='MATCHED':return observed
        try:
            if quality_gate is None:
                from visual_quality import VisualQualityInspector
                owned=VisualQualityInspector(root,job);quality_gate=CandidateQualityGate(owned)
            checked=verify_content(root,plan,reader,quality_gate)
            compiled=json.loads((root/'compiled_plan.json').read_text(encoding='utf-8'))
            status=('PARTIALLY_AUTO_FIXED' if compiled.get('deferred_count') else 'AUTO_VERIFIED') if checked['ok'] else 'CONTENT_REVIEW_REQUIRED'
            if (root/'translation_pending.json').exists():
                retried=json.loads((root/'translation_retry.json').read_text(encoding='utf-8')) if (root/'translation_retry.json').exists() else {}
                if checked['ok'] and retried.get('translation_status')!='TRANSLATED':status='TRANSLATION_PENDING'
            result=dict(observed,status=status,content_validation=checked)
            result.update(run_id=uuid.uuid4().hex,total_elapsed_ms=round((time.perf_counter()-started)*1000,3))
            manager.finish_automatic(job_id,status);report(root,job,status,result,writer=reader,inspector=quality_gate.inspector)
            ledger=ExecutionLedger()
            try:ledger.finish(account,job['shop_id'],job['pid'],job_id,status)
            finally:ledger.close()
            return result
        finally:
            if owned:owned.close()

def run_automatic(manager,job,policy,*,writer=None,auditor=None,judge=None,quality_gate=None,full_audit_reader=None):
    """Account-serialized execution, using local preauthorization instead of review clicks."""
    from auto_workflow import prepare,verify_content,report
    from candidate_quality import CandidateQualityGate
    from executor.local import LocalExecutor
    import time,uuid
    started=time.perf_counter();run_id=uuid.uuid4().hex
    policy.authorize(job['pid'],job['shop_id'],[],execution=job['mode']=='auto_apply')
    root=manager.directory(job['job_id'])
    def observed_account(client):
        try:return client.account_fingerprint()
        except ValueError as exc:
            if job['mode']=='audit' and str(exc)=='ACCOUNT_PRINCIPAL_UNVERIFIED':return None
            raise
    def emit(status,result):
        result.update(run_id=run_id,total_elapsed_ms=round((time.perf_counter()-started)*1000,3))
        return report(root,job,status,result,writer=writer,inspector=quality_gate.inspector if quality_gate else None)
    if manager.load(job['job_id'])!=job:raise ValueError('job binding mismatch')
    use_full_audit=auditor is None or full_audit_reader is not None
    if auditor is None:
        if writer is None:
            from site_client import ReadOnlySiteClient
            config_path=os.environ.get('AE_READONLY_SITE_CFG')
            if not config_path:raise ValueError('EXPLICIT_SITE_CONFIG_REQUIRED')
            writer=ReadOnlySiteClient(json.loads(Path(config_path).read_text(encoding='utf-8-sig')))
        readonly=getattr(writer,'readonly_client',None)
        if not callable(readonly):raise ValueError('EXPLICIT_READONLY_CLIENT_REQUIRED')
        audit_reader=readonly()
        full_audit_reader=audit_reader
        from audit_one import audit
        if job.get('image_workflow')=='v2':
            from full_product_audit import download_only as audit
        def auditor(pid,shop,output_dir):
            before=observed_account(audit_reader)
            if before!=observed_account(writer):raise ValueError('ACCOUNT_MISMATCH')
            result=audit(pid,shop,output_dir=output_dir,site=audit_reader)
            if observed_account(audit_reader)!=before:raise ValueError('ACCOUNT_CONTEXT_CHANGED')
            atomic_json(Path(output_dir)/'audit_account.json',{'account_fingerprint':before,'status':'VERIFIED' if before else 'UNVERIFIED'})
            return result
    previous=json.loads((root/'state.json').read_text(encoding='utf-8'))['state']
    completed={'CLEAN','DEFERRED','PREWRITE_FAILED','BLOCKED_FATAL','AUTO_VERIFIED','PARTIALLY_AUTO_FIXED','TRANSLATION_PENDING','CONTENT_REVIEW_REQUIRED'}
    if previous in completed:
        result_path=root/'automatic_result.json'
        if not result_path.exists():raise ValueError('AUTOMATIC_RESULT_MISSING')
        return json.loads(result_path.read_text(encoding='utf-8'))
    if previous=='APPLY_UNKNOWN' or (root/'local_execution.json').exists():
        if writer is not None and (root/'local_execution.json').exists():
            plan=json.loads((root/'plan.v2.json').read_text(encoding='utf-8'))
            return LocalExecutor(writer,root).recover_readback(plan)
        return {'status':'APPLY_UNKNOWN','job_id':job['job_id'],'read_only_recovery_required':True,'retry_save_allowed':False}
    owned_inspector=None
    from account_coordination import account_lock,account_key
    has_account_probe=callable(getattr(type(writer),'account_fingerprint',None))
    bound_account=observed_account(writer) if has_account_probe else None
    account=bound_account if bound_account else 'readonly-unverified:'+str(getattr(writer,'coordination_key',manager.root)) if has_account_probe else account_key(writer,manager.root)
    ledger=None
    with account_lock(account):
        try:
            if has_account_probe:
                if observed_account(writer)!=bound_account:raise ValueError('ACCOUNT_CONTEXT_CHANGED')
                if bound_account:job=manager.bind_account(job['job_id'],bound_account)
            if use_full_audit:
                from full_product_audit import run_full_audit
                # The existing full-audit implementation owns this same Job's
                # machine/semantic stages; no narrower second model queue.
                if not (root/'full_audit_report.json').exists():
                    def full_machine(pid,shop,output_dir,site):
                        if full_audit_reader is not None and auditor is not None:
                            # Explicit injected full-audit fixtures support site=.
                            import inspect
                            if 'site' in inspect.signature(auditor).parameters:
                                return auditor(pid,shop,output_dir=output_dir,site=site)
                        return auditor(pid,shop,output_dir=output_dir)
                    run_full_audit(manager.root,job['pid'],job['shop_id'],full_audit_reader,
                                   manager=manager,job=job,auditor=full_machine,judge=judge)
            else:run(manager,job,auditor=auditor,judge=judge)
            job=manager.load(job['job_id'])
            if quality_gate is None:
                from visual_quality import VisualQualityInspector
                owned_inspector=VisualQualityInspector(root,job)
                quality_gate=CandidateQualityGate(owned_inspector)
            phase=time.perf_counter();compiled=prepare(root,job,policy,quality_gate)
            update_metrics(root,'remedy_plan_ms',round((time.perf_counter()-phase)*1000,3))
            status=compiled['status']; result=compiled
            if not compiled['ok'] or compiled['read_only']:
                if status=='CLEAN' and job.get('image_workflow')!='v2':
                    from audit_coverage import complete_readonly
                    content=complete_readonly(root,job,writer)
                    result.update(site_save_calls=0,upload_calls=0,translate_calls=0,status_calls=0,verification_ok=True,content_validation=content)
                manager.finish_automatic(job['job_id'],status)
                emit(status,result)
                return dict(result,status=status)
            manager.automatic_plan_ready(job['job_id'],compiled)
            if job['mode']=='audit':
                emit(status,result)
                return result
            if writer is None: raise ValueError('EXPLICIT_WRITER_REQUIRED')
            dry=live_dry_run(manager,job['job_id'],writer)
            if job['mode']=='dry_run':
                emit('DRY_RUN_PASSED',dry)
                return dict(dry,status='DRY_RUN_PASSED')
            atomic_json(root/'auto_authorization.json',{'policy_sha256':policy.sha256,'plan_sha256':dry['plan_sha256'],'job_id':job['job_id'],'pid':job['pid'],'shop':job['shop_id']})
            plan=json.loads((root/'plan.v2.json').read_text(encoding='utf-8'))
            from execution_ledger import ExecutionLedger,operation_digest
            ledger=ExecutionLedger()
            reservation=ledger.claim(account,job['shop_id'],job['pid'],job['job_id'],plan['precondition']['state_sha256'],operation_digest(plan))
            atomic_json(root/'execution_reservation.json',reservation)
            if not reservation['ok']:
                status=reservation['status']
                manager.finish_automatic(job['job_id'],status);emit(status,reservation)
                return reservation
            def before_remote_write():ledger.begin_side_effect(account,job['shop_id'],job['pid'],job['job_id'])
            phase=time.perf_counter();result=LocalExecutor(writer,root,before_remote_write=before_remote_write).execute_auto(plan,policy)
            update_metrics(root,'apply_ms',round((time.perf_counter()-phase)*1000,3))
            phase=time.perf_counter();checked=verify_content(root,plan,writer,quality_gate or CandidateQualityGate())
            update_metrics(root,'verify_ms',round((time.perf_counter()-phase)*1000,3))
            status=('PARTIALLY_AUTO_FIXED' if compiled['deferred_count'] else 'AUTO_VERIFIED') if checked['ok'] else 'CONTENT_REVIEW_REQUIRED'
            if checked['ok'] and result.get('translation_status')=='TRANSLATION_PENDING':status='TRANSLATION_PENDING'
            ledger.finish(account,job['shop_id'],job['pid'],job['job_id'],status)
            result.update(status=status,content_validation=checked)
            manager.finish_automatic(job['job_id'],status)
            emit(status,result)
            return result
        except Exception as exc:
            ledger_state=ledger.state(account,job['shop_id'],job['pid'],job['job_id']) if ledger else None
            if ledger_state=='RESERVED':
                ledger.prewrite_failed(account,job['shop_id'],job['pid'],job['job_id'])
                status='PREWRITE_FAILED'
            else:
                journal=json.loads((root/'local_execution.json').read_text(encoding='utf-8')) if (root/'local_execution.json').exists() else {}
                status='APPLY_UNKNOWN' if ledger_state=='APPLY_UNKNOWN' or journal.get('state')=='APPLY_UNKNOWN' else 'PREWRITE_FAILED' if journal.get('state')=='PREWRITE_FAILED' else 'FAILED'
            if status!='FAILED':manager.finish_automatic(job['job_id'],status)
            emit(status,{'ok':False,'error':type(exc).__name__+': '+str(exc)})
            raise
        finally:
            if ledger:ledger.close()
            if owned_inspector: owned_inspector.close()

def run(manager, job, auditor=None, judge=None):
    if auditor is None:
        from audit_one import audit
        auditor = audit
    if manager.load(job['job_id']) != job:
        raise ValueError('job binding mismatch')
    directory = manager.directory(job['job_id'])
    checkpoint = json.loads((directory / 'state.json').read_text(encoding='utf-8'))['state']
    if checkpoint in {'PLAN_READY','VALIDATED','DRY_RUN_PASSED','NEEDS_REVIEW','STRUCTURE_CHECKED','CONTENT_REVIEWED','VERIFIED'}:
        return json.loads((directory / 'review.json').read_text(encoding='utf-8'))
    lock = manager.root / ('pid_' + str(job['pid']) + '.lock')
    with lock.open('x') as handle:
        json.dump({'job_id':job['job_id'], 'pid':os.getpid()}, handle)
        handle.flush()
        os.fsync(handle.fileno())
        try:
            state = json.loads((directory / 'state.json').read_text())['state']
            if state == 'CREATED':
                manager.transition(job['job_id'], 'PREFLIGHT')
                state = 'PREFLIGHT'
            if state == 'PREFLIGHT':
                auditor(job['pid'], job['shop_id'], output_dir=directory)
                manager.transition(job['job_id'], 'AUDITED')
                state = 'AUDITED'
            if state == 'AUDITED':
                manager.transition(job['job_id'], 'AI_PENDING')
            elif state != 'AI_PENDING':
                raise ValueError('unsupported checkpoint')
            product_path = directory / 'audit_product.json'
            if job.get('account_fingerprint'):
                account_path=directory/'audit_account.json'
                if not account_path.exists():raise ValueError('AUDIT_ACCOUNT_UNVERIFIED')
                observed_account=json.loads(account_path.read_text(encoding='utf-8')).get('account_fingerprint')
                if observed_account!=job['account_fingerprint']:raise ValueError('ACCOUNT_MISMATCH')
            if product_path.exists():
                job = manager.bind_input(job['job_id'], json.loads(product_path.read_text(encoding='utf-8')))
            from workflow_v2_pipeline import pipeline
            review = pipeline(directory, job, judge=judge)
            atomic_json(directory / 'review.json', review)
            if review.get('plan_validation', {}).get('ok'):
                for target in ('AI_RESOLVED','PLAN_READY'):
                    manager.transition(job['job_id'], target)
            else:
                manager.transition(job['job_id'], 'NEEDS_REVIEW')
        except Exception:
            state = json.loads((directory / 'state.json').read_text(encoding='utf-8'))['state']
            if state not in {'NEEDS_REVIEW', 'FAILED'}:
                manager.transition(job['job_id'], 'FAILED')
            raise
        finally:
            handle.close()
            lock.unlink(missing_ok=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).parent / 'work' / 'v2')
    sub = parser.add_subparsers(dest='command', required=True)
    full=sub.add_parser('full-audit',help='Read-only semantic audit of every image and SKU reference')
    full.add_argument('--pid',type=int,required=True)
    full.add_argument('--shop',type=int,required=True)
    full.add_argument('--site-config',type=Path,required=True)
    full.add_argument('--model-config',type=Path,required=True)
    full.add_argument('--template-config',type=Path,help='Template configuration for explicit legacy audits')
    full.add_argument('--image-workflow',choices=['v2','legacy'],default='v2')
    full.add_argument('--image-options',type=Path)
    start = sub.add_parser('run')
    selection=start.add_mutually_exclusive_group(required=True)
    selection.add_argument('--pid', type=int)
    selection.add_argument('--batch',help='Comma-separated PID list')
    selection.add_argument('--pending',type=int,help='Read-only selection of pending products')
    start.add_argument('--shop', type=int, required=True)
    start.add_argument('--mode', choices=['read_only','audit','dry_run','apply','auto_apply'], default='audit')
    start.add_argument('--model-budget-config',type=Path,help='Explicit new-Job read-only model budget; disabled by default')
    full.add_argument('--model-budget-config',type=Path)
    start.add_argument('--automation-config',type=Path,default=Path('local/automation.v1.json'))
    start.add_argument('--site-config',type=Path)
    start.add_argument('--template-config',type=Path,help='Explicit template applicability and template paths')
    start.add_argument('--model-config',type=Path,help='Secret-free gateway/model/output profile, frozen into this Job')
    start.add_argument('--image-workflow',choices=['v2','legacy'],default='v2',help='V2 unified vision strategy; legacy only for explicit compatibility')
    start.add_argument('--image-options',type=Path,help='Program rights, mask limit and optional local LaMa model')
    apply_parser=sub.add_parser('apply')
    apply_parser.add_argument('--job',required=True)
    apply_parser.add_argument('--site-config',type=Path,required=True)
    apply_parser.add_argument('--confirmation',type=Path,required=True)
    live_parser=sub.add_parser('live-dry-run')
    live_parser.add_argument('--job',required=True)
    live_parser.add_argument('--site-config',type=Path,required=True)
    recovery_parser=sub.add_parser('recover-readback')
    recovery_parser.add_argument('--job',required=True)
    recovery_parser.add_argument('--site-config',type=Path,required=True)
    verify_parser=sub.add_parser('verify-saved')
    verify_parser.add_argument('--job',required=True)
    verify_parser.add_argument('--site-config',type=Path,required=True)
    retry_parser=sub.add_parser('retry-translation')
    retry_parser.add_argument('--job',required=True)
    retry_parser.add_argument('--site-config',type=Path,required=True)
    retry_parser.add_argument('--automation-config',type=Path,required=True)
    for rollback_command in ('rollback-preview','rollback-apply','rollback-readback'):
        child=sub.add_parser(rollback_command)
        child.add_argument('--job',required=True);child.add_argument('--site-config',type=Path,required=True)
        if rollback_command=='rollback-apply':child.add_argument('--confirmation',type=Path,required=True)
    review_parser=sub.add_parser('review-submit')
    review_parser.add_argument('--job',required=True)
    review_parser.add_argument('--review',type=Path,required=True)
    for name in ['status', 'resume','report']:
        child = sub.add_parser(name)
        child.add_argument('--job', required=True)
    execute = sub.add_parser('executor-request')
    execute.add_argument('--job', required=True)
    execute.add_argument('--address', required=True)
    execute.add_argument('--expected-server-sid', required=True)
    execute.add_argument('--request', required=True, type=Path)
    for child in sub.choices.values():
        child.add_argument('--root',type=Path,default=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.command=='full-audit':
        from model_config import load_config
        from site_client import ReadOnlySiteClient
        from full_product_audit import run_full_audit
        profile=load_config(args.model_config)
        reader=ReadOnlySiteClient(json.loads(args.site_config.read_text(encoding='utf-8-sig')))
        options={'model_budget':json.loads(args.model_budget_config.read_text(encoding='utf-8-sig'))} if args.model_budget_config else {'model_budget':{'mode':'RECORD_ONLY','usage_source':'GATEWAY_REPORTED_UNVERIFIED'}}
        if args.image_workflow=='v2':options.update(image_workflow='v2',image_options=json.loads(args.image_options.read_text(encoding='utf-8-sig')) if args.image_options else None)
        result=run_full_audit(args.root,args.pid,args.shop,reader,model_config=profile,template_config=args.template_config,**options)
        print(json.dumps({key:result.get(key) for key in ('job_id','audit_complete','audit_status','compliance_status','unresolved_count')},ensure_ascii=False))
        return
    if args.command == 'executor-request':
        from executor.ipc import request
        from plan_v2 import plan_hash
        manager=JobManager(args.root)
        job=manager.load(args.job); directory=manager.directory(args.job)
        plan=json.loads((directory/'plan.v2.json').read_text(encoding='utf-8'))
        body=json.loads(args.request.read_text(encoding='utf-8-sig'))
        if body.get('plan')!=plan or body.get('dry_run') is not False:
            raise ValueError('request must bind current plan and explicit apply')
        state=json.loads((directory/'state.json').read_text(encoding='utf-8'))['state']
        dry=json.loads((directory/'dry_run.json').read_text(encoding='utf-8'))
        if state!='DRY_RUN_PASSED' or not dry.get('live') or dry.get('plan_sha256')!=plan_hash(plan):
            raise ValueError('live dry run required')
        response=request(args.address,body,expected_server_sid=args.expected_server_sid)
        atomic_json(directory/'executor_response.json',response)
        if not response.get('ok'):
            manager.transition(args.job,'FAILED')
            raise SystemExit(1)
        receipt=dict(response['result'],ok=True)
        record_executor_receipt(manager,args.job,receipt)
        print(json.dumps(receipt))
        return
    manager = JobManager(args.root)
    if args.command in {'rollback-preview','rollback-apply','rollback-readback'}:
        from controlled_rollback import prepare_rollback,apply_rollback,rollback_readback
        root=manager.directory(args.job);manager.load(args.job)
        config=json.loads(args.site_config.read_text(encoding='utf-8-sig'))
        if args.command=='rollback-apply':
            from site_client import _SiteTransport
            from executor.site_write_client import SiteWriteClient
            writer=SiteWriteClient(_SiteTransport(cfg=config,verify_tls=True))
            result=apply_rollback(root,writer,json.loads(args.confirmation.read_text(encoding='utf-8-sig')))
        else:
            from site_client import ReadOnlySiteClient
            reader=ReadOnlySiteClient(config)
            result=prepare_rollback(root,reader) if args.command=='rollback-preview' else rollback_readback(root,reader)
        print(json.dumps(result,ensure_ascii=False));return
    if args.command=='verify-saved':
        from site_client import ReadOnlySiteClient
        reader=ReadOnlySiteClient(json.loads(args.site_config.read_text(encoding='utf-8-sig')))
        print(json.dumps(resume_verification(manager,args.job,reader),ensure_ascii=False));return
    if args.command=='retry-translation':
        from automation_policy import AutomationPolicy
        from executor.local import LocalExecutor
        from executor.site_write_client import SiteWriteClient
        from site_client import _SiteTransport
        policy=AutomationPolicy.load(args.automation_config);job=manager.load(args.job);root=manager.directory(args.job)
        plan=json.loads((root/'plan.v2.json').read_text(encoding='utf-8'))
        if (plan['job_id'],plan['pid'],plan['shop'])!=(job['job_id'],job['pid'],job['shop_id']):raise ValueError('RECOVERY_BINDING_MISMATCH')
        writer=SiteWriteClient(_SiteTransport(cfg=json.loads(args.site_config.read_text(encoding='utf-8-sig')),verify_tls=True))
        result=LocalExecutor(writer,root).retry_translation(plan,policy)
        if result['translation_status']=='TRANSLATED':result=resume_verification(manager,args.job,writer)
        print(json.dumps(result,ensure_ascii=False));return
    if args.command=='recover-readback':
        from executor.local import LocalExecutor
        from site_client import ReadOnlySiteClient
        job=manager.load(args.job);root=manager.directory(args.job)
        plan=json.loads((root/'plan.v2.json').read_text(encoding='utf-8'))
        if (plan['job_id'],plan['pid'],plan['shop'])!=(job['job_id'],job['pid'],job['shop_id']):raise ValueError('RECOVERY_BINDING_MISMATCH')
        reader=ReadOnlySiteClient(json.loads(args.site_config.read_text(encoding='utf-8-sig')))
        print(json.dumps(LocalExecutor(reader,root).recover_readback(plan),ensure_ascii=False))
        return
    if args.command == 'apply':
        from site_client import _SiteTransport
        from executor.site_write_client import SiteWriteClient
        confirmation=json.loads(args.confirmation.read_text(encoding='utf-8-sig'))
        writer=SiteWriteClient(_SiteTransport(cfg=json.loads(args.site_config.read_text(encoding='utf-8-sig')),verify_tls=True))
        print(json.dumps(local_apply(manager,args.job,writer,confirmation)))
        return
    if args.command == 'live-dry-run':
        from site_client import ReadOnlySiteClient
        reader=ReadOnlySiteClient(json.loads(args.site_config.read_text(encoding='utf-8-sig')))
        print(json.dumps(live_dry_run(manager,args.job,reader)))
        return
    if args.command == 'review-submit':
        from manual_review import submit
        print(json.dumps(submit(manager,args.job,json.loads(args.review.read_text(encoding='utf-8-sig')))))
        return
    if args.command == 'run':
        model_options={}
        if args.model_config:
            from model_config import load_config
            model_options['model_config']=load_config(args.model_config)
        model_options['model_budget']=json.loads(args.model_budget_config.read_text(encoding='utf-8-sig')) if args.model_budget_config else {'mode':'RECORD_ONLY','usage_source':'GATEWAY_REPORTED_UNVERIFIED'}
        limits=dict(LIMITS)
        pids=[args.pid] if args.pid is not None else [int(v.strip()) for v in args.batch.split(',')] if args.batch else []
        if args.pending is not None:
            if args.pending<=0 or args.site_config is None:raise ValueError('positive --pending and --site-config required')
            from site_client import ReadOnlySiteClient
            reader=ReadOnlySiteClient(json.loads(args.site_config.read_text(encoding='utf-8-sig')))
            pids=select_pending_products(reader,args.shop,args.pending)
            if not pids:print(json.dumps({'status':'NO_PRODUCTS','read_only':True}));return
        if args.mode in {'audit','dry_run','auto_apply'}:
            from automation_policy import AutomationPolicy
            policy_path=args.automation_config
            if args.mode!='auto_apply' and not policy_path.exists():
                policy_path=Path(__file__).parent/'config'/('automation.v2.example.json' if args.image_workflow=='v2' else 'automation.v1.example.json')
            policy=AutomationPolicy.load(policy_path)
            for pid in pids:policy.authorize(pid,args.shop,[],product_count=len(pids),execution=args.mode=='auto_apply')
            limits['ai_requests']=min(limits.get('ai_requests',45),policy.config['max_ai_requests_per_job'])
        if args.mode in {'audit','dry_run','auto_apply'}:
            transport=None;reader=None
            if args.mode in {'audit','dry_run','auto_apply'}:
                config_path=args.site_config
                if config_path is None and args.mode=='audit' and os.environ.get('AE_READONLY_SITE_CFG'):config_path=Path(os.environ['AE_READONLY_SITE_CFG'])
                if config_path is None:raise ValueError('--site-config required for a bound account session')
                config=json.loads(config_path.read_text(encoding='utf-8-sig'))
                if args.mode in {'audit','dry_run'}:
                    from site_client import ReadOnlySiteClient
                    reader=ReadOnlySiteClient(config)
                else:
                    from site_client import _SiteTransport
                    from executor.site_write_client import SiteWriteClient
                    transport=_SiteTransport(cfg=config,verify_tls=True)
            def run_one(pid,shop):
                writer=SiteWriteClient(transport) if transport is not None else reader
                image_options=json.loads(args.image_options.read_text(encoding='utf-8-sig')) if args.image_options else None
                image_kwargs={'image_workflow':'v2','image_options':image_options} if args.image_workflow=='v2' else {}
                job=manager.create(pid,shop,limits,args.mode,templates_required=args.image_workflow=='legacy',**model_options,**image_kwargs)
                if args.template_config:
                    from template_applicability import snapshot
                    snapshot(args.template_config,manager.directory(job['job_id']))
                print(job['job_id'],flush=True)
                return run_automatic(manager,job,policy,writer=writer)
            if len(pids)>1:
                from batch_scheduler import run_batch
                result=run_batch(pids,args.shop,policy,run_one,execution=args.mode=='auto_apply')
                atomic_json(manager.root/'batch_report.json',result)
            else:result=run_one(pids[0],args.shop)
            print(json.dumps(result,ensure_ascii=False))
        else:
            if len(pids)!=1:raise ValueError('batch requires audit/dry_run/auto_apply')
            job=manager.create(pids[0],args.shop,limits,args.mode,templates_required=True,**model_options)
            print(job['job_id'],flush=True);run(manager,job)
    else:
        directory = manager.directory(args.job)
        if args.command=='report':
            print((directory/'report.md').read_text(encoding='utf-8'))
            return
        state = json.loads((directory / 'state.json').read_text(encoding='utf-8'))
        if args.command == 'resume':
            manager.recover(args.job)
            run(manager, manager.load(args.job))
            return
        print(json.dumps(state))






def select_pending_products(reader, shop, count):
    """Select pending IDs using a read bracketed by current-shop checks."""
    if type(count) is not int or count <= 0:
        raise ValueError('positive pending count required')
    if str(reader.current_shop()) != str(shop):
        raise ValueError('SHOP_MISMATCH')
    data = reader.call('/api/admin/products?status=PENDING&size='+str(count)+'&page=1')
    if str(reader.current_shop()) != str(shop):
        raise ValueError('SHOP_MISMATCH')
    rows = data['data']['items']
    if any(row.get('status') != 'PENDING' for row in rows):
        raise ValueError('PENDING_STATUS_MISMATCH')
    return [int(row['id']) for row in rows][:count]


def live_dry_run(manager,job_id,reader):
    """Read current state under an injected read-only client; never mutate shop."""
    import time
    started=time.perf_counter()
    from plan_v2 import validate_plan,plan_hash
    from product_state import canonical_state_hash
    from executor.service import ExecutorService
    job=manager.load(job_id); root=manager.directory(job_id)
    plan=validate_plan(json.loads((root/'plan.v2.json').read_text(encoding='utf-8')))
    if (plan['job_id'],plan['pid'],plan['shop']) != (job_id,job['pid'],job['shop_id']):
        raise ValueError('plan binding mismatch')
    compiled=json.loads((root/'compiled_plan.json').read_text(encoding='utf-8'))
    if compiled.get('plan_sha256')!=plan_hash(plan): raise ValueError('plan hash changed')
    state=json.loads((root/'state.json').read_text(encoding='utf-8'))['state']
    if state not in {'PLAN_READY','VALIDATED'}: raise ValueError('plan not ready')
    ExecutorService(None,None,root).execute(plan,dry_run=True)
    current=reader.product(job['pid'])
    if plan['desired'] or plan['post_actions'] or plan['schema']=='token-opt-plan/v3':
        ExecutorService(None,reader,root)._identity(current,plan)
    if canonical_state_hash(current)!=plan['precondition']['state_sha256']:
        manager.transition(job_id,'STATE_DRIFT'); raise ValueError('STATE_DRIFT')
    from copy import deepcopy
    from product_state import diff_state
    from final_state import simulate_final_snapshot, pre_apply_validate,upload_placeholders
    uploads=(plan.get('post_actions') or {}).get('uploads',[])
    validation=pre_apply_validate(current,plan)
    # Legacy no-op previews can inspect incomplete snapshots, but never write them.
    if (plan['desired'] or uploads) and not validation['ok']:
        raise ValueError('PRE_APPLY_VALIDATION: '+repr(validation['errors']))
    desired=simulate_final_snapshot(current,plan,upload_placeholders(plan,'UPLOAD_TOKEN:ASSET_'))
    changes=diff_state(current,desired)
    result={'changes':changes,'ok':True,'live':True,'plan_sha256':plan_hash(plan),'site_get_calls':1,'site_save_calls':0,'upload_calls':0}
    if job.get('account_fingerprint'):
        if plan['precondition'].get('account_fingerprint')!=job['account_fingerprint']:raise ValueError('ACCOUNT_BINDING_MISMATCH')
        result['account_fingerprint']=job['account_fingerprint']
    from plan_v2 import planned_upload_count
    result.update(planned_upload_count=planned_upload_count(plan),status_calls=0,read_only=True,validation=validation)
    result['elapsed_ms']=round((time.perf_counter()-started)*1000,3)
    atomic_json(root/'dry_run.json',result)
    atomic_json(root/'live_dry_run_report.json',result)
    update_metrics(root,'dry_run_ms',result['elapsed_ms'])
    if state=='PLAN_READY': manager.transition(job_id,'VALIDATED')
    manager.transition(job_id,'DRY_RUN_PASSED')
    return result


def local_apply(manager, job_id, writer, confirmation):
    """Explicit local confirmation follows a fresh read-only comparison."""
    from executor.local import LocalExecutor
    from plan_v2 import plan_hash
    root=manager.directory(job_id); job=manager.load(job_id)
    plan=json.loads((root/'plan.v2.json').read_text(encoding='utf-8'))
    state=json.loads((root/'state.json').read_text(encoding='utf-8'))['state']
    dry=json.loads((root/'dry_run.json').read_text(encoding='utf-8'))
    if state != 'DRY_RUN_PASSED' or not dry.get('live') or dry.get('plan_sha256')!=plan_hash(plan):
        raise ValueError('live dry run required')
    if (plan['job_id'],plan['pid'],plan['shop'])!=(job_id,job['pid'],job['shop_id']):
        raise ValueError('plan binding mismatch')
    receipt=LocalExecutor(writer,root).execute(plan,confirmation,dry_run=False)
    receipt=dict(receipt,job_id=job_id,plan_sha256=plan_hash(plan),ok=True)
    atomic_json(root/'apply_receipt.json',receipt)
    return record_executor_receipt(manager,job_id,receipt)


def record_executor_receipt(manager,job_id,receipt):
    """Called only with an identity-verified IPC response, never a user JSON file."""
    from plan_v2 import plan_hash
    job=manager.load(job_id); root=manager.directory(job_id)
    plan=json.loads((root/'plan.v2.json').read_text(encoding='utf-8'))
    if receipt.get('plan_sha256')!=plan_hash(plan) or receipt.get('job_id')!=job_id:
        raise ValueError('receipt binding mismatch')
    if receipt.get('dry_run') is not False or not receipt.get('ok') or receipt.get('verification_ok') is not True:
        raise ValueError('execution not verified')
    state=json.loads((root/'state.json').read_text(encoding='utf-8'))['state']
    if state!='DRY_RUN_PASSED': raise ValueError('live dry run required')
    dry=json.loads((root/'dry_run.json').read_text(encoding='utf-8'))
    if not dry.get('live') or dry.get('plan_sha256')!=plan_hash(plan): raise ValueError('stale dry run')
    atomic_json(root/'executor_receipt.json',receipt)
    update_metrics(root,'apply_ms',receipt.get('elapsed_ms'),receipt)
    for target in ('APPLY_AUTHORIZED','APPLIED','APPLY_MATCHED','STRUCTURE_CHECKED'): manager.transition(job_id,target)
    if receipt.get('content_review_status')=='CONTENT_REVIEWED':
        for target in ('CONTENT_REVIEWED','VERIFIED'): manager.transition(job_id,target)
    from render_token_report import render
    (root/'report.md').write_text(render(root,job['pid']),encoding='utf-8')
    return receipt

def update_metrics(root,timing_key,value,receipt=None):
    path=root/'run_metrics.json'
    metrics=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    metrics.setdefault('timing',{})[timing_key]=value
    if receipt:
        metrics.setdefault('executor',{}).update({key:receipt.get(key) for key in ('site_save_calls','upload_calls','verification_ok')})
    atomic_json(path,metrics)

if __name__ == '__main__':
    main()
