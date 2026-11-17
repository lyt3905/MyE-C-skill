"""V2 unified DeepSeek visual contract (no I/O writer)."""
from copy import deepcopy
import math
import json
from pathlib import Path

CONFIDENCE_POLICY='RECORD_ONLY'

SCHEMA_VERSION='image-action-decision.v2'
PROMPT=(Path(__file__).resolve().parents[1]/'prompts/image_action_decision.v2.md').read_text(encoding='utf-8')
PROMPT+='\nOUTPUT_JSON_SCHEMA:\n'+json.dumps(json.loads((Path(__file__).resolve().parents[1]/'config/schemas/image-action-decision.v2.schema.json').read_text(encoding='utf-8')),ensure_ascii=False,separators=(',',':'))
ACTIONS={'KEEP','DELETE','REMOVE_TEXT','AI_REGENERATE','REVIEW'}
CLASSES={'TOY_PRODUCT','TOY_WITH_RETAIL_BOX','RETAIL_BOX_ONLY','ACCESSORY','PART_OR_COMPONENT','LIFESTYLE_OR_SCENE','INFO_GRAPHIC','OTHER','UNKNOWN'}
MARKS={'STORE_WATERMARK','PROMOTIONAL_TEXT','MANUFACTURER_LOGO','PRODUCT_PRINT','PACKAGING_PRINT','CREATOR_CREDIT','UNKNOWN_TEXT'}
CLASSES.update({'PRODUCT_MAIN','PRODUCT_DETAIL','PRODUCT_SCENE','STORE_WATERMARK','TEXT_WATERMARK','DECORATED_COMPOSITE','SIZE_CHART','INFORMATION_IMAGE'})
MARKS.update({'MODEL_TEXT','NORMAL_PHOTO_TEXT','TEXT_WATERMARK'})
OWNERS={'OWN_STORE','THIRD_PARTY_STORE','MANUFACTURER','PRODUCT','PACKAGING','CREATOR','UNKNOWN'}

def mark_owner(mark):
    return mark.get('owner',{'STORE_WATERMARK':'THIRD_PARTY_STORE','MANUFACTURER_LOGO':'MANUFACTURER',
        'PRODUCT_PRINT':'PRODUCT','PACKAGING_PRINT':'PACKAGING','CREATOR_CREDIT':'CREATOR',
        'MODEL_TEXT':'PRODUCT','NORMAL_PHOTO_TEXT':'PRODUCT'}.get(mark['kind'],'UNKNOWN'))

