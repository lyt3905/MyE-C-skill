"""DeepSeek title rules adapted solely from the standalone title-rewriter reference."""
import hashlib,json,re,time,urllib.error
from pathlib import Path
from mye_c_automation.resources import resource_path
from mye_c_automation.job_manager import atomic_json
from mye_c_automation.product_state import canonical_state_hash
from mye_c_automation.ai_judge.client import parse_json_content

PREFIX={4:'In Stock',7:'Hot Sale'}
SUFFIX='Action Figures Collection Gifts'
def prompt():return resource_path('prompts/title_rewrite.deepseek.md').read_text(encoding='utf-8')

def make_messages(product,shop,*,confirmed_facts=()):
    if shop not in PREFIX:raise ValueError('UNKNOWN_SHOP')
    if not isinstance(product.get('title'),str) or not product['title'].strip():raise ValueError('ORIGINAL_TITLE_MISSING')
    data={k:product[k] for k in ('title','titleEn','identityJson') if k in product}
    data['skus']=[{k:row[k] for k in ('skuName','name','modelCode') if k in row} for row in product.get('skus',[]) if isinstance(row,dict)]
    data.update(shop=shop,shop_prefix=PREFIX[shop])
    if confirmed_facts:data['confirmed_facts']=list(confirmed_facts)
    return [{'role':'system','content':prompt()},{'role':'user','content':json.dumps(data,ensure_ascii=False)}]

def parse_result(raw,shop):
    if not isinstance(raw,dict) or not isinstance(raw.get('choices'),list) or not raw['choices'] or not isinstance(raw['choices'][0],dict):raise ValueError('INVALID_COMPLETION_RESPONSE')
    choice=raw['choices'][0]
    if choice.get('finish_reason')!='stop' or not isinstance(choice.get('message'),dict):raise ValueError('MODEL_OUTPUT_INCOMPLETE')
    result=parse_json_content(choice['message']['content'])
    if not isinstance(result,dict):raise ValueError('MODEL_OUTPUT_NOT_OBJECT')
    title=result.get('titleEn')
    if not isinstance(title,str) or not title.strip() or len(title)>120 or title!=title.strip() or '\n' in title or '\r' in title or not title.startswith(PREFIX[shop]+' ') or not title.endswith(' '+SUFFIX):raise ValueError('INVALID_TITLE_FORMAT_OR_LENGTH')
    if re.search(r'\b(?:Megatron|Hasbro)\b',title,re.I):raise ValueError('FORBIDDEN_TITLE_WORD')
    warnings=result.get('warnings',[]);model=result.get('modelCode')
    if not isinstance(warnings,list) or any(not isinstance(w,str) for w in warnings):raise ValueError('INVALID_WARNINGS')
    if model is not None and (not isinstance(model,str) or not model.strip()):raise ValueError('INVALID_MODEL_CODE')
    return dict(titleEn=title,modelCode=model,warnings=warnings)

def _candidate(record,product):
    source=dict(type='DEEPSEEK_TITLE',sha256=canonical_state_hash(product))
    base=dict(remedy_id='V2_TITLE',item_id='V2_TITLE',target={'field':'titleEn'},source=source,checks={},evidence_ids=['title_generation.json'],v2_contract=True,title_generation=True)
    if record['status']=='FAILED':return dict(base,action='WEB_DEFER',reason_codes=['TITLE_'+record['status']]+record.get('reason_codes',[]))
    if record['result']['titleEn']==product.get('titleEn'):return dict(base,action='KEEP',reason_codes=['TITLE_UNCHANGED'])
    return dict(base,action='TITLE_REWRITE',titleEn=record['result']['titleEn'],checks={'title_rules_pass':True,'source_bound':True,'first_valid_response':True},reason_codes=['DEEPSEEK_REFERENCE_TITLE_RULES'])

