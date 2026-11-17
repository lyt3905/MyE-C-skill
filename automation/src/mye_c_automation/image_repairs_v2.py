"""Pixel-only V2 mask execution; semantic regions come exclusively from vision."""
import hashlib
import time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from mye_c_automation.ai_judge.image_action_decision import region, mark_disposition
from mye_c_automation.job_manager import atomic_json

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def freeze_image_edit_config(config):
    """Pin an explicitly installed local adapter; never infer a provider API."""
    from mye_c_automation.model_config import require_enabled_model
    if not isinstance(config,dict) or not {'adapter_path','model'}<=config.keys() or config.keys()-{'adapter_path','adapter_sha256','model'}:raise ValueError('INVALID_IMAGE_EDIT_CONFIG')
    require_enabled_model(config['model'])
    if not isinstance(config['adapter_path'],str):raise ValueError('INVALID_IMAGE_EDIT_ADAPTER_PATH')
    path=Path(config['adapter_path']).resolve()
    if path.suffix!='.py' or not path.is_file():raise ValueError('IMAGE_EDIT_ADAPTER_UNAVAILABLE')
    digest=sha(path)
    if config.get('adapter_sha256',digest)!=digest:raise ValueError('IMAGE_EDIT_ADAPTER_CHANGED')
    return dict(adapter_path=str(path),adapter_sha256=digest,model=config['model'])

def configured_image_edit(config,source,context,observation,destination):
    """Execute trusted configured adapter code only inside the budgeted call."""
    import types
    path=Path(config['adapter_path']);content=path.read_bytes()
    if hashlib.sha256(content).hexdigest()!=config['adapter_sha256']:raise ValueError('IMAGE_EDIT_ADAPTER_CHANGED')
    module=types.ModuleType('configured_image_edit_'+config['adapter_sha256'])
    module.__file__=str(path)
    exec(compile(content,str(path),'exec'),module.__dict__)
    adapter=getattr(module,'edit_image',None)
    if not callable(adapter):raise ValueError('IMAGE_EDIT_ADAPTER_CONTRACT')
    return adapter(source,context,observation,destination)

def pixels(path):
    with Image.open(path) as im:im.load();return np.array(im.convert('RGB'))


def known_pattern_residuals(source,candidate,observation):
    """Verify disappearance of existing AI-approved IMAGE patterns; no new labels."""
    from mye_c_automation.template_glyphs import repeated_template_strokes
    patterns=[m for m in (observation or {}).get('watermarks',[]) if mark_disposition(m)=='REMOVABLE' and m.get('repair_mode')=='TEMPLATE_GLYPHS' and m.get('glyph_search_scope')=='IMAGE']
    if not patterns:return dict(status='NOT_APPLICABLE',patterns=[])
    before=pixels(source);after=pixels(candidate);results=[];errors=[];seen=set()
    for original in patterns:
        key=tuple(original['glyph_template_bbox'])
        if key in seen:continue
        seen.add(key);mark=dict(original,glyph_template_source='ORIGINAL');proof={}
        try:
            repeated_template_strokes(after,mark,template_image=before,proof=proof)
            results.append(proof)
        except ValueError as exc:
            if str(exc)!='GLYPH_MATCH_UNPROVEN':errors.append(str(exc))
    return dict(status='REMAINS' if results else 'UNRESOLVED' if errors else 'NO_MATCH',patterns=results,errors=errors,
        source_sha256=sha(source),candidate_sha256=sha(candidate),semantic_source='EXISTING_AI_APPROVED_PATTERN_ONLY')


def _uniform_background_cleanup(source,output,mask):
    count,labels,stats,_=cv2.connectedComponentsWithStats((mask>0).astype(np.uint8),8);changed=0
    for label in range(1,count):
        x,y,w,h,area=stats[label]
        if area<5:continue
        x0,y0,x1,y1=max(0,x-4),max(0,y-4),min(mask.shape[1],x+w+4),min(mask.shape[0],y+h+4)
        part=(labels[y0:y1,x0:x1]==label).astype(np.uint8)*255
        ring=(cv2.dilate(part,np.ones((7,7),np.uint8))>0)&(mask[y0:y1,x0:x1]==0)
        samples=source[y0:y1,x0:x1][ring]
        if len(samples)<8:continue
        median=np.median(samples,axis=0)
        if np.quantile(np.linalg.norm(samples.astype(float)-median,axis=1),.95)>8:continue
        output[y0:y1,x0:x1][part>0]=np.round(median).astype(np.uint8);changed+=1
    return changed