def mark_disposition(mark):
    # New observations give an executable instruction per region. The model's
    # content labels remain observations, never a second program content vote.
    if mark.get('action')=='REMOVE_TEXT':return 'REMOVABLE'
    if mark.get('action')=='KEEP':return 'PROTECTED'
    # Compatibility for sealed V2 observations that predate region instructions.
    owner=mark_owner(mark)
    if mark['kind'] in {'MANUFACTURER_LOGO','PRODUCT_PRINT','PACKAGING_PRINT','MODEL_TEXT','CREATOR_CREDIT','NORMAL_PHOTO_TEXT'}:return 'PROTECTED'
    if owner in {'MANUFACTURER','PRODUCT','PACKAGING','CREATOR'}:return 'PROTECTED'
    if mark.get('overlay_role') in {'ADDED_WATERMARK','OTHER_STORE_FRAME'}:return 'REMOVABLE'
    if owner in {'OWN_STORE','THIRD_PARTY_STORE'} and mark['kind'] in {'STORE_WATERMARK','PROMOTIONAL_TEXT','TEXT_WATERMARK'}:return 'REMOVABLE'
    return 'UNKNOWN'

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
    if not isinstance(result,dict) or not required<=result.keys() or result.keys()-required-{'decision_confidence','field_confidences','retail_box_bbox_note'}:raise ValueError('V2_FIELDS')
    r=deepcopy(result)
    if r.get('retail_box_bbox_note') is not None and (not isinstance(r['retail_box_bbox_note'],str) or len(r['retail_box_bbox_note'])>2000):raise ValueError('V2_BOX_NOTE')
    if (r['schema_version']!=SCHEMA_VERSION or r['task_type']!='image_action_decision' or
        r['image_sha256']!=item.get('sha256') or r['item_id']!=item['id'] or r['image_id']!=item['id'] or r['image_type']!=item.get('image_type')):raise ValueError('V2_BINDING')
    if r['decision'] not in ACTIONS or r['visual_class'] not in CLASSES:raise ValueError('V2_ENUM')
    if any(not number(r[k]) for k in ('confidence','retail_box_confidence','toy_confidence')):raise ValueError('V2_CONFIDENCE')
    if 'decision_confidence' in r and r['decision_confidence']!=r['confidence']:raise ValueError('AMBIGUOUS_CONFIDENCE')
    if 'field_confidences' in r:
        fields={'visual_class','product_identity','box_relation','watermark_ownership','sku_suitability'}
        if not isinstance(r['field_confidences'],dict) or set(r['field_confidences'])!=fields or not all(number(v) for v in r['field_confidences'].values()):raise ValueError('V2_FIELD_CONFIDENCE')
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
    validate_watermarks(r['watermarks'])
    for protected in r['preserve_regions']:
        if not isinstance(protected,dict) or not isinstance(protected.get('kind'),str):raise ValueError('V2_PROTECTED')
        if protected.get('scope') not in {None,'EXACT_REGION','PRODUCT_FOREGROUND','BRIGHT_PRINT_GLYPHS','PRINT_RESTORE'}:raise ValueError('V2_PROTECTED_SCOPE')
        region(protected)
    if r['decision']=='REMOVE_TEXT':
        removable=[m for m in r['watermarks'] if mark_disposition(m)=='REMOVABLE']
        # Overlap is recorded, not a prediction-based veto. Fixed protection
        # geometry and actual candidate quality are checked by the executor.
        if not removable:raise ValueError('V2_NOT_REMOVABLE')
    return r


def validate_watermarks(marks):
    if not isinstance(marks,list):raise ValueError('V2_REGIONS')
    for mark in marks:
        if (not isinstance(mark,dict) or mark.get('kind') not in MARKS or not number(mark.get('confidence')) or mark.get('preserve_overlap_risk') not in {'LOW','MEDIUM','HIGH'}):raise ValueError('V2_MARK')
        if 'owner' in mark and mark['owner'] not in OWNERS:raise ValueError('V2_MARK_OWNER')
        if 'action' in mark and mark['action'] not in {'KEEP','REMOVE_TEXT'}:raise ValueError('V2_MARK_ACTION')
        for key in ('watermark_id','group_id'):
            if key in mark and (not isinstance(mark[key],str) or not 1<=len(mark[key])<=128):raise ValueError('V2_INSTANCE_METADATA')
        for key,allowed in [('region_type',{'BBOX','POLYGON'}),('arrangement',{'SINGLE','REPEATED','DIAGONAL','HORIZONTAL','VERTICAL','GRID','SCATTERED','MIXED'}),('content_type',{'TEXT','GRAPHIC','LOGO','TEXT_AND_GRAPHIC'})]:
            if key in mark and mark[key] not in allowed:raise ValueError('V2_INSTANCE_METADATA')
        if 'opacity' in mark and not number(mark['opacity']):raise ValueError('V2_INSTANCE_METADATA')
        if 'subject_overlap' in mark and type(mark['subject_overlap']) is not bool:raise ValueError('V2_INSTANCE_METADATA')
        if mark.get('overlay_role') not in {None,'OTHER_STORE_FRAME','SELLER_NOTICE','ADDED_WATERMARK','UNRESOLVED_TEXT'}:raise ValueError('V2_OVERLAY_ROLE')
        if mark.get('repair_mode') not in {None,'BACKGROUND_GLYPHS','REGION','TEMPLATE_GLYPHS'}:raise ValueError('V2_REPAIR_MODE')
        if mark.get('repair_mode')=='TEMPLATE_GLYPHS':region({'bbox':mark.get('glyph_template_bbox')})
        elif 'glyph_template_bbox' in mark:raise ValueError('V2_TEMPLATE_WITHOUT_MODE')
        if mark.get('glyph_search_scope') not in {None,'REGION','IMAGE'}:raise ValueError('V2_GLYPH_SCOPE')
        if mark.get('glyph_template_source') not in {None,'CANDIDATE','ORIGINAL'} or 'glyph_template_source' in mark and mark.get('repair_mode')!='TEMPLATE_GLYPHS':raise ValueError('V2_GLYPH_TEMPLATE_SOURCE')
        if mark.get('glyph_search_scope')=='IMAGE' and (mark.get('repair_mode')!='TEMPLATE_GLYPHS' or mark.get('action')!='REMOVE_TEXT'):raise ValueError('V2_GLOBAL_TEMPLATE_REQUIRED')
        if 'glyph_template_candidates' in mark:
            alternatives=mark['glyph_template_candidates']
            if mark.get('repair_mode')!='TEMPLATE_GLYPHS' or mark.get('glyph_search_scope')!='IMAGE' or not isinstance(alternatives,list) or len(alternatives)>3:raise ValueError('V2_TEMPLATE_ALTERNATIVES')
            for box in alternatives:region({'bbox':box})
        if 'preserve_mode' in mark and (mark['preserve_mode'] not in {'EXACT_REGION','BRIGHT_PRINT_GLYPHS','PRINT_RESTORE'} or mark.get('action')!='KEEP'):raise ValueError('V2_PRINT_PRESERVE_MODE')
        region(mark)

