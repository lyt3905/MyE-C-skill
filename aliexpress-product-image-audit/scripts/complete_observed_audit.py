"""Complete never-called pairs in a stopped observed batch, without retries.

Existing model-format errors remain exceptions. Parent Jobs are read-only;
new calls use a new sibling Job and a single-use continuation claim.
"""
from policy_engine import MODEL_CONFIDENCE_MIN
from pathlib import Path
import argparse
from datetime import datetime,timezone
import json
import os
import shutil
import urllib.error

import observed_audit as oa
import run_8788_real_validation as rv


class ItemJournal(oa.Journal):
    def schema_exception(self,sequence,usage,error):
        """Persist an item error without resetting the batch request counter."""
        with self._transaction() as db:
            changed=db.execute("UPDATE requests SET status='ERROR',raw_usage=?,error=?,completed_at=? WHERE sequence=? AND status='DISPATCHED'",
                (json.dumps(usage,ensure_ascii=False,allow_nan=False),error,datetime.now(timezone.utc).isoformat(),sequence))
            if changed.rowcount!=1:raise rv.Blocked('DUPLICATE_COMPLETION')


def verify_parent(parent, *, fake):
    parent=rv.validate_output(parent,rv.DEFAULT_SOURCE)
    inputs=rv.read(parent/'inputs.json');config=rv.read(parent/'model-profile.json')
    auth=rv.read(parent/'observed-authorization.json');plan=rv.read(parent/'request-plan.json')
    producer=rv.read(parent/'source-versions.json');current=rv.source_versions()
    rv.verify_inputs(inputs['source_job'],inputs)
    if (auth['job_id']!=parent.name or auth['mode']!=oa.MODE or auth['max_provider_requests']!=24
            or auth['inputs_sha256']!=rv.canonical(inputs) or auth['config_sha256']!=rv.fingerprint(config)
            or auth['versions_sha256']!=rv.canonical(producer) or auth['plan_sha256']!=rv.canonical(plan)
            or auth['generation_sha256']!=rv.canonical(rv.read(parent/'generation-options.json'))):
        raise rv.Blocked('PARENT_BINDING_MISMATCH')
    if not fake and (auth['real_authorized'] is not True or not auth['user_statement'].strip()):
        raise rv.Blocked('REAL_AUTHORIZATION_REQUIRED')
    expected_mode='FAKE' if fake else oa.MODE
    if rv.read(parent/'observed-started.json')['mode']!=expected_mode: raise rv.Blocked('PARENT_MODE_MISMATCH')
    if any(current['files'].get(path)!=digest for path,digest in producer['files'].items()):
        raise rv.Blocked('PARENT_PRODUCER_SOURCE_CHANGED')
    if set(current['files'])-set(producer['files'])-{'scripts/complete_observed_audit.py'}:
        raise rv.Blocked('UNAPPROVED_SOURCE_ADDITION')
    if (producer['contracts']!=current['contracts'] or producer['confidence_min']!=MODEL_CONFIDENCE_MIN
            or producer['matching']!=current['matching']): raise rv.Blocked('PARENT_CONTRACT_CHANGED')
    if len(plan)!=24 or len({(p['item_id'],p['model']) for p in plan})!=24: raise rv.Blocked('PARENT_PLAN_SCOPE')
    rows=oa.Journal(parent/'observed-requests.sqlite',parent.name,create=False).rows()
    if any(r['status']=='DISPATCHED' for r in rows): raise rv.Blocked('PARENT_IN_FLIGHT')
    if any(r['status']=='ERROR' and not str(r['error']).startswith('SCHEMA_OR_TRANSPORT_ERROR:') for r in rows):
        raise rv.Blocked('PARENT_NON_SCHEMA_ERROR_REQUIRES_STOP')
    attempted={(r['item_id'],r['model']) for r in rows}
    allowed={(p['item_id'],p['model']):p for p in plan}
    if len(rows)!=len(attempted) or not attempted<=set(allowed): raise rv.Blocked('PARENT_ATTEMPT_SCOPE')
    for row in rows:
        p=allowed[(row['item_id'],row['model'])]
        if row['sha256']!=p['sha256']:raise rv.Blocked('PARENT_IMAGE_BINDING')
        if row['status']=='SUCCESS':
            item=next(i for i in inputs['tasks'] if i['id']==row['item_id'])
            record=rv.read(parent/'observed-normalized'/f"{row['sequence']:02d}.json")
            if record['model']!=row['model']:raise rv.Blocked('PARENT_MODEL_BINDING')
            rv.validate_result(record['result'],item['task_type'],item['id'],item,allow_legacy=False)
    remaining=[dict(p,batch_sequence=index+1) for index,p in enumerate(plan) if (p['item_id'],p['model']) not in attempted]
    if not remaining:raise rv.Blocked('NO_REMAINING_REQUESTS')
    return parent,inputs,config,auth,rows,remaining


