"""Independent identity observations; missing models remain unverifiable."""
from mye_c_automation.policy_engine import MODEL_CONFIDENCE_MIN
from copy import deepcopy
import re
from .watermark_contract import number,refs_valid,reason

VERSION='product-identity/v3'
DIMENSIONS=('product_subject','image_type','model_identity','color','packaging')


def color_terms(value):
    patterns={'red':r'\bred\b|红','green':r'\bgreen\b|\blime\b|绿','blue':r'\bblue\b|\bcyan\b|蓝|青',
        'purple':r'\bpurple\b|\bviolet\b|紫','yellow':r'\byellow\b|黄','orange':r'\borange\b|橙',
        'pink':r'\bpink\b|粉','brown':r'\bbrown\b|棕','gold':r'\bgold\b|金','black':r'\bblack\b|黑',
        'white':r'\bwhite\b|白','gray':r'\b(?:grey|gray|silver)\b|灰|银'}
    return {name for name,p in patterns.items() if isinstance(value,str) and re.search(p,value,re.I)}


def validate_identity(row,evidence=None):
    obs=row.get('observations')
    if not isinstance(obs,dict) or not set(DIMENSIONS)<=set(obs):raise ValueError('REQUIRED_FIELD_MISSING:observations')
    allowed=evidence.get('evidence_ids',[]) if evidence else row['evidence_ids']
    if row.get('task_type')!='product_identity' or (evidence and evidence.get('id') is not None and row.get('item_id')!=evidence['id']):raise ValueError('EVIDENCE_INSUFFICIENT:item_id')
    if not refs_valid(row.get('evidence_ids'),allowed):raise ValueError('EVIDENCE_INSUFFICIENT:evidence_ids')
    for field in DIMENSIONS:
        value=obs[field]
        if (not isinstance(value,dict) or not {'value','decision','confidence','abstain','evidence_ids'}<=set(value) or
            not number(value['confidence']) or type(value['abstain']) is not bool or value['decision'] not in {'MATCH','MISMATCH','UNCERTAIN'} or
            not refs_valid(value['evidence_ids'],allowed)):raise ValueError('EVIDENCE_INSUFFICIENT:observations.'+field)
        if value['value'] is not None and not isinstance(value['value'],str):raise ValueError('invalid identity observation')
        if field=='image_type' and value['value'] not in {'BOX','FIGURE','MIXED','UNCERTAIN'}:raise ValueError('invalid image type')
        if field=='packaging' and value['value'] not in {'BOXED','UNBOXED','MIXED','UNCERTAIN'}:raise ValueError('invalid packaging')
        if field=='model_identity' and value.get('visibility') not in {'VISIBLE','NOT_VISIBLE','NOT_VERIFIABLE'}:raise ValueError('model visibility required')
    result=deepcopy(row)
    for field,flat in (('model_identity','model'),('color','color'),('image_type','image_type')):
        observed=obs[field]['value']
        if flat in result and result[flat]!=observed:raise ValueError('contradictory identity observations:'+flat)
        result[flat]=observed
    result['model_evidence_ids']=deepcopy(obs['model_identity']['evidence_ids'])
    return result


def _observation(row,field):
    if isinstance(row.get('observations'),dict):
        value=row['observations'].get(field)
        return deepcopy(value) if isinstance(value,dict) else None
    # Legacy observations retain their actual fields/confidence. Missing
    # subject/packaging is never fabricated from a generic MATCH decision.
    key={'image_type':'image_type','model_identity':'model','color':'color'}.get(field)
    if not key or key not in row:return None
    return {'value':row[key],'decision':row.get('decision'),'confidence':None,'legacy_root_confidence':row.get('confidence'),
            'confidence_scope':'ROOT_ONLY','legacy_observation':True,'abstain':row.get('abstain'),
            'evidence_ids':deepcopy(row.get('model_evidence_ids',[]) if field=='model_identity' else row.get('evidence_ids',[])),
            **({'visibility':'NOT_VERIFIABLE'} if field=='model_identity' and not row[key] else {})}