def retains_text(row):
    """KEEP does not need an owner for text that will remain untouched."""
    return row['decision']=='KEEP' and not any(mark_disposition(m)=='REMOVABLE' for m in row['watermarks'])

def deletes_text_only_notice(row):
    """Deleting a text-only notice is distinct from editing an unknown mark."""
    return (row['decision']=='DELETE' and (row['visual_class'] in {'TEXT_WATERMARK','STORE_WATERMARK','INFO_GRAPHIC','INFORMATION_IMAGE'} or any(m.get('overlay_role')=='SELLER_NOTICE' for m in row['watermarks']))
            and row['toy_present'] is False and row['retail_box_status']=='ABSENT')

def decisive(row):
    return bool(row) and not row['abstain']


def is_large_promotional_frame(row):
    """Combine AI-identified edge overlays; do not classify pixels as shop text."""
    # Older observations sometimes outline text glyphs instead of the banner.
    # Preserve explicitly identified framed promotional composites in that case.
    edge=[m for m in row.get('watermarks',[]) if mark_disposition(m)!='PROTECTED' and
          m['kind'] in {'STORE_WATERMARK','PROMOTIONAL_TEXT','TEXT_WATERMARK'} and _bounds(m)[1]>=.80]
    if (row.get('visual_class')=='DECORATED_COMPOSITE' and
        any(m.get('overlay_role')=='OTHER_STORE_FRAME' for m in edge) and
        any(m['kind']=='STORE_WATERMARK' for m in edge) and any(m['kind']=='PROMOTIONAL_TEXT' for m in edge)):
        bounds=[_bounds(m) for m in edge]
        if max(b[2] for b in bounds)-min(b[0] for b in bounds)>=.80 and max(b[3] for b in bounds)-min(b[1] for b in bounds)+1e-9>=.10:return True
    marks=[m for m in row.get('watermarks',[]) if mark_disposition(m)=='REMOVABLE' and
           m['kind'] in {'STORE_WATERMARK','PROMOTIONAL_TEXT','TEXT_WATERMARK'}]
    boxes=[_bounds(m) for m in marks]
    if not boxes:return False
    # Union area avoids counting overlapping labels twice.
    xs=sorted({x for b in boxes for x in (b[0],b[2])});ys=sorted({y for b in boxes for y in (b[1],b[3])})
    area=sum((b-a)*(d-c) for a,b in zip(xs,xs[1:]) for c,d in zip(ys,ys[1:]) if any(x0<=(a+b)/2<=x1 and y0<=(c+d)/2<=y1 for x0,y0,x1,y1 in boxes))
    if area<.15:return False
    if any(m.get('overlay_role')=='OTHER_STORE_FRAME' for m in marks):return True
    top=any(y0<=.05 and y1<=.30 for x0,y0,x1,y1 in boxes)
    bottom=any(y1>=.95 and y0>=.70 for x0,y0,x1,y1 in boxes)
    horizontal_band=any(x1-x0>=.45 and (y0<=.05 or y1>=.95) for x0,y0,x1,y1 in boxes)
    return top and bottom and horizontal_band and any(m['kind']=='STORE_WATERMARK' for m in marks)


