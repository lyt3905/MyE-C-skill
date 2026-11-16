"""Exhaustive mark observations, conservative region agreement and legacy evidence."""
from mye_c_automation.policy_engine import MODEL_CONFIDENCE_MIN
from copy import deepcopy
import json
import math
from pathlib import Path

from mye_c_automation.policy_engine import KEEP, REMOVE

VERSION='watermark/v3'
CLASSES=KEEP|REMOVE|{'unknown','marketing_text','chinese_promotion_poster'}
THRESHOLD=MODEL_CONFIDENCE_MIN
MATCHING=json.loads((Path(__file__).parents[1]/'config'/'watermark.matching.v3.json').read_text(encoding='utf-8'))
UNPROVEN={'','unknown','uncertain','none','n/a','unproven','未知','不确定'}


class ContractError(ValueError):
    def __init__(self,code,field):
        self.code,self.field=code,field
        super().__init__(code+':'+field)


def number(value):return type(value) in (int,float) and math.isfinite(value) and 0<=value<=1


def refs_valid(refs,allowed):
    return isinstance(refs,list) and bool(refs) and all(isinstance(x,str) and x for x in refs) and set(refs)<=set(allowed)


def validate_watermark(row,evidence=None):
    required={'schema_version','task_type','item_id','confidence','abstain','coverage_complete',
              'no_marks_detected','image_size','marks','unresolved_items','evidence_ids'}
    for field in sorted(required):
        if field not in row:raise ContractError('REQUIRED_FIELD_MISSING',field)
    if row['task_type']!='watermark' or not isinstance(row['item_id'],str) or not row['item_id']:
        raise ContractError('EVIDENCE_INSUFFICIENT','task_type/item_id')
    if evidence and evidence.get('id') is not None and row['item_id']!=evidence['id']:raise ContractError('EVIDENCE_INSUFFICIENT','item_id')
    if row['schema_version']!=VERSION:raise ContractError('LEGACY_RESULT_NOT_EXHAUSTIVE','schema_version')
    if not number(row['confidence']) or type(row['abstain']) is not bool:raise ContractError('REQUIRED_FIELD_MISSING','confidence/abstain')
    for field in ('coverage_complete','no_marks_detected'):
        if type(row[field]) is not bool:raise ContractError('REQUIRED_FIELD_MISSING',field)
    size=row['image_size']
    if not isinstance(size,list) or len(size)!=2 or any(type(v) is not int or v<=0 for v in size):raise ContractError('SOURCE_UNVERIFIED','image_size')
    if evidence and evidence.get('dimensions') is not None and size!=evidence['dimensions']:raise ContractError('SOURCE_UNVERIFIED','image_size')
    allowed=evidence.get('evidence_ids',[]) if evidence else row['evidence_ids']
    if not refs_valid(row['evidence_ids'],allowed):raise ContractError('EVIDENCE_INSUFFICIENT','evidence_ids')
    if not isinstance(row['marks'],list) or not isinstance(row['unresolved_items'],list):raise ContractError('MARKS_INCOMPLETE','marks/unresolved_items')
    if row['no_marks_detected'] and (row['marks'] or not row['coverage_complete']):raise ContractError('MARKS_INCOMPLETE','no_marks_detected')
    if not row['marks'] and not row['no_marks_detected'] and row['coverage_complete']:raise ContractError('MARKS_INCOMPLETE','marks')
    ids=set()
    for index,mark in enumerate(row['marks']):
        path='marks['+str(index)+']'
        if not isinstance(mark,dict):raise ContractError('REQUIRED_FIELD_MISSING',path)
        for field in ('mark_id','classification','owner','location','bbox_xyxy','confidence','abstain','evidence_ids'):
            if field not in mark:raise ContractError('REQUIRED_FIELD_MISSING',path+'.'+field)
        if not isinstance(mark['mark_id'],str) or not mark['mark_id'] or mark['mark_id'] in ids:raise ContractError('MARKS_INCOMPLETE',path+'.mark_id')
        ids.add(mark['mark_id'])
        if not isinstance(mark['classification'],str) or mark['classification'] not in CLASSES:raise ContractError('REQUIRED_FIELD_MISSING',path+'.classification')
        if any(not isinstance(mark[f],str) or not mark[f].strip() for f in ('owner','location')):raise ContractError('OWNER_UNPROVEN',path+'.owner/location')
        if not number(mark['confidence']) or type(mark['abstain']) is not bool:raise ContractError('REQUIRED_FIELD_MISSING',path+'.confidence/abstain')
        box=mark['bbox_xyxy']
        if (not isinstance(box,list) or len(box)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in box)
            or not (0<=box[0]<box[2]<=size[0] and 0<=box[1]<box[3]<=size[1])):
            raise ContractError('EVIDENCE_INSUFFICIENT',path+'.bbox_xyxy')
        if not refs_valid(mark['evidence_ids'],allowed):raise ContractError('EVIDENCE_INSUFFICIENT',path+'.evidence_ids')
    for index,item in enumerate(row['unresolved_items']):
        if (not isinstance(item,dict) or not isinstance(item.get('reason_code'),str) or
            not isinstance(item.get('location'),str) or not refs_valid(item.get('evidence_ids'),allowed)):
            raise ContractError('EVIDENCE_INSUFFICIENT','unresolved_items['+str(index)+']')
    return deepcopy(row)


