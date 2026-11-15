"""Explicit observed-token image audit. Strict budget mode is unchanged.

Default: offline preparation. Actual requests require the separate observed
execution switch and a recorded user instruction waiving hard token admission.
No site, writer, recovery, or image-remediation entrypoint is used.
"""
from policy_engine import MODEL_CONFIDENCE_MIN
import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import uuid
import urllib.error

import run_8788_real_validation as rv

MODE = 'OBSERVED_NO_TOKEN_CAP'
JOURNAL_VERSION = 'observed-requests/v1'
GENERATION_OPTIONS = dict(reasoning_effort='low', max_output_tokens=16384)


def body_for(model, item, context, options):
    body,images=rv.request_body(model,item,context,options['max_output_tokens'])
    body['reasoning_effort']=options['reasoning_effort']
    return body,images


class Journal:
    """Durable 24-attempt/no-retry admission, deliberately no token guarantee."""
    def __init__(self, path, job_id, *, create, mode='FAKE'):
        self.path, self.job_id = Path(path), job_id
        if create:
            try:
                with self.path.open('xb'): pass
            except OSError: raise rv.Blocked('JOURNAL_ALREADY_EXISTS') from None
            db = sqlite3.connect(self.path, isolation_level=None)
            try:
                db.execute('PRAGMA synchronous=FULL')
                db.executescript('''
                    CREATE TABLE meta(version TEXT,job_id TEXT,mode TEXT,status TEXT);
                    CREATE TABLE requests(sequence INTEGER PRIMARY KEY,item_id TEXT,model TEXT,sha256 TEXT,
                        status TEXT,raw_usage TEXT,error TEXT,created_at TEXT,completed_at TEXT,
                        UNIQUE(item_id,model));
                ''')
                db.execute('INSERT INTO meta VALUES(?,?,?,?)',(JOURNAL_VERSION,job_id,mode,'READY'))
            finally: db.close()
        with self._transaction() as db: pass

    @contextmanager
    def _transaction(self):
        db = None
        try:
            if not self.path.is_file(): raise rv.Blocked('JOURNAL_MISSING')
            db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
            db.execute('PRAGMA synchronous=FULL'); db.execute('BEGIN IMMEDIATE')
            if db.execute('PRAGMA quick_check').fetchone() != ('ok',): raise rv.Blocked('JOURNAL_CORRUPT')
            meta = db.execute('SELECT version,job_id,mode,status FROM meta').fetchall()
            if len(meta)!=1 or meta[0][:2] != (JOURNAL_VERSION,self.job_id) or meta[0][2] not in ('FAKE',MODE):
                raise rv.Blocked('JOURNAL_SCOPE_MISMATCH')
            yield db
            db.execute('COMMIT')
        except sqlite3.Error:
            if db is not None and db.in_transaction: db.execute('ROLLBACK')
            raise rv.Blocked('JOURNAL_IO_FAILURE') from None
        except BaseException:
            if db is not None and db.in_transaction: db.execute('ROLLBACK')
            raise
        finally:
            if db is not None: db.close()

    def dispatch(self, item_id, model, digest):
        with self._transaction() as db:
            count = db.execute('SELECT count(*) FROM requests').fetchone()[0]
            if count >= 24: raise rv.Blocked('REQUEST_LIMIT')
            if db.execute('SELECT status FROM meta').fetchone()[0] != 'READY': raise rv.Blocked('JOURNAL_STOPPED')
            if db.execute("SELECT 1 FROM requests WHERE status='DISPATCHED'").fetchone():
                raise rv.Blocked('IN_FLIGHT_REQUEST_EXISTS')
            if db.execute('SELECT 1 FROM requests WHERE item_id=? AND model=?',(item_id,model)).fetchone():
                raise rv.Blocked('DUPLICATE_REQUEST_NO_RETRY')
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?,?,?)',
                       (count+1,item_id,model,digest,'DISPATCHED',None,None,rv.datetime.now(timezone.utc).isoformat(),None))
            return count+1

    def complete(self, sequence, status, usage, error, *, stop_on_error=True):
        with self._transaction() as db:
            if status not in ('SUCCESS','ERROR'): raise rv.Blocked('INVALID_REQUEST_STATE')
            changed = db.execute("UPDATE requests SET status=?,raw_usage=?,error=?,completed_at=? WHERE sequence=? AND status='DISPATCHED'",
                (status,json.dumps(usage,ensure_ascii=False,allow_nan=False),error,datetime.now(timezone.utc).isoformat(),sequence))
            if changed.rowcount != 1: raise rv.Blocked('DUPLICATE_COMPLETION')
            if status == 'ERROR' and stop_on_error: db.execute("UPDATE meta SET status='STOPPED'")

    def rows(self):
        with self._transaction() as db:
            rows = db.execute('SELECT * FROM requests ORDER BY sequence').fetchall()
        return [dict(sequence=r[0],item_id=r[1],model=r[2],sha256=r[3],status=r[4],
                     raw_usage=json.loads(r[5]) if r[5] else None,error=r[6],created_at=r[7],completed_at=r[8]) for r in rows]


