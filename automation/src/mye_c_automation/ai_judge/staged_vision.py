"""Versioned phase contracts derived from canonical business enums, no I/O client."""
from copy import deepcopy
import hashlib,json
from pathlib import Path
from jsonschema import Draft202012Validator
from .structured_output import load_v2_schema

VERSION='image-review.staged-v1'
INITIAL=('decision','visual_class','retail_box_status','sku_suitability','abstain','reason')
MARK_FIELDS=('watermark_id','group_id','action','kind','owner','content_type','bbox','polygon')

def phase_schema(phase):
    old=load_v2_schema();properties=old['properties']
    if phase=='initial':props={k:deepcopy(properties[k]) for k in INITIAL}
    else:
        mark=deepcopy(properties['watermarks']['items'])
        mark['properties']={k:v for k,v in mark['properties'].items() if k in MARK_FIELDS}
        mark['required']=[k for k in MARK_FIELDS if k not in {'bbox','polygon'}];mark.pop('allOf',None)
        marks=dict(type='array',maxItems=256,items=mark)
        if phase=='planning':
            protected=deepcopy(properties['preserve_regions']);protected['maxItems']=256
            protected['items']['additionalProperties']=False
            protected['items']['properties']['scope']['enum']=['EXACT_REGION']
            props=dict(watermarks=marks,preserve_regions=protected,reason=deepcopy(properties['reason']))
        elif phase=='quality':
            from .image_quality_v2 import CHECKS
            props=dict(decision=dict(enum=['MATCH','MISMATCH','UNCERTAIN']),abstain=dict(type='boolean'),
                checks=dict(type='object',properties={k:dict(type='boolean') for k in sorted(CHECKS)},required=sorted(CHECKS),additionalProperties=False),
                residual_watermarks=marks,reason=deepcopy(properties['reason']))
        else:raise ValueError('UNKNOWN_VISION_PHASE')
    props['reason']['maxLength']=600
    return dict(type='object',properties=props,required=list(props),additionalProperties=False)

def phase_prompt(phase):
    text=(Path(__file__).resolve().parents[1]/'prompts'/('vision_'+phase+'.staged.md')).read_text(encoding='utf-8')
    return text+'\nOUTPUT_JSON_SCHEMA:\n'+json.dumps(phase_schema(phase),ensure_ascii=False,separators=(',',':'))

def validate_phase(phase,row):
    errors=list(Draft202012Validator(phase_schema(phase)).iter_errors(row))
    if errors:raise ValueError('SCHEMA_VALIDATION_FAILED:'+(';'.join('/'.join(map(str,e.absolute_path))+':'+str(e.validator) for e in errors[:8])))
    if phase!='initial':
        from .image_action_decision import region
        from mye_c_automation.watermark_processing.contracts import check_polygon
        marks=row.get('watermarks',row.get('residual_watermarks',[]));ids=set()
        for mark in marks:
            check_polygon(mark)
            if mark['watermark_id'] in ids:raise ValueError('BUSINESS_VALIDATION_FAILED:DUPLICATE_MARK_ID')
            ids.add(mark['watermark_id'])
            if mark['action']=='REMOVE_TEXT' and (mark['owner'] in {'MANUFACTURER','PRODUCT','PACKAGING','CREATOR'} or mark['kind'] in {'MANUFACTURER_LOGO','PRODUCT_PRINT','PACKAGING_PRINT','MODEL_TEXT','CREATOR_CREDIT','NORMAL_PHOTO_TEXT','UNKNOWN_TEXT'}):
                raise ValueError('BUSINESS_VALIDATION_FAILED:PROTECTED_REMOVAL_CONFLICT')
        for p in row.get('preserve_regions',[]):check_polygon(p)
        if phase=='planning' and not any(m['action']=='REMOVE_TEXT' for m in marks):raise ValueError('BUSINESS_VALIDATION_FAILED:NO_REMOVAL_TARGET')
        if phase=='quality':
            if row['decision']=='MATCH' and (row['abstain'] or not all(row['checks'].values()) or marks):raise ValueError('BUSINESS_VALIDATION_FAILED:QUALITY_CONTRADICTION')
            if marks and (row['checks']['overlay_removed'] or any(m['action']!='REMOVE_TEXT' for m in marks)):raise ValueError('BUSINESS_VALIDATION_FAILED:RESIDUAL_CONTRADICTION')
    return row

