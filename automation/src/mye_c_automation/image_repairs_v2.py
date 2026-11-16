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

def mask_for(size,observation,*,max_area=.25,dilation=2,image=None):
    width,height=size;mask=np.zeros((height,width),np.uint8);protected=mask.copy()
    def fill(target,row):
        points=region(row)
        coords=np.array([[min(width-1,int(x*width)),min(height-1,int(y*height))] for x,y in points],np.int32)
        cv2.fillPoly(target,[coords],255)
    glyph_mode=any(mark_disposition(row)=='REMOVABLE' and row.get('repair_mode')=='BACKGROUND_GLYPHS' for row in observation['watermarks'])
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
            if row.get('repair_mode')=='BACKGROUND_GLYPHS':
                roi=np.zeros((height,width),np.uint8);fill(roi,row)
                selected=(roi>0)&background&(low<254)
                mask[selected]=255
            else:
                if row['preserve_overlap_risk']!='LOW':raise ValueError('REGION_RISK')
                fill(mask,row)
        else:fill(protected,row)
    for row in observation['preserve_regions']:
        part=np.zeros((height,width),np.uint8);fill(part,row)
        if (glyph_mode and row.get('scope')=='PRODUCT_FOREGROUND' and observation.get('toy_present') is True and
            observation.get('retail_box_status')=='ABSENT' and observation.get('background_complexity')=='SMOOTH'):
            part[background]=0
        protected=np.maximum(protected,part)
    if dilation:mask=cv2.dilate(mask,np.ones((2*dilation+1,2*dilation+1),np.uint8))
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

def remove_text(source,observation,directory,*,rights,algorithm=None,lama=None,max_area=.25):
    if rights!='OWNED_OR_LICENSED':raise ValueError('RIGHTS_NOT_AUTHORIZED')
    root=Path(directory);root.mkdir(parents=True,exist_ok=True);source=Path(source)
    start=time.perf_counter();digest=sha(source);image=pixels(source);h,w=image.shape[:2]
    mask,ratio=mask_for((w,h),observation,max_area=max_area,image=image)
    algorithm=algorithm or ('OPENCV_TELEA' if ratio<=.04 and observation['background_complexity']=='SMOOTH' else 'LAMA_INPAINT')
    if algorithm=='LAMA_INPAINT':
        if lama is None:raise ValueError('LAMA_UNAVAILABLE')
        output=lama(image.copy(),mask.copy())
    elif algorithm in {'OPENCV_TELEA','OPENCV_NS'}:
        output=cv2.inpaint(image,mask,3,cv2.INPAINT_TELEA if algorithm=='OPENCV_TELEA' else cv2.INPAINT_NS)
    else:raise ValueError('UNKNOWN_INPAINT_ALGORITHM')
    if not isinstance(output,np.ndarray) or output.shape!=image.shape or output.dtype!=np.uint8:raise ValueError('INVALID_INPAINT_OUTPUT')
    output[mask==0]=image[mask==0]
    mask_path=root/'mask.png';output_path=root/(algorithm+'.png')
    if source.resolve() in {mask_path.resolve(),output_path.resolve()}:raise ValueError('ORIGINAL_OVERWRITE_FORBIDDEN')
    Image.fromarray(mask).save(mask_path)
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
    if algorithm=='LAMA_INPAINT':result.update(model_sha256=getattr(lama,'model_sha256',None),model_contract=getattr(lama,'input_contract','INJECTED_BACKEND'))
    atomic_json(root/(algorithm+'.json'),result);return result

def deterministic_quality(source,candidate,mask=None):
    try:
        before=pixels(source);after=pixels(candidate)
        with Image.open(source) as im:before_rgba=np.array(im.convert('RGBA'))
        with Image.open(candidate) as im:
            if im.format not in {'PNG','JPEG','WEBP'} or im.mode not in {'RGB','RGBA'} or min(im.size)<800:raise ValueError('FORMAT_SIZE_MODE')
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
