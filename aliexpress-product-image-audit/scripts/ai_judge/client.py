"""Strict, queue-only AI judgement client. Never mutates products."""
import base64
import hashlib
import json
import os
import re
import time
from threading import BoundedSemaphore
import urllib.request
import urllib.error
from pathlib import Path

from .schemas import validate_result
from .cache import cache_key, ResultCache
from concurrent.futures import ThreadPoolExecutor
from threading import RLock
from PIL import Image
import io

COMMON_OUTPUT_CONTRACT = (' Return one JSON object. task_type must exactly equal the supplied item.task_type; '
                          'item_id must exactly equal the supplied item.id. '
                          'confidence must be a JSON number from 0 to 1, not a string or percentage. '
                          'abstain must be a JSON boolean. evidence_ids must be a non-empty array of strings containing '
                          'only IDs from the supplied item.evidence_ids. '
                          'For non-watermark tasks, decision must be one of MATCH, MISMATCH, UNCERTAIN. '
                          'For watermark tasks, return classification, owner, location as specified by the task contract; do not return decision.')

def safe_payload(item, context):
    allowed={'id','item_id','task_type','image_id','pool','kind','index','sha256','sku_id','sku_name','reason','evidence_ids','purpose','dimensions','proposed_title'}
    safe_item={k:v for k,v in item.items() if k in allowed}
    # Image-derived annotations only. Neither the product Description nor price
    # fields enter this channel. OCR text is observation, never an instruction.
    import math
    for field in ('observed_text_regions','reference_text_regions'):
        if field not in item:continue
        regions=[]
        for row in item[field] if isinstance(item[field],list) else []:
            if not isinstance(row,dict):continue
            rect=row.get('rect');score=row.get('score');value=row.get('text')
            if (not isinstance(value,str) or type(score) not in (int,float) or not math.isfinite(score) or not 0<=score<=1
                    or not isinstance(rect,list) or len(rect)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in rect)):continue
            regions.append({'text':value[:250],'score':score,'rect':rect})
        safe_item[field]=regions[:30]
    if type(item.get('shared_across_skus')) is bool:safe_item['shared_across_skus']=item['shared_across_skus']
    safe_context={k:v for k,v in context.items() if k in {'pid','shop','title','titleEn','titleTranslationZh','brand','brandId','product_type','model'}}
    identity=context.get('identityJson') or {}
    if isinstance(identity,str):
        try: identity=json.loads(identity)
        except ValueError: identity={}
    if isinstance(identity,dict): safe_context['identityJson']={k:v for k,v in identity.items() if k in {'modelCode','logoCode'}}
    safe_context['skus']=[{k:v for k,v in row.items() if k in {'skuId','id','skuName','name','color','modelCode'}} for row in context.get('skus',[]) if isinstance(row,dict)]
    return {'item':safe_item,'context':safe_context}

def validate(result, task, item):
    return validate_result(result,task,item)

def parse_json_content(content):
    """Accept JSON or one complete JSON code fence, without extracting prose."""
    if not isinstance(content, str):
        raise TypeError('response content must be text')
    content = content.strip()
    fence = re.fullmatch(r'```(?:json)?[ \t]*\r?\n(.*?)\r?\n```', content, re.DOTALL)
    if fence:
        content = fence.group(1)
    return json.loads(content)

def _http_failure_details(exc):
    """Keep status and a known failure category, never raw upstream text/secrets."""
    details={'http_status':exc.code}
    try:
        error=json.loads(exc.read(8192)).get('error',{})
        message=error.get('message','') if isinstance(error,dict) else ''
        if (exc.code==502 and isinstance(message,str) and 'empty reply' in message.lower()
                and 'reasoning' in message.lower()):
            details['provider_error_code']='OUTPUT_LIMIT_EXHAUSTED'
    except (ValueError,TypeError,AttributeError,OSError):
        pass
    return details