def complete(parent, *, transport=None, fake=False):
    parent,inputs,config,auth,parent_rows,remaining=verify_parent(Path(parent),fake=fake)
    if not fake and transport is None and not os.environ.get('VLM_API_KEY'):raise rv.Blocked('LOCAL_CREDENTIAL_MISSING')
    if fake and transport is None:raise rv.Blocked('FAKE_TRANSPORT_REQUIRED')
    parent_seal=rv.tree(parent)
    claims=parent.parent/'continuation-claims';claims.mkdir(exist_ok=True)
    try:
        with (claims/(parent.name+'.json')).open('x',encoding='utf-8') as handle:
            json.dump(dict(parent=str(parent),remaining_requests=len(remaining),fake=fake),handle)
            handle.flush();os.fsync(handle.fileno())
    except FileExistsError:raise rv.Blocked('CONTINUATION_ALREADY_CLAIMED') from None
    job=oa.prepare(parent.parent,user_statement=auth['user_statement'],authorize_real=not fake)
    if rv.read(job/'model-profile.json')!=config:raise rv.Blocked('CONTINUATION_PROFILE_CHANGED')
    rv.write(job/'observed-started.json',dict(mode='FAKE' if fake else oa.MODE,continuation=True,parent=str(parent)))
    rv.write(job/'continuation-scope.json',dict(parent=str(parent),parent_tree=parent_seal,
        parent_requests=len(parent_rows),new_request_limit=len(remaining),combined_request_limit=24,
        remaining=remaining,no_retry_of_parent_errors=True))
    for row in parent_rows:
        path=parent/'observed-normalized'/f"{row['sequence']:02d}.json"
        if row['status']=='SUCCESS':shutil.copyfile(path,job/'observed-normalized'/path.name)
    journal=ItemJournal(job/'observed-requests.sqlite',job.name,create=True,mode='FAKE' if fake else oa.MODE)
    combined=[dict(r,origin_job=str(parent),origin_sequence=r['sequence']) for r in parent_rows]
    generation=rv.read(job/'generation-options.json')
    state='PIPELINE_COMPLETED_WITH_EXCEPTIONS';stop_reason=None
    try:
        for planned in remaining:
            oa._verify(job)
            if rv.tree(parent)!=parent_seal:raise rv.Blocked('PARENT_EVIDENCE_CHANGED')
            item=next(i for i in inputs['tasks'] if i['id']==planned['item_id']);model=planned['model']
            body,_=oa.body_for(model,item,inputs['context'],generation)
            if rv.canonical(body)!=planned['body_sha256']:raise rv.Blocked('CONTINUATION_BODY_CHANGED')
            local_sequence=journal.dispatch(item['id'],model,item['sha256']);batch_sequence=planned['batch_sequence']
            print(json.dumps(dict(event='CONTINUATION_DISPATCHED',local_sequence=local_sequence,batch_sequence=batch_sequence,model=model)),flush=True)
            usage=None;schema_error=None
            try:
                raw=transport(model,item,inputs['context']) if transport else rv._http_transport(config,model,item,inputs['context'],body=body)
                if isinstance(raw,bytes):
                    (job/'observed-raw'/f'{batch_sequence:02d}.bin').write_bytes(raw);raw=json.loads(raw)
                else:rv.write(job/'observed-raw'/f'{batch_sequence:02d}.json',raw)
                usage=raw.get('usage')
                if raw.get('model')!=model:raise rv.Blocked('ACTUAL_MODEL_ID_CHANGED')
                if raw['choices'][0].get('finish_reason')=='length':raise rv.Blocked('OUTPUT_LIMIT_EXHAUSTED')
                try:
                    result=rv.validate_result(rv.parse_json_content(raw['choices'][0]['message']['content']),
                                              item['task_type'],item['id'],item,allow_legacy=False)
                except (ValueError,TypeError,KeyError) as exc:
                    schema_error='SCHEMA_OR_TRANSPORT_ERROR:'+type(exc).__name__
                    rv.write(job/'observed-raw'/f'{batch_sequence:02d}.error.json',dict(reason=schema_error,detail=str(exc)[:500]))
                if schema_error is None:
                    rv.write(job/'observed-normalized'/f'{batch_sequence:02d}.json',dict(model=model,result=result,raw_usage=usage))
                if schema_error:journal.schema_exception(local_sequence,usage,schema_error)
                else:journal.complete(local_sequence,'SUCCESS',usage,None)
                combined.append(dict(journal.rows()[-1],sequence=batch_sequence,origin_job=str(job),origin_sequence=local_sequence))
                print(json.dumps(dict(event='CONTINUATION_EXCEPTION' if schema_error else 'CONTINUATION_SUCCESS',batch_sequence=batch_sequence)),flush=True)
            except Exception as exc:
                reason=('HTTP_'+str(exc.code) if isinstance(exc,urllib.error.HTTPError) else
                        'TIMEOUT' if isinstance(exc,TimeoutError) else str(exc) if isinstance(exc,rv.Blocked) else 'TRANSPORT_OR_LOCAL_ERROR')
                if isinstance(exc,urllib.error.HTTPError):(job/'observed-raw'/f'{batch_sequence:02d}.http-error.bin').write_bytes(exc.read())
                rv.write(job/'observed-raw'/f'{batch_sequence:02d}.error.json',dict(reason=reason))
                journal.complete(local_sequence,'ERROR',usage,reason)
                combined.append(dict(journal.rows()[-1],sequence=batch_sequence,origin_job=str(job),origin_sequence=local_sequence))
                raise rv.Blocked(reason) from None
    except (rv.Blocked,OSError) as exc:
        state='PIPELINE_STOPPED';stop_reason=str(exc) if isinstance(exc,rv.Blocked) else 'LOCAL_IO_FAILURE'
    if rv.tree(parent)!=parent_seal:raise rv.Blocked('PARENT_EVIDENCE_CHANGED')
    mode_state=('FAKE_'+state) if fake else state
    report=oa.report(job,mode_state,combined,stop_reason,fake=fake)
    new_count=len(combined)-len(parent_rows)
    report.update(report_scope='COMBINED_BATCH_WITH_PARENT',parent_job=str(parent),
        new_provider_requests=0 if fake else new_count,simulated_new_requests=new_count if fake else 0,
        parent_provider_requests=len(parent_rows),schema_exception_count=sum(r['status']=='ERROR' for r in combined),
        parent_evidence_unchanged=True,never_retried_pairs=True)
    rv.write(job/'observed-audit-report.json',report)
    with (job/'observed-audit-report.md').open('a',encoding='utf-8') as handle:
        handle.write('\n合并批次报告：复用父Job请求记录'+str(len(parent_rows))+'条；本子Job新增调用'+str(new_count)+
                     '次；未重试父Job失败项；格式异常'+str(report['schema_exception_count'])+'条。父Job文件全树哈希未变。\n')
    return job,report


