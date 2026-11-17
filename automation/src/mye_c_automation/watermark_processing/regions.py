"""Deterministic grouping and sparse masks for explicitly supplied instances."""
import cv2
import numpy as np
from mye_c_automation.ai_judge.image_action_decision import mark_disposition


class WatermarkMaskBuilder:
    def build(self,parsed,policy):
        from mye_c_automation.image_repairs_v2 import mask_for
        masks=[];protected=[m for m in parsed.request['watermarks'] if mark_disposition(m)!='REMOVABLE']
        for instance in parsed.instances:
            observation=dict(parsed.request,watermarks=[instance]+protected)
            mask,_=mask_for((parsed.pixels.shape[1],parsed.pixels.shape[0]),observation,image=parsed.pixels,
                max_area=policy['max_mask_area'],dilation=policy['dilation'])
            masks.append(dict(instance=instance,mask=mask))
        if not masks:raise ValueError('NO_EXECUTABLE_WATERMARK_INSTANCES')
        union=np.maximum.reduce([row['mask'] for row in masks]);ratio=float(np.count_nonzero(union)/union.size)
        if not 0<ratio<=policy['max_mask_area']:raise ValueError('MASK_AREA')
        return masks,union


class WatermarkRegionManager:
    def plan(self,parsed,masks,policy):
        h,w=parsed.pixels.shape[:2];regions=[];gap=policy['adjacency_pixels'];context=policy['context_pixels']
        def bounds(mask):
            ys,xs=np.where(mask>0)
            return [int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1]
        def extend(b):return [max(0,b[0]-context),max(0,b[1]-context),min(w,b[2]+context),min(h,b[3]+context)]
        def area(b):return (b[2]-b[0])*(b[3]-b[1])/(w*h)
        for row in masks:
            mark=row['instance'];b=bounds(row['mask']);roi=extend(b)
            if area(roi)>policy['max_roi_area']:raise ValueError('ROI_AREA')
            selected=None
            for group in regions:
                a=group['bounds'];joined=[min(a[0],b[0]),min(a[1],b[1]),max(a[2],b[2]),max(a[3],b[3])]
                near=max(0,a[0]-b[2],b[0]-a[2])<=gap and max(0,a[1]-b[3],b[1]-a[3])<=gap
                if group['group_id']==mark['group_id'] and near and area(extend(joined))<=policy['max_roi_area']:
                    group['bounds']=joined;group['roi']=extend(joined);selected=group;break
            if selected is None:
                selected=dict(region_id='roi-'+str(len(regions)),group_id=mark['group_id'],bounds=b,roi=roi,instance_ids=[],marks=[],mask=np.zeros((h,w),np.uint8))
                regions.append(selected)
            selected['instance_ids'].append(mark['watermark_id']);selected['marks'].append(mark)
            selected['mask']=np.maximum(selected['mask'],row['mask'])
        return regions


def visualization(pixels,mask):
    tinted=(pixels.astype(np.float32)*.45+np.array([255,30,60])*.55).round().astype(np.uint8)
    return np.where(mask[:,:,None]>0,tinted,pixels)
