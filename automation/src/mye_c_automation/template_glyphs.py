"""Pixel geometry for an AI-selected repeated glyph; never classifies content."""
import cv2
import numpy as np

from mye_c_automation.ai_judge.image_action_decision import region


def _sample_window(image,mark):
    """Select complete contained ink within bounded, AI-confirmed sample seeds."""
    from itertools import product
    height,width=image.shape[:2];margin=max(2,round(.06*min(width,height)))
    seeds=[mark.get('glyph_template_bbox')]+list(mark.get('glyph_template_candidates',[]))
    examined=0
    for index,box in enumerate(seeds):
        region({'bbox':box});a,b,c,d=[int(v*s) for v,s in zip(box,(width,height,width,height))]
        candidates=[];seen=set()
        for left,top,right,bottom in product((0,margin//2,margin,-margin//2),repeat=4):
            bounds=(max(0,a-left),max(0,b-top),min(width,c+right),min(height,d+bottom))
            if bounds in seen:continue
            seen.add(bounds);examined+=1;x0,y0,x1,y1=bounds
            sample=image[y0:y1,x0:x1].astype(np.float32)
            if sample.size==0 or min(sample.shape[:2])<8 or sample.shape[0]*sample.shape[1]>.35*width*height:continue
            border=np.concatenate((sample[:2].reshape(-1,3),sample[-2:].reshape(-1,3),sample[:,:2].reshape(-1,3),sample[:,-2:].reshape(-1,3)))
            background=np.median(border,axis=0)
            if np.quantile(np.linalg.norm(border-background,axis=1),.9)>12:continue
            foreground=np.linalg.norm(sample-background,axis=2)>15
            fraction=float(foreground.mean())
            if not .005<=fraction<=.40:continue
            ys,xs=np.where(foreground)
            if len(xs)<12 or xs.min()<2 or ys.min()<2 or xs.max()>=sample.shape[1]-2 or ys.max()>=sample.shape[0]-2:continue
            candidates.append((int(foreground.sum()),-sample.shape[0]*sample.shape[1],bounds))
        if candidates:
            _,_,bounds=max(candidates)
            return bounds,dict(selected_template_index=index,selected_template_bbox=box,
                sample_search_windows=examined,sample_foreground_complete=True),margin
    raise ValueError('GLYPH_TEMPLATE_BACKGROUND')


def _match_scores(search,reference):
    # Reuse the established watermark scanner's flat-window floor. OpenCV's
    # normalized matcher can report 1.0 for zero-variance floating-point windows.
    from mye_c_automation.wm_tpl import STD_FLOOR
    scores=cv2.matchTemplate(search,reference,cv2.TM_CCOEFF_NORMED)
    th,tw=reference.shape;data=search.astype(np.float64)
    mean=cv2.boxFilter(data,-1,(tw,th),anchor=(0,0),normalize=True,borderType=cv2.BORDER_REPLICATE)
    square=cv2.boxFilter(data*data,-1,(tw,th),anchor=(0,0),normalize=True,borderType=cv2.BORDER_REPLICATE)
    deviation=np.sqrt(np.maximum(0,square-mean*mean))[:scores.shape[0],:scores.shape[1]]
    return np.where(np.isfinite(scores)&(deviation>=STD_FLOOR),scores,-1)


def _template_data(image, mark, template_image=None):
    if image is None or image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError('GLYPH_PIXELS_REQUIRED')
    height, width = image.shape[:2]
    reference_image=template_image if mark.get('glyph_template_source')=='ORIGINAL' and template_image is not None else image
    if reference_image.shape!=image.shape or reference_image.dtype!=np.uint8:raise ValueError('GLYPH_REFERENCE_SIZE')
    box = mark.get('glyph_template_bbox')
    region({'bbox': box})
    (x0,y0,x1,y1),selection,margin=_sample_window(reference_image,mark)
    sample = reference_image[y0:y1,x0:x1].astype(np.float32)
    if min(sample.shape[:2]) < 8 or sample.shape[0]*sample.shape[1] > image.shape[0]*image.shape[1]*.35:
        raise ValueError('GLYPH_TEMPLATE_SIZE')
    border = np.concatenate((sample[:2].reshape(-1,3),sample[-2:].reshape(-1,3),
        sample[:,:2].reshape(-1,3),sample[:,-2:].reshape(-1,3)))
    background = np.median(border,axis=0)
    if np.quantile(np.linalg.norm(border-background,axis=1),.9) > 12:
        raise ValueError('GLYPH_TEMPLATE_BACKGROUND')
    distance = np.linalg.norm(sample-background,axis=2)
    foreground = distance > 15
    fraction = float(foreground.mean())
    if not .005 <= fraction <= .40:
        raise ValueError('GLYPH_TEMPLATE_FOREGROUND')
    direction = np.median(sample[foreground],axis=0)-background
    chroma = direction-direction.mean()
    chromatic=np.linalg.norm(chroma)>=6
    if chromatic:direction = chroma
    norm = np.linalg.norm(direction)
    if norm < 6:raise ValueError('GLYPH_TEMPLATE_CONTRAST')
    direction /= norm
    projected = np.maximum((image.astype(np.float32)-background) @ direction,0)
    reference_projected=np.maximum((reference_image.astype(np.float32)-background) @ direction,0)
    if chromatic:
        # Ignore differently coloured product pixels and cap contrast so a red
        # product panel cannot dominate a faint pink glyph correlation. These
        # are sample-relative pixel operations, not content/ownership decisions.
        chromatic_pixels=image.astype(np.float32)-image.mean(axis=2,keepdims=True)
        magnitude=np.linalg.norm(chromatic_pixels,axis=2)
        cosine=projected/np.maximum(magnitude,1)
        projected[cosine<.92]=0
        reference_chroma=reference_image.astype(np.float32)-reference_image.mean(axis=2,keepdims=True)
        reference_cosine=reference_projected/np.maximum(np.linalg.norm(reference_chroma,axis=2),1)
        reference_projected[reference_cosine<.92]=0
        sample_projection=reference_projected[y0:y1,x0:x1]
        positive=sample_projection[foreground & (sample_projection>6)]
        if not len(positive):raise ValueError('GLYPH_TEMPLATE_CONTRAST')
        projected=np.minimum(projected,float(np.median(positive))*1.5)
        reference_projected=np.minimum(reference_projected,float(np.median(positive))*1.5)
    reference = reference_projected[y0:y1,x0:x1]
    strokes = (foreground & (reference > 6)).astype(np.uint8)*255
    if np.count_nonzero(strokes) < 12:raise ValueError('GLYPH_TEMPLATE_EMPTY')
    sy,sx=np.where(strokes>0)
    crop_left,crop_top=max(0,int(sx.min())-2),max(0,int(sy.min())-2)
    crop_right,crop_bottom=min(strokes.shape[1],int(sx.max())+3),min(strokes.shape[0],int(sy.max())+3)
    strokes=strokes[crop_top:crop_bottom,crop_left:crop_right]
    reference=reference[crop_top:crop_bottom,crop_left:crop_right]
    metadata=dict(selection,template_bbox=box,refined_template_bbox_pixels=[x0+crop_left,y0+crop_top,x0+crop_right,y0+crop_bottom],
        maximum_refinement_pixels=margin,minimum_correlation=.60,semantic_classification=False,
        template_source=mark.get('glyph_template_source','CANDIDATE'))
    return projected,reference,strokes,metadata


def template_strokes(image, mark, target, *, proof=None,template_image=None):
    projected,reference,strokes,metadata=_template_data(image,mark,template_image)
    ys,xs = np.where(target>0)
    if not len(xs):raise ValueError('GLYPH_TARGET_EMPTY')
    left,top,right,bottom = int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)
    th,tw = reference.shape
    search = projected[top:bottom,left:right]
    if search.shape[0] < th or search.shape[1] < tw:raise ValueError('GLYPH_TARGET_SIZE')
    scores = _match_scores(search,reference)
    _,best,_,(x,y) = cv2.minMaxLoc(scores)
    if best < .60:raise ValueError('GLYPH_MATCH_UNPROVEN')
    separated = scores.copy();radius=max(3,min(th,tw)//4)
    separated[max(0,y-radius):y+radius+1,max(0,x-radius):x+radius+1] = -1
    if separated.max() > best-.04:raise ValueError('GLYPH_MATCH_AMBIGUOUS')
    mask = np.zeros(image.shape[:2],np.uint8)
    mask[top+y:top+y+th,left+x:left+x+tw] = strokes
    if np.any((mask>0)&(target==0)):raise ValueError('GLYPH_OUTSIDE_TARGET')
    if proof is not None:
        proof.update(metadata,matched_bbox_pixels=[left+x,top+y,left+x+tw,top+y+th],
            correlation=float(best),separated_correlation=float(separated.max()),
            minimum_correlation=.60,minimum_separation=.04,mask_pixels=int(np.count_nonzero(mask)),
            method='AI_SELECTED_TEMPLATE_PIXEL_ALIGNMENT',semantic_classification=False)
    return mask


def _overlap(a,b):
    intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    area=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection
    return intersection/max(1,area)


def _partial_edge_matches(candidate_edges,edge_reference,ink,existing):
    """Two adjacent source stroke fragments must agree at the same translation."""
    height,width=candidate_edges.shape;th,tw=ink.shape
    scores=[];bounds=[]
    for strip in range(8):
        left,right=strip*tw//8,(strip+1)*tw//8
        ys,xs=np.where(ink[:,left:right])
        if len(xs)<12:
            scores.append(None);bounds.append(None);continue
        top,bottom=max(0,int(ys.min())-3),min(th,int(ys.max())+4)
        reference=edge_reference[top:bottom,left:right].astype(np.float32)
        values=_match_scores(candidate_edges.astype(np.float32),reference)
        scores.append(values[top:top+height-th+1,left:left+width-tw+1])
        bounds.append([left,top,right,bottom])
    accepted=[]
    for strip in range(7):
        if scores[strip] is None or scores[strip+1] is None:continue
        values=np.minimum(scores[strip],scores[strip+1])
        peaks=(values>=.60)&(values>=cv2.dilate(values,np.ones((5,5),np.uint8))-1e-6)
        positions=np.argwhere(peaks)
        if len(positions)>512:raise ValueError('GLYPH_PARTIAL_PROPOSAL_LIMIT')
        for y,x in sorted(positions,key=lambda p:-values[p[0],p[1]]):
            x,y=int(x),int(y);box=[x,y,x+tw,y+th]
            if any(_overlap(box,m['bbox_pixels'])>.10 for m in existing+accepted):continue
            accepted.append(dict(bbox_pixels=box,method='ALIGNED_SOURCE_STROKE_FRAGMENTS',
                minimum_correlation=.60,fragment_boxes=[bounds[strip],bounds[strip+1]],
                fragment_correlations=[float(scores[strip][y,x]),float(scores[strip+1][y,x])]))
            if len(existing)+len(accepted)>256:raise ValueError('GLOBAL_GLYPH_MATCH_LIMIT')
    return accepted


def _contrast_matches(image,reference_image,strokes,metadata,existing):
    """Confirm the approved stroke pattern despite varying underlying colours."""
    x0,y0,x1,y1=metadata['refined_template_bbox_pixels'];sample=reference_image[y0:y1,x0:x1].astype(float)
    ink=strokes>0;ring=(cv2.dilate(ink.astype(np.uint8),np.ones((5,5),np.uint8))>0)&~ink
    if not ring.any():return []
    axis=np.median(sample[ink],axis=0)-np.median(sample[ring],axis=0)
    chroma=axis-axis.mean()
    if np.linalg.norm(chroma)>=6:axis=chroma
    norm=np.linalg.norm(axis)
    if norm<6:return []
    axis/=norm;reference=sample@axis;projected=image.astype(float)@axis
    source_plane=reference_image.astype(float)@axis
    source_edges=source_plane-cv2.GaussianBlur(source_plane,(0,0),3)
    candidate_edges=projected-cv2.GaussianBlur(projected,(0,0),3)
    edge_reference=source_edges[y0:y1,x0:x1];edge_reference=edge_reference-edge_reference.mean()
    edge_norm=np.linalg.norm(edge_reference)
    kernel=ink.astype(float)/ink.sum()-ring.astype(float)/ring.sum()
    baseline=float(np.sum(reference*kernel))
    if baseline<6:return []
    ratios=cv2.matchTemplate(projected.astype(np.float32),kernel.astype(np.float32),cv2.TM_CCORR)/baseline
    peaks=(ratios>=.70)&(ratios>=cv2.dilate(ratios,np.ones((5,5),np.uint8))-1e-6)
    positions=np.argwhere(peaks)
    if len(positions)>512:raise ValueError('GLYPH_CONTRAST_PROPOSAL_LIMIT')
    positions=sorted(positions,key=lambda p:-ratios[p[0],p[1]])
    th,tw=ink.shape;accepted=[]
    for y,x in positions:
        x,y=int(x),int(y);box=[x,y,x+tw,y+th]
        if any(_overlap(box,m['bbox_pixels'])>.10 for m in existing+accepted):continue
        patch=projected[y:y+th,x:x+tw];cells=[]
        for cell in range(8):
            left,right=cell*tw//8,(cell+1)*tw//8;i=ink[:,left:right];r=ring[:,left:right]
            if np.count_nonzero(i)<8 or np.count_nonzero(r)<8:continue
            ref=reference[:,left:right];delta=float(ref[i].mean()-ref[r].mean())
            if delta<3:continue
            part=patch[:,left:right];cells.append(float((part[i].mean()-part[r].mean())/delta))
        support=sum(.35<=v<=1.65 for v in cells)
        if len(cells)<6 or support/len(cells)<.875 or not .60<=np.median(cells)<=1.40:continue
        edge_patch=candidate_edges[y:y+th,x:x+tw];edge_patch=edge_patch-edge_patch.mean()
        denominator=np.linalg.norm(edge_patch)*edge_norm
        edge_correlation=float(np.sum(edge_patch*edge_reference)/denominator) if denominator else 0
        if edge_correlation<.35:continue
        accepted.append(dict(bbox_pixels=box,method='STROKE_LOCAL_CONTRAST',contrast_ratio=float(ratios[y,x]),
            strip_support=support,strip_count=len(cells),median_strip_ratio=float(np.median(cells)),edge_correlation=edge_correlation))
        if len(existing)+len(accepted)>256:raise ValueError('GLOBAL_GLYPH_MATCH_LIMIT')
    # Occluded/faint copies can lose most whole-pattern evidence. Two separate
    # adjacent stroke fragments must independently meet the unchanged NCC floor
    # at exactly the same source-pattern translation. No free text detection.
    accepted+=_partial_edge_matches(candidate_edges,source_edges[y0:y1,x0:x1],ink,existing+accepted)
    return accepted


def repeated_template_strokes(image,mark,*,proof=None,template_image=None):
    """Locate all copies only after the model explicitly grants IMAGE scope."""
    if mark.get('glyph_search_scope')!='IMAGE':raise ValueError('GLOBAL_GLYPH_SCOPE_REQUIRED')
    projected,reference,strokes,metadata=_template_data(image,mark,template_image)
    th,tw=reference.shape
    scores=_match_scores(projected,reference)
    yy,xx=np.indices(scores.shape);mask=np.zeros(image.shape[:2],np.uint8);matches=[]
    for _ in range(257):
        _,best,_,(x,y)=cv2.minMaxLoc(scores)
        if best<.60:break
        if len(matches)==256:raise ValueError('GLOBAL_GLYPH_MATCH_LIMIT')
        mask[y:y+th,x:x+tw]=np.maximum(mask[y:y+th,x:x+tw],strokes)
        matches.append(dict(bbox_pixels=[x,y,x+tw,y+th],correlation=float(best),method='NCC'))
        intersection=np.maximum(0,tw-np.abs(xx-x))*np.maximum(0,th-np.abs(yy-y))
        overlap=intersection/np.maximum(1,2*tw*th-intersection)
        scores[overlap>.10]=-1
    reference_image=template_image if mark.get('glyph_template_source')=='ORIGINAL' and template_image is not None else image
    additional=_contrast_matches(image,reference_image,strokes,metadata,matches)
    for match in additional:
        x,y,x1,y1=match['bbox_pixels'];mask[y:y1,x:x1]=np.maximum(mask[y:y1,x:x1],strokes)
    matches+=additional
    if not matches:raise ValueError('GLYPH_MATCH_UNPROVEN')
    if proof is not None:
        proof.update(metadata,method='AI_APPROVED_PATTERN_GLOBAL_PIXEL_ALIGNMENT',scope='IMAGE',
            matches=matches,duplicate_overlap_limit=.10,mask_pixels=int(np.count_nonzero(mask)))
    return mask