def run_new(output, *, user_statement, transport=None, fake=False):
    job=oa.prepare(output,user_statement=user_statement,authorize_real=not fake)
    result=oa.run(job,transport=transport,fake=fake,continue_item_errors=True)
    return job,result


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent-job',type=Path)
    p.add_argument('--status-job',type=Path,help='Read existing local audit progress/report; no model or site calls')
    p.add_argument('--output-dir',type=Path,default=rv.ROOT/'work/8788-observed-audit-20261114')
    p.add_argument('--execute-observed-models',action='store_true')
    p.add_argument('--user-statement',default='')
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    if args.status_job:
        if args.execute_observed_models or args.parent_job:raise rv.Blocked('STATUS_IS_READ_ONLY')
        print(json.dumps(oa.read_status(args.status_job),ensure_ascii=False));return 0
    if not args.execute_observed_models:
        if args.parent_job:
            parent,inputs,config,auth,rows,remaining=verify_parent(args.parent_job,fake=False)
            print(json.dumps(dict(state='OBSERVED_CONTINUATION_READY_NO_TOKEN_CAP',remaining_requests=len(remaining),HARD_CAP_GUARANTEED=False)))
        else:
            job=oa.prepare(args.output_dir,user_statement=args.user_statement,authorize_real=False)
            print(json.dumps(dict(state='OBSERVED_READY_NO_TOKEN_CAP',job=str(job),HARD_CAP_GUARANTEED=False)))
        return 0
    job,result=complete(args.parent_job) if args.parent_job else run_new(args.output_dir,user_statement=args.user_statement)
    print(json.dumps(dict(job=str(job),state=result['state'],batch_requests=result['request_count'],new_requests=result.get('new_provider_requests',result['actual_provider_requests']))))
    return 0 if 'COMPLETED' in result['state'] else 2


if __name__=='__main__':raise SystemExit(main())
