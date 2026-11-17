"""Pixel geometry inside AI-approved text regions; never reads/classifies text."""
from copy import deepcopy
import cv2
import numpy as np
from mye_c_automation.ai_judge.image_action_decision import region


def execution_observation(original,plans):
    """Append-only derived execution geometry; caller retains the original reply."""
    from mye_c_automation.ai_judge.image_action_decision import mark_disposition
    derived=deepcopy(original);by_id={p['watermark_id']:p['execution_mark'] for p in plans}
    derived['watermarks']=[deepcopy(by_id.get(m.get('watermark_id','v2-instance-'+str(i)),m))
        if mark_disposition(m)=='REMOVABLE' else m for i,m in enumerate(derived['watermarks'])]
    return derived


def _box(mark):
    points=region(mark)
    return [min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]


def prepare_execution(image,original,policy):
    """User-approved execution policy over AI semantics; never rewrite a reply."""
    from mye_c_automation.image_repairs_v2 import mask_for
    from mye_c_automation.ai_judge.image_action_decision import mark_disposition,mark_owner
    from mye_c_automation.template_glyphs import _template_data
    h,w=image.shape[:2];derived=deepcopy(original)
    proof=dict(authority='CONFIGURED_USER_EXECUTION_POLICY',semantic_classification=False,
        groups=[],sample_failures=[],protection_adjustments=[],policy={k:policy[k] for k in
            ('prefer_repeated_glyphs','covered_print_policy','protection_overlap_trial')})
    groups={}
    if policy['prefer_repeated_glyphs'] and policy['auto_text_masks']:
        for i,m in enumerate(derived['watermarks']):
            if (mark_disposition(m)=='REMOVABLE' and m.get('content_type')=='TEXT' and m.get('group_id')
                and m.get('repair_mode') in {None,'REGION','TEMPLATE_GLYPHS'}):
                groups.setdefault(m['group_id'],[]).append((i,m))
    replacements={};removed=set()
    for group,members in groups.items():
        if len(members)<2:continue
        selected=False
        for index,sample in members[:8]:
            trial=deepcopy(sample)
            trial.update(repair_mode='TEMPLATE_GLYPHS',glyph_search_scope='IMAGE',
                glyph_template_bbox=sample.get('glyph_template_bbox',_box(sample)),glyph_template_source='ORIGINAL')
            try:
                _,_,strokes,_=_template_data(image,trial)
                count,_,stats,_=cv2.connectedComponentsWithStats((strokes>0).astype(np.uint8),8)
                if sum(int(stats[i,cv2.CC_STAT_AREA])>=2 for i in range(1,count))<2:
                    raise ValueError('GLYPH_REFERENCE_COMPONENTS')
                geometry=[]
                mask,_=mask_for((w,h),dict(original,watermarks=[trial],preserve_regions=[]),image=image,
                    max_area=policy['max_mask_area'],dilation=policy['dilation'],geometry=geometry)
                if len(geometry[0].get('matches',[]))<2:raise ValueError('REPEATED_PATTERN_NOT_PROVEN')
                replacements[members[0][0]]=trial;removed.update(i for i,m in members[1:])
                proof['groups'].append(dict(group_id=group,source_instance_ids=[m.get('watermark_id','v2-instance-'+str(i)) for i,m in members],
                    sample_instance_id=sample.get('watermark_id','v2-instance-'+str(index)),sample_bbox=trial['glyph_template_bbox'],
                    geometry=geometry,mask_pixels=int(np.count_nonzero(mask)),strategy='REPEATED_PATTERN_GLYPHS'))
                selected=True
                break
            except ValueError as exc:
                proof['sample_failures'].append(dict(group_id=group,sample_index=index,reason=str(exc)))
        if not selected:
            # Fresh explicit instances retain a bounded region trial when the
            # supplied templates all fail. A single legacy IMAGE seed cannot
            # claim complete repair by falling back to only its sample box.
            for index,mark in members:
                if mark.get('glyph_search_scope')=='IMAGE':continue
                fallback=deepcopy(mark);fallback['repair_mode']='REGION'
                for key in ('glyph_search_scope','glyph_template_bbox','glyph_template_source','glyph_template_candidates'):fallback.pop(key,None)
                replacements[index]=fallback
    derived['watermarks']=[deepcopy(replacements.get(i,m)) for i,m in enumerate(derived['watermarks']) if i not in removed]
    if policy['protection_overlap_trial']:
        proof['protection_handling']='POST_EXECUTION_REVIEW'
        return derived,proof
    removable=[m for m in derived['watermarks'] if mark_disposition(m)=='REMOVABLE']
    # A broad/unknown removal cannot acquire covered-print reconstruction.
    if (policy['covered_print_policy']=='EXACT' or not removable or
        any(m.get('repair_mode')!='TEMPLATE_GLYPHS' for m in removable)):
        return derived,proof
    def print_label(m):
        return (mark_disposition(m)=='PROTECTED' and m.get('preserve_mode','EXACT_REGION')=='EXACT_REGION' and
            (m['kind'] in {'MODEL_TEXT','PRODUCT_PRINT','PACKAGING_PRINT'} or
             m['kind']=='PROMOTIONAL_TEXT' and mark_owner(m)=='MANUFACTURER'))
    labels=[m for m in derived['watermarks'] if print_label(m)]
    def same_box(a,b):
        x,y,u,v=_box(a);xx,yy,uu,vv=_box(b)
        overlap=max(0,min(u,uu)-max(x,xx))*max(0,min(v,vv)-max(y,yy))
        return overlap/max(1e-12,(u-x)*(v-y)+(uu-xx)*(vv-yy)-overlap)>=.8
    selected=[]
    for i,m in enumerate(derived['watermarks']):
        if print_label(m):selected.append(('watermarks',i,'preserve_mode'))
    for i,r in enumerate(derived['preserve_regions']):
        if r.get('scope','EXACT_REGION')=='EXACT_REGION' and any(same_box(r,m) for m in labels):
            selected.append(('preserve_regions',i,'scope'))
    if not selected:return derived,proof
    bright=deepcopy(derived)
    for field,index,key in selected:bright[field][index][key]='BRIGHT_PRINT_GLYPHS'
    try:
        geometry=[]
        mask_for((w,h),bright,image=image,max_area=policy['max_mask_area'],dilation=policy['dilation'],protection_geometry=geometry)
        mode='BRIGHT_PRINT_GLYPHS';derived=bright
    except ValueError as exc:
        # Only actual ink overlap can use the approved small restoration trial.
        # Missing ink, unknown/structural regions and area limits never disappear.
        if str(exc)!='PROTECTED_REGION_OVERLAP':return derived,proof
        restored=deepcopy(derived)
        for field,index,key in selected:restored[field][index][key]='PRINT_RESTORE'
        geometry=[]
        mask_for((w,h),restored,image=image,max_area=policy['max_mask_area'],dilation=policy['dilation'],protection_geometry=geometry)
        mode='PRINT_RESTORE';derived=restored
    proof['protection_adjustments']=[dict(field=field,index=index,from_mode='EXACT_REGION',to_mode=mode) for field,index,key in selected]
    proof['print_protection']=geometry
    return derived,proof


