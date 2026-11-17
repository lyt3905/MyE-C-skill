"""Local, bounded inpainting only. No model client, job, network or product I/O."""
import cv2
import numpy as np
import hashlib
import json
import base64
from pathlib import Path


def _local_inpaint(original,mask,chosen,policy,lama,cache_dir):
    backend=(getattr(lama,'model_sha256',None) if chosen=='LAMA_INPAINT' else cv2.__version__)
    cache=None;key=None
    if cache_dir is not None and backend:
        from mye_c_automation.ai_judge.cache import ResultCache
        implementation=hashlib.sha256(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py')))+
            (Path(__file__).parents[1]/'image_repairs_v2.py').read_bytes()).hexdigest()
        binding=dict(source=hashlib.sha256(original.tobytes()).hexdigest(),mask=hashlib.sha256(mask.tobytes()).hexdigest(),
            shape=original.shape,algorithm=chosen,policy=policy,backend=backend,implementation=implementation)
        key=hashlib.sha256(json.dumps(binding,sort_keys=True).encode()).hexdigest();cache=ResultCache(cache_dir)
        try:
            saved=cache.get(key);raw=base64.b64decode(saved['pixels'],validate=True)
            if len(raw)!=original.size or hashlib.sha256(raw).hexdigest()!=saved['sha256']:raise ValueError('REPAIR_CACHE_CHANGED')
            return np.frombuffer(raw,dtype=np.uint8).reshape(original.shape).copy(),True,key
        except (ValueError,TypeError,KeyError,OSError):pass
    if chosen=='LAMA_INPAINT':
        if lama is None:raise RuntimeError('LAMA_UNAVAILABLE')
        candidate=lama(original.copy(),mask.copy())
    else:candidate=cv2.inpaint(original,mask,policy['radius'],cv2.INPAINT_TELEA if chosen=='OPENCV_TELEA' else cv2.INPAINT_NS)
    if not isinstance(candidate,np.ndarray) or candidate.shape!=original.shape or candidate.dtype!=np.uint8:raise ValueError('INVALID_INPAINT_OUTPUT')
    if cache is not None:
        raw=candidate.tobytes();cache.put(key,dict(pixels=base64.b64encode(raw).decode(),sha256=hashlib.sha256(raw).hexdigest()),lambda _:None)
    return candidate,False,key


class RepairRouter:
    def select(self,parsed,region,policy,algorithm=None):
        mask=region['mask'];x0,y0,x1,y1=region['roi'];count=np.count_nonzero(mask)
        mask_area=float(count/mask.size);roi_area=(x1-x0)*(y1-y0)/mask.size
        translucent=any(m.get('opacity',1)<1 for m in region['marks'])
        overlap=any(m.get('subject_overlap') is True for m in region['marks'])
        simple=(parsed.request.get('background_complexity')=='SMOOTH' and not translucent and not overlap
                and mask_area<=policy['opencv_max_mask_area'] and roi_area<=policy['opencv_max_roi_area'])
        chosen='OPENCV_TELEA' if simple else 'LAMA_INPAINT'
        reason='SMALL_SIMPLE_BACKGROUND' if simple else 'COMPLEX_LARGE_TRANSLUCENT_OR_SUBJECT'
        if algorithm is not None:
            if algorithm not in {'OPENCV_TELEA','OPENCV_NS','LAMA_INPAINT'}:raise ValueError('UNKNOWN_INPAINT_ALGORITHM')
            if not simple and algorithm!='LAMA_INPAINT':raise ValueError('UNSUITABLE_ALGORITHM')
            chosen=algorithm;reason='EXPLICIT_BOUNDED_WORKFLOW_ALTERNATE'
        return chosen,dict(reason=reason,mask_area=mask_area,roi_area=roi_area,mask_density=float(count/max(1,(x1-x0)*(y1-y0))),
            translucent=translucent,subject_overlap=overlap)


class InpaintingEngine:
    def __init__(self):self.records=[]

    def run(self,parsed,regions,policy,*,lama=None,algorithm=None,cache_dir=None):
        output=parsed.pixels.copy();records=self.records;router=RepairRouter()
        for region in regions:
            chosen,route=router.select(parsed,region,policy,algorithm)
            x0,y0,x1,y1=region['roi'];original=parsed.pixels[y0:y1,x0:x1].copy();mask=region['mask'][y0:y1,x0:x1].copy()
            # Every batch starts from original context. Backend changes outside
            # its local mask are discarded, including all future instances.
            record=dict(region_id=region['region_id'],group_id=region['group_id'],instance_ids=region['instance_ids'],
                roi=region['roi'],algorithm=chosen,routing_reason=route,mask_pixels=int(np.count_nonzero(mask)),
                parameters=dict(radius=policy['radius'],context_pixels=policy['context_pixels']),
                model_version=(getattr(lama,'model_sha256',None) or 'INJECTED_BACKEND') if chosen=='LAMA_INPAINT' else cv2.__version__,status='RUNNING')
            records.append(record)
            try:
                candidate,hit,key=_local_inpaint(original,mask,chosen,policy,lama,cache_dir)
                output[y0:y1,x0:x1][mask>0]=candidate[mask>0]
                record.update(status='PROCESSED',cache_hit=hit,cache_key=key)
                if chosen=='LAMA_INPAINT':record['model_version']=getattr(lama,'model_sha256',None) or 'INJECTED_BACKEND'
            except (ValueError,OSError,RuntimeError,ImportError,TypeError,cv2.error) as exc:
                record.update(status='FAILED',failure_reason=str(exc),error_type=type(exc).__name__);raise
        return output,records