def is_seller_promotional_composite(row):
    """Explicit seller poster roles, distinct from a useful photo's small badge."""
    if row.get('visual_class')!='DECORATED_COMPOSITE':return False
    marks=[m for m in row.get('watermarks',[]) if mark_disposition(m)!='PROTECTED']
    # A thin surrounding frame is not a small badge: its extent can span an
    # image edge while its pixel area is tiny. Retain the model's explicit
    # whole-poster DELETE without requiring ownership of each interior caption.
    frames=[_bounds(m) for m in marks if m['kind'] in {'STORE_WATERMARK','PROMOTIONAL_TEXT','TEXT_WATERMARK'} and
            m.get('overlay_role')=='OTHER_STORE_FRAME']
    surrounding=any((x1-x0>=.80 and (y0<=.05 or y1>=.95)) or
                    (y1-y0>=.80 and (x0<=.05 or x1>=.95)) for x0,y0,x1,y1 in frames)
    if row.get('decision')=='DELETE' and decisive(row) and surrounding:
        return True
    # The AI can outline only the glyphs of an otherwise explicit seller frame.
    # Keep its whole-poster DELETE when store header and stock footer agree;
    # this branch does not promote a raw REVIEW or an ordinary small badge.
    header=[m for m in marks if m['kind']=='STORE_WATERMARK' and m.get('overlay_role')=='OTHER_STORE_FRAME' and
            _bounds(m)[1]<=.05 and _bounds(m)[3]<=.15 and _bounds(m)[2]-_bounds(m)[0]>=.30]
    stock=[m for m in marks if m['kind']=='PROMOTIONAL_TEXT' and m.get('overlay_role')=='SELLER_NOTICE' and
           _bounds(m)[1]>=.80 and _bounds(m)[2]-_bounds(m)[0]>=.15]
    if row.get('decision')=='DELETE' and header and stock:return True
    footer=[m for m in marks if _bounds(m)[1]>=.80]
    stores=[m for m in footer if m['kind']=='STORE_WATERMARK' and m.get('overlay_role') in {'ADDED_WATERMARK','OTHER_STORE_FRAME'}]
    promos=[m for m in footer if m['kind']=='PROMOTIONAL_TEXT' and m.get('overlay_role') in {'SELLER_NOTICE','OTHER_STORE_FRAME'}]
    repeated=[m for m in marks if m['kind']=='STORE_WATERMARK' and m.get('overlay_role')=='ADDED_WATERMARK' and _bounds(m)[1]<.80]
    if not stores or not promos or len(repeated)<2:return False
    boxes=[_bounds(m) for m in stores+promos]
    return max(b[2] for b in boxes)-min(b[0] for b in boxes)>=.60


def apply_visual_rules(row):
    """Business rules follow explicit visual roles; preserve the raw observation."""
    value=deepcopy(row);changes=[]
    if not decisive(value):return value,changes
    seller_poster=is_seller_promotional_composite(value)
    if value['decision']=='REVIEW' and not seller_poster:return value,changes
    editable=[m for m in value['watermarks'] if mark_disposition(m)!='PROTECTED']
    action=value['decision']
    if seller_poster:action='DELETE'
    elif is_large_promotional_frame(value):action='DELETE'
    elif value['toy_present'] is False and value['retail_box_status']=='ABSENT' and any(m.get('overlay_role')=='SELLER_NOTICE' for m in editable):action='DELETE'
    elif action=='DELETE' and value['toy_present'] and value['clear'] and any(m.get('overlay_role')=='OTHER_STORE_FRAME' and mark_disposition(m)=='REMOVABLE' for m in editable):
        # A small shop badge is not a large surrounding promotional frame.
        action='REMOVE_TEXT'
    elif action=='KEEP' and any(mark_disposition(m)=='REMOVABLE' for m in editable):
        action='REMOVE_TEXT'
    if action!=value['decision']:
        changes.append(dict(rule='SELLER_PROMOTIONAL_COMPOSITE' if seller_poster else 'EXPLICIT_VISUAL_ROLE',raw_decision=value['decision'],decision=action))
        value['decision']=action
    return value,changes