def prepare_title(directory,job,policy,judge=None):
    if not policy.permits('TITLE_REWRITE'):return []
    root=Path(directory);product=json.loads((root/'audit_product.json').read_text(encoding='utf-8'));record_path=root/'title_generation.json'
    owned=None;start_call=len(judge.metrics['calls']) if judge is not None else 0
    try:
        if judge is None:
            from mye_c_automation.budget_manager import BudgetManager
            from mye_c_automation.ai_judge import JudgeClient
            owned=BudgetManager(job['budget'],root/'budget.sqlite')
            if 'model_budget' in job:owned.configure_model_budget(job['model_budget'],job['job_id'])
            judge=JudgeClient(owned,root/'judge_cache',**({'config':job['model_config']} if 'model_config' in job else {}))
        facts=policy.config.get('title_rewrite',{}).get('confirmed_facts',[])
        try:messages=make_messages(product,job['shop_id'],confirmed_facts=facts)
        except (ValueError,TypeError,KeyError) as exc:
            record=dict(status='FAILED',reason_codes=[str(exc)],calls=[],source_state_sha256=canonical_state_hash(product));atomic_json(record_path,record);return [_candidate(record,product)]
        settings=dict(base_url=judge.base_url,models=list(judge.models),max_tokens=judge.max_output_tokens,reasoning_effort=judge.reasoning_effort,timeout=judge.timeout)
        fingerprint=hashlib.sha256(json.dumps(dict(messages=messages,settings=settings),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if record_path.exists():
            record=json.loads(record_path.read_text(encoding='utf-8'))
            if record.get('fingerprint')!=fingerprint or record.get('source_state_sha256')!=canonical_state_hash(product):raise ValueError('TITLE_FROZEN_INPUT_CHANGED')
            if record['status'] in {'GENERATED','REVIEW_REQUIRED'}:
                row=_candidate(record,product)
                if row['action']=='TITLE_REWRITE':verify_title(root,row,product)
                return [row]
        else:record=dict(status='FAILED',fingerprint=fingerprint,source_state_sha256=canonical_state_hash(product),shop=job['shop_id'],prompt_sha256=hashlib.sha256(messages[0]['content'].encode()).hexdigest(),settings=settings,confirmed_facts=facts,calls=[])
        (root/'title_generation.prompt.md').write_text(messages[0]['content'],encoding='utf-8')
        options=policy.config.get('title_rewrite',{});retries=options.get('retries',2)
        for attempt in range(1,retries+2):
            call=dict(attempt=len(record['calls'])+1,status='FAILED',usage=None);record['calls'].append(call)
            try:
                raw=judge.generate_title(messages,pid=job['pid'],attempt=attempt);call['raw_response']=raw;call['usage']=raw.get('usage') if isinstance(raw,dict) else None
                result=parse_result(raw,job['shop_id']);call['status']='SUCCEEDED'
                record.update(result=result,status='GENERATED');record.pop('reason_codes',None)
                atomic_json(record_path,record);break
            except (OSError,ValueError,TypeError,KeyError,IndexError,RuntimeError) as exc:
                error='HTTP_'+str(exc.code) if isinstance(exc,urllib.error.HTTPError) else type(exc).__name__
                call['error']=error;record.update(status='FAILED',reason_codes=[error]);atomic_json(record_path,record)
                permanent=isinstance(exc,urllib.error.HTTPError) and exc.code not in {408,409,425,429} and exc.code<500
                if permanent or attempt>retries:break
                time.sleep(min(options.get('retry_delay',1)*2**(attempt-1),30))
        return [_candidate(record,product)]
    finally:
        if judge is not None:
            fresh=[c for c in judge.metrics['calls'][start_call:] if c.get('task_type')=='title_rewrite']
            if fresh:
                path=root/'title_ai_metrics.json'
                previous=json.loads(path.read_text(encoding='utf-8'))['calls'] if path.exists() else []
                atomic_json(path,dict(calls=previous+fresh))
        if owned is not None:owned.close()

def validate_title_candidate(row):
    if row.get('action')!='TITLE_REWRITE' or row.get('title_generation') is not True or row.get('target')!={'field':'titleEn'} or any(row.get('checks',{}).get(k) is not True for k in ('title_rules_pass','source_bound','first_valid_response')):raise ValueError('TITLE_CANDIDATE_INVALID')
    return row

def verify_title(directory,row,product):
    validate_title_candidate(row);root=Path(directory);record=json.loads((root/'title_generation.json').read_text(encoding='utf-8'))
    if record['status'] not in {'GENERATED','REVIEW_REQUIRED'} or record['source_state_sha256']!=canonical_state_hash(product) or row['source']!={'type':'DEEPSEEK_TITLE','sha256':canonical_state_hash(product)}:raise ValueError('TITLE_SOURCE_UNBOUND')
    if record['prompt_sha256']!=hashlib.sha256(prompt().encode()).hexdigest() or (root/'title_generation.prompt.md').read_text(encoding='utf-8')!=prompt():raise ValueError('TITLE_PROMPT_CHANGED')
    messages=make_messages(product,record['shop'],confirmed_facts=record.get('confirmed_facts',[]))
    fingerprint=hashlib.sha256(json.dumps(dict(messages=messages,settings=record['settings']),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if record['fingerprint']!=fingerprint:raise ValueError('TITLE_INPUT_BINDING')
    first=None
    for call in record['calls']:
        if 'raw_response' not in call:continue
        try:first=parse_result(call['raw_response'],record['shop']);break
        except (ValueError,TypeError,KeyError,IndexError):continue
    if first!=record['result'] or first is None or first['titleEn']!=row['titleEn']:raise ValueError('TITLE_RESPONSE_UNBOUND')
    return first

def summary(directory):
    root=Path(directory);path=root/'title_generation.json'
    if not path.exists():return {'status':'DISABLED'}
    r=json.loads(path.read_text(encoding='utf-8'))
    read=lambda name:json.loads((root/name).read_text(encoding='utf-8')) if (root/name).exists() else {}
    proposed=r.get('result',{}).get('titleEn');plan=read('plan.v2.json');checked=read('independent_verification.json')
    applied=('TITLE_REWRITE' in plan.get('automation',{}).get('actions',[]) and read('apply_receipt.json').get('apply_status')=='APPLY_MATCHED' and checked.get('ok') is True and checked.get('title_exact') is True)
    return dict(status=r['status'],attempts=len(r['calls']),**r.get('result',{}),reason_codes=r.get('reason_codes',[]),changed=proposed is not None and proposed!=read('audit_product.json').get('titleEn'),applied=applied)
