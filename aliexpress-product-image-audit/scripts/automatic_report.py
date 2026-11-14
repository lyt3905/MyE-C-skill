"""Unified job report: observed counters, provenance and explicit unknown usage."""
from collections import Counter
import json,sqlite3
from pathlib import Path
from urllib.parse import quote
from job_manager import atomic_json

def image_observations(directory):
    """Read existing observations only; never invent labels, calls or stage times."""
    import hashlib
    root=Path(directory)
    def read(name,default=None):
        path=root/name
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else ({} if default is None else default)
    raw=read('audit_raw.json');flags=read('audit_flags.json');queue=read('ai_queue.json').get('items',[])
    judgements=read('ai_judgements.json');metrics=read('ai_metrics.json')
    templates=read('template_scan.json');residuals=read('residual_manifest.json').get('items',[])
    highpass=read('highpass_manifest.json').get('items',[]);rois=read('candidate_crop_manifest.json').get('items',[])
    decisions=read('auto_decisions.json').get('items',[]);items=[]
    for row in raw.get('images',[]):
        pool,index=row.get('kind'),row.get('index')
        if pool not in {'main','detail','sku'}:continue
        identity=row.get('image_id') or pool.upper()+'_'+str(index).zfill(3)
        queued=[q for q in queue if q.get('task_type')=='watermark' and q.get('pool')==pool and q.get('index')==index and q.get('source_url')==row.get('url')]
        ids={q['id'] for q in queued}
        events=[e for e in metrics.get('calls',[]) if e.get('item_id') in ids]
        calls=[e for e in events if e.get('called')]
        actual=sum(e['total_tokens'] for e in calls) if calls and all(type(e.get('total_tokens')) is int for e in calls) else None
        status_counts=dict(Counter(e['usage_status'] for e in events))
        token_status=('UNKNOWN' if actual is None else 'ACTUAL_ZERO' if actual==0 else 'ACTUAL_REPORTED') if calls else (
            'BUDGET_BLOCKED' if 'BUDGET_BLOCKED' in status_counts else 'NOT_CALLED' if events or not queued or 'calls' in metrics else 'UNKNOWN')
        model_results=[{'item_id':q['id'],'judgement':judgements.get(q['id'],{'status':'NOT_CALLED'})} for q in queued]
        missing_models=[m for m in metrics.get('models',[]) if m not in {e.get('model') for e in events if e.get('called')}]
        by_identity=lambda records:[r for r in records if r.get('image_id',r.get('evidence_id'))==identity]
        timing=row.get('timing_ms') or {}
        timing=dict(timing,residual=next((r.get('elapsed_ms') for r in by_identity(residuals)),None),
                    highpass=next((r.get('elapsed_ms') for r in by_identity(highpass)),None))
        items.append({'image_id':identity,'pool':pool,'index':index,'url':row.get('url'),
            'source_sha256':row.get('content_sha256'),'source_field':row.get('source','images'),
            'source_index':row.get('source_index',index),'error':row.get('error'),
            'processing_status':row.get('processing_status',{}),
            'ground_truth':None,'label_status':'UNLABELED',
            'signals':{'ocr':{'items':row.get('ocr'),'hits':[h for h in flags.get('ocr_hits',[]) if h.get('kind')==pool and h.get('index')==index]},
                'cv':{'borders':row.get('borders'),'phash_pairs':[p for p in flags.get('duplicates',[]) if pool=='main' and index in (p.get('a'),p.get('b'))]},
                'residual':{'audit':row.get('residual'),'evidence':by_identity(residuals)},
                'highpass':by_identity(highpass),'template':{'configuration_status':templates.get('status','UNKNOWN'),'items':by_identity(templates.get('items',[]))},
                'roi':by_identity(rois)},
            'models':{'judgements':model_results,'events':events,'not_called_models':missing_models,
                      'actual_tokens':actual,'token_status':token_status,'usage_status_counts':status_counts,
                      'events_available':'calls' in metrics},
            'actions':[r for r in decisions if (r.get('target',{}).get('pool'),r.get('target',{}).get('index'))==(pool,index) or r.get('item_id') in ids],
            'timing_ms':{key:timing.get(key) for key in ('download','cv','ocr','residual','highpass')},
            'model_attempt_elapsed_ms':sum(e['elapsed_ms'] for e in events) if events and all(type(e.get('elapsed_ms')) in (int,float) for e in events) else None})
    source_names=['audit_raw.json','audit_flags.json','ai_queue.json','ai_judgements.json','ai_metrics.json',
                  'template_scan.json','residual_manifest.json','highpass_manifest.json','candidate_crop_manifest.json','auto_decisions.json','quality_metrics.json']
    sources=[{'path':name,'sha256':hashlib.sha256((root/name).read_bytes()).hexdigest()} for name in source_names if (root/name).exists()]
    duplicate_ids=[key for key,count in Counter(r['image_id'] for r in items).items() if count>1]
    return {'schema':'image-observations/v1.3','pid':raw.get('pid'),'image_count':len(items),'images':items,'sources':sources,
            'warnings':['DUPLICATE_IMAGE_IDS'] if duplicate_ids else [],'duplicate_image_ids':duplicate_ids,
            'purpose':'Observed signals only; no ground truth or execution authorization. Model events cover the machine audit queue; independent quality calls remain in quality_metrics.json. Attempt timing includes admission/cache/validation. CV timing includes audit residual statistics; download time is per unique URL, repeated across its occurrences. Do not sum overlapping/shared stages. Missing measurements remain null.'}

