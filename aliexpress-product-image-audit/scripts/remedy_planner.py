"""Reuse existing pool hashing and crop tools; preserve originals on every failure."""
from pathlib import Path
import cv2
import numpy as np
from candidate_quality import sha256
from imgpool import _phash, _ham
from job_manager import atomic_json

def _official_letterbox_match(source, candidate, fingerprint):
    """Compare only in memory; original candidate still needs independent validation."""
    h,w=source.shape[:2]
    ch,cw=candidate.shape[:2]
    if min(h,w,ch,cw)<=0 or max(h,w)>4096: return False
    scale=min(w/cw,h/ch)
    tw,th=max(1,round(cw*scale)),max(1,round(ch*scale))
    if tw<w:
        if not (np.all(source[:,0]>=245) and np.all(source[:,-1]>=245)): return False
    elif th<h:
        if not (np.all(source[0]>=245) and np.all(source[-1]>=245)): return False
    else: return False
    canvas=np.full((h,w),255,np.uint8)
    x,y=(w-tw)//2,(h-th)//2
    canvas[y:y+th,x:x+tw]=cv2.resize(candidate,(tw,th),interpolation=cv2.INTER_AREA)
    return _ham(fingerprint,_phash(canvas))<=10

class RemedyPlanner:
    def __init__(self, directory, quality_gate,allowed_actions=None):
        self.root=Path(directory)
        self.quality_gate=quality_gate
        self.quality=[]
        self.conditional=[]
        self.allowed_actions=allowed_actions

    def _path(self, row):
        path=Path(row.get('local') or row['file'])
        return path if path.is_absolute() else Path(__file__).parent/path

    def _candidate(self,item,path,action,source,context,asset=None):
        transition={'item_id':item['id'],'action':action,'source_sha256':source.get('sha256'),
                    'decision':'AUTO_CONDITIONAL','required_checks':'independent_candidate_quality'}
        self.conditional.append(transition)
        atomic_json(self.root/'conditional_decisions.json',{'items':self.conditional})
        scope=None
        if item.get('full_confirmed_findings') and action in {'CROP_BANNER','ERASE_LOCAL'}:
            scope={'type':'CONFIRMED_MARK_REPAIR','action':action,'phase':'PREPARE',
                   'boxes':[r['bbox_xyxy'] for r in item['full_confirmed_findings'] if r.get('bbox_xyxy')],
                   'source_sha256':source.get('original_sha256')}
        quality_context=dict(context,_image_repair=scope) if scope else context
        checked=self.quality_gate.validate(self._path(item),path,quality_context,source.get('sha256'))
        if scope:checked['validation_scope']=scope
        allowed=self.allowed_actions is None or action in self.allowed_actions
        self.conditional.append(dict(transition,decision='AUTO_CONDITIONAL' if checked['ok'] and allowed else 'DEFERRED',quality_passed=bool(checked['ok']),
                                     evidence_ids=checked.get('evidence_ids',[]),reason=checked.get('reason') if allowed else 'ACTION_NOT_AUTHORIZED'))
        atomic_json(self.root/'conditional_decisions.json',{'items':self.conditional})
        self.quality.append(dict(item_id=item['id'],action=action,**checked))
        atomic_json(self.root/'candidate_quality.json',{'items':self.quality})
        if not checked['ok']: return None
        if self.allowed_actions is not None and action not in self.allowed_actions:return None
        candidate=dict(remedy_id='REM_'+item['id'],item_id=item['id'],action=action,
                    target={'pool':item['pool'],'index':item['index'],'image_id':item['image_id']},
                    source=source,candidate_asset=asset,
                    evidence_ids=item['evidence_ids']+checked['evidence_ids'],checks=checked['checks'],
                    reason_codes=[action+'_QUALITY_VERIFIED'])
        if scope:candidate['validation_scope']=scope
        return candidate

    def plan_box(self,item,context):
        if self.allowed_actions is None or 'BOX_NORMALIZE' not in self.allowed_actions:return None
        try:
            from product_state import identity_object
            original=self._path(item)
            observed=self.quality_gate.inspector.observe_image(original,context)
            model=identity_object(context.get('identityJson') or {}).get('modelCode')
            if not model or observed.get('verified') is not True or observed.get('clean') is not True or observed.get('image_type')!='BOX' or observed.get('model')!=model or observed.get('sha256')!=sha256(original) or not observed.get('evidence_ids'):return None
            from box_normalization import normalize_box
            target=self.root/('box_'+item['image_id']+'.png')
            transform=normalize_box(original,target)
            asset={'path':target.name,'sha256':sha256(target),'pool':item['pool'],'index':item['index']}
            row=self._candidate(item,target,'BOX_NORMALIZE',{'type':'normalized_box','sha256':sha256(target),'original_sha256':sha256(original)},context,asset)
            if row:
                row['checks']['box_verified']=True
                row['evidence_ids']+=observed['evidence_ids']
                proof_path=self.root/'box_validation.json'
                import json
                proofs=json.loads(proof_path.read_text(encoding='utf-8')) if proof_path.exists() else {'items':[]}
                proofs['items'].append({'candidate':row,'observation':observed,'transform':transform})
                atomic_json(proof_path,proofs)
            return row
        except Exception:return None

    def plan(self,item,images,context,*,crop_box=None,subject_box=None,erase_box=None,local_pool=()):
        original=self._path(item)
        gray=cv2.imdecode(np.frombuffer(original.read_bytes(),np.uint8),cv2.IMREAD_GRAYSCALE)
        if gray is None: return None
        fingerprint=_phash(gray)
        for row in images:
            if row.get('kind') not in {'main','detail','sku'}:continue
            if row.get('source')=='skus':continue  # no actual pool/index source slot
            if row.get('url')==item.get('source_url'): continue
            try:
                path=self._path(row)
                decoded=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_GRAYSCALE)
                if decoded is None or _ham(fingerprint,_phash(decoded))>6: continue
                digest=sha256(path)
                if row.get('content_sha256') not in (None,digest): continue
                candidate=self._candidate(item,path,'REPLACE_TWIN',{'type':'existing_pool','url':row['url'],'sha256':digest,'pool':row['kind'],'index':row['index']},context)
                if candidate: return candidate
            except (OSError,ValueError,KeyError): continue
        if crop_box is not None and subject_box is not None:
            try:
                x0,y0,x1,y1=crop_box; sx0,sy0,sx1,sy1=subject_box
                h,w=gray.shape
                valid=all(type(v) is int for v in crop_box+subject_box) and 0<=x0<=sx0<sx1<=x1<=w and 0<=y0<=sy0<sy1<=y1<=h
                # Only a single edge strip, at most 28%; never a general interior crop.
                valid=valid and ((x0==0 and x1==w and (y0==0 or y1==h)) or (y0==0 and y1==h and (x0==0 or x1==w)))
                valid=valid and (x1-x0)*(y1-y0)>=.72*w*h and max(x1-x0,y1-y0)>=800
                if valid:
                    from clean_band import crop_border
                    image=cv2.imdecode(np.frombuffer(original.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
                    asset_path=self.root/('crop_'+item['image_id']+'.png')
                    cv2.imencode('.png',crop_border(image,crop_box,size=800,preserve_aspect=True))[1].tofile(str(asset_path))
                    digest=sha256(asset_path)
                    asset={'path':asset_path.name,'sha256':digest,'pool':item['pool'],'index':item['index']}
                    candidate=self._candidate(item,asset_path,'CROP_BANNER',{'type':'generated_crop','sha256':digest,'original_sha256':sha256(original),'crop_box':crop_box,'subject_box':subject_box},context,asset)
                    if candidate and candidate['checks'].get('subject_bounds_safe') is True: return candidate
            except (OSError,ValueError,TypeError): pass
        # One local background trial only; no whole-image inpainting or product masks.
        if erase_box is not None and subject_box is not None:
            try:
                x0,y0,x1,y1=erase_box;sx0,sy0,sx1,sy1=subject_box;h,w=gray.shape
                valid=all(type(v) is int for v in erase_box+subject_box) and 0<=x0<x1<=w and 0<=y0<y1<=h and 0<=sx0<sx1<=w and 0<=sy0<sy1<=h
                valid=valid and (x1<=sx0 or x0>=sx1 or y1<=sy0 or y0>=sy1) and (x1-x0)*(y1-y0)<=.02*w*h
                if valid:
                    image=cv2.imdecode(np.frombuffer(original.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
                    roi=image[y0:y1,x0:x1];median=np.median(roi.reshape(-1,3),axis=0)
                    # Flatness only admits a trial. The independent semantic/residual gate decides it.
                    flat=float(np.mean(np.max(np.abs(roi.astype(float)-median),axis=2)<=12))>=.90
                    if flat:
                        mask=np.zeros(gray.shape,dtype=np.uint8);mask[y0:y1,x0:x1]=255
                        from clean_band import wipe_band
                        after=wipe_band(image.copy(),mask,pad=0,fill=tuple(int(v) for v in median),grow=1,iters=1)
                        outside=bool(np.array_equal(image[mask==0],after[mask==0]))
                        target=self.root/('erase_'+item['image_id']+'.png')
                        mask_path=self.root/('erase_'+item['image_id']+'_mask.png')
                        cv2.imencode('.png',after)[1].tofile(str(target));cv2.imencode('.png',mask)[1].tofile(str(mask_path))
                        asset={'path':target.name,'sha256':sha256(target),'pool':item['pool'],'index':item['index']}
                        source={'type':'generated_erase','sha256':asset['sha256'],'original_sha256':sha256(original),'mask_path':mask_path.name,'mask_sha256':sha256(mask_path),'erase_box':erase_box,'subject_box':subject_box}
                        candidate=self._candidate(item,target,'ERASE_LOCAL',source,context,asset)
                        if candidate and outside:
                            candidate['checks'].update(mask_background_only=True,outside_mask_unchanged=True)
                            return candidate
            except (OSError,ValueError,TypeError):pass
        for row in local_pool:
            from product_state import identity_object
            try: model=context.get('model') or identity_object(context.get('identityJson') or {}).get('modelCode')
            except ValueError:model=None
            if row.get('official_source') is not True or not row.get('model') or row.get('model')!=model: continue
            try:
                path=self._path(row)
                decoded=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_GRAYSCALE)
                if decoded is None: continue
                if _ham(fingerprint,_phash(decoded))>10:
                    source_color=cv2.imdecode(np.frombuffer(original.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
                    if source_color is None or not _official_letterbox_match(source_color,decoded,fingerprint): continue
                digest=sha256(path)
                if row.get('sha256')!=digest: continue
                target=self.root/('local_'+digest+'.png')
                from PIL import Image
                with Image.open(path) as image: image.convert('RGB').save(target)
                asset={'path':target.name,'sha256':sha256(target),'pool':item['pool'],'index':item['index']}
                candidate=self._candidate(item,target,'REPLACE_LOCAL',{'type':'official_local','sha256':asset['sha256'],'original_sha256':digest,'original_path':str(path),'target_original_sha256':sha256(original),'source_url':row.get('source_url'),'model':row.get('model'),'packaging_type':row.get('packaging_type')},context,asset)
                if candidate: return candidate
            except (OSError,ValueError,KeyError): continue
        atomic_json(self.root/'candidate_quality.json',{'items':self.quality})
        return None
