"""V2 unified visual contract and conditional independent review (no I/O writer)."""
from copy import deepcopy
import math
import json
from pathlib import Path
from policy_engine import MODEL_CONFIDENCE_MIN as THRESHOLD

SCHEMA_VERSION='image-action-decision.v2'
PROMPT=(Path(__file__).resolve().parents[2]/'prompts/image_action_decision.v2.md').read_text(encoding='utf-8')
PROMPT+='\nOUTPUT_JSON_SCHEMA:\n'+json.dumps(json.loads((Path(__file__).resolve().parents[1]/'config/schemas/image-action-decision.v2.schema.json').read_text(encoding='utf-8')),ensure_ascii=False,separators=(',',':'))
ACTIONS={'KEEP','DELETE','REMOVE_TEXT','AI_REGENERATE','REVIEW'}
CLASSES={'TOY_PRODUCT','TOY_WITH_RETAIL_BOX','RETAIL_BOX_ONLY','ACCESSORY','PART_OR_COMPONENT','LIFESTYLE_OR_SCENE','INFO_GRAPHIC','OTHER','UNKNOWN'}
MARKS={'STORE_WATERMARK','PROMOTIONAL_TEXT','MANUFACTURER_LOGO','PRODUCT_PRINT','PACKAGING_PRINT','CREATOR_CREDIT','UNKNOWN_TEXT'}

def number(value):
    return type(value) in (int,float) and math.isfinite(value) and 0<=value<=1

def region(row):
    """Validate normalized nonempty rectangle or polygon; never clip bad input."""
    if 'bbox' in row:
        box=row['bbox']
        if not isinstance(box,list) or len(box)!=4 or not all(number(v) for v in box) or not (box[0]<box[2] and box[1]<box[3]):raise ValueError('INVALID_BBOX')
        return [[box[0],box[1]],[box[2],box[1]],[box[2],box[3]],[box[0],box[3]]]
    points=row.get('polygon')
    if (not isinstance(points,list) or len(points)<3 or len(points)>128 or
        any(not isinstance(p,list) or len(p)!=2 or not all(number(v) for v in p) for p in points)):
        raise ValueError('INVALID_POLYGON')
    area=abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1])))/2
    if area<=0:raise ValueError('EMPTY_POLYGON')
    return points

def validate(result,item):
    required={'schema_version','task_type','item_id','image_id','image_sha256','image_type','evidence_ids','confidence','abstain','decision','visual_class','retail_box_status','retail_box_confidence','retail_box_bbox','box_relation','toy_present','toy_confidence','watermarks','product_identity','sku_suitability','subject_complete','clear','angle','background_complexity','preserve_regions','reason'}
    if not isinstance(result,dict) or not required<=result.keys() or result.keys()-required-{'decision_confidence'}:raise ValueError('V2_FIELDS')
    r=deepcopy(result)
    if (r['schema_version']!=SCHEMA_VERSION or r['task_type']!='image_action_decision' or
        r['image_sha256']!=item.get('sha256') or r['item_id']!=item['id'] or r['image_id']!=item['id'] or r['image_type']!=item.get('image_type')):raise ValueError('V2_BINDING')
    if r['decision'] not in ACTIONS or r['visual_class'] not in CLASSES:raise ValueError('V2_ENUM')
    if any(not number(r[k]) for k in ('confidence','retail_box_confidence','toy_confidence')):raise ValueError('V2_CONFIDENCE')
    if 'decision_confidence' in r and r['decision_confidence']!=r['confidence']:raise ValueError('AMBIGUOUS_CONFIDENCE')
    if any(type(r[k]) is not bool for k in ('abstain','toy_present','subject_complete','clear')):raise ValueError('V2_BOOLEAN')
    if (not isinstance(r['evidence_ids'],list) or not r['evidence_ids'] or any(type(e) is not str for e in r['evidence_ids']) or
        not set(r['evidence_ids'])<=set(item.get('evidence_ids',[]))):raise ValueError('V2_EVIDENCE')
    if r['retail_box_status'] not in {'PRESENT','ABSENT','UNCERTAIN'} or r['box_relation'] not in {'SAME_PRODUCT','POSSIBLY_SAME_PRODUCT','UNRELATED'}:raise ValueError('V2_BOX_ENUM')
    if r['retail_box_status']=='PRESENT':region({'bbox':r['retail_box_bbox']})
    elif r['retail_box_bbox'] is not None:raise ValueError('BOX_REGION_WITHOUT_BOX')
    if not isinstance(r['reason'],str) or not r['reason'].strip() or not isinstance(r['angle'],str):raise ValueError('V2_REASON')
    if r['background_complexity'] not in {'SMOOTH','COMPLEX','UNKNOWN'}:raise ValueError('V2_BACKGROUND')
    identity=r['product_identity'];fields={'same_product_as_context','model_visible','structure_match','color_match'}
    if not isinstance(identity,dict) or set(identity)!=fields or any(v not in {'YES','NO','UNKNOWN'} for v in identity.values()):raise ValueError('V2_IDENTITY')
    suitability=r['sku_suitability']
    if not isinstance(suitability,dict) or set(suitability)!={'is_toy_photo','is_retail_box_photo','recommended_group'} or any(type(suitability[k]) is not bool for k in ('is_toy_photo','is_retail_box_photo')) or suitability['recommended_group'] not in {'WITH_RETAIL_BOX','WITHOUT_RETAIL_BOX','UNKNOWN'}:raise ValueError('V2_SUITABILITY')
    if not isinstance(r['watermarks'],list) or not isinstance(r['preserve_regions'],list):raise ValueError('V2_REGIONS')
    for mark in r['watermarks']:
        if (not isinstance(mark,dict) or mark.get('kind') not in MARKS or not number(mark.get('confidence')) or mark.get('preserve_overlap_risk') not in {'LOW','MEDIUM','HIGH'}):raise ValueError('V2_MARK')
        region(mark)
    for protected in r['preserve_regions']:
        if not isinstance(protected,dict) or not isinstance(protected.get('kind'),str):raise ValueError('V2_PROTECTED')
        region(protected)
    if r['decision']=='REMOVE_TEXT':
        removable=[m for m in r['watermarks'] if m['kind'] in {'STORE_WATERMARK','PROMOTIONAL_TEXT'}]
        if not removable or any(m['preserve_overlap_risk']!='LOW' for m in removable):raise ValueError('V2_NOT_REMOVABLE')
    return r

