"""Bounded OCR geometry fallback over source-bound V2 semantics.

OCR never decides ownership; reference-ID selection uses the existing judge.
Only the existing proven glyph matcher can supply an execution mask.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import cv2
import numpy as np
from PIL import Image,ImageDraw
from mye_c_automation.job_manager import atomic_json
from mye_c_automation.candidate_quality import sha256
from mye_c_automation.ai_judge.image_action_decision import mark_disposition

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def extract_regions(source):
    try:from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:raise ValueError('OCR_FALLBACK_UNAVAILABLE') from exc
    image=cv2.imdecode(np.frombuffer(Path(source).read_bytes(),np.uint8),cv2.IMREAD_COLOR)
    if image is None:raise ValueError('OCR_FALLBACK_SOURCE_UNREADABLE')
    # Same fixed three passes as the measured experiment, no semantic keywords.
    engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1)
    large=cv2.resize(image,None,fx=2,fy=2,interpolation=cv2.INTER_CUBIC)
    gray=cv2.createCLAHE(clipLimit=2,tileGridSize=(8,8)).apply(cv2.cvtColor(large,cv2.COLOR_BGR2GRAY))
    regions=[];passes=[]
    for name,pixels,scale in [('original',image,1),('upscale2',large,2),('contrast2',cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR),2)]:
        raw,_=engine(pixels);rows=[]
        for polygon,text,score in raw or []:
            points=(np.asarray(polygon,float)/scale).tolist();row=dict(polygon=points,text=text,score=float(score));rows.append(row)
            candidate=np.array(points,np.float32);matched=None
            for r in regions:
                old=np.array(r['polygon'],np.float32);inter,_=cv2.intersectConvexConvex(candidate,old)
                if inter/max(1,cv2.contourArea(candidate)+cv2.contourArea(old)-inter)>.55:matched=r;break
            if matched is None:
                if len(regions)>=256:raise ValueError('OCR_FALLBACK_REGION_LIMIT')
                matched=dict(id='T'+str(len(regions)+1),polygon=points,observations=[]);regions.append(matched)
            matched['observations'].append(dict(pass_name=name,text=text,score=float(score)))
        passes.append(dict(name=name,rows=rows))
    return dict(regions=regions,passes=passes)

def validate_selection(value,regions,observation):
    fields={'remove_groups','keep_ids','uncertain_ids','missed_texts'}
    if not isinstance(value,dict) or set(value)!=fields:raise ValueError('OCR_FALLBACK_SELECTION_FORMAT')
    if any(not isinstance(value[k],list) for k in fields):raise ValueError('OCR_FALLBACK_SELECTION_FORMAT')
    normalize=lambda text:re.sub(r'[^\w]','',text.casefold())
    # Compare literal identifiers from prior protection evidence; no OCR semantic
    # classifier and no overlap veto (watermarks may legitimately cross print).
    preserved=[r for r in observation.get('watermarks',[]) if mark_disposition(r)=='PROTECTED']+observation.get('preserve_regions',[])
    labels=[normalize(str(r.get(k,''))) for r in preserved for k in ('kind','text','ownership_visual_guess')]
    if len(value['remove_groups'])>32:raise ValueError('OCR_FALLBACK_GROUP_LIMIT')
    assigned=[]
    for group in value['remove_groups']:
        if (not isinstance(group,dict) or set(group)!={'text','ids'} or not isinstance(group['text'],str)
            or not group['text'].strip() or len(group['text'])>250 or not isinstance(group['ids'],list) or not group['ids']):
            raise ValueError('OCR_FALLBACK_SELECTION_FORMAT')
        text=normalize(group['text'])
        if len(text)>=3 and any(text in label for label in labels):raise ValueError('OCR_FALLBACK_PROTECTED_TEXT_CONFLICT')
        assigned+=group['ids']
    assigned+=value['keep_ids']+value['uncertain_ids']
    if (any(not isinstance(v,str) for v in assigned) or len(assigned)!=len(set(assigned))
        or set(assigned)!={r['id'] for r in regions}):raise ValueError('OCR_FALLBACK_SELECTION_IDS')
    if any(not isinstance(v,str) or len(v)>1000 for v in value['missed_texts']):raise ValueError('OCR_FALLBACK_SELECTION_FORMAT')
    if not value['remove_groups'] or value['uncertain_ids']:raise ValueError('OCR_FALLBACK_SELECTION_UNRESOLVED')
    return value

def prepare_fallback(source,observation,directory,judge,context,*,max_area=.25,policy=None):
    from mye_c_automation.ai_judge.client import parse_json_content
    from mye_c_automation.ai_judge.structured_output import chat_text
    from mye_c_automation.image_repairs_v2 import mask_for
    from mye_c_automation.watermark_processing.contracts import policy_options
    source=Path(source);root=Path(directory);root.mkdir(parents=True,exist_ok=True)
    digest=sha256(source)
    if observation.get('image_sha256',digest)!=digest:raise ValueError('OCR_FALLBACK_SOURCE_CHANGED')
    if not any(mark_disposition(m)=='REMOVABLE' for m in observation['watermarks']):raise ValueError('OCR_FALLBACK_NO_APPROVED_WATERMARK')
    options=policy_options(policy);max_area=min(max_area,options['max_mask_area'])
    detected=extract_regions(source);atomic_json(root/'ocr.json',detected)
    if not detected['regions']:raise ValueError('OCR_FALLBACK_EMPTY_DETECTION')
    with Image.open(source) as photo:preview=photo.convert('RGB');w,h=photo.size
    draw=ImageDraw.Draw(preview)
    for r in detected['regions']:
        points=[tuple(p) for p in r['polygon']];draw.line(points+[points[0]],fill='cyan',width=2)
        x,y=min(p[0] for p in points),min(p[1] for p in points);draw.rectangle([x,y,x+28,y+15],fill='black');draw.text((x+1,y+1),r['id'],fill='yellow')
    preview.save(root/'numbered.png')
    raw=judge.select_ocr_regions(source,root/'numbered.png',detected['regions'],observation,context)
    atomic_json(root/'selection-raw.json',raw)
    selection=validate_selection(parse_json_content(chat_text(raw)),detected['regions'],observation)
    atomic_json(root/'selection.json',selection)
    image=cv2.imdecode(np.frombuffer(source.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
    by={r['id']:r for r in detected['regions']};marks=[];trials=[]
    try:
        for gi,group in enumerate(selection['remove_groups']):
            chosen=None
            # Fixed cap per group, no model retries to force a successful action.
            for identifier in group['ids'][:8]:
                points=np.array(by[identifier]['polygon']);left,top=points.min(axis=0);right,bottom=points.max(axis=0)
                for padding in (4,10,18):
                    box=[float(max(0,(left-padding)/w)),float(max(0,(top-padding)/h)),float(min(1,(right+padding)/w)),float(min(1,(bottom+padding)/h))]
                    mark=dict(action='REMOVE_TEXT',kind='STORE_WATERMARK',owner='THIRD_PARTY_STORE',overlay_role='ADDED_WATERMARK',
                        repair_mode='TEMPLATE_GLYPHS',glyph_search_scope='IMAGE',
                        glyph_template_source='ORIGINAL',glyph_template_bbox=box,bbox=box,region_type='BBOX',
                        watermark_id='OCR_GROUP_'+str(gi),group_id='OCR_GROUP_'+str(gi),content_type='TEXT',subject_overlap=True)
                    if observation.get('schema_version')!='image-review.staged-v1':mark.update(confidence=observation['confidence'],preserve_overlap_risk='HIGH')
                    geometry=[]
                    try:
                        mask_for((w,h),dict(observation,watermarks=[mark],preserve_regions=[]),image=image,max_area=max_area,
                            dilation=options['dilation'],geometry=geometry,allow_protected_overlap=True)
                        matches=geometry[0].get('matches',[])
                        if len(matches)<(2 if len(group['ids'])>1 else 1):raise ValueError('REPEATED_PATTERN_NOT_PROVEN')
                        trials.append(dict(id=identifier,padding=padding,status='MATCHED',geometry=geometry));chosen=mark;break
                    except ValueError as exc:trials.append(dict(id=identifier,padding=padding,status='FAILED',reason=str(exc)))
                if chosen:break
            if chosen is None:raise ValueError('OCR_FALLBACK_NO_RELIABLE_GLYPHS')
            marks.append(chosen)
    finally:atomic_json(root/'glyph-trials.json',trials)
    derived=deepcopy(observation)
    derived['watermarks']=marks+[deepcopy(m) for m in observation['watermarks'] if mark_disposition(m)!='REMOVABLE']
    # Validate combined area/geometry/protection before the caller can run LaMa.
    mask_for((w,h),derived,image=image,max_area=max_area,dilation=options['dilation'],
        allow_protected_overlap=(policy or {}).get('protection_overlap_trial',True))
    atomic_json(root/'execution-observation.json',derived)
    if sha256(source)!=digest:raise ValueError('OCR_FALLBACK_SOURCE_CHANGED')
    manifest=dict(source_sha256=digest,original_observation_sha256=fingerprint(observation),execution_observation_sha256=fingerprint(derived),
        implementation_sha256=sha256(__file__),files=[dict(path=n,sha256=sha256(root/n)) for n in
            ('ocr.json','numbered.png','selection-raw.json','selection.json','glyph-trials.json','execution-observation.json')])
    atomic_json(root/'manifest.json',manifest)
    return derived,dict(path=str(root/'manifest.json'),sha256=sha256(root/'manifest.json'))

def verify_fallback(root,repair,source,observation):
    root=Path(root).resolve();ref=repair['ocr_fallback'];path=Path(ref['path']).resolve()
    if not path.is_relative_to(root) or sha256(path)!=ref['sha256']:raise ValueError('OCR_FALLBACK_PROOF_CHANGED')
    receipt=json.loads(path.read_text(encoding='utf-8'))
    if (receipt['source_sha256']!=sha256(source) or receipt['original_observation_sha256']!=fingerprint(observation)
        or receipt['execution_observation_sha256']!=fingerprint(repair['execution_observation'])
        or receipt['implementation_sha256']!=sha256(__file__)):raise ValueError('OCR_FALLBACK_PROOF_UNBOUND')
    for ref in receipt['files']:
        file=(path.parent/ref['path']).resolve()
        if not file.is_relative_to(path.parent) or sha256(file)!=ref['sha256']:raise ValueError('OCR_FALLBACK_EVIDENCE_CHANGED')
    selection=json.loads((path.parent/'selection.json').read_text(encoding='utf-8'))
    detected=json.loads((path.parent/'ocr.json').read_text(encoding='utf-8'))
    validate_selection(selection,detected['regions'],observation)

def eligible_failure(reason):
    """Geometry/extraction/local-backend failures; never authorization/integrity."""
    return reason in {'PROTECTED_REGION_OVERLAP','PRINT_RESTORE_AREA','MASK_AREA','ROI_AREA','EMPTY_MASK','EMPTY_ERASE_MASK',
        'LAMA_UNAVAILABLE','INPAINT_BACKEND_FAILED','INVALID_INPAINT_OUTPUT'} or reason.startswith(('GLYPH_','GLOBAL_GLYPH_','REPEATED_PATTERN_'))