def _budget(path):
    if not path.is_file():return {'status':'UNKNOWN'}
    connection=sqlite3.connect('file:'+quote(path.resolve().as_posix(),safe='/:')+'?mode=ro',uri=True)
    try:
        rows=list(connection.execute('SELECT resource,cap,used FROM budgets'))
        actual,known=connection.execute('SELECT actual,known FROM token_usage WHERE id=1').fetchone()
        return {'limits':{r:c for r,c,u in rows},'used':{r:u for r,c,u in rows},'actual_tokens':actual if known else None,'token_usage_known':bool(known)}
    finally:connection.close()

def write(directory,job,status,result,writer=None,inspector=None):
    root=Path(directory)
    def read(name,default=None):
        path=root/name
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else ({} if default is None else default)
    metrics=read('run_metrics.json');pipeline=read('ai_metrics.json')
    phases=read('quality_metrics.json',{'phases':{}})
    judge=getattr(inspector,'judge',None);quality=getattr(judge,'metrics',None)
    if isinstance(quality,dict):
        phases['phases'][getattr(inspector,'metrics_phase','current')]=quality
        atomic_json(root/'quality_metrics.json',phases)
    sources=[pipeline]+list(phases.get('phases',{}).values())
    def summed(key):
        values=[source.get(key) for source in sources]
        return sum(values) if values and all(type(v) is int for v in values) else None
    budget=_budget(root/'budget.sqlite');write_budget=_budget(root/'auto_write_budget.sqlite')
    actual=summed('total_tokens') if all(source.get('usage_available') is True for source in sources) and budget.get('token_usage_known',True) else None
    requests=summed('requests')
    admitted=budget.get('used',{}).get('ai_requests')
    coverage=('UNKNOWN' if type(admitted) is not int else
              'VERIFIED' if type(requests) is int and requests==admitted else 'INCOMPLETE')
    if coverage=='INCOMPLETE':actual=None
    ai={'reported_requests':requests,'admitted_requests':budget.get('used',{}).get('ai_requests'),
        'metrics_completeness':coverage,
        'actual_tokens':actual,'token_status':'UNKNOWN' if actual is None else 'NOT_CALLED' if requests==0 else 'ACTUAL_ZERO' if actual==0 else 'ACTUAL_REPORTED',
        'cache_hits':summed('cache_hits'),'quality_metrics_available':isinstance(quality,dict),
        'accounted_tokens':budget.get('used',{}).get('total_tokens')}
    raw=read('audit_raw.json');flags=read('audit_flags.json');before=read('before.json');after=read('after.json')
    observations=image_observations(root)
    atomic_json(root/'image_observations.json',observations)
    decisions=read('auto_decisions.json').get('items',[]);deferred=read('deferred_items.json').get('items',[])
    plan=read('plan.v2.json');dry=read('dry_run.json');receipt=read('apply_receipt.json');retry=read('translation_retry.json')
    executor={key:receipt.get(key,result.get(key)) for key in ('site_save_calls','upload_calls','translate_calls','status_calls')}
    if executor['site_save_calls'] is None:executor['site_save_calls']=read('save_attempt.json').get('site_save_calls')
    if executor['upload_calls'] is None:executor['upload_calls']=read('upload_receipts.json').get('upload_calls')
    if type(retry.get('translate_calls')) is int:executor['translate_calls']=(executor.get('translate_calls') or 0)+retry['translate_calls']
    executor['publish_calls']=0
    observed=getattr(writer,'metrics',None)
    if isinstance(observed,dict):executor['current_command_observed']=observed
    counts=Counter(row['action'] for row in decisions if row.get('decision')=='AUTO_SAFE')
    details=[]
    def at(snapshot,pool,index):
        try:return snapshot.get('images',{}).get(pool,[])[index]
        except (IndexError,KeyError,TypeError):return None
    for row in decisions:
        if row.get('decision')!='AUTO_SAFE':continue
        target=row['target'];pool,index=target.get('pool'),target.get('index');old=None;new=None
        if pool is not None and type(index) is int:
            old=at(before,pool,index)
            if row['action']=='DELETE_REDUNDANT':new='REMOVED'
            else:
                position=(plan.get('post_actions') or {}).get('target_positions',{}).get(target.get('image_id'),target)
                new=at(after,position['pool'],position['index']) if after else 'UPLOAD_TOKEN:'+row['candidate_asset']['sha256'][:16] if row.get('candidate_asset') else row['source'].get('url')
        elif row['action'] in {'TITLE_REWRITE','BRAND_CODE'}:
            field='titleEn' if row['action']=='TITLE_REWRITE' else 'brandId';old=before.get(field);new=after.get(field,plan.get('desired',{}).get(field))
        elif row['action']=='SKU_ASSIGN':new=row.get('assignments')
        details.append({'item_id':row['item_id'],'action':row['action'],'target':target,'before':old,'after':new,'source':row['source'],'evidence_ids':row['evidence_ids'],'checks':row['checks']})
    run_times=metrics.setdefault('timing_ms_by_run',{})
    if result.get('run_id') and type(result.get('total_elapsed_ms')) in (int,float):run_times[result['run_id']]=result['total_elapsed_ms']
    timing=dict(metrics.get('timing',{}));timing['total_ms']=round(sum(run_times.values()),3) if run_times else result.get('total_elapsed_ms',timing.get('total_ms'))
    data={'schema':'automatic-report/v1','status':status,'identity':{'pid':job['pid'],'shop':job['shop_id'],'job_id':job['job_id'],'automation_policy_sha256':read('automation_policy_summary.json').get('sha256')},
          'audit':{'image_occurrences':sum(r.get('kind') in {'main','detail','sku'} for r in raw.get('images',[])),'machine_anomalies':len(flags.get('anomalies',[])),'deferred_items':len(deferred),
                   'image_observations':'image_observations.json'},
          'ai':ai,'budget':{'audit_and_models':budget,'writes':write_budget},'timing_ms':timing,
          'actions':{'planned_safe_counts':dict(counts),'executed_safe_counts':dict(counts) if executor.get('site_save_calls')==1 else {}},
          'action_details':details,'conditional_transitions':read('conditional_decisions.json',{'items':[]})['items'],'deferred':deferred,'dry_run':dry,'executor':executor,
          'verification':{'structure':read('final_check.json',read('verification.json')),'content':read('content_validation.json'),'recovery':read('recovery_readback.json'),'overall_status':status},
          'unverified_items':(['PROVIDER_USAGE_UNKNOWN'] if actual is None else [])+
              (['MODEL_METRICS_INCOMPLETE'] if coverage=='INCOMPLETE' else [])}
    metrics.update(automatic_report=data,executor=executor,timing=timing)
    metrics.setdefault('ai',{}).update(requests=requests,total_tokens=actual,usage_available=actual is not None)
    atomic_json(root/'run_metrics.json',metrics);atomic_json(root/'report_data.json',data)
    text=f"# 商品自动审核与整改 {job['pid']}\n\nShop: {job['shop_id']} · Job: {job['job_id']}\n\nStatus: **{status}**\n\n"
    text+=f"审核图片：{data['audit']['image_occurrences']}；待处理项：{len(deferred)}；实际 Token：{actual if actual is not None else 'UNKNOWN'}。\n\n"
    text+='## 执行与验证\n\n```json\n'+json.dumps({'actions':data['actions'],'executor':executor,'timing_ms':timing,'ai':ai,'verification':data['verification']},ensure_ascii=False,indent=2)+'\n```\n\n'
    text+='## 逐项变更与证据\n\n```json\n'+json.dumps(details,ensure_ascii=False,indent=2)+'\n```\n\n## 暂缓项目（原引用保留）\n\n'
    for row in deferred:text+='- '+row['item_id']+': '+', '.join(row.get('reason_codes',[]))+'\n'
    text+='\n完整机器记录：report_data.json；逐图片独立信号：image_observations.json。来源、质量、预算、预演与回读证据均保留在同一 Job 目录。缺失 usage 标 UNKNOWN，不等同于零 Token。\n'
    (root/'report.md').write_text(text,encoding='utf-8')
    return data

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Export existing per-image observations offline; never calls a site or model')
    parser.add_argument('directory',type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();atomic_json(args.output,image_observations(args.directory))
