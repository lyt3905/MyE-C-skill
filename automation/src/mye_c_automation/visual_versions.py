"""Geometric and pixel evidence for versions of one photograph, not same products."""
import hashlib
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageOps

VERSION='same-photo-versions/v1'
PARAMETERS=dict(max_side=1000,ratio=.72,min_inliers=32,min_inlier_fraction=.75,min_feature_coverage=.20,
                min_visible_coverage=.90,max_mean_difference=10.,min_pixel_agreement=.88,min_center_agreement=.88)


def _sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class FeatureCache:
    def __init__(self):self.items={}
    def get(self,path):
        key=str(Path(path).resolve())
        if key not in self.items:
            with Image.open(path) as original:
                im=ImageOps.exif_transpose(original);im.thumbnail((1000,1000))
                rgba=im.convert('RGBA');background=Image.new('RGBA',rgba.size,'white');background.alpha_composite(rgba)
                pixels=np.array(background.convert('RGB'))
            gray=cv2.cvtColor(pixels,cv2.COLOR_RGB2GRAY)
            points,descriptors=cv2.SIFT_create(nfeatures=2500).detectAndCompute(gray,None)
            self.items[key]=(pixels,gray,points,descriptors)
        return self.items[key]


def compare_versions(source,candidate,observation,*,cache=None):
    """Require broad feature agreement and dense foreground agreement after alignment."""
    from mye_c_automation.ai_judge.image_action_decision import region, mark_disposition
    cache=cache or FeatureCache();image,gray,kp,des=cache.get(source);other,_,op,od=cache.get(candidate)
    h,w=gray.shape;oh,ow=other.shape[:2]
    result=dict(verified=False,algorithm_version=VERSION,source_sha256=_sha(source),candidate_sha256=_sha(candidate))
    def reject(code):result['reason']=code;return result
    if des is None or od is None or len(kp)<32 or len(op)<32:return reject('INSUFFICIENT_FEATURES')
    allowed=np.ones((h,w),np.uint8)*255
    for mark in observation.get('watermarks',[]):
        if mark_disposition(mark)=='PROTECTED':continue
        if mark_disposition(mark)!='REMOVABLE' and mark.get('overlay_role')!='OTHER_STORE_FRAME':continue
        points=np.array([[min(w-1,int(x*w)),min(h-1,int(y*h))] for x,y in region(mark)],np.int32)
        cv2.fillPoly(allowed,[points],0)
    allowed=cv2.erode(allowed,np.ones((5,5),np.uint8))
    if np.count_nonzero(allowed)/allowed.size<.60:return reject('TOO_LITTLE_UNCOVERED_PHOTO')
    matches=[]
    for pair in cv2.BFMatcher().knnMatch(des,od,k=2):
        if len(pair)!=2:continue
        a,b=pair;x,y=kp[a.queryIdx].pt
        if a.distance<PARAMETERS['ratio']*b.distance and allowed[min(h-1,int(y)),min(w-1,int(x))]:matches.append(a)
    if len(matches)<32:return reject('INSUFFICIENT_MATCHES')
    source_points=np.float32([kp[m.queryIdx].pt for m in matches]);candidate_points=np.float32([op[m.trainIdx].pt for m in matches])
    matrix,inlier_mask=cv2.findHomography(candidate_points,source_points,cv2.RANSAC,2.5)
    if matrix is None or not np.isfinite(matrix).all():return reject('NO_STABLE_ALIGNMENT')
    inliers=inlier_mask.ravel().astype(bool);count=int(inliers.sum());fraction=float(inliers.mean())
    result.update(matches=len(matches),inliers=count,inlier_fraction=fraction)
    if count<32 or fraction<PARAMETERS['min_inlier_fraction']:return reject('INCONSISTENT_FEATURES')
    hull=cv2.convexHull(source_points[inliers]);coverage=float(cv2.contourArea(hull)/(w*h));result['feature_coverage']=coverage
    if coverage<PARAMETERS['min_feature_coverage']:return reject('MATCHES_TOO_LOCAL')
    corners=np.float32([[[0,0],[ow,0],[ow,oh],[0,oh]]]);projected=cv2.perspectiveTransform(corners,matrix)[0]
    area=float(cv2.contourArea(projected,oriented=True)/(w*h))
    if not .65<=area<=1.8 or not cv2.isContourConvex(projected):return reject('UNSUITABLE_FRAMING_OR_FLIP')
    warped=cv2.warpPerspective(other,matrix,(w,h));valid=cv2.warpPerspective(np.ones((oh,ow),np.uint8)*255,matrix,(w,h),flags=cv2.INTER_NEAREST)>0
    usable=allowed>0;visible=valid&usable
    coverage=float(visible.sum()/max(1,usable.sum()));result['visible_coverage']=coverage
    if coverage<PARAMETERS['min_visible_coverage']:return reject('SOURCE_CONTENT_CROPPED')
    # Features in a common background cannot prove that a toy has the same pose.
    a=cv2.GaussianBlur(image,(3,3),0).astype(np.float32);b=cv2.GaussianBlur(warped,(3,3),0).astype(np.float32)
    difference=np.abs(a-b);agreement=difference.max(axis=2)<=25
    center=np.zeros((h,w),bool);center[int(.15*h):int(.85*h),int(.2*w):int(.8*w)]=True
    center_valid=visible&center
    if center_valid.sum()/max(1,center.sum())<.60:return reject('SUBJECT_COMPARISON_UNAVAILABLE')
    mean=float(difference[visible].mean());pixel=float(agreement[visible].mean());central=float(agreement[center_valid].mean());center_mean=float(difference[center_valid].mean())
    result.update(mean_difference=mean,pixel_agreement=pixel,center_agreement=central,center_mean_difference=center_mean)
    if mean>10 or center_mean>10 or pixel<.88 or central<.88:return reject('DIFFERENT_PHOTOGRAPH_CONTENT')
    result.update(verified=True,reason='SAME_PHOTO_GEOMETRY_AND_PIXELS',homography=matrix.tolist())
    return result


def clean_candidate(result,content):
    o=result.get('observation') or {}
    return (bool(o) and result.get('decision')=='KEEP' and not o.get('abstain') and
            all(type(content.get(k)) is int and content[k]>0 for k in ('width','height')) and content.get('format') in {'PNG','JPEG','WEBP'})


def find_versions(inventory,judgements):
    cache=FeatureCache();matches={};attempts=[];contents=inventory['contents']
    clean=[(d,c) for d,c in contents.items() if clean_candidate(judgements[d],c)]
    clean.sort(key=lambda pair:(-pair[1]['width']*pair[1]['height'],pair[0]))
    for digest,source in contents.items():
        result=judgements[digest];o=result.get('observation') or {}
        if result.get('decision') not in {'DELETE','REMOVE_TEXT','AI_REGENERATE'} or not o or o.get('abstain'):continue
        for candidate_digest,candidate in clean:
            if candidate_digest==digest:continue
            if _sha(source['file'])!=digest or _sha(candidate['file'])!=candidate_digest:raise ValueError('VISUAL_VERSION_SOURCE_CHANGED')
            checked=compare_versions(source['file'],candidate['file'],o,cache=cache)
            attempts.append(dict(source_sha256=digest,candidate_sha256=candidate_digest,proof=checked))
            if checked['verified']:
                matches[digest]=dict(source_sha256=digest,candidate_sha256=candidate_digest,replacement_url=candidate['urls'][0],proof=checked)
                break
    return dict(schema=VERSION,parameters=PARAMETERS,matches=matches,attempts=attempts,semantic_source='EXISTING_AI_OBSERVATIONS',new_model_calls=0)