def reason(code,index=None,field=None,observation=None,detail=None):
    row={'reason_code':code,'model_index':index,'field':field,'evidence_ids':deepcopy((observation or {}).get('evidence_ids',[]))}
    if observation and 'bbox_xyxy' in observation:row['bbox_xyxy']=deepcopy(observation['bbox_xyxy'])
    if detail is not None:row['detail']=detail
    return row


def _mark_reasons(mark,index):
    reasons=[]
    if mark['abstain']:reasons.append(reason('MODEL_ABSTAIN',index,'marks.abstain',mark))
    if mark['confidence']<THRESHOLD:reasons.append(reason('LOW_CONFIDENCE',index,'marks.confidence',mark,mark['confidence']))
    if mark['classification'] not in KEEP|REMOVE:reasons.append(reason('OWNER_UNPROVEN',index,'marks.classification',mark,mark['classification']))
    if mark['owner'].strip().casefold() in UNPROVEN:reasons.append(reason('OWNER_UNPROVEN',index,'marks.owner',mark))
    if mark['location'].strip().casefold() in UNPROVEN:reasons.append(reason('EVIDENCE_INSUFFICIENT',index,'marks.location',mark))
    return reasons


def _iou(a,b):
    area=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    return area/((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-area)


def aggregate_watermarks(result,evidence=None,matching=None):
    matching=MATCHING if matching is None else matching
    threshold=matching.get('min_iou')
    if type(threshold) not in (int,float) or not math.isfinite(threshold) or not 0<threshold<=1:raise ValueError('INVALID_REGION_MATCHING_CONFIG')
    rows=result.get('results',[]);unresolved=[];valid={};legacy=[];findings=[];regions=[]
    if len(rows)!=2:unresolved.append(reason('REQUIRED_FIELD_MISSING',field='results',detail='two distinct model results required'))
    model_names=result.get('models')
    if model_names is not None and (len(model_names)!=2 or len(set(model_names))!=2):unresolved.append(reason('MODEL_DISAGREEMENT',field='models'))
    for index,row in enumerate(rows):
        if not isinstance(row,dict):unresolved.append(reason('REQUIRED_FIELD_MISSING',index,'result'));continue
        if row.get('schema_version')!=VERSION:
            legacy.append({'model_index':index,'legacy_single_mark':deepcopy({k:row.get(k) for k in
                ('classification','owner','location','confidence','abstain','evidence_ids')}),'legacy_marks':deepcopy(row.get('marks',[])),
                'coverage_complete':False})
            unresolved.append(reason('LEGACY_RESULT_NOT_EXHAUSTIVE',index,'schema_version',row))
            if row.get('classification') not in KEEP|REMOVE:unresolved.append(reason('OWNER_UNPROVEN',index,'classification',row,row.get('classification')))
            if isinstance(row.get('owner'),str) and row['owner'].strip().casefold() in UNPROVEN:unresolved.append(reason('OWNER_UNPROVEN',index,'owner',row))
            for j,mark in enumerate(row.get('marks',[]) if isinstance(row.get('marks'),list) else []):
                if not isinstance(mark,dict):continue
                observed=[]
                if mark.get('abstain') is True:observed.append(('MODEL_ABSTAIN','abstain',True))
                if 'confidence' in mark and (not number(mark['confidence']) or mark['confidence']<THRESHOLD):observed.append(('LOW_CONFIDENCE','confidence',mark['confidence']))
                if isinstance(mark.get('classification'),str) and mark['classification'] not in KEEP|REMOVE:observed.append(('OWNER_UNPROVEN','classification',mark['classification']))
                if isinstance(mark.get('owner'),str) and mark['owner'].strip().casefold() in UNPROVEN:observed.append(('OWNER_UNPROVEN','owner',mark['owner']))
                for code,field,value in observed:
                    item=reason(code,index,f'marks[{j}].{field}',mark,value)
                    item.update(mark_index=j,location=mark.get('location'),legacy_observation=True)
                    unresolved.append(item)
        else:
            try:valid[index]=validate_watermark(row,evidence)
            except ContractError as exc:unresolved.append(reason(exc.code,index,exc.field,row));continue
            if evidence is None or evidence.get('dimensions') is None:unresolved.append(reason('SOURCE_UNVERIFIED',index,'dimensions',row))
            if not row['coverage_complete']:unresolved.append(reason('MARKS_INCOMPLETE',index,'coverage_complete',row))
            unresolved.extend(dict(reason(v['reason_code'],index,'unresolved_items',v),location=v['location']) for v in row['unresolved_items'])
        if row.get('abstain') is not False:unresolved.append(reason('MODEL_ABSTAIN',index,'abstain',row))
        if not number(row.get('confidence')) or row['confidence']<THRESHOLD:unresolved.append(reason('LOW_CONFIDENCE',index,'confidence',row,row.get('confidence')))
    if legacy and len(rows)==2 and all(isinstance(r,dict) for r in rows) and rows[0].get('classification')!=rows[1].get('classification'):
        unresolved.append(reason('MODEL_DISAGREEMENT',field='classification',detail='legacy root categories differ; no common region inferred'))
    # Historical root findings are retained as findings, never as exhaustive
    # observations or actionable authorization. No bbox is invented for them.
    if len(rows)==2 and all(isinstance(r,dict) and r.get('classification') in REMOVE and r.get('abstain') is False and
        number(r.get('confidence')) and r['confidence']>=THRESHOLD and r.get('owner') and r.get('location') for r in rows):
        if any(r.get('schema_version')!=VERSION for r in rows):
            findings.append({'rule':'store_watermark','verdict':'FAIL','confirmation_basis':'legacy_root_dual',
                'observations':deepcopy(rows),'remediation_authorized':False})
    a=valid.get(0,{}).get('marks',[]);b=valid.get(1,{}).get('marks',[])
    edges={(i,j) for i,x in enumerate(a) for j,y in enumerate(b) if _iou(x['bbox_xyxy'],y['bbox_xyxy'])>=threshold}
    matched={(i,j) for i,j in edges if sum(x==i for x,y in edges)==1 and sum(y==j for x,y in edges)==1}
    pairs=[(i,j) for i,j in sorted(matched)]+[(i,None) for i in range(len(a)) if not any(x==i for x,y in matched)]+[(None,j) for j in range(len(b)) if not any(y==j for x,y in matched)]
    for i,j in pairs:
        left=a[i] if i is not None else None;right=b[j] if j is not None else None;issues=[]
        if left:issues+=_mark_reasons(left,0)
        if right:issues+=_mark_reasons(right,1)
        if left is None or right is None:issues.append(reason('EVIDENCE_INSUFFICIENT',field='region_pair',observation=left or right,detail='unmatched or ambiguous region'))
        elif left['classification']!=right['classification']:issues.append(reason('MODEL_DISAGREEMENT',field='region.classification',observation=left))
        elif left['owner'].strip().casefold()!=right['owner'].strip().casefold():issues.append(reason('OWNER_UNPROVEN',field='region.owner',observation=left,detail='owner observations differ'))
        if left and right and left['classification'] in REMOVE and left['owner'].strip().casefold() in {'store','shop','seller','manufacturer','factory','third party','third-party','third_party_store','third_party'}:
            issues.append(reason('OWNER_UNPROVEN',field='region.owner',observation=left,detail='generic owner'))
        status='UNKNOWN' if issues else 'FAIL' if left['classification'] in REMOVE else 'PASS'
        region={'model_a_observation':deepcopy(left),'model_b_observation':deepcopy(right),'status':status,
                'reason_codes':sorted({v['reason_code'] for v in issues}),'unresolved_items':issues}
        regions.append(region);unresolved+=issues
        if status=='FAIL':findings.append({'rule':'store_watermark','verdict':'FAIL','confirmation_basis':'dual_model_region',
            'bbox_xyxy':deepcopy(left['bbox_xyxy']),'observations':[deepcopy(left),deepcopy(right)],'remediation_authorized':False})
    complete=(len(rows)==2 and len(valid)==2 and all(r['coverage_complete'] for r in valid.values()) and
              evidence is not None and evidence.get('dimensions') is not None)
    coverage='COMPLETE' if complete else 'PARTIAL' if regions or legacy else 'INCOMPLETE'
    review='PARTIAL' if findings and unresolved else 'FAIL' if findings else 'UNKNOWN' if unresolved or not complete else 'PASS'
    return {'schema_version':VERSION,'coverage_status':coverage,'review_status':review,'regions':regions,
            'confirmed_findings':findings,'unresolved_items':unresolved,'legacy_observations':legacy,
            'matching':{'min_iou':threshold,'automatic_action_release':False}}
