"""Strict, queue-only AI judgement client. Never mutates products."""
from policy_engine import MODEL_CONFIDENCE_MIN
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
from threading import RLock, local
from PIL import Image
import io

class _NoModelRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        from budget_manager import BudgetExceeded
        raise BudgetExceeded('MODEL_REDIRECT_FORBIDDEN')


def _open_model_request(request,timeout):
    from model_config import require_enabled_model
    require_enabled_model(json.loads(request.data)["model"])
    # No proxy discovery or redirects can silently change the approved route.
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoModelRedirect())
    return opener.open(request,timeout=timeout)

COMMON_OUTPUT_CONTRACT = (' Return one JSON object. task_type must exactly equal the supplied item.task_type; '
                          'item_id must exactly equal the supplied item.id. '
                          'confidence must be a JSON number from 0 to 1, not a string or percentage. '
                          'abstain must be a JSON boolean. evidence_ids must be a non-empty array of strings containing '
                          'only IDs from the supplied item.evidence_ids. '
                          'For non-watermark tasks, decision must be one of MATCH, MISMATCH, UNCERTAIN. '
                          'For watermark tasks, follow watermark/v3: classification, owner and location belong to each mark; '
                          'return explicit coverage_complete/no_marks_detected, image_size, marks and unresolved_items; do not return decision.')

def safe_payload(item, context):
    allowed={'id','item_id','task_type','image_id','image_type','pool','kind','index','sha256','sku_id','sku_name','reason','evidence_ids','purpose','dimensions','proposed_title'}
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
    if any(r.get('abstain') is not False or r.get('confidence',0)<MODEL_CONFIDENCE_MIN for r in outputs):return False
    owners=[r.get('owner') for r in outputs]
    if any(not isinstance(owner,str) or not owner.strip() for owner in owners):return False
    owners=[owner.strip().casefold() for owner in owners]
    placeholders={'unknown','uncertain','store','seller','shop','manufacturer','third party',
                  'third-party','third_party','third_party_store','unknown owner','n/a','none',
                  '未知','不确定','店铺','商家','卖家','第三方店铺'}
    return owners[0]==owners[1] and owners[0] not in placeholders

