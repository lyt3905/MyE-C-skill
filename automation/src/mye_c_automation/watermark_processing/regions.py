"""Deterministic grouping and sparse masks for explicitly supplied instances."""
import cv2
import numpy as np
from mye_c_automation.ai_judge.image_action_decision import mark_disposition


class WatermarkMaskBuilder:
    def build(self,parsed,policy):
        from .text_masks import build_instance_mask
        masks=[];protected=[m for m in parsed.request['watermarks'] if mark_disposition(m)!='REMOVABLE']
        for instance in parsed.instances:
            mask,plan=build_instance_mask(parsed,instance,protected,policy)
            masks.append(dict(instance=instance,mask=mask,mask_plan=plan))
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
        pieces=[]
        for row in masks:
            b=bounds(row['mask'])
            if area(extend(b))<=policy['max_roi_area']:
                pieces.append(row);continue
            if not policy['tile_large_regions']:raise ValueError('ROI_AREA')
            # Context can shrink, but cannot be discarded to evade ROI policy.
            margin=max(policy['context_pixels'],policy['tile_overlap_pixels'])
            def padded(b):return [max(0,b[0]-margin),max(0,b[1]-margin),min(w,b[2]+margin),min(h,b[3]+margin)]
            pending=[b];leaves=[]
            while pending:
                box=pending.pop();x0,y0,x1,y1=box
                if not np.any(row['mask'][y0:y1,x0:x1]):continue
                if area(padded(box))<=policy['max_roi_area']:
                    part=np.zeros((h,w),np.uint8);part[y0:y1,x0:x1]=row['mask'][y0:y1,x0:x1]
                    if np.any(part):leaves.append(dict(row,mask=part,tile_roi=padded(box)))
                    continue
                if len(pending)+len(leaves)>=256:raise ValueError('ROI_TILE_LIMIT')
                if x1-x0>=y1-y0 and x1-x0>1:
                    mid=(x0+x1)//2;pending.extend([[x0,y0,mid,y1],[mid,y0,x1,y1]])
                elif y1-y0>1:
                    mid=(y0+y1)//2;pending.extend([[x0,y0,x1,mid],[x0,mid,x1,y1]])
                else:raise ValueError('ROI_AREA_CONTEXT')
            pieces.extend(leaves)
        for row in pieces:
            mark=row['instance'];b=bounds(row['mask']);roi=row.get('tile_roi',extend(b))
            selected=None
            for group in regions:
                if 'tile_roi' in row or group.get('tiled'):continue
                a=group['bounds'];joined=[min(a[0],b[0]),min(a[1],b[1]),max(a[2],b[2]),max(a[3],b[3])]
                near=max(0,a[0]-b[2],b[0]-a[2])<=gap and max(0,a[1]-b[3],b[1]-a[3])<=gap
                if group['group_id']==mark['group_id'] and near and area(extend(joined))<=policy['max_roi_area']:
                    group['bounds']=joined;group['roi']=extend(joined);selected=group;break
            if selected is None:
                selected=dict(region_id='roi-'+str(len(regions)),group_id=mark['group_id'],bounds=b,roi=roi,
                    tiled='tile_roi' in row,instance_ids=[],marks=[],mask=np.zeros((h,w),np.uint8))
                regions.append(selected)
            selected['instance_ids'].append(mark['watermark_id']);selected['marks'].append(mark)
            selected['mask']=np.maximum(selected['mask'],row['mask'])
        return regions


def visualization(pixels,mask):
    tinted=(pixels.astype(np.float32)*.45+np.array([255,30,60])*.55).round().astype(np.uint8)
    return np.where(mask[:,:,None]>0,tinted,pixels)
