"""Public product-independent watermark execution API. AI review is external."""
from .contracts import WatermarkInputParser, policy_options, from_v2, VERSION
from .regions import WatermarkRegionManager, WatermarkMaskBuilder, visualization
from .engine import RepairRouter, InpaintingEngine
from .quality import WatermarkQualityChecker, sha
import hashlib
import json
from pathlib import Path
import time
import cv2
import numpy as np
from PIL import Image


def _new_image(path,array):
    with Path(path).open('xb') as stream:Image.fromarray(array).save(stream,format='PNG')


def process_watermarks(request,directory,*,lama=None,policy=None,algorithm=None,mask_source=None,prior_mask=None,cache_dir=None):
    """One deterministic attempt. No retry/AI/network/publication is performed."""
    started=time.perf_counter();root=Path(directory).resolve();parsed=None;running=False;owned_directory=False;engine=None
    result=dict(schema_version=VERSION,processing_status='BLOCKED',quality_status='REVIEW',input_sha256=None,output_sha256=None,
        output_path=None,mask_paths=[],mask_sha256={},visualization_path=None,watermark_instances_total=0,watermark_instances_processed=0,
        algorithm_used=[],model_version=[],processing_parameters={},execution_time=0,failure_reason=None,regions=[])
    try:
        if root.exists() and any(root.iterdir()):raise ValueError('OUTPUT_DIRECTORY_NOT_EMPTY')
        root.mkdir(parents=True,exist_ok=True);owned_directory=True
        options=policy_options(policy);result['processing_parameters']=options
        parsed=WatermarkInputParser().parse(request);result['input_sha256']=parsed.sha256
        result['watermark_instances_total']=len(parsed.instances)
        if parsed.request['decision']!='REMOVE_TEXT':result.update(processing_status='NOT_APPLICABLE');return result
        if parsed.request['authorization_status']!='OWNED_OR_LICENSED':raise ValueError('RIGHTS_NOT_AUTHORIZED')
        masks,union=WatermarkMaskBuilder().build(parsed,options)
        result['mask_plans']=[row['mask_plan'] for row in masks]
        if (mask_source is None)!=(prior_mask is None):raise ValueError('RESIDUAL_INPUT_PAIR_REQUIRED')
        if prior_mask is not None:
            from mye_c_automation.image_repairs_v2 import deterministic_quality,mask_for
            if parsed.source_path is None or not deterministic_quality(parsed.source_path,mask_source,prior_mask)['ok']:raise ValueError('RESIDUAL_SOURCE_UNBOUND')
            with Image.open(prior_mask) as previous:inherited=np.array(previous)
            if inherited.shape!=union.shape or inherited.dtype!=np.uint8 or not np.isin(inherited,[0,255]).all():raise ValueError('INVALID_PRIOR_MASK')
            # Revalidate all protected pixels and area constraints on the union.
            from .text_masks import execution_observation
            executed=execution_observation(parsed.request,result['mask_plans'])
            mask_for((parsed.pixels.shape[1],parsed.pixels.shape[0]),executed,image=parsed.pixels,
                max_area=options['max_mask_area'],dilation=options['dilation'],inherited_mask=inherited)
            # Previous masks may contain many distant components. Preserve their
            # independent geometry rather than turning them into one huge ROI.
            count,labels=cv2.connectedComponents((inherited>0).astype(np.uint8),8)
            for index in range(1,count):
                part=(labels==index).astype(np.uint8)*255
                mark=dict(watermark_id='prior-mask-component-'+str(index),group_id='prior-mask')
                masks.append(dict(instance=mark,mask=part,origin='BOUND_PREVIOUS_MASK_GEOMETRY_NOT_NEW_AI_OBSERVATION'))
            union=np.maximum(union,inherited)
            result['inherited_mask_sha256']=sha(prior_mask);result['mask_source_sha256']=sha(mask_source)
        regions=WatermarkRegionManager().plan(parsed,masks,options)
        root.mkdir(parents=True,exist_ok=True)
        union_path=root/'mask.png';_new_image(union_path,union);result['mask_paths'].append(str(union_path))
        for i,row in enumerate(masks):
            path=root/('instance-'+str(i)+'-mask.png');_new_image(path,row['mask']);result['mask_paths'].append(str(path))
        result['mask_sha256']={name:sha(name) for name in result['mask_paths']}
        preview=root/'mask-overlay.png';_new_image(preview,visualization(parsed.pixels,union));result['visualization_path']=str(preview)
        running=True;engine=InpaintingEngine();output,records=engine.run(parsed,regions,options,lama=lama,algorithm=algorithm,cache_dir=cache_dir)
        glyph_masks=[row['mask'] for row in masks if row.get('mask_plan',{}).get('strategy')=='AUTO_TEXT_GLYPHS']
        if glyph_masks:
            from mye_c_automation.image_repairs_v2 import _uniform_background_cleanup
            result['uniform_background_cleanup_components']=_uniform_background_cleanup(parsed.pixels,output,np.maximum.reduce(glyph_masks))
        if parsed.source_path and sha(parsed.source_path)!=parsed.sha256:raise ValueError('ORIGINAL_CHANGED')
        path=root/'repaired.png'
        _new_image(path,np.dstack([output,parsed.rgba[:,:,3]]) if np.any(parsed.rgba[:,:,3]!=255) else output)
        result.update(output_path=str(path),output_sha256=sha(path),regions=records,watermark_instances_processed=len(parsed.instances),
            algorithm_used=list(dict.fromkeys(row['algorithm'] for row in records)),model_version=list(dict.fromkeys(row['model_version'] for row in records)))
        checked=WatermarkQualityChecker().check(parsed.request,result);result['deterministic_quality']=checked
        if not checked['ok']:raise ValueError(checked['reason'])
        result.update(processing_status='PROCESSED',quality_status='PENDING_AI_REVIEW')
    except (ValueError,OSError,RuntimeError,ImportError,KeyError,TypeError,cv2.error) as exc:
        if engine is not None:result['regions']=engine.records
        counts={}
        for row in result['regions']:
            if row['status']=='PROCESSED':
                for i in row['instance_ids']:counts[i]=counts.get(i,0)+1
        completed={i for i,n in counts.items() if engine is not None and n==engine.expected_instances.get(i)}
        processed=sum(m['watermark_id'] in completed for m in parsed.instances) if parsed else 0
        result.update(processing_status='FAILED' if running else 'BLOCKED',quality_status='FAIL' if running else 'REVIEW',
            failure_reason=str(exc),error_type=type(exc).__name__,output_path=None,output_sha256=None,watermark_instances_processed=processed,
            algorithm_used=list(dict.fromkeys(row['algorithm'] for row in result['regions'])),model_version=list(dict.fromkeys(row['model_version'] for row in result['regions'])))
    finally:
        result['execution_time']=round(time.perf_counter()-started,6)
        if owned_directory and not (root/'processing-result.json').exists():
            with (root/'processing-result.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    return result