def bind_initial(row,item):
    validate_phase('initial',row)
    return dict(deepcopy(row),schema_version=VERSION,task_type='image_action_decision',item_id=item['id'],image_id=item['id'],
        image_sha256=item['sha256'],image_type=item['image_type'],evidence_ids=deepcopy(item['evidence_ids']))

def execution_marks(marks):
    # This is executor configuration, not a fabricated model observation/score.
    return [dict(deepcopy(m),repair_mode='REGION') if m['action']=='REMOVE_TEXT' else deepcopy(m) for m in marks]

def decide(client,item,context):
    from mye_c_automation.model_config import review_models
    try:
        response=client.request_vision_phase('initial',item,context);raw=response['result'];observed=bind_initial(raw,item)
        action=raw['decision'] if not raw['abstain'] else 'REVIEW'
        return dict(decision=action,observation=observed,results=[deepcopy(raw)],staged_evidence=response,policy_adjustments=[],models=list(review_models(client.models)),
            decision_authority='MODEL',confidence_policy='NOT_REQUESTED',normalized_results=[deepcopy(raw)],field_differences={},geometry_differences={},
            reason_codes=['VISION_UNRESOLVED'] if action=='REVIEW' else [],second_model_called=False)
    except (ValueError,OSError,KeyError,TypeError) as exc:
        return dict(decision='REVIEW',observation=None,results=[],models=list(review_models(client.models)),reason_codes=['STAGED_INITIAL_FAILED:'+str(exc)],
            policy_adjustments=[],decision_authority='MODEL',confidence_policy='NOT_REQUESTED',second_model_called=False)

def plan(client,source,observation,directory,context):
    from mye_c_automation.job_manager import atomic_json
    from mye_c_automation.candidate_quality import sha256
    root=Path(directory);root.mkdir(parents=True,exist_ok=True)
    if sha256(source)!=observation['image_sha256']:raise ValueError('STAGED_SOURCE_CHANGED')
    item=dict(id=observation['item_id'],sha256=observation['image_sha256'],image_type=observation['image_type'],local=str(source),evidence_ids=observation['evidence_ids'])
    result=client.request_vision_phase('planning',item,dict(context,_initial_observation={k:observation[k] for k in INITIAL}))
    atomic_json(root/'response.json',result)
    derived=deepcopy(observation);derived.update(watermarks=execution_marks(result['result']['watermarks']),preserve_regions=deepcopy(result['result']['preserve_regions']))
    atomic_json(root/'observation.json',derived)
    atomic_json(root/'binding.json',dict(source_sha256=sha256(source),initial_sha256=fingerprint(observation),response_sha256=sha256(root/'response.json'),observation_sha256=sha256(root/'observation.json')))
    return derived

def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def effective(root,digest,result):
    from mye_c_automation.candidate_quality import sha256
    observed=result.get('observation');folder=Path(root)/'v2_candidates'/digest/'planning'
    if not observed or observed.get('schema_version')!=VERSION or not folder.exists():return observed
    read=lambda n:json.loads((folder/n).read_text(encoding='utf-8'))
    binding=read('binding.json');response=read('response.json');derived=read('observation.json')
    if (binding['source_sha256']!=digest or binding['initial_sha256']!=fingerprint(observed) or binding['response_sha256']!=sha256(folder/'response.json')
        or binding['observation_sha256']!=sha256(folder/'observation.json')):raise ValueError('STAGED_PLAN_UNBOUND')
    validate_phase('planning',response['result'])
    expected=dict(deepcopy(observed),watermarks=execution_marks(response['result']['watermarks']),preserve_regions=response['result']['preserve_regions'])
    if derived!=expected:raise ValueError('STAGED_PLAN_CHANGED')
    return derived
