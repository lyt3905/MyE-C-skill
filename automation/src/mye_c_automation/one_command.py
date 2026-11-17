"""URL/configuration entry; all business execution belongs to workflow_runner."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from datetime import datetime,timezone
from urllib.parse import urlsplit

from mye_c_automation.job_manager import JobManager, atomic_json
from mye_c_automation.paths import config_root, initialize_data


def _load(path):
    try:return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError,ValueError,TypeError):raise ValueError('CONFIG_FILE_INVALID: '+Path(path).name) from None


def product_id_from_url(url,base):
    try:
        target=urlsplit(url);site=urlsplit(base)
        origin=lambda p:(p.scheme,p.hostname,p.port or 443)
        match=re.fullmatch(r'/products/([1-9][0-9]*)/?',target.path)
        valid=(origin(target)==origin(site) and target.scheme=='https' and target.hostname
               and not any((target.username,target.password,target.query,target.fragment))
               and site.path in ('','/') and match)
        if not valid:raise ValueError()
        return int(match[1])
    except (ValueError,TypeError,AttributeError):raise ValueError('PRODUCT_URL_MUST_MATCH_CONFIGURED_SITE') from None


@contextmanager
def _runtime_environment(directory,root):
    names=('VLM_API_KEY','MYEC_CONFIG_DIR','MYEC_DATA_ROOT')
    before={key:os.environ.get(key) for key in names}
    try:
        if not os.environ.get('VLM_API_KEY'):
            from mye_c_automation.configuration import model_api_key
            key=model_api_key(directory)
            if not isinstance(key,str) or not key.strip():raise ValueError('MODEL_API_KEY_MISSING')
            os.environ['VLM_API_KEY']=key
        os.environ['MYEC_CONFIG_DIR']=str(directory);os.environ['MYEC_DATA_ROOT']=str(root)
        yield
    finally:
        for key,value in before.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value


def _writer(config):
    from mye_c_automation.site_client import _SiteTransport
    from mye_c_automation.executor.site_write_client import SiteWriteClient
    return SiteWriteClient(_SiteTransport(cfg=config,verify_tls=True))


def _reader(config):
    from mye_c_automation.site_client import ReadOnlySiteClient
    return ReadOnlySiteClient(config)


def _scoped_path(directory,pid,name):
    scoped=directory/'products'/str(pid)/name
    return scoped if scoped.exists() else directory/name

def _progress(directory,message):
    with (directory/'process_events.jsonl').open('a',encoding='utf-8') as stream:
        stream.write(json.dumps(dict(at=datetime.now(timezone.utc).isoformat(),message=message),ensure_ascii=False)+'\n')
    print(message,file=sys.stderr,flush=True)


def _summary(directory,job,result,preflight=None):
    deferred=_load(directory/'deferred_items.json')['items'] if (directory/'deferred_items.json').exists() else []
    independent=_load(directory/'independent_verification.json') if (directory/'independent_verification.json').exists() else {}
    models=dict(requests=0,gateway_reported_tokens=None,usage_complete=False)
    db_path=directory/'budget.sqlite'
    if db_path.exists():
        db=sqlite3.connect(db_path)
        try:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='model_calls'").fetchone():
                count,known,total=db.execute('SELECT count(*),count(actual),sum(actual) FROM model_calls').fetchone()
                models=dict(requests=count,gateway_reported_tokens=total if count==known else None,usage_complete=count==known)
        finally:db.close()
    status=result.get('status','REVIEW_REQUIRED')
    from mye_c_automation.title_generation import summary as title_summary
    out=dict(status=status,technical_status=result.get('technical_status',status),job_id=job['job_id'],pid=job['pid'],shop=job['shop_id'],
        read_only=job['mode']=='audit',whole_product_clean=status in {'AUTO_VERIFIED','CLEAN'} and not deferred,
        deferred_count=len(deferred),deferred_items=[dict(target=r.get('target'),reasons=r.get('reason_codes')) for r in deferred],
        site_save_calls=result.get('site_save_calls',0),upload_calls=result.get('upload_calls',0),models=models,title=title_summary(directory),
        independent_verification={k:independent[k] for k in ('ok','description_exact','protected_fields_exact','title_exact','sku_references_exact','evidence_directory') if k in independent},
        report=str(directory/'report.md'),evidence_directory=str(directory),result_path=str(directory/'process_result.json'))
    if preflight:out['main_count_preflight']=preflight
    atomic_json(directory/'process_result.json',out)
    return out


def process_product(url,*,config_dir=None,data_dir=None,shop=None,audit_only=False,resume=None):
    """Run one configured product to a truthful terminal result, without prompts."""
    from mye_c_automation.automation_policy import AutomationPolicy
    from mye_c_automation.configuration import load_image_options
    from mye_c_automation.download_manager import load_download_options
    from mye_c_automation.model_config import load_config
    directory=config_root(config_dir);config=_load(directory/'site.local.json')
    pid=product_id_from_url(url,config.get('base'))
    policy=AutomationPolicy.load(_scoped_path(directory,pid,'automation.local.json'))
    profile=load_config(directory/'model.local.json')
    options=load_image_options(_scoped_path(directory,pid,'image-options.local.json'))
    load_download_options(directory)
    execution=not audit_only
    # Check disabled policies/PID restrictions before creating any network session.
    if execution and not policy.config['enabled']:raise ValueError('AUTO_APPLY_DISABLED')
    if policy.config['pid_allowlist'] and pid not in policy.config['pid_allowlist']:raise ValueError('PID_NOT_AUTHORIZED')
    if shop is not None:policy.authorize(pid,shop,[],execution=execution)
    root=initialize_data(data_dir);manager=JobManager(root/'jobs')
    mode='audit' if audit_only else 'auto_apply'
    if resume:
        job=manager.load(resume);work=manager.directory(resume)
        invocation=_load(work/'process_invocation.json')
        preflight_resume=invocation.get('phase')=='main_count_preflight'
        if (job['pid'],job['mode'])!=(pid,mode) or not preflight_resume and (job.get('model_config'),job.get('image_options'))!=(profile,options):raise ValueError('RESUME_CONFIGURATION_OR_PRODUCT_MISMATCH')
        if shop is not None and job['shop_id']!=shop:raise ValueError('RESUME_SHOP_MISMATCH')
        if invocation['policy_sha256']!=policy.sha256 or invocation['url']!=url:raise ValueError('RESUME_POLICY_OR_URL_MISMATCH')
        if (work/'process_result.json').exists():
            recorded=_load(work/'process_result.json')
            if recorded.get('technical_status') not in {'APPLY_UNKNOWN','CONTENT_REVIEW_REQUIRED','TRANSLATION_PENDING'}:return recorded
    with _runtime_environment(directory,root):
        from mye_c_automation.workflow_runner import run_automatic,run_main_count_preflight,resume_main_count_preflight
        reader=_reader(config);current=reader.current_shop()
        if type(current) is not int or current<=0:raise ValueError('SHOP_CONTEXT_UNVERIFIED')
        if shop is not None and shop!=current:raise ValueError('SHOP_MISMATCH')
        shop=current;policy.authorize(pid,shop,[],execution=execution)
        account=reader.account_fingerprint()
        def independent():return _reader(config)
        preflight=None
        if resume and preflight_resume:
            preflight=resume_main_count_preflight(manager,resume,independent())
            if preflight['status']!='AUTO_VERIFIED':
                return dict(preflight,phase='main_count_preflight',job_id=resume)
            resume=None
        if resume:
            if job.get('account_fingerprint') not in (None,account) or job['shop_id']!=shop:raise ValueError('RESUME_ACCOUNT_MISMATCH')
            if (work/'local_execution.json').exists():
                from mye_c_automation.workflow_runner import resume_verification
                result=resume_verification(manager,resume,reader,independent_reader_factory=independent)
                return _summary(work,job,result)
        else:
            if execution and preflight is None:
                preflight_job=None
                def created(value):
                    nonlocal preflight_job
                    preflight_job=value
                    atomic_json(manager.directory(value['job_id'])/'process_invocation.json',dict(url=url,pid=pid,shop=shop,mode=mode,policy_sha256=policy.sha256,phase='main_count_preflight'))
                    _progress(manager.directory(value['job_id']),'正在处理超过六张主图的预处理；随后继续图片审核。')
                try:preflight=run_main_count_preflight(manager,pid,shop,policy,_writer(config),independent,on_job_created=created)
                except Exception:
                    if preflight_job:
                        path=manager.directory(preflight_job['job_id']);journal=_load(path/'local_execution.json') if (path/'local_execution.json').exists() else {}
                        if journal.get('state')=='APPLY_UNKNOWN':
                            return dict(status='APPLY_UNKNOWN',technical_status='APPLY_UNKNOWN',phase='main_count_preflight',job_id=preflight_job['job_id'],pid=pid,shop=shop,retry_save_allowed=False,evidence_directory=str(path))
                    raise
            limits=dict(ai_requests=policy.config['max_ai_requests_per_job'],full_resolution_images=10000,site_save=1)
            job=manager.create(pid,shop,limits,mode=mode,image_workflow='v2',image_options=options,model_config=profile,
                model_budget=dict(mode='RECORD_ONLY',usage_source='GATEWAY_REPORTED_UNVERIFIED'))
            work=manager.directory(job['job_id'])
            atomic_json(work/'process_invocation.json',dict(url=url,pid=pid,shop=shop,mode=mode,policy_sha256=policy.sha256,
                policy_file=str(policy.path),config_directory=str(directory),main_count_preflight=preflight))
        _progress(work,'正在只读审核商品图片。' if not execution else '正在自动审核、整改并核验商品图片；任务 '+job['job_id'])
        if not execution:
            from mye_c_automation.full_product_audit import run_full_audit
            result=run_full_audit(manager.root,pid,shop,reader,manager=manager,job=job)
            from mye_c_automation.title_generation import prepare_title
            title_rows=prepare_title(work,manager.load(job['job_id']),policy)
            title_review=any(row['action']=='WEB_DEFER' for row in title_rows)
            outcome=dict(status='REVIEW_REQUIRED' if result['unresolved_count'] or title_review else 'AUDITED',audit_status=result['audit_status'],read_only=True)
            if title_rows:
                from mye_c_automation.automatic_report import write
                write(work,manager.load(job['job_id']),outcome['status'],outcome)
            return _summary(work,manager.load(job['job_id']),outcome)
        try:
            result=run_automatic(manager,job,policy,writer=_writer(config),full_audit_reader=reader,independent_reader_factory=independent)
        except Exception:
            if (work/'automatic_result.json').exists():
                return _summary(work,manager.load(job['job_id']),_load(work/'automatic_result.json'),preflight)
            raise
        return _summary(work,manager.load(job['job_id']),result,preflight)