def decisive(row):
    return bool(row) and not row['abstain'] and row['confidence']>=THRESHOLD

def decide(client,item,context):
    """Each selected model sees only original pixels and sanitized context once."""
    from .client import safe_payload
    context=safe_payload({},context)['context']
    if len(client.models)!=2 or len(set(client.models))!=2:raise ValueError('TWO_DISTINCT_MODELS_REQUIRED')
    if {m.removeprefix('workbuddy/') for m in client.models}!={'deepseek-v4.1-flash','mimo-v2.6-pro'}:raise ValueError('V2_MODEL_PAIR_REQUIRED')
    primary=client.classify('image_action_decision',item,context,models=(client.models[0],),attempts=1)
    rows=primary.get('results',[]);a=rows[0] if rows and rows[0] else None
    uncertain=(not a or not decisive(a) or a['retail_box_status']=='UNCERTAIN' or
        a['retail_box_confidence']<THRESHOLD or a['box_relation']=='POSSIBLY_SAME_PRODUCT' or
        any(m['kind']=='UNKNOWN_TEXT' or m['confidence']<THRESHOLD for m in a['watermarks']) or
        any(a['product_identity'][k]!='YES' for k in ('same_product_as_context','structure_match','color_match')))
    second=uncertain or a['decision'] in {'DELETE','AI_REGENERATE'}
    models=[client.models[0]]
    if second:
        response=client.classify('image_action_decision',item,context,models=(client.models[1],),attempts=1)
        b=response.get('results',[]);b=b[0] if b and b[0] else None
        rows=[a,b];models.append(client.models[1])
    def semantic(r):
        return (r['decision'],r['visual_class'],r['retail_box_status'],r['box_relation'],r['product_identity'],
                [(m['kind'],m.get('bbox'),m.get('polygon')) for m in r['watermarks']],r['preserve_regions'])
    ok=all(decisive(r) for r in rows) and (len(rows)==1 or semantic(rows[0])==semantic(rows[1]))
    chosen=next((r for r in rows if r),None)
    action=chosen['decision'] if ok else 'REVIEW'
    if chosen and (chosen['visual_class']=='UNKNOWN' or chosen['retail_box_status']=='UNCERTAIN' or chosen['box_relation']=='POSSIBLY_SAME_PRODUCT' or chosen['retail_box_confidence']<THRESHOLD or
        any(chosen['product_identity'][k]!='YES' for k in ('same_product_as_context','structure_match','color_match')) or
        any(m['kind']=='UNKNOWN_TEXT' for m in chosen['watermarks'])):action='REVIEW'
    return dict(decision=action,observation=chosen,results=rows,models=models,
                reason_codes=[] if action!='REVIEW' else ['VISION_UNRESOLVED'],second_model_called=second)