def aggregate_identity(result,declared_model,evidence=None):
    rows=result.get('results',[]);output={};overall=[]
    if len(rows)!=2:overall.append(reason('REQUIRED_FIELD_MISSING',field='results'))
    for i,row in enumerate(rows):
        if row.get('schema_version')==VERSION:
            try:validate_identity(row,evidence)
            except (ValueError,KeyError,TypeError) as exc:overall.append(reason('EVIDENCE_INSUFFICIENT',i,'observations',row,str(exc)))
        if row.get('abstain') is not False:overall.append(reason('MODEL_ABSTAIN',i,'abstain',row))
        if not number(row.get('confidence')) or row['confidence']<MODEL_CONFIDENCE_MIN:overall.append(reason('LOW_CONFIDENCE',i,'confidence',row,row.get('confidence')))
        if row.get('decision') not in ('MATCH','MISMATCH'):overall.append(reason('EVIDENCE_INSUFFICIENT',i,'decision',row,row.get('decision')))
    if len(rows)==2 and rows[0].get('decision')!=rows[1].get('decision'):overall.append(reason('MODEL_DISAGREEMENT',field='decision'))
    if result.get('models') is not None and (len(result['models'])!=2 or len(set(result['models']))!=2):overall.append(reason('MODEL_DISAGREEMENT',field='models'))
    for field in DIMENSIONS:
        values=[_observation(r,field) for r in rows];issues=[]
        for i,ob in enumerate(values):
            if ob is None:issues.append(reason('REQUIRED_FIELD_MISSING',i,field));continue
            if ob.get('abstain') is not False:issues.append(reason('MODEL_ABSTAIN',i,field+'.abstain',ob))
            if ob.get('confidence') is None:issues.append(reason('REQUIRED_FIELD_MISSING',i,field+'.confidence',ob,'dimension confidence not recorded'))
            elif not number(ob['confidence']) or ob['confidence']<MODEL_CONFIDENCE_MIN:issues.append(reason('LOW_CONFIDENCE',i,field+'.confidence',ob,ob.get('confidence')))
            allowed=evidence.get('evidence_ids',[]) if evidence else rows[i].get('evidence_ids',[])
            if not refs_valid(ob.get('evidence_ids'),allowed):issues.append(reason('EVIDENCE_INSUFFICIENT',i,field+'.evidence_ids',ob))
            value=ob.get('value')
            unknown=value is None or not isinstance(value,str) or value.strip().casefold() in {'','unknown','uncertain','none','n/a','not visible'}
            if field=='model_identity' and (unknown or ob.get('visibility') in {'NOT_VISIBLE','NOT_VERIFIABLE'}):issues.append(reason('MODEL_NOT_VISIBLE',i,field+'.visibility',ob))
            elif field=='model_identity' and ob.get('visibility')!='VISIBLE':issues.append(reason('EVIDENCE_INSUFFICIENT',i,field+'.visibility',ob,'model visibility not recorded'))
            elif unknown:issues.append(reason('REQUIRED_FIELD_MISSING',i,field+'.value',ob))
            if ob.get('decision') not in ('MATCH','MISMATCH'):issues.append(reason('EVIDENCE_INSUFFICIENT',i,field+'.decision',ob))
            flat={'model_identity':'model','color':'color','image_type':'image_type'}.get(field)
            if flat and rows[i].get('observations') and flat in rows[i] and rows[i][flat]!=value:issues.append(reason('MODEL_DISAGREEMENT',i,field+'.flat_alias',ob))
        if len(values)!=2:issues.append(reason('REQUIRED_FIELD_MISSING',field=field+'.models'))
        if len(values)==2 and all(v is not None for v in values):
            a,b=values;av,bv=(v.get('value') if isinstance(v.get('value'),str) else None for v in values)
            if a.get('decision')!=b.get('decision'):issues.append(reason('MODEL_DISAGREEMENT',field=field+'.decision'))
            if field in {'image_type','packaging'} and av!=bv:issues.append(reason('IMAGE_TYPE_CONFLICT',field=field+'.value',detail=[av,bv]))
            if field=='image_type' and any(v not in {'BOX','FIGURE','MIXED'} for v in (av,bv)):issues.append(reason('IMAGE_TYPE_CONFLICT',field=field+'.value'))
            if field=='color':
                colors=[color_terms(v) for v in (av,bv)];chromatic=[v-{'black','white','gray'} for v in colors]
                palettes=chromatic if all(chromatic) else colors
                if not all(palettes) or not palettes[0]&palettes[1]:issues.append(reason('COLOR_CONFLICT',field=field+'.value',detail=[av,bv]))
            if field=='model_identity' and not any(v['reason_code']=='MODEL_NOT_VISIBLE' for v in issues):
                compact=lambda v:re.sub(r'[-\s]','',str(v)).upper()
                if not declared_model:issues.append(reason('EVIDENCE_INSUFFICIENT',field=field+'.declared_model'))
                elif any(v.get('decision')=='MATCH' and compact(v.get('value'))!=compact(declared_model) for v in values):issues.append(reason('MODEL_DISAGREEMENT',field=field+'.declared_model',detail=[av,bv]))
        status='UNKNOWN' if issues else 'FAIL' if all(v['decision']=='MISMATCH' for v in values) else 'PASS'
        output[field]={'model_a_observation':values[0] if values else None,'model_b_observation':values[1] if len(values)>1 else None,
            'confidence':[v.get('confidence') if v else None for v in values],'evidence_ids':sorted({x for v in values if v and isinstance(v.get('evidence_ids'),list) for x in v['evidence_ids'] if isinstance(x,str)}),
            'status':status,'reason_code':issues[0]['reason_code'] if issues else None,'reason_codes':sorted({v['reason_code'] for v in issues}),'unresolved_items':issues}
    if rows and all(r.get('decision')=='MISMATCH' for r in rows) and all(v['status']=='PASS' for v in output.values()):overall.append(reason('MODEL_DISAGREEMENT',field='decision/observations'))
    verdict='UNKNOWN' if overall or any(v['status']=='UNKNOWN' for v in output.values()) else 'FAIL' if any(v['status']=='FAIL' for v in output.values()) else 'PASS'
    return {'schema_version':VERSION,'verdict':verdict,'dimensions':output,'unresolved_items':overall+[r for v in output.values() for r in v['unresolved_items']]}