def bright_print_pixels(image,roi):
    """Extract light ink only in an AI-designated bright-print search region."""
    if image is None:raise ValueError('PRINT_PIXELS_REQUIRED')
    low=image.min(axis=2);high=image.max(axis=2)
    gray=cv2.cvtColor(image,cv2.COLOR_RGB2GRAY)
    ink=((low>=100)&(gray>=180)&((high.astype(int)-low.astype(int))<=110)&(roi>0)).astype(np.uint8)*255
    area=int(np.count_nonzero(roi));count=int(np.count_nonzero(ink))
    if count<3 or not .001<=count/max(1,area)<=.60:raise ValueError('PRINT_GLYPHS_UNRESOLVED')
    contours,_=cv2.findContours(ink,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    filled=np.zeros_like(ink);cv2.drawContours(filled,contours,-1,255,cv2.FILLED)
    filled=cv2.dilate(filled,np.ones((3,3),np.uint8));filled[roi==0]=0
    if np.count_nonzero(filled)/max(1,area)>.75:raise ValueError('PRINT_GLYPHS_UNRESOLVED')
    return filled


def mask_for(size,observation,*,max_area=.25,dilation=2,image=None,geometry=None,inherited_mask=None,template_image=None,protection_geometry=None):
    width,height=size;mask=np.zeros((height,width),np.uint8);protected=mask.copy()
    if image is not None and image.shape[:2]!=(height,width):raise ValueError('MASK_IMAGE_SIZE')
    def fill(target,row):
        points=region(row)
        coords=np.array([[min(width-1,int(x*width)),min(height-1,int(y*height))] for x,y in points],np.int32)
        cv2.fillPoly(target,[coords],255)
    restore_areas=[]
    def protection(row,mode):
        part=np.zeros_like(mask);fill(part,row)
        if mode=='BRIGHT_PRINT_GLYPHS':
            margin=max(1,round(.015*min(width,height)))
            part=cv2.dilate(part,np.ones((margin*2+1,margin*2+1),np.uint8))
            part=bright_print_pixels(template_image if template_image is not None else image,part)
            if protection_geometry is not None:protection_geometry.append(dict(kind=row['kind'],mode=mode,protected_pixels=int(np.count_nonzero(part))))
        elif mode=='PRINT_RESTORE':
            margin=max(1,round(.015*min(width,height)))
            part=cv2.dilate(part,np.ones((margin*2+1,margin*2+1),np.uint8))
            proof=dict(kind=row['kind'],mode=mode,maximum_restore_fraction=.10,search_margin_pixels=margin)
            restore_areas.append((part,proof))
            if protection_geometry is not None:protection_geometry.append(proof)
            return np.zeros_like(part)
        return part
    glyph_mode=any(mark_disposition(row)=='REMOVABLE' and row.get('repair_mode')=='BACKGROUND_GLYPHS' for row in observation['watermarks'])
    template_mode=any(mark_disposition(row)=='REMOVABLE' and row.get('repair_mode')=='TEMPLATE_GLYPHS' for row in observation['watermarks'])
    image_scope=any(mark_disposition(row)=='REMOVABLE' and row.get('glyph_search_scope')=='IMAGE' for row in observation['watermarks'])
    seen_global=set()
    background=None
    if glyph_mode:
        if image is None:raise ValueError('BACKGROUND_PIXELS_REQUIRED')
        low=image.min(axis=2);high=image.max(axis=2)
        bright=((low>=225)&((high.astype(int)-low.astype(int))<=20)).astype(np.uint8)
        _,labels,_,_=cv2.connectedComponentsWithStats(bright,8)
        boundary=set(np.concatenate([labels[0],labels[-1],labels[:,0],labels[:,-1]]).tolist())-{0}
        background=np.isin(labels,list(boundary))
    for row in observation['watermarks']:
        if mark_disposition(row)=='REMOVABLE':
            if row.get('glyph_search_scope')=='IMAGE':
                if row.get('repair_mode')!='TEMPLATE_GLYPHS':raise ValueError('V2_GLOBAL_TEMPLATE_REQUIRED')
                from mye_c_automation.template_glyphs import repeated_template_strokes
                key=tuple(row.get('glyph_template_bbox',[]))
                if key in seen_global:continue
                seen_global.add(key);proof={}
                mask=np.maximum(mask,repeated_template_strokes(image,row,proof=proof,template_image=template_image))
                if geometry is not None:geometry.append(proof)
                continue
            if row.get('repair_mode')=='TEMPLATE_GLYPHS':
                from mye_c_automation.template_glyphs import template_strokes
                roi=np.zeros((height,width),np.uint8);fill(roi,row)
                margin=max(2,round(.08*min(width,height)))
                kernel=np.ones((margin*2+1,margin*2+1),np.uint8)
                roi=cv2.dilate(roi,kernel)
                allowed=np.zeros_like(roi)
                for other in observation['watermarks']:
                    if mark_disposition(other)=='REMOVABLE':
                        part=np.zeros_like(roi);fill(part,other)
                        if other.get('repair_mode')=='TEMPLATE_GLYPHS':part=cv2.dilate(part,kernel)
                        allowed=np.maximum(allowed,part)
                reference=np.zeros_like(roi);fill(reference,{'bbox':row.get('glyph_template_bbox')})
                if row.get('glyph_template_source')!='ORIGINAL' and np.any((reference>0)&(allowed==0)):raise ValueError('GLYPH_TEMPLATE_NOT_IN_ERASE_REGIONS')
                proof={'maximum_target_refinement_pixels':margin}
                mask=np.maximum(mask,template_strokes(image,row,roi,proof=proof,template_image=template_image))
                if geometry is not None:geometry.append(proof)
            elif row.get('repair_mode')=='BACKGROUND_GLYPHS':
                roi=np.zeros((height,width),np.uint8);fill(roi,row)
                selected=(roi>0)&background&(low<254)
                mask[selected]=255
            else:
                if row['preserve_overlap_risk']!='LOW':raise ValueError('REGION_RISK')
                fill(mask,row)
        else:protected=np.maximum(protected,protection(row,row.get('preserve_mode','EXACT_REGION')))
    for row in observation['preserve_regions']:
        part=protection(row,row.get('scope','EXACT_REGION'))
        if (glyph_mode and row.get('scope')=='PRODUCT_FOREGROUND' and observation.get('toy_present') is True and
            observation.get('retail_box_status')=='ABSENT' and observation.get('background_complexity')=='SMOOTH'):
            part[background]=0
        protected=np.maximum(protected,part)
    if dilation:mask=cv2.dilate(mask,np.ones((2*dilation+1,2*dilation+1),np.uint8))
    if template_mode and not image_scope and np.any((mask>0)&(allowed==0)):raise ValueError('GLYPH_DILATION_OUTSIDE_TARGETS')
    fresh_mask=mask.copy()
    if inherited_mask is not None:
        if not isinstance(inherited_mask,np.ndarray) or inherited_mask.shape!=mask.shape or inherited_mask.dtype!=np.uint8 or not np.isin(inherited_mask,[0,255]).all():raise ValueError('INVALID_PRIOR_MASK')
        mask=np.maximum(mask,inherited_mask)
    for part,proof in restore_areas:
        if np.any((fresh_mask>0)&(part>0)) and any(mark_disposition(m)=='REMOVABLE' and m.get('repair_mode')!='TEMPLATE_GLYPHS' for m in observation['watermarks']):raise ValueError('PRINT_RESTORE_REQUIRES_GLYPHS')
        count=int(np.count_nonzero((mask>0)&(part>0)))
        proof['restore_pixels']=count
        if count>.10*np.count_nonzero(part):raise ValueError('PRINT_RESTORE_AREA')
    if (template_mode or inherited_mask is not None) and np.any((mask>0)&(protected>0)):raise ValueError('PROTECTED_REGION_OVERLAP')
    if glyph_mode:mask[protected>0]=0
    ratio=float(np.count_nonzero(mask)/mask.size)
    if not 0<ratio<=max_area:raise ValueError('MASK_AREA')
    if np.any((mask>0)&(protected>0)):raise ValueError('PROTECTED_REGION_OVERLAP')
    return mask,ratio

def lama_torchscript(model_path,expected_sha256=None):
    """Explicit local TorchScript model only; never download weights."""
    path=Path(model_path)
    if not path.is_file():raise ValueError('LAMA_UNAVAILABLE')
    digest=sha(path)
    if expected_sha256 is not None and digest!=expected_sha256:raise ValueError('LAMA_MODEL_CHANGED')
    import torch
    model=torch.jit.load(str(path),map_location='cpu').eval()
    arguments=list(model.forward.schema.arguments)[1:]
    if len(arguments)==2 and all(str(a.type)=='Tensor' for a in arguments):contract='IMAGE_MASK_TENSORS'
    elif len(arguments)==1 and str(arguments[0].type).startswith('Dict['):contract='IMAGE_MASK_DICTIONARY'
    else:raise ValueError('LAMA_MODEL_CONTRACT')
    def run(image,mask):
        h,w=image.shape[:2];pad_h=(-h)%8;pad_w=(-w)%8
        data=np.pad(image,((0,pad_h),(0,pad_w),(0,0)),mode='reflect')
        m=np.pad(mask,((0,pad_h),(0,pad_w)),mode='constant')
        with torch.inference_mode():
            image_tensor=torch.from_numpy(data.transpose(2,0,1).copy()).float()[None]/255
            mask_tensor=torch.from_numpy(m.copy()).float()[None,None]/255
            output=model(image_tensor,mask_tensor) if contract=='IMAGE_MASK_TENSORS' else model({'image':image_tensor,'mask':mask_tensor})
        if isinstance(output,dict):output=output['inpainted']
        return (output[0].clamp(0,1).numpy().transpose(1,2,0)[:h,:w]*255).round().astype(np.uint8)
    run.model_sha256=digest;run.input_contract=contract
    return run

def remove_text(source,observation,directory,*,rights,algorithm=None,lama=None,max_area=.25,cache_dir=None,mask_source=None,prior_mask=None,processing_policy=None):
    if rights!='OWNED_OR_LICENSED':raise ValueError('RIGHTS_NOT_AUTHORIZED')
    # Explicit V2 instance geometry uses the reusable ROI module. Sealed older
    # glyph modes retain their original implementation and evidence contracts.
    removable=[m for m in observation['watermarks'] if mark_disposition(m)=='REMOVABLE']
    generic_parent=(prior_mask is None or (Path(prior_mask).parent/'processing-result.json').is_file())
    if generic_parent and removable and all(m.get('repair_mode') in {None,'REGION'} for m in removable):
        from mye_c_automation.watermark_processing import process_watermarks,from_v2
        from mye_c_automation.watermark_processing.contracts import policy_options
        configured=policy_options(processing_policy);configured['max_mask_area']=min(configured['max_mask_area'],max_area)
        result=process_watermarks(from_v2(source,observation,rights),directory,lama=lama,algorithm=algorithm,
            policy=configured,mask_source=mask_source,prior_mask=prior_mask,cache_dir=cache_dir)
        if result['processing_status']!='PROCESSED':raise ValueError(result['failure_reason'] or result['processing_status'])
        mask_path=result['mask_paths'][0]
        with Image.open(mask_path) as mask_image:ratio=float(np.count_nonzero(np.array(mask_image))/(mask_image.width*mask_image.height))
        result.update(input_path=str(source),mask_path=mask_path,mask_sha256_map=result['mask_sha256'],mask_sha256=sha(mask_path),
            algorithm=result['algorithm_used'][0] if len(result['algorithm_used'])==1 else 'MIXED',
            mask_ratio=ratio,module_result_path=str(Path(directory)/'processing-result.json'),module_result_sha256=sha(Path(directory)/'processing-result.json'),
            elapsed_ms=round(result['execution_time']*1000,3),cache_hit=False,cache_key=None,
            model_sha256=getattr(lama,'model_sha256',None),parameters=result['processing_parameters'])
        return result
    root=Path(directory);root.mkdir(parents=True,exist_ok=True);source=Path(source)
    start=time.perf_counter();digest=sha(source);image=pixels(source);h,w=image.shape[:2]
    geometry=[];print_protection=[];inherited=None;mask_image=image
    if (mask_source is None)!=(prior_mask is None):raise ValueError('RESIDUAL_INPUT_PAIR_REQUIRED')
    if prior_mask is not None:
        if not deterministic_quality(source,mask_source,prior_mask)['ok']:raise ValueError('RESIDUAL_SOURCE_UNBOUND')
        with Image.open(prior_mask) as previous:inherited=np.array(previous.convert('L'))
        mask_image=pixels(mask_source)
    try:
        mask,ratio=mask_for((w,h),observation,max_area=max_area,image=mask_image,geometry=geometry,inherited_mask=inherited,template_image=image,protection_geometry=print_protection)
    except ValueError as exc:
        atomic_json(root/'mask_geometry.json',dict(input_sha256=digest,geometry=geometry,print_protection=print_protection,status='BLOCKED',reason=str(exc)))
        raise
    template_mode=any(mark_disposition(row)=='REMOVABLE' and row.get('repair_mode')=='TEMPLATE_GLYPHS' for row in observation['watermarks'])
    if template_mode and algorithm not in (None,'LAMA_INPAINT'):raise ValueError('GLYPH_REQUIRES_LAMA')
    algorithm=algorithm or ('OPENCV_TELEA' if not template_mode and ratio<=.04 and observation['background_complexity']=='SMOOTH' else 'LAMA_INPAINT')
    if algorithm not in {'LAMA_INPAINT','OPENCV_TELEA','OPENCV_NS'}:raise ValueError('UNKNOWN_INPAINT_ALGORITHM')
    mask_path=root/'mask.png';output_path=root/(algorithm+'.png')
    if source.resolve() in {mask_path.resolve(),output_path.resolve()}:raise ValueError('ORIGINAL_OVERWRITE_FORBIDDEN')
    Image.fromarray(mask).save(mask_path)
    cache=None;cache_key=None
    backend=getattr(lama,'model_sha256',None) if algorithm=='LAMA_INPAINT' else cv2.__version__
    if cache_dir is not None and backend:
        import json,base64
        from mye_c_automation.ai_judge.cache import ResultCache
        from mye_c_automation import template_glyphs
        binding=dict(source=digest,observation=observation,mask=sha(mask_path),algorithm=algorithm,backend=backend,
            max_area=max_area,implementation=sha(__file__),glyph_implementation=sha(template_glyphs.__file__),
            mask_source=sha(mask_source) if mask_source else None)
        cache_key=hashlib.sha256(json.dumps(binding,sort_keys=True).encode()).hexdigest();cache=ResultCache(cache_dir)
        try:
            cached=cache.get(cache_key);receipt=cached['receipt'];data=base64.b64decode(cached['png'],validate=True)
            if receipt['input_sha256']!=digest or receipt['mask_sha256']!=sha(mask_path) or hashlib.sha256(data).hexdigest()!=receipt['output_sha256']:raise ValueError('REPAIR_CACHE_CHANGED')
            output_path.write_bytes(data)
            if not deterministic_quality(source,output_path,mask_path)['ok']:raise ValueError('REPAIR_CACHE_INVALID')
            if sha(source)!=digest:raise ValueError('ORIGINAL_CHANGED')
            result=dict(receipt,input_path=str(source),output_path=str(output_path),mask_path=str(mask_path),
                elapsed_ms=round((time.perf_counter()-start)*1000,3),cache_hit=True,cache_key=cache_key)
            atomic_json(root/(algorithm+'.json'),result);return result
        except (ValueError,KeyError,TypeError,OSError):pass
    if algorithm=='LAMA_INPAINT':
        if lama is None:raise ValueError('LAMA_UNAVAILABLE')
        output=lama(image.copy(),mask.copy())
    elif algorithm in {'OPENCV_TELEA','OPENCV_NS'}:
        output=cv2.inpaint(image,mask,3,cv2.INPAINT_TELEA if algorithm=='OPENCV_TELEA' else cv2.INPAINT_NS)
    else:raise ValueError('UNKNOWN_INPAINT_ALGORITHM')
    if not isinstance(output,np.ndarray) or output.shape!=image.shape or output.dtype!=np.uint8:raise ValueError('INVALID_INPAINT_OUTPUT')
    uniform_components=_uniform_background_cleanup(image,output,mask) if template_mode else 0
    output[mask==0]=image[mask==0]
    with Image.open(source) as original:
        alpha=np.array(original.convert('RGBA').getchannel('A')) if original.mode=='RGBA' or 'transparency' in original.info else None
    if alpha is not None:
        repaired_alpha=alpha.copy()
        Image.fromarray(np.dstack([output,repaired_alpha])).save(output_path)
    else:Image.fromarray(output).save(output_path)
    if sha(source)!=digest:raise ValueError('ORIGINAL_CHANGED')
    result=dict(algorithm=algorithm,parameters={'radius':3,'dilation':2,'max_area':max_area},mask_ratio=ratio,
                input_sha256=digest,output_sha256=sha(output_path),mask_sha256=sha(mask_path),
                input_path=str(source),output_path=str(output_path),mask_path=str(mask_path),elapsed_ms=round((time.perf_counter()-start)*1000,3))
    if geometry:result['template_geometry']=geometry
    if print_protection:result['print_protection']=print_protection
    if template_mode:result['uniform_background_components']=uniform_components
    result.update(cache_hit=False,cache_key=cache_key)
    if prior_mask is not None:result.update(prior_mask_sha256=sha(prior_mask),mask_source_sha256=sha(mask_source))
    if algorithm=='LAMA_INPAINT':result.update(model_sha256=getattr(lama,'model_sha256',None),model_contract=getattr(lama,'input_contract','INJECTED_BACKEND'))
    if cache is not None and deterministic_quality(source,output_path,mask_path)['ok']:
        import base64
        cache.put(cache_key,dict(receipt=result,png=base64.b64encode(output_path.read_bytes()).decode()),lambda value:None)
    atomic_json(root/(algorithm+'.json'),result);return result

def deterministic_quality(source,candidate,mask=None):
    try:
        before=pixels(source);after=pixels(candidate)
        with Image.open(source) as im:before_rgba=np.array(im.convert('RGBA'))
        with Image.open(candidate) as im:
            if im.format not in {'PNG','JPEG','WEBP'} or im.mode not in {'RGB','RGBA'}:raise ValueError('FORMAT_SIZE_MODE')
            if im.mode=='RGBA' and im.getchannel('A').getextrema()==(0,0):raise ValueError('TRANSPARENT_CANDIDATE')
            after_rgba=np.array(im.convert('RGBA'))
        if not np.any(np.ptp(after_rgba.reshape(-1,4),axis=0)>0):raise ValueError('BLANK_CANDIDATE')
        if Path(candidate).stat().st_size>20*1024*1024 or after.shape!=before.shape:raise ValueError('SHAPE_OR_BYTES')
        if np.array_equal(before_rgba,after_rgba):raise ValueError('UNCHANGED_CANDIDATE')
        if mask is not None:
            with Image.open(mask) as im:m=np.array(im)>0
            if m.shape!=before.shape[:2] or not np.array_equal(before_rgba[~m],after_rgba[~m]):raise ValueError('OUTSIDE_MASK_CHANGED')
        return {'ok':True,'source_sha256':sha(source),'candidate_sha256':sha(candidate),'outside_mask_unchanged':mask is not None}
    except (ValueError,OSError) as exc:return {'ok':False,'reason':str(exc)}