def _bounds(mark):
    points=region(mark)
    return [min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]


def reassess_seller_poster(result):
    """Offline correction of this narrow old program blocker; raw results stay intact."""
    unchanged=deepcopy(result);rows=result.get('results') or []
    from mye_c_automation.model_config import review_models
    if (result.get('decision')!='REVIEW' or len(rows)!=1 or not rows[0] or
        not result.get('reason_codes') or set(result['reason_codes'])-{'TEXT_OWNERSHIP_UNRESOLVED','VISION_UNRESOLVED'}):return unchanged
    try:
        if tuple(result.get('models',[]))!=review_models(result.get('models',[])):return unchanged
    except ValueError:return unchanged
    raw=rows[0]
    poster=is_seller_promotional_composite(raw) or (raw.get('visual_class')=='DECORATED_COMPOSITE' and is_large_promotional_frame(raw))
    if raw.get('decision')!='DELETE' or raw.get('abstain') is not False or raw.get('retail_box_status')=='UNCERTAIN' or not poster:return unchanged
    observed,_=apply_visual_rules(raw)
    if observed['decision']!='DELETE':return unchanged
    unchanged.update(decision='DELETE',observation=observed,reason_codes=[])
    unchanged.setdefault('policy_adjustments',[]).append(dict(rule='SELLER_POSTER_REASSESSMENT',raw_decision='DELETE',previous_program_decision='REVIEW',decision='DELETE'))
    return unchanged

def _iou(a,b):
    intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    union=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection
    return intersection/union if union else 0

def _business(row):
    aliases={'PRODUCT_MAIN':'TOY_PRODUCT','PRODUCT_DETAIL':'TOY_PRODUCT','PRODUCT_SCENE':'LIFESTYLE_OR_SCENE','INFORMATION_IMAGE':'INFO_GRAPHIC'}
    return dict(decision=row['decision'],visual_class=aliases.get(row['visual_class'],row['visual_class']),
        retail_box_status=row['retail_box_status'],box_relation=row['box_relation'],
        product_identity={k:row['product_identity'][k] for k in ('same_product_as_context','structure_match')},
        sku_suitability=row['sku_suitability'],subject_complete=row['subject_complete'],clear=row['clear'],toy_present=row['toy_present'])

def decide(client,item,context):
    """One DeepSeek observation; listing identity fields are recorded only."""
    from .client import safe_payload
    from mye_c_automation.model_config import review_models
    context=safe_payload({},context)['context']
    models=review_models(client.models)
    rows=[];reasons=[];differences={};geometry=[]
    for model in models:
        response=client.classify('image_action_decision',item,context,models=(model,),attempts=1+getattr(client,'vision_retry_limit',0))
        values=response.get('results',[]);rows.append(values[0] if values and values[0] else None)
    chosen=deepcopy(next((r for r in rows if r),None))
    adjustments=[]
    if not all(rows):reasons.append('MODEL_OUTPUT_INCOMPLETE')
    for row in ([chosen] if chosen else []):
        if not decisive(row):reasons.append('MODEL_NOT_DECISIVE')
    action=chosen['decision'] if chosen and not reasons else 'REVIEW'
    return dict(decision=action,observation=chosen,results=rows,policy_adjustments=adjustments,decision_authority='MODEL',models=list(models),confidence_policy=CONFIDENCE_POLICY,normalized_results=[_business(r) if r else None for r in rows],
                field_differences=differences,geometry_differences=geometry,reason_codes=sorted(set(reasons)) or (['VISION_UNRESOLVED'] if action=='REVIEW' else []),second_model_called=False)
