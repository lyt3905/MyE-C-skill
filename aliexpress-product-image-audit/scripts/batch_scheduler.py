"""Conservative serial batch scheduling with explicit circuit-breaker outcomes."""
import time

HALT={'APPLY_UNKNOWN','BLOCKED_FATAL','STATE_DRIFT','CONTENT_REVIEW_REQUIRED','SHOP_MISMATCH','SHOP_CONTEXT_CHANGED'}

def run_batch(pids,shop,policy,run_one,*,execution=True):
    if not isinstance(pids,list) or not pids or len(pids)!=len(set(pids)):raise ValueError('INVALID_BATCH')
    for pid in pids:policy.authorize(pid,shop,[],product_count=len(pids),execution=execution)
    started=time.perf_counter();items=[];halted=False
    for pid in pids:
        try:
            result=run_one(pid,shop)
        except Exception as exc:
            # An unclassified exception may follow a successful remote write. Never continue guessing.
            result={'status':'APPLY_UNKNOWN','error':type(exc).__name__}
        items.append({'pid':pid,'shop':shop,'result':result})
        if result.get('status') in HALT or result.get('technical_status') in HALT:
            halted=True;break
    return {'schema':'auto-batch/v1','items':items,'halted':halted,'not_started':pids[len(items):],
            'elapsed_ms':round((time.perf_counter()-started)*1000,3),'write_concurrency':1}
