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


def build_instance_mask(parsed,instance,protected,policy):
    from mye_c_automation.image_repairs_v2 import mask_for
    from mye_c_automation.template_glyphs import _template_data
    image=parsed.pixels;h,w=image.shape[:2]
    plan=dict(watermark_id=instance['watermark_id'],group_id=instance['group_id'],
        strategy='EXPLICIT_REGION',sample_failures=[],semantic_classification=False)
    def build(mark):
        geometry=[]
        mask,_=mask_for((w,h),dict(parsed.request,watermarks=[mark]+protected),image=image,
            max_area=policy['max_mask_area'],dilation=policy['dilation'],geometry=geometry)
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
