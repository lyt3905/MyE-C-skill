"""Explicitly authorized supplemental read-only inference; never unlock old budgets."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from mye_c_automation.ai_judge import JudgeClient
from mye_c_automation.ai_judge.client import safe_payload
from mye_c_automation.ai_judge.schemas import validate_result
from mye_c_automation.budget_manager import BudgetManager
from mye_c_automation.download_manager import download_unique
from mye_c_automation.full_product_audit import assemble_report, _watermark, _identity, _sku
from mye_c_automation.job_manager import JobManager, atomic_json
from mye_c_automation.model_config import validate_config
from mye_c_automation.product_state import canonical_state_hash, identity_object

PHASE='recovery_8788_1'
LIMITS={'ai_requests':28,'total_tokens':500000,'site_save':0,'upload':0,
        'translate_title':0,'delete':0,'status':0}


def normalize_saved(queue,results):
    items={v['id']:v for v in queue['items']};normalized=deepcopy(results)
    for key,value in normalized.items():
        if key not in items:raise ValueError('UNBOUND_SAVED_JUDGEMENT')
        item=items[key]
        value['results']=[validate_result(row,item['task_type'],key,item) for row in value.get('results',[])]
    return normalized


def select_pending(product,inventory,queue,results):
    results=normalize_saved(queue,results)
    model=identity_object(product.get('identityJson') or {}).get('modelCode')
    pending=[]
    for item in queue['items']:
        result=results.get(item['id'],{});task=item['task_type']
        if task=='watermark':verdict=_watermark(result,item)
        elif task=='product_identity':verdict=_identity(result,model,item)
        elif task=='sku_match':
            shared=sum(r['target_type']=='sku_reference' and r['sha256']==item['sha256'] for r in inventory['occurrences'])>1
            verdict=_sku(result,item['sku_name'],shared)
        else:raise ValueError('UNAUTHORIZED_RECOVERY_TASK')
        if verdict=='UNKNOWN':pending.append(deepcopy(item))
    return dict(queue,items=pending)


def add_source_labels(queue,registry):
    """Only explicit human binary labels for exactly the same source bytes."""
    queue=deepcopy(queue);proof=[]
    for item in queue['items']:
        if item['task_type']!='watermark':continue
        confirmations=[]
        for sample in registry.get('samples',[]):
            if sample.get('source_sha256')!=item['sha256']:continue
            for row in sample.get('confirmations',[]):
                value=(row.get('ground_truth') or {}).get('third_party_watermark')
                if (row.get('label_status')=='USER_CONFIRMED' and type(value) is bool and
                    isinstance(row.get('sample_id'),str) and re.fullmatch(r'[A-Za-z0-9_-]{1,180}',row['sample_id'])):
                    confirmations.append({'sample_id':row['sample_id'],'third_party_watermark':value})
        if not confirmations:continue
        if len({r['third_party_watermark'] for r in confirmations})!=1:raise ValueError('CONFLICTING_HUMAN_SOURCE_LABELS')
        evidence={'source_sha256':item['sha256'],'confirmations':confirmations}
        proof.append(evidence)
        item['purpose']+=' Exact-source human provenance: '+json.dumps(evidence)+'. This only confirms whether third-party watermark exists in these exact bytes. It does not identify model/color/packaging, assign numerical model confidence, or authorize deletion. Independently inspect all marks and explain any conflict; keep uncertainty when unsupported.'
    return queue,proof


def recover(parent,authorization,reader,*,registry=None,judge_factory=None):
    parent=Path(parent);read=lambda n:json.loads((parent/n).read_text(encoding='utf-8'))
    auth=deepcopy(authorization)
    if (auth.get('schema')!='read-only-audit-recovery-proposal/v1' or auth.get('enabled') is not True or
        auth.get('supplemental_phase_limits')!=LIMITS):raise ValueError('RECOVERY_AUTHORIZATION_REQUIRED')
    if (parent/PHASE).exists():raise ValueError('RECOVERY_ALREADY_STARTED')
    job=JobManager(parent.parent).load(parent.name)
    for key,value in (('parent_job_id',job['job_id']),('pid',job['pid']),('shop',job['shop_id']),
                      ('source_state_sha256',job['input_state_sha256'])):
        if auth.get(key)!=value:raise ValueError('RECOVERY_AUTHORIZATION_BINDING')
    profile=validate_config(auth['model_config'])
    if profile['retries']!=0:raise ValueError('RECOVERY_RETRIES_NOT_AUTHORIZED')
    def verify_state():
        if str(reader.current_shop())!=str(job['shop_id']):raise ValueError('SHOP_CONTEXT_UNVERIFIED')
        if reader.account_fingerprint()!=job['account_fingerprint']:raise ValueError('ACCOUNT_MISMATCH')
        fresh=reader.product(job['pid'])
        if canonical_state_hash(fresh)!=job['input_state_sha256']:raise ValueError('RECOVERY_STATE_DRIFT')
        return fresh
    verify_state()
    product=read('audit_product.json');inventory=read('full_inventory.json');queue=read('full_ai_queue.json')
    if canonical_state_hash(product)!=job['input_state_sha256']:raise ValueError('SAVED_SOURCE_CHANGED')
    original_results=normalize_saved(queue,read('full_ai_judgements.json'))
    pending=select_pending(product,inventory,queue,original_results)
    if len(pending['items'])*2>LIMITS['ai_requests']:raise ValueError('RECOVERY_REQUEST_LIMIT')
    pending,labels=add_source_labels(pending,registry or {})
    for item in pending['items']:
        if item['task_type']=='product_identity':
            item['purpose']+=' Follow product-identity/v3 observations for each dimension with independent confidence and evidence. Windowed packaging enclosing a toy is BOX; MIXED requires an unpackaged figure outside its packaging. Keep unverifiable model identity explicitly uncertain.'
        if item['task_type']=='sku_match':
            item['purpose']+=' A toy enclosed inside windowed packaging is box. An unpackaged product outside its box alongside packaging is mixed. For a without-box SKU, mixed must be MISMATCH. For an explicitly with-box SKU, mixed is permitted if identity is consistent and the image is not shared with the without-box row.'
    protected={name:hashlib.sha256((parent/name).read_bytes()).hexdigest() for name in
        ('job.json','binding.json','state.json','budget.sqlite','full_audit_report.json','full_ai_judgements.json','full_ai_metrics.json','full_ai_queue.json','full_inventory.json')}
    phase=parent/PHASE;phase.mkdir()
    atomic_json(phase/'authorization.json',auth);atomic_json(phase/'parent_bindings.json',protected)
    atomic_json(phase/'label_evidence.json',labels);atomic_json(phase/'queue.json',pending)
    atomic_json(phase/'state.json',{'state':'PREFLIGHT','read_only':True})
    budget=None;judge=None
    try:
        expected_urls={url:sha for sha,c in inventory['contents'].items() for url in c['urls']}
        downloads=download_unique(list(expected_urls),phase/'source_downloads',force=True,ttl_seconds=0)
        verified=[]
        for url,expected in expected_urls.items():
            content=downloads.get(url,{})
            if 'path' not in content or hashlib.sha256(Path(content['path']).read_bytes()).hexdigest()!=expected:
                raise ValueError('REMOTE_IMAGE_SOURCE_CHANGED_OR_UNAVAILABLE')
            verified.append({'url':url,'sha256':expected,'file':str(content['path'])})
        for sha,content in inventory['contents'].items():
            if hashlib.sha256(Path(content['file']).read_bytes()).hexdigest()!=sha:raise ValueError('LOCAL_IMAGE_SOURCE_CHANGED')
        atomic_json(phase/'source_verified.json',verified)
        context=safe_payload({}, {'pid':job['pid'],'shop':job['shop_id'],'identityJson':product.get('identityJson'),
                                 'brand':product.get('brand'),'brandId':product.get('brandId'),'skus':product.get('skus',[])})['context']
        limits={'ai_requests':28,'full_resolution_images':32,'total_tokens':500000,'site_save':0,'translate_title':0}
        budget=BudgetManager(limits,phase/'budget.sqlite')
        judge=(judge_factory or JudgeClient)(budget,phase/'judge_cache',config=profile)
        if list(judge.models)!=profile['models']:raise ValueError('RECOVERY_MODELS_CHANGED')
        new={};atomic_json(phase/'state.json',{'state':'AI_PENDING','expected_tasks':len(pending['items'])})
        for index,item in enumerate(pending['items']):
            new[item['id']]=judge.classify(item['task_type'],item,context)
            atomic_json(phase/'new_judgements.json',new);atomic_json(phase/'new_metrics.json',judge.metrics)
            print(json.dumps({'completed_tasks':index+1,'expected_tasks':len(pending['items']),'item':item['id'],'status':new[item['id']].get('status')},ensure_ascii=False),flush=True)
            if budget.snapshot()['token_status']=='UNKNOWN':break
        combined=dict(original_results);combined.update(new)
        old_report=read('full_audit_report.json')
        generated=('required_pool_','main_count_1_to_6','main_exact_duplicates','sku_pool_reference_')
        checks=[r for r in old_report['global_checks'] if not r['rule'].startswith(generated) and r['rule']!='source_state_and_account_unchanged']
        try:verify_state();stable=True
        except ValueError:stable=False
        checks.append({'rule':'source_state_and_account_unchanged','verdict':'PASS' if stable else 'UNKNOWN'})
        report=assemble_report(product,inventory,combined,checks,queue=queue)
        previous=read('full_ai_metrics.json');all_calls=previous.get('calls',[])+judge.metrics.get('calls',[])
        known_tokens=sum(c['total_tokens'] for c in all_calls if c.get('called') and c.get('usage_status') in {'ACTUAL_ZERO','ACTUAL_REPORTED'})
        unknown=sum(bool(c.get('called')) and c.get('usage_status')=='UNKNOWN' for c in all_calls)
        report.update(parent_job_id=job['job_id'],recovery_phase=PHASE,shop=job['shop_id'],source_state_sha256=job['input_state_sha256'],
            source_unchanged=stable,new_ai=judge.metrics,new_budget=budget.snapshot(),
            combined_token_accounting={'requests':previous['requests']+judge.metrics['requests'],'known_token_subtotal':known_tokens,
                'unknown_usage_calls':unknown,'total_tokens':None if unknown else known_tokens,'token_status':'UNKNOWN' if unknown else 'ACTUAL_REPORTED'},
            reused_task_ids=[r['id'] for r in queue['items'] if r['id'] not in new],
            judgement_provenance={key:('supplemental_8788' if key in new else 'original_job') for key in combined})
        atomic_json(phase/'combined_judgements.json',combined);atomic_json(phase/'full_audit_report.json',report)
        atomic_json(phase/'coverage_matrix.json',{'positions':[{'id':r['id'],'checks':r['checks']} for r in report['occurrences']],
            'unresolved_count':report['unresolved_count']})
        for name,digest in protected.items():
            if hashlib.sha256((parent/name).read_bytes()).hexdigest()!=digest:raise ValueError('PARENT_EVIDENCE_MODIFIED')
        atomic_json(phase/'state.json',{'state':report['audit_status'],'original_evidence_preserved':True})
        return report
    except BaseException as exc:
        atomic_json(phase/'state.json',{'state':'FAILED','error_type':type(exc).__name__,'retry_requires_same_phase_recovery':True})
        raise
    finally:
        if judge is not None:atomic_json(phase/'new_metrics.json',judge.metrics)
        if budget is not None:budget.close()


def main():
    parser=argparse.ArgumentParser(description='Authorized read-only continuation, preserving original UNKNOWN usage')
    parser.add_argument('--job-dir',type=Path,required=True);parser.add_argument('--authorization',type=Path,required=True)
    parser.add_argument('--site-config',type=Path,required=True);parser.add_argument('--label-registry',type=Path)
    args=parser.parse_args()
    from mye_c_automation.site_client import ReadOnlySiteClient
    read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
    report=recover(args.job_dir,read(args.authorization),ReadOnlySiteClient(read(args.site_config)),
                   registry=read(args.label_registry) if args.label_registry else None)
    print(json.dumps({k:report[k] for k in ('audit_status','compliance_status','unresolved_count','combined_token_accounting')},ensure_ascii=False))


if __name__=='__main__':main()