def build_instance_mask(parsed,instance,protected,policy):
    from mye_c_automation.image_repairs_v2 import mask_for
    from mye_c_automation.template_glyphs import _template_data
    image=parsed.pixels;h,w=image.shape[:2]
    plan=dict(watermark_id=instance['watermark_id'],group_id=instance['group_id'],
        strategy='EXPLICIT_REGION',sample_failures=[],semantic_classification=False)
    def build(mark):
        geometry=[]
        mask,_=mask_for((w,h),dict(parsed.request,watermarks=[mark]+protected),image=image,
            max_area=policy['max_mask_area'],dilation=policy['dilation'],geometry=geometry,
            allow_protected_overlap=policy['protection_overlap_trial'])
        return mask,geometry
    eligible=(policy['auto_text_masks'] and instance.get('content_type')=='TEXT'
        and instance.get('repair_mode') in {None,'REGION'})
    if eligible:
        # Try this exact instance first (also supports SINGLE), then up to seven
        # explicitly same-group text samples. Never search arbitrary other text.
        samples=[instance]+[m for m in parsed.instances if m['watermark_id']!=instance['watermark_id']
            and m['group_id']==instance['group_id'] and m.get('content_type')=='TEXT'
            and m.get('repair_mode') in {None,'REGION'}]
        unshared=None
        for sample in samples[:8]:
            seed=_box(sample);trial=deepcopy(instance)
            trial.update(repair_mode='TEMPLATE_GLYPHS',glyph_template_bbox=seed,glyph_template_source='ORIGINAL')
            try:
                _,_,strokes,metadata=_template_data(image,trial)
                count,_,stats,_=cv2.connectedComponentsWithStats((strokes>0).astype(np.uint8),8)
                components=sum(int(stats[i,cv2.CC_STAT_AREA])>=2 for i in range(1,count))
                # A filled rectangular object is not a glyph reference. This
                # is a geometry test, not recognition of its word or ownership.
                if components<2:raise ValueError('GLYPH_REFERENCE_COMPONENTS')
                mask,geometry=build(trial)
                selected=dict(plan,strategy='AUTO_TEXT_GLYPHS',sample_instance_id=sample['watermark_id'],
                    sample_bbox=seed,execution_mark=trial,template_geometry=geometry,
                    reference_components=components)
                if sample['watermark_id']==instance['watermark_id'] and len(samples)>1:
                    shared=False
                    for peer in samples[1:4]:
                        probe=deepcopy(peer);probe.update(repair_mode='TEMPLATE_GLYPHS',glyph_template_bbox=seed,glyph_template_source='ORIGINAL')
                        try:build(probe);shared=True;break
                        except ValueError:pass
                    if not shared:
                        unshared=(mask,selected)
                        plan['sample_failures'].append(dict(sample_instance_id=sample['watermark_id'],reason='GROUP_REFERENCE_NOT_SHARED'))
                        continue
                return mask,selected
            except ValueError as exc:
                if str(exc) in {'PROTECTED_REGION_OVERLAP','PRINT_RESTORE_AREA','MASK_AREA'}:raise
                plan['sample_failures'].append(dict(sample_instance_id=sample['watermark_id'],reason=str(exc)))
        if unshared is not None:return unshared
        plan['strategy']='BOUNDED_REGION_FALLBACK'
    mask,geometry=build(instance)
    plan.update(execution_mark=deepcopy(instance),template_geometry=geometry)
    return mask,plan