def prepare(output, *, user_statement='', authorize_real=False, source=rv.DEFAULT_SOURCE, config_path=rv.DEFAULT_CONFIG):
    source = Path(source).resolve()
    output = rv.validate_output(output,source)
    baseline = rv.baseline_check()
    inputs = rv.build_inputs(source)
    config = rv.load_config(config_path)
    if config['base_url']!='http://127.0.0.1:8788/v1' or config['models']!=['deepseek-v4.1-flash','mimo-v2.6-pro'] or config['retries']!=0:
        raise rv.Blocked('MODEL_PROFILE_NOT_APPROVED')
    if authorize_real and not user_statement.strip(): raise rv.Blocked('REAL_AUTHORIZATION_REQUIRED')
    config=dict(config,max_output_tokens=GENERATION_OPTIONS['max_output_tokens'])
    versions = rv.source_versions()
    if (versions['contracts']['watermark']['schema']!='watermark/v3' or
            versions['contracts']['product_identity']['schema']!='product-identity/v3' or
            versions['confidence_min']!=MODEL_CONFIDENCE_MIN or versions['matching']['min_iou']!=.5):
        raise rv.Blocked('CONTRACT_VERSION_MISMATCH')
    output.mkdir(parents=True,exist_ok=True)
    job = output/('OBSERVED_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex)
    job.mkdir(exist_ok=False)
    for name in ('observed-raw','observed-normalized','8788-real-validation-overlay'): (job/name).mkdir()
    plan = []
    for item in inputs['tasks']:
        for model in config['models']:
            body, images = body_for(model,item,inputs['context'],GENERATION_OPTIONS)
            plan.append(dict(item_id=item['id'],task_type=item['task_type'],sha256=item['sha256'],model=model,
                             body_sha256=rv.canonical(body),visual_inputs=images))
    rv.write(job/'inputs.json',inputs); rv.write(job/'model-profile.json',config)
    rv.write(job/'source-versions.json',versions); rv.write(job/'request-plan.json',plan)
    rv.write(job/'generation-options.json',GENERATION_OPTIONS)
    rv.write(job/'observed-authorization.json',dict(mode=MODE,job_id=job.name,real_authorized=authorize_real,
        user_statement=user_statement,max_provider_requests=24,token_cap=None,HARD_CAP_GUARANTEED=False,
        online_writes=False,automatic_remediation=False,inputs_sha256=rv.canonical(inputs),
        config_sha256=rv.fingerprint(config),versions_sha256=rv.canonical(versions),plan_sha256=rv.canonical(plan),
        generation_sha256=rv.canonical(GENERATION_OPTIONS)))
    rv.write(job/'observed-preflight.json',dict(state='OBSERVED_READY_NO_TOKEN_CAP',mode=MODE,
        strict_budget_preflight='PREFLIGHT_BLOCKED',HARD_CAP_GUARANTEED=False,request_limit=24,
        user_waived_token_admission=authorize_real,baseline=baseline,git=rv.git_info(),
        online_writes=0,automatic_remediation=0,source_evidence_files_unchanged=433))
    return job


def _verify(job):
    inputs = rv.read(job/'inputs.json'); config = rv.read(job/'model-profile.json')
    authorization = rv.read(job/'observed-authorization.json'); plan = rv.read(job/'request-plan.json')
    generation=rv.read(job/'generation-options.json')
    rv.verify_inputs(inputs['source_job'],inputs)
    if authorization['job_id']!=job.name or authorization['mode']!=MODE or authorization['max_provider_requests']!=24:
        raise rv.Blocked('AUTHORIZATION_SCOPE_MISMATCH')
    if authorization['HARD_CAP_GUARANTEED'] is not False or authorization['token_cap'] is not None:
        raise rv.Blocked('OBSERVED_MODE_MISLABELLED')
    if authorization['online_writes'] is not False or authorization['automatic_remediation'] is not False:
        raise rv.Blocked('WRITE_SCOPE_FORBIDDEN')
    if (authorization['inputs_sha256']!=rv.canonical(inputs) or authorization['config_sha256']!=rv.fingerprint(config)
            or authorization['versions_sha256']!=rv.canonical(rv.source_versions())
            or authorization['plan_sha256']!=rv.canonical(plan)
            or authorization['generation_sha256']!=rv.canonical(generation)
            or generation!=GENERATION_OPTIONS):
        raise rv.Blocked('SOURCE_INPUT_PROFILE_OR_PLAN_CHANGED')
    if len(plan)!=24: raise rv.Blocked('REQUEST_SCOPE_MISMATCH')
    return inputs,config,authorization,plan


def usage_summary(rows):
    known = 0; unknown = 0; per_request = []
    for row in rows:
        raw = row['raw_usage']
        numeric = (isinstance(raw,dict) and all(type(raw.get(k)) is int and raw[k]>=0
                   for k in ('prompt_tokens','completion_tokens','total_tokens'))
                   and raw['prompt_tokens']+raw['completion_tokens']==raw['total_tokens'])
        if numeric: known += raw['total_tokens']
        else: unknown += 1
        per_request.append(dict(sequence=row['sequence'],model=row['model'],item_id=row['item_id'],
            gateway_usage=raw,usage_status='GATEWAY_REPORTED_UNVERIFIED' if numeric else 'UNKNOWN',
            verified_actual_tokens=None))
    return dict(gateway_reported_known_tokens=known,gateway_reported_total_tokens=None if unknown else known,
                unknown_usage_requests=unknown,verified_actual_tokens=None,
                usage_provenance='WorkBuddy gateway; may contain estimates; not verified supplier billing',
                HARD_CAP_GUARANTEED=False,per_request=per_request)


def execution_status(state):
    return state.removeprefix('FAKE_').removeprefix('PIPELINE_')


def save_progress(job,state,rows,*,current=None,stop_reason=None,conclusive=None):
    value=dict(job_id=job.name,execution_status=execution_status(state),request_count=len(rows),expected_requests=24,
        valid_response_count=sum(r['status']=='SUCCESS' for r in rows),exception_count=sum(r['status']=='ERROR' for r in rows),
        in_flight=sum(r['status']=='DISPATCHED' for r in rows),current_item=current,stop_reason=stop_reason,
        all_image_checks_conclusive=conclusive,report_path=str(job/'observed-audit-report.md'),
        online_writes=0,automatic_remediations=0)
    rv.write(job/'observed-progress.json',value)
    return value


def read_status(job):
    """Read local progress, including old reports, without touching a Job."""
    job=Path(job)
    if (job/'observed-progress.json').is_file():return rv.read(job/'observed-progress.json')
    result=rv.read(job/'observed-audit-report.json')
    return dict(job_id=result.get('job_id',job.name),execution_status=execution_status(result['state']),
        request_count=result['request_count'],valid_response_count=result['normalized_response_count'],
        exception_count=result.get('schema_exception_count',result['request_count']-result['normalized_response_count']),
        all_image_checks_conclusive=result['all_image_checks_conclusive'],stop_reason=result.get('stop_reason'),
        report_path=str(job/'observed-audit-report.md'))


def report(job, state, rows, stop_reason, *, fake):
    inputs = rv.read(job/'inputs.json'); config = rv.read(job/'model-profile.json')
    watermark,identity = {},{}
    for item in inputs['tasks']:
        by_model={}
        for row in rows:
            path = job/'observed-normalized'/f"{row['sequence']:02d}.json"
            if row['item_id']==item['id'] and path.is_file():
                by_model[row['model']]=rv.read(path)['result']
        # Preserve configured A/B provenance even when one response failed
        # schema validation. An empty observation remains invalid/UNKNOWN.
        models=list(config['models'])
        results=[by_model.get(model,{}) for model in models]
        pair = dict(results=results,models=models)
        if item['task_type']=='watermark':
            analysis = rv.aggregate_watermarks(pair,item); watermark[item['sha256']] = analysis
            if results: rv.overlay(job,item,results,analysis,fake)
        else: identity[item['sha256']] = rv.aggregate_identity(pair,'DW-ES09T',item)
    evidence_unchanged=True
    try: rv.verify_seal(Path(inputs['source_job']))
    except rv.Blocked: evidence_unchanged=False
    occurrences=[dict(row,watermark=watermark[row['sha256']],identity=identity[row['sha256']]) for row in inputs['occurrences']]
    conclusive = all(w['review_status'] in ('PASS','FAIL') and w['coverage_status']=='COMPLETE' for w in watermark.values()) and all(i['verdict']!='UNKNOWN' for i in identity.values())
    usage=usage_summary(rows)
    result=dict(state=state,mode='FAKE' if fake else MODE,HARD_CAP_GUARANTEED=False,
        strict_budget_preflight='PREFLIGHT_BLOCKED',job_id=job.name,shop=7,pid=5097,
        request_count=len(rows),actual_provider_requests=0 if fake else len(rows),
        simulated_requests=len(rows) if fake else 0,models=config['models'],
        normalized_response_count=len(list((job/'observed-normalized').glob('*.json'))),
        schema_exception_count=sum(r['status']=='ERROR' and (str(r['error']).startswith('SCHEMA_OR_TRANSPORT_ERROR:') or r['error']=='OUTPUT_LIMIT_EXHAUSTED') for r in rows),
        all_image_checks_conclusive=conclusive,watermark=watermark,identity=identity,occurrences=occurrences,
        source_evidence_unchanged=evidence_unchanged,stop_reason=stop_reason,usage=usage,
        online_writes=0,automatic_remediations=0,description_included=False,
        sku_packaging_reaudited=False,full_product_business_audit_complete=False,
        accuracy='NOT_MEASURED_WITHOUT_INDEPENDENT_GROUND_TRUTH',bbox_manual_review='NOT_REVIEWED')
    rv.write(job/'observed-audit-report.json',result); rv.write(job/'observed-usage.json',usage)
    rv.write(job/'observed-request-records.json',rows)
    comparison = rv.read(Path(inputs['source_job'])/'recovery_8788_1/combined_judgements.final2.json')
    rv.write(job/'historical-comparison.json',dict(historical_source=str(Path(inputs['source_job'])/'recovery_8788_1/combined_judgements.final2.json'),
        tasks={item['id']:dict(historical=comparison.get(('WM_' if item['task_type']=='watermark' else 'IDENTITY_')+item['sha256'][:16]),
                              new_analysis=(watermark if item['task_type']=='watermark' else identity)[item['sha256']]) for item in inputs['tasks']}))
    lines=['# 自动图片审核运行报告','',state,'',
        '模式：'+result['mode']+'；HARD_CAP_GUARANTEED=false；严格预算预检仍为PREFLIGHT_BLOCKED。',
        '请求数：'+str(result['request_count'])+' /24；规范化响应：'+str(result['normalized_response_count'])+'；线上写入0；自动整改0。',
        '旧证据433个文件未变：'+str(evidence_unchanged)+'。',
        '停止原因：'+str(stop_reason)+'；所有图片结论确定：'+str(conclusive)+'。',
        '网关报告Token小计：'+str(usage['gateway_reported_known_tokens'])+'；完整网关合计：'+str(usage['gateway_reported_total_tokens'])+'；缺失/异常用量请求：'+str(usage['unknown_usage_requests'])+'。',
        '供应商真实计费Token：UNKNOWN；网关可能回填估算，不能把上述数字当作已核实账单。',
        '', '| 图片SHA256 | 水印覆盖 | 水印复核 | 身份 | 已确认异常 |', '|---|---|---|---|---|']
    for image in inputs['images']:
        digest=image['sha256']; w=watermark[digest]; i=identity[digest]
        lines.append('| '+digest+' | '+w['coverage_status']+' | '+w['review_status']+' | '+i['verdict']+' | '+str(len(w['confirmed_findings']))+' |')
    lines+=['','16位置映射及每个mark/身份维度见同名JSON；原图、模型区域和聚合区域对照在8788-real-validation-overlay。',
            '流程完成不表示所有图片合规或所有结论确定。固定描述不进入输入，SKU包装本轮未额外请求，不宣称全商品业务审核完成。',
            '未访问商品网站；未保存、上传、删除、翻译、发布、重新分配SKU或更改状态。']
    (job/'observed-audit-report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    save_progress(job,state,rows,stop_reason=stop_reason,conclusive=conclusive)
    return result


def run(job, *, transport=None, fake=False, continue_item_errors=False):
    job = rv.validate_output(job,rv.DEFAULT_SOURCE)
    inputs,config,authorization,plan = _verify(job)
    if not fake:
        if authorization['real_authorized'] is not True or not authorization['user_statement'].strip():
            raise rv.Blocked('REAL_AUTHORIZATION_REQUIRED')
        if transport is None and not os.environ.get('VLM_API_KEY'): raise rv.Blocked('LOCAL_CREDENTIAL_MISSING')
    elif transport is None: raise rv.Blocked('FAKE_TRANSPORT_REQUIRED')
    try:
        with (job/'observed-started.json').open('x',encoding='utf-8') as handle:
            json.dump(dict(mode='FAKE' if fake else MODE,started_at=datetime.now(timezone.utc).isoformat()),handle)
            handle.flush(); os.fsync(handle.fileno())
    except FileExistsError: raise rv.Blocked('JOB_ALREADY_STARTED') from None
    journal=Journal(job/'observed-requests.sqlite',job.name,create=True,mode='FAKE' if fake else MODE)
    generation=rv.read(job/'generation-options.json')
    sender=transport or (lambda model,item,context:rv._http_transport(config,model,item,context,
        body=body_for(model,item,context,generation)[0]))
    state='FAKE_PIPELINE_COMPLETED' if fake else 'PIPELINE_COMPLETED'; stop_reason=None
    last_rows=[]
    save_progress(job,'RUNNING',last_rows)
    try:
        for item in inputs['tasks']:
            for model in config['models']:
                _verify(job)
                body,_=body_for(model,item,inputs['context'],generation)
                planned=next(p for p in plan if p['item_id']==item['id'] and p['model']==model)
                if rv.canonical(body)!=planned['body_sha256']: raise rv.Blocked('REQUEST_BODY_CHANGED')
                sequence=journal.dispatch(item['id'],model,item['sha256']); last_rows=journal.rows()
                save_progress(job,'RUNNING',last_rows,current=dict(item_id=item['id'],model=model,task_type=item['task_type']))
                print(json.dumps(dict(event='DISPATCHED',sequence=sequence,task=item['task_type'],sha256=item['sha256'],model=model)),flush=True)
                raw_usage=None;response_received=False
                try:
                    raw=sender(model,deepcopy(item),deepcopy(inputs['context']))
                    response_received=True
                    if isinstance(raw,bytes):
                        (job/'observed-raw'/f'{sequence:02d}.bin').write_bytes(raw)
                        raw=json.loads(raw)
                    else: rv.write(job/'observed-raw'/f'{sequence:02d}.json',raw)
                    raw_usage=raw.get('usage')
                    if raw.get('model')!=model: raise rv.Blocked('ACTUAL_MODEL_ID_CHANGED')
                    if raw['choices'][0].get('finish_reason')=='length': raise rv.Blocked('OUTPUT_LIMIT_EXHAUSTED')
                    normalized=rv.validate_result(rv.parse_json_content(raw['choices'][0]['message']['content']),
                                                  item['task_type'],item['id'],item,allow_legacy=False)
                    rv.write(job/'observed-normalized'/f'{sequence:02d}.json',dict(model=model,result=normalized,raw_usage=raw_usage))
                    journal.complete(sequence,'SUCCESS',raw_usage,None)
                    print(json.dumps(dict(event='SUCCESS',sequence=sequence)),flush=True)
                except Exception as exc:
                    if isinstance(exc,urllib.error.HTTPError):
                        (job/'observed-raw'/f'{sequence:02d}.http-error.bin').write_bytes(exc.read())
                        reason='HTTP_'+str(exc.code)
                    elif isinstance(exc,rv.Blocked): reason=str(exc)
                    elif isinstance(exc,TimeoutError): reason='TIMEOUT'
                    else: reason='SCHEMA_OR_TRANSPORT_ERROR:'+type(exc).__name__
                    rv.write(job/'observed-raw'/f'{sequence:02d}.error.json',dict(reason=reason,exception_type=type(exc).__name__,
                        detail=str(exc)[:500] if isinstance(exc,(ValueError,TypeError)) else None))
                    item_error=response_received and (
                        isinstance(exc,(ValueError,TypeError,KeyError,AttributeError)) and not isinstance(exc,rv.Blocked)
                        or reason=='OUTPUT_LIMIT_EXHAUSTED')
                    keep_going=continue_item_errors and item_error
                    journal.complete(sequence,'ERROR',raw_usage,reason,stop_on_error=not keep_going)
                    if not keep_going:raise rv.Blocked(reason) from None
                    state='FAKE_PIPELINE_COMPLETED_WITH_EXCEPTIONS' if fake else 'PIPELINE_COMPLETED_WITH_EXCEPTIONS'
                last_rows=journal.rows()
                save_progress(job,'RUNNING',last_rows)
    except (rv.Blocked,OSError) as exc:
        state='FAKE_PIPELINE_STOPPED' if fake else 'PIPELINE_STOPPED'; stop_reason=str(exc) if isinstance(exc,rv.Blocked) else 'LOCAL_IO_FAILURE'
    try: last_rows=journal.rows()
    except rv.Blocked: stop_reason=stop_reason or 'JOURNAL_IO_FAILURE'
    return report(job,state,last_rows,stop_reason,fake=fake)


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,default=rv.ROOT/'work/8788-observed-audit-20261114')
    p.add_argument('--user-statement',default='')
    p.add_argument('--execute-observed-models',action='store_true')
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    job=prepare(args.output_dir,user_statement=args.user_statement,authorize_real=args.execute_observed_models)
    print(json.dumps(dict(job=str(job),state='OBSERVED_READY_NO_TOKEN_CAP',HARD_CAP_GUARANTEED=False)),flush=True)
    if not args.execute_observed_models: return 0
    result=run(job)
    print(json.dumps(dict(job=str(job),state=result['state'],request_count=result['request_count'])),flush=True)
    return 0 if result['state']=='PIPELINE_COMPLETED' else 2


if __name__=='__main__': raise SystemExit(main())