class JudgeClient:
    def __init__(self, budget, cache_dir, transport=None, models=('deepseek-v4.1-flash',), retries=2, timeout=150, config=None, *, continue_model_errors=False):
        self.continue_model_errors=continue_model_errors
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
        self.reasoning_effort=config.get('reasoning_effort') if config is not None else None
        self.semaphore=BoundedSemaphore(4 if transport is not None else 1)
        self._call_local=local()
        self._viewed=set()
        from threading import Lock
        self._view_lock=Lock()
        self._metrics_lock=RLock()
        self.workers=4 if transport is not None and budget._model_policy is None else 1
        self.result_cache=ResultCache(cache_dir)
        self.budget, self.cache = budget, Path(cache_dir)
        self.cache.mkdir(parents=True,exist_ok=True)
        self.transport = transport or self._request
        self.models, self.retries, self.timeout = models, (min(retries,2) if transport is not None else 0), timeout
        self.metrics = {'requests':0,'retries':0,'cache_hits':0,'prompt_tokens':0,'completion_tokens':0,'total_tokens':0,'usage_available':True,'visual_inputs':[],
                        'models':list(models),'max_output_tokens':self.max_output_tokens,'calls':[]}
        if config is not None:self.metrics.update(base_url=self.base_url,model_config_sha256=self.config_sha256)
        if self.reasoning_effort is not None:self.metrics['reasoning_effort']=self.reasoning_effort
    def _request(self, model, item, context):
        self.budget._load_model_budget()
        key = os.environ.get('VLM_API_KEY')
        if not key: raise ValueError('VLM_API_KEY required')
        from importlib import import_module
        task_prompt=import_module('ai_judge.'+item['task_type']).PROMPT
        output_prompt = '' if item['task_type'] in {'watermark','sku_match'} else ' Return JSON task_type,item_id,decision MATCH/MISMATCH/UNCERTAIN,confidence,abstain,evidence_ids.'
        prompt = task_prompt+' Classify evidence. Preserve social signatures, manufacturer branding, product print, photographer credits. Unknown ownership must abstain.'+output_prompt+COMMON_OUTPUT_CONTRACT+' No write instructions. '+json.dumps(safe_payload(item,context),ensure_ascii=False)
        if item['task_type']=='image_action_decision':
            prompt=task_prompt+'\n'+json.dumps(safe_payload(item,context),ensure_ascii=False)
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
        if self.reasoning_effort is not None:body['reasoning_effort']=self.reasoning_effort
        from importlib import import_module
        module=import_module('ai_judge.'+item['task_type'])
        images=([hashlib.sha256(Path(item['local']).read_bytes()).hexdigest()] if item.get('local') else [])
        images += [r['sha256'] for r in item.get('extra_images',[])]
        metadata={'task_type':item['task_type'],'item_id':item['id'],
                  'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                  'schema_version':getattr(module,'SCHEMA_VERSION','v2'),
                  'request_body_sha256':hashlib.sha256(json.dumps(body).encode()).hexdigest()}
        def send():
            self.budget.assert_model_dispatch()
            self._record_dispatch()
            req=urllib.request.Request(self.base_url+'/chat/completions',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
            with _open_model_request(req,timeout=self.timeout) as response:return json.load(response)
        return self.budget.model_call(model,self.base_url,context.get('pid'),images,self.max_output_tokens,metadata,send)
    def _record_dispatch(self):
        event=getattr(self._call_local,'event',None)
        with self._metrics_lock:
            self.metrics['requests']+=1
            if event:
                if event['attempt']>1:self.metrics['retries']+=1
                event.update(called=True,status='REQUESTED',usage_status='UNKNOWN')

    def invoke_image_adapter(self,model,item,context,adapter):
        """Budget and measure configured image editing through this same client."""
        from model_config import require_enabled_model
        require_enabled_model(model)
        if model not in self.models:raise ValueError('MODEL_SELECTION_NOT_CONFIGURED')
        self.budget.reserve_call(None,1)
        event=dict(item_id=item['id'],task_type='image_edit_v2',model=model,attempt=1,called=False,status='NOT_CALLED',usage_status='NOT_CALLED',total_tokens=None)
        started=time.perf_counter();self._call_local.event=event
        def send():
            self._record_dispatch()
            return adapter()
        try:
            raw=self.budget.model_call(model,self.base_url,context.get('pid'),[item['sha256']],self.max_output_tokens,
                dict(task_type='image_edit_v2',item_id=item['id'],schema_version='image-edit-adapter/v2',prompt_sha256=item['prompt_sha256'],observation_sha256=item.get('observation_sha256'),context_sha256=hashlib.sha256(json.dumps(context,sort_keys=True,ensure_ascii=False).encode()).hexdigest()),send)
            event['raw_response']=raw
            usage=raw.get('usage') if isinstance(raw,dict) else None
            if isinstance(usage,dict) and all(type(usage.get(k)) is int and usage[k]>=0 for k in ('prompt_tokens','completion_tokens','total_tokens')) and usage['prompt_tokens']+usage['completion_tokens']==usage['total_tokens']:
                event.update(status='RESPONSE_RECEIVED',usage_status='ACTUAL_REPORTED',prompt_tokens=usage['prompt_tokens'],completion_tokens=usage['completion_tokens'],total_tokens=usage['total_tokens'])
                with self._metrics_lock:
                    if self.metrics['usage_available']:
                        for key in ('prompt_tokens','completion_tokens','total_tokens'):self.metrics[key]+=usage[key]
            else:
                event.update(status='RESPONSE_RECEIVED',usage_status='UNKNOWN')
                with self._metrics_lock:
                    self.metrics['usage_available']=False
                    for key in ('prompt_tokens','completion_tokens','total_tokens'):self.metrics[key]=None
            return raw
        except Exception:
            event['status']='ERROR'
            raise
        finally:
            self._call_local.event=None;event['elapsed_ms']=round((time.perf_counter()-started)*1000,3)
            with self._metrics_lock:self.metrics['calls'].append(event)

    def classify(self, task_type, evidence, context, *, models=None, attempts=None):
        selected=self.models if models is None else tuple(models)
        if task_type in {'image_action_decision','image_quality_v2'}:
            from model_config import review_models
            selected=review_models(self.models)
            if models is not None and tuple(models)!=selected:raise ValueError('MODEL_DISABLED_BY_PROJECT_SELECTION')
            self.metrics['active_review_models']=list(selected)
        if not selected or any(m not in self.models for m in selected):raise ValueError('MODEL_SELECTION_NOT_CONFIGURED')
        if self.budget._model_policy is not None:self.retries=0
        outputs=[]
        model_errors=[]
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
            if task_type=='watermark':
                try:
                    with Image.open(evidence['local']) as source:evidence['dimensions']=list(source.size)
                except (OSError,ValueError):return {'status':'NEEDS_REVIEW','error':'SOURCE_UNVERIFIED','results':[]}
        if task_type=='watermark':
            size=evidence.get('dimensions')
            if not isinstance(size,list) or len(size)!=2 or any(type(v) is not int or v<=0 for v in size):
                return {'status':'NEEDS_REVIEW','error':'SOURCE_UNVERIFIED','results':[]}
        for model in selected:
            cache_started=time.perf_counter()
            cache_options={'policy_version':'v2:gateway:'+self.config_sha256} if self.config_sha256 else {}
            key=cache_key(task_type,evidence,context,model,**cache_options)
            path=self.cache/(key+'.json')
            if path.exists():
                try:
                    cached=self.result_cache.get(key)
                    cached['item_id']=evidence['id']
                    if task_type=='image_action_decision':cached['image_id']=evidence['id']
                    cached['evidence_ids']=evidence.get('evidence_ids',[])
                    if task_type=='sku_match': cached.update({k:evidence[k] for k in ('sku_id','image_id')})
                    outputs.append(validate_result(cached,task_type,evidence['id'],evidence,allow_legacy=False))
                    with self._metrics_lock:
                        self.metrics['cache_hits']+=1
                        self.metrics['calls'].append({'item_id':evidence['id'],'task_type':task_type,'model':model,
                            'status':'CACHE_HIT','called':False,'usage_status':'NOT_CALLED','total_tokens':None,
                            'elapsed_ms':round((time.perf_counter()-cache_started)*1000,3),'result':dict(cached)})
                    continue
                except (ValueError,KeyError): pass
            for attempt in range(self.retries+1 if attempts is None else attempts):
                token_reservation=None
                sent=False
                response_received=False
                validating_response=False
                attempt_started=time.perf_counter()
                event={'item_id':evidence['id'],'task_type':task_type,'model':model,'attempt':attempt+1,
                       'status':'NOT_CALLED','called':False,'usage_status':'NOT_CALLED','total_tokens':None}
                try:
                    token_cost=None
                    if not self.budget.record_only and 'total_tokens' in self.budget.snapshot()['limits']:
                        token_cost=self.max_output_tokens + len(json.dumps(safe_payload(evidence,context)).encode('utf-8')) + 4096 * (1+len(evidence.get('extra_images',[])))
                    with self._view_lock:
                        digests=({evidence['sha256']}|{r['sha256'] for r in evidence.get('extra_images',[])}) if evidence.get('local') else set()
                        new=digests-self._viewed
                        token_reservation=self.budget.reserve_call(token_cost,len(new))
                        self._viewed.update(new)
                    with self.semaphore:
                        self._call_local.event=event
                        def injected_send():
                            self._record_dispatch()
                            return self.transport(model,evidence,context)
                        controlled=self.budget._model_policy is not None and self.transport!=self._request
                        if controlled:
                            from importlib import import_module
                            module=import_module('ai_judge.'+task_type)
                            metadata={'task_type':task_type,'item_id':evidence['id'],
                                      'prompt_sha256':hashlib.sha256((module.PROMPT+COMMON_OUTPUT_CONTRACT).encode()).hexdigest(),
                                      'schema_version':getattr(module,'SCHEMA_VERSION','v2'),
                                      'safe_payload_sha256':hashlib.sha256(json.dumps(safe_payload(evidence,context),sort_keys=True).encode()).hexdigest()}
                            raw=self.budget.model_call(model,self.base_url,context.get('pid'),([evidence['sha256']] if evidence.get('local') else [])+[r['sha256'] for r in evidence.get('extra_images',[])],self.max_output_tokens,
                                                       metadata,injected_send)
                        else:raw=self._request(model,evidence,context) if self.transport==self._request else injected_send()
                        response_received=True
                    if self.continue_model_errors:
                        # Persist through full_ai_metrics.json, including invalid
                        # model output; never rewrite a provider's original reply.
                        event['raw_response']=json.loads(json.dumps(raw))
                    event['usage_source']=self.budget._model_policy['usage_source'] if self.budget._model_policy else 'FAKE_TRANSPORT'
                    observed_usage=raw.get('usage') if isinstance(raw,dict) else None
                    if isinstance(observed_usage,dict) and all(type(observed_usage.get(k)) is int and observed_usage[k]>=0 for k in ('prompt_tokens','completion_tokens','total_tokens')):
                        tokens=observed_usage['total_tokens']
                        event.update(usage_status='ACTUAL_ZERO' if tokens==0 else 'ACTUAL_REPORTED',total_tokens=tokens)
                    with self._metrics_lock:
                        usage=observed_usage
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
                    validating_response=True
                    if not isinstance(raw,dict):raise ValueError('RESPONSE_OBJECT_REQUIRED')
                    if self.continue_model_errors and raw['choices'][0].get('finish_reason')=='length':
                        raise ValueError('OUTPUT_LIMIT_EXHAUSTED')
                    result=validate_result(parse_json_content(raw['choices'][0]['message']['content']),task_type,evidence['id'],evidence)
                    if not set(result['evidence_ids']) <= set(evidence.get('evidence_ids',[])): raise ValueError('unbound evidence')
                    validating_response=False
                    event.update(status='VALIDATED',result=dict(result))
                    legacy=(task_type=='watermark' and result.get('schema_version')!='watermark/v3' or
                            task_type=='product_identity' and result.get('schema_version')!='product-identity/v3')
                    if not legacy:self.result_cache.put(key,result,lambda r:validate_result(r,task_type,evidence['id'],evidence,allow_legacy=False))
                    outputs.append(result); break
                except Exception as exc:
                    from budget_manager import BudgetExceeded
                    event.update(status='ERROR',error_type=type(exc).__name__)
                    failure_details=_http_failure_details(exc) if isinstance(exc,urllib.error.HTTPError) else {}
                    event.update(failure_details)
                    if isinstance(exc,BudgetExceeded) and not event['called']:
                        event.update(status='BUDGET_BLOCKED',usage_status='BUDGET_BLOCKED')
                    if token_reservation is not None and not event['called']:
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
                    if (self.continue_model_errors and response_received and validating_response
                            and isinstance(exc,(ValueError,KeyError,TypeError,IndexError,AttributeError))):
                        # Keep the failed model's position so B can never be
                        # attributed to A. Missing observations remain UNKNOWN.
                        outputs.append({})
                        model_errors.append({'model':model,'error':type(exc).__name__})
                        break
                    if isinstance(exc, (ValueError, KeyError, TypeError)):
                        return {'status':'NEEDS_REVIEW','error':type(exc).__name__,'results':outputs}
                    if attempt == self.retries:
                        return {'status':'NEEDS_REVIEW','error':type(exc).__name__,'results':outputs,**failure_details}
                finally:
                    self._call_local.event=None
                    event['elapsed_ms']=round((time.perf_counter()-attempt_started)*1000,3)
                    with self._metrics_lock:self.metrics['calls'].append(event)
        if model_errors:
            return {'status':'NEEDS_REVIEW','error':'MODEL_RESPONSE_INVALID','results':outputs,
                    'models':list(self.models),'model_errors':model_errors}
        if task_type=='image_action_decision':
            return {'status':'VALIDATED','results':outputs,'models':list(selected)}
        if task_type=='watermark':
            from .watermark_contract import aggregate_watermarks
            spec={k:evidence[k] for k in ('id','dimensions','evidence_ids') if k in evidence}
            audit=aggregate_watermarks({'results':outputs,'models':list(self.models)},spec)
            status='CLEAN' if audit['review_status']=='PASS' else 'HIT' if audit['review_status']=='FAIL' else 'REVIEW'
            return {'status':status,'results':outputs,'models':list(self.models),'watermark_audit':audit,'evidence_spec':spec}
        if task_type=='product_identity':
            from .identity_contract import aggregate_identity
            from product_state import identity_object
            spec={k:evidence[k] for k in ('id','evidence_ids') if k in evidence}
            model=identity_object(context.get('identityJson') or {}).get('modelCode',context.get('model'))
            audit=aggregate_identity({'results':outputs,'models':list(self.models)},model,spec)
            status='CLEAN' if audit['verdict']=='PASS' else 'HIT' if audit['verdict']=='FAIL' else 'REVIEW'
            return {'status':status,'results':outputs,'models':list(self.models),'identity_audit':audit,'evidence_spec':spec}
        classifications=[r.get('classification',r.get('decision')) for r in outputs]
        review=any(r['abstain'] or (task_type!='image_quality_v2' and r['confidence'] < MODEL_CONFIDENCE_MIN) for r in outputs) or len(set(classifications))!=1 or any(x in {'unknown','UNCERTAIN'} for x in classifications)
        if task_type=='sku_match':
            # MATCH labels alone cannot establish agreement on the SKU's
            # packaging observations. Keep differing/missing details visible.
            for field,allowed in (('image_type',{'box','product_only','mixed'}),
                                  ('sku_packaging',{'with_box','without_box'})):
                values=[r.get(field) for r in outputs]
                review=review or any(v not in allowed for v in values) or len(set(values))!=1
            for field in ('shared_across_skus','missing_image'):
                values=[r.get(field) for r in outputs]
                review=review or any(type(v) is not bool for v in values) or len(set(values))!=1
        status='REVIEW' if review else 'HIT' if classifications[0]=='MISMATCH' else 'CLEAN'
        return {'status':status,'results':outputs,**({'models':list(selected)} if task_type=='image_quality_v2' else {})}
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