def _same_store_remove_consensus(outputs, models):
    """Different seller-mark subtypes can agree under the existing removal policy."""
    if len(outputs)!=2 or len(models)!=2 or len(set(models))!=2:return False
    from policy_engine import REMOVE
    if any(r.get('task_type')!='watermark' or r.get('classification') not in REMOVE for r in outputs):return False
    if any(r.get('abstain') is not False or r.get('confidence',0)<.9 for r in outputs):return False
    owners=[r.get('owner') for r in outputs]
    if any(not isinstance(owner,str) or not owner.strip() for owner in owners):return False
    owners=[owner.strip().casefold() for owner in owners]
    placeholders={'unknown','uncertain','store','seller','shop','manufacturer','third party',
                  'third-party','third_party','third_party_store','unknown owner','n/a','none',
                  '未知','不确定','店铺','商家','卖家','第三方店铺'}
    return owners[0]==owners[1] and owners[0] not in placeholders

class JudgeClient:
    def __init__(self, budget, cache_dir, transport=None, models=('glm-5v-turbo','kimi-k3-1'), retries=2, timeout=150, config=None):
        self.config_sha256=None
        self.base_url=os.environ.get('VLM_BASE','http://127.0.0.1:8788/v1')
        if config is not None:
            from model_config import validate_config,fingerprint
            config=validate_config(config)
            self.base_url=config['base_url']
            models=tuple(config['models']);retries=config['retries'];timeout=config['timeout']
            self.config_sha256=fingerprint(config)
        output_limit=str(config['max_output_tokens']) if config is not None else os.environ.get('VLM_MAX_OUTPUT_TOKENS','2000')
        if not output_limit.isascii() or not output_limit.isdecimal() or not 1<=int(output_limit)<=16384:
            raise ValueError('VLM_MAX_OUTPUT_TOKENS must be an integer from 1 to 16384')
        self.max_output_tokens=int(output_limit)
        self.semaphore=BoundedSemaphore(4)
        self._viewed=set()
        from threading import Lock
        self._view_lock=Lock()
        self._metrics_lock=RLock()
        self.workers=4
        self.result_cache=ResultCache(cache_dir)
        self.budget, self.cache = budget, Path(cache_dir)
        self.cache.mkdir(parents=True,exist_ok=True)
        self.transport = transport or self._request
        self.models, self.retries, self.timeout = models, min(retries,2), timeout
        self.metrics = {'requests':0,'retries':0,'cache_hits':0,'prompt_tokens':0,'completion_tokens':0,'total_tokens':0,'usage_available':True,'visual_inputs':[],
                        'models':list(models),'max_output_tokens':self.max_output_tokens,'calls':[]}
        if config is not None:self.metrics.update(base_url=self.base_url,model_config_sha256=self.config_sha256)
    def _request(self, model, item, context):
        key = os.environ.get('VLM_API_KEY')
        if not key: raise ValueError('VLM_API_KEY required')
        from importlib import import_module
        task_prompt=import_module('ai_judge.'+item['task_type']).PROMPT
        output_prompt = '' if item['task_type']=='watermark' else ' Return JSON task_type,item_id,decision MATCH/MISMATCH/UNCERTAIN,confidence,abstain,evidence_ids.'
        prompt = task_prompt+' Classify evidence. Preserve social signatures, manufacturer branding, product print, photographer credits. Unknown ownership must abstain.'+output_prompt+COMMON_OUTPUT_CONTRACT+' No write instructions. '+json.dumps(safe_payload(item,context),ensure_ascii=False)
        content=[{'type':'text','text':prompt}]
        if item.get('local'):
            sent,metadata=prepare_image(item['local'])
            metadata.update(item_id=item['id'],task_type=item['task_type'],model=model)
            with self._metrics_lock: self.metrics['visual_inputs'].append(metadata)
            content.append({'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(sent).decode()}})
        for extra in item.get('extra_images',[]):
            sent,metadata=prepare_image(extra['path'])
            if metadata['original_sha256']!=extra['sha256']: raise ValueError('comparison image changed')
            content.append({'type':'text','text':extra['image_id']})
            content.append({'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(sent).decode()}})
        body={'model':model,'temperature':0,'max_tokens':self.max_output_tokens,'response_format':{'type':'json_object'},'messages':[{'role':'user','content':content}]}
        req=urllib.request.Request(self.base_url+'/chat/completions',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=self.timeout) as response: return json.load(response)
    def classify(self, task_type, evidence, context):
        outputs=[]
        evidence=dict(evidence)
        for comparison in evidence.get('extra_images',[]):
            try:actual=hashlib.sha256(Path(comparison['path']).read_bytes()).hexdigest()
            except (OSError,KeyError,TypeError):return {'status':'NEEDS_REVIEW','error':'comparison evidence unavailable','results':[]}
            if actual!=comparison.get('sha256'):
                return {'status':'NEEDS_REVIEW','error':'comparison evidence hash mismatch','results':[]}
        if evidence.get("local"):
            actual=hashlib.sha256(Path(evidence["local"]).read_bytes()).hexdigest()
            if evidence.get("sha256") and evidence["sha256"] != actual:
                return {"status":"NEEDS_REVIEW","error":"evidence hash mismatch","results":[]}
            evidence["sha256"]=actual
        for model in self.models:
            cache_started=time.perf_counter()
            cache_options={'policy_version':'v2:gateway:'+self.config_sha256} if self.config_sha256 else {}
            key=cache_key(task_type,evidence,context,model,**cache_options)
            path=self.cache/(key+'.json')
            if path.exists():
                try:
                    cached=self.result_cache.get(key)
                    cached['item_id']=evidence['id']
                    cached['evidence_ids']=evidence.get('evidence_ids',[])
                    if task_type=='sku_match': cached.update({k:evidence[k] for k in ('sku_id','image_id')})
                    outputs.append(validate_result(cached,task_type,evidence['id'],evidence))
                    with self._metrics_lock:
                        self.metrics['cache_hits']+=1
                        self.metrics['calls'].append({'item_id':evidence['id'],'task_type':task_type,'model':model,
                            'status':'CACHE_HIT','called':False,'usage_status':'NOT_CALLED','total_tokens':None,
                            'elapsed_ms':round((time.perf_counter()-cache_started)*1000,3),'result':dict(cached)})
                    continue
                except (ValueError,KeyError): pass
            for attempt in range(self.retries+1):
                token_reservation=None
                sent=False
                attempt_started=time.perf_counter()
                event={'item_id':evidence['id'],'task_type':task_type,'model':model,'attempt':attempt+1,
                       'status':'NOT_CALLED','called':False,'usage_status':'NOT_CALLED','total_tokens':None}
                try:
                    token_cost=None
                    if 'total_tokens' in self.budget.snapshot()['limits']:
                        token_cost=self.max_output_tokens + len(json.dumps(safe_payload(evidence,context)).encode('utf-8')) + 4096 * (1+len(evidence.get('extra_images',[])))
                    with self._view_lock:
                        digests=({evidence['sha256']}|{r['sha256'] for r in evidence.get('extra_images',[])}) if evidence.get('local') else set()
                        new=digests-self._viewed
                        token_reservation=self.budget.reserve_call(token_cost,len(new))
                        self._viewed.update(new)
                    with self._metrics_lock:
                        self.metrics['requests']+=1
                        if attempt: self.metrics['retries']+=1
                    with self.semaphore:
                        sent=True
                        event.update(called=True,status='REQUESTED',usage_status='UNKNOWN')
                        raw=self.transport(model,evidence,context)
                    observed_usage=raw.get('usage')
                    if isinstance(observed_usage,dict) and all(type(observed_usage.get(k)) is int and observed_usage[k]>=0 for k in ('prompt_tokens','completion_tokens','total_tokens')):
                        tokens=observed_usage['total_tokens']
                        event.update(usage_status='ACTUAL_ZERO' if tokens==0 else 'ACTUAL_REPORTED',total_tokens=tokens)
                    with self._metrics_lock:
                        usage=raw.get('usage')
                        if not isinstance(usage,dict) or any(type(usage.get(k)) is not int or usage[k]<0 for k in ('prompt_tokens','completion_tokens','total_tokens')):
                            self.metrics['usage_available']=False
                            for k in ('prompt_tokens','completion_tokens','total_tokens'): self.metrics[k]=None
                        elif self.metrics['usage_available']:
                            for k in ('prompt_tokens','completion_tokens','total_tokens'): self.metrics[k]+=usage[k]
                    if token_reservation is not None:
                        # Settle this response's usage even if another in-flight
                        # call made the aggregate unknown. The budget retains
                        # its UNKNOWN latch while preserving known subtotals.
                        self.budget.settle_tokens(token_reservation,event['total_tokens'])
                    token_reservation=None
                    result=validate_result(parse_json_content(raw['choices'][0]['message']['content']),task_type,evidence['id'],evidence)
                    if not set(result['evidence_ids']) <= set(evidence.get('evidence_ids',[])): raise ValueError('unbound evidence')
                    event.update(status='VALIDATED',result=dict(result))
                    self.result_cache.put(key,result,lambda r: validate(r,task_type,evidence['id'])); outputs.append(result); break
                except Exception as exc:
                    from budget_manager import BudgetExceeded
                    event.update(status='ERROR',error_type=type(exc).__name__)
                    failure_details=_http_failure_details(exc) if isinstance(exc,urllib.error.HTTPError) else {}
                    event.update(failure_details)
                    if isinstance(exc,BudgetExceeded) and not event['called']:
                        event.update(status='BUDGET_BLOCKED',usage_status='BUDGET_BLOCKED')
                    if token_reservation is not None and not sent:
                        self.budget.release_tokens(token_reservation)
                        token_reservation=None
                    if event['called'] and event['usage_status']=='UNKNOWN':
                        with self._metrics_lock:
                            self.metrics['usage_available']=False
                            for name in ('prompt_tokens','completion_tokens','total_tokens'):self.metrics[name]=None
                        if token_reservation is not None and 'total_tokens' in self.budget.snapshot()['limits']:
                            self.budget.mark_tokens_unknown()
                    if isinstance(exc, BudgetExceeded):
                        return {'status':'NEEDS_REVIEW','error':'BUDGET_EXCEEDED','blocked_reason':str(exc),'results':outputs}
                    if isinstance(exc, (ValueError, KeyError, TypeError)):
                        return {'status':'NEEDS_REVIEW','error':type(exc).__name__,'results':outputs}
                    if attempt == self.retries:
                        return {'status':'NEEDS_REVIEW','error':type(exc).__name__,'results':outputs,**failure_details}
                finally:
                    event['elapsed_ms']=round((time.perf_counter()-attempt_started)*1000,3)
                    with self._metrics_lock:self.metrics['calls'].append(event)
        classifications=[r.get('classification',r.get('decision')) for r in outputs]
        store_consensus=len(set(classifications))!=1 and _same_store_remove_consensus(outputs,self.models)
        review=any(r['abstain'] or r['confidence'] < .9 for r in outputs) or len(set(classifications)) != 1 and not store_consensus or any(x in {'unknown','UNCERTAIN'} for x in classifications)
        if task_type=='watermark':
            from policy_engine import KEEP,REMOVE
            review=review or any(value not in KEEP|REMOVE for value in classifications)
            status='REVIEW' if review else 'HIT' if store_consensus or classifications[0] in REMOVE else 'CLEAN'
        else:
            status='REVIEW' if review else 'HIT' if classifications[0]=='MISMATCH' else 'CLEAN'
        return {'status':status,'results':outputs}
    def process_queue(self, queue, context):
        if queue.get('schema') != 'ai-queue/v2' or queue.get('pid') != context.get('pid'): raise ValueError('invalid queue')
        def run(item):
            if item.get('reason') == 'MISSING_IMAGE': return item['id'], {'status':'NEEDS_REVIEW','error':'missing SKU image','results':[]}
            return item['id'], self.classify(item['task_type'],item,context)
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            return dict(sorted(pool.map(run,queue['items'])))


def prepare_image(path):
    original=Path(path).read_bytes()
    with Image.open(io.BytesIO(original)) as image:
        image.load()
        original_format=image.format
        width,height=image.size
        buf=io.BytesIO()
        image.convert('RGB').save(buf,format='JPEG',quality=95)
    sent=buf.getvalue()
    return sent,{'original_sha256':hashlib.sha256(original).hexdigest(),'sent_sha256':hashlib.sha256(sent).hexdigest(),'original_format':original_format,'sent_format':'JPEG','mime':'image/jpeg','width':width,'height':height,'sent_bytes':len(sent)}
