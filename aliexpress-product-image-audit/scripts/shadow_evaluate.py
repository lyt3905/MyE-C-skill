"""Offline shadow comparison. Never invokes models or a site."""
import argparse
import json
from pathlib import Path


def quality_metrics(rows):
    """Score labelled observations only; abstention and unavailable usage stay explicit.

    Recall on decided samples is conditional. The lower bound also counts labelled
    positives deferred by the detector, so abstaining cannot inflate release evidence.
    This function never authorizes an automatic action.
    """
    if not rows:raise ValueError('empty sample set')
    groups={};seen=set()
    statuses={'ACTUAL_REPORTED','ACTUAL_ZERO','UNKNOWN','NOT_CALLED','BUDGET_BLOCKED'}
    for row in rows:
        if row.get('image_type') not in {'main','detail','sku'}:raise ValueError('invalid image type')
        for field in ('sample_id','category','detector'):
            if not isinstance(row.get(field),str) or not row[field]:raise ValueError('missing identity')
        truth=row.get('ground_truth');prediction=row.get('prediction')
        if truth is not None and type(truth) is not bool:raise ValueError('invalid ground truth')
        if prediction is not None and type(prediction) is not bool:raise ValueError('invalid prediction')
        if truth is not None and (not isinstance(row.get('label_source'),str) or not row['label_source']):
            raise ValueError('label provenance required')
        status=row.get('usage_status');tokens=row.get('tokens')
        if status not in statuses:raise ValueError('invalid usage status')
        if status=='ACTUAL_REPORTED' and (type(tokens) is not int or tokens<=0):raise ValueError('reported usage required')
        if status=='ACTUAL_ZERO' and (type(tokens) is not int or tokens!=0):raise ValueError('actual zero required')
        if status in {'UNKNOWN','NOT_CALLED','BUDGET_BLOCKED'} and tokens is not None:raise ValueError('unknown usage cannot be zero')
        key=(row['image_type'],row['category'],row['detector'])
        identity=(row['sample_id'],)+key
        if identity in seen:raise ValueError('duplicate observation')
        seen.add(identity)
        group=groups.setdefault(key,{'image_type':key[0],'category':key[1],'detector':key[2],
                   'samples':0,'labeled':0,'deferred':0,'usage_status_counts':{},'reported_token_subtotal':0,
                   'confusion':dict(tp=0,fp=0,fn=0,tn=0,undecided_positive=0,undecided_negative=0)})
        group['samples']+=1;group['deferred']+=prediction is None
        group['usage_status_counts'][status]=group['usage_status_counts'].get(status,0)+1
        if tokens is not None:group['reported_token_subtotal']+=tokens
        if truth is None:continue
        group['labeled']+=1
        cell=('undecided_positive' if truth else 'undecided_negative') if prediction is None else (
            'tp' if truth and prediction else 'fn' if truth else 'fp' if prediction else 'tn')
        group['confusion'][cell]+=1
    def ratio(numerator,denominator):return numerator/denominator if denominator else None
    for group in groups.values():
        c=group['confusion'];usage=group['usage_status_counts']
        group.update(precision=ratio(c['tp'],c['tp']+c['fp']),
                     recall_decided=ratio(c['tp'],c['tp']+c['fn']),
                     recall_lower_bound=ratio(c['tp'],c['tp']+c['fn']+c['undecided_positive']),
                     false_clean_rate=ratio(c['fn'],c['tn']+c['fn']),
                     deferred_rate=ratio(group['deferred'],group['samples']))
        group['actual_tokens']=(group['reported_token_subtotal'] if 'UNKNOWN' not in usage and
                 any(s in usage for s in ('ACTUAL_REPORTED','ACTUAL_ZERO')) else None)
    return {'schema':'shadow-quality/v1.3','groups':[groups[k] for k in sorted(groups)],
            'release_authorized':False,'release_gate':'30 confirmed samples/action, precision >=98%, no severe protected-content damage'}


def evaluate(rows):
    if not rows:
        raise ValueError('empty sample set')
    ids = set()
    totals = {name: dict(false_negative=0, false_positive=0, tokens=0, latency_ms=0) for name in ('baseline', 'candidate')}
    positives = 0
    for row in rows:
        if set(row) != {'sample_id', 'human_issue', 'baseline', 'candidate'} or not isinstance(row['sample_id'], str) or not row['sample_id'] or row['sample_id'] in ids or type(row['human_issue']) is not bool:
            raise ValueError('invalid or duplicate sample')
        ids.add(row['sample_id'])
        positives += row['human_issue']
        for name in totals:
            result = row[name]
            if not isinstance(result, dict) or set(result) != {'issue', 'tokens', 'latency_ms'} or type(result['issue']) is not bool:
                raise ValueError('invalid result')
            if any(type(result[k]) is not int or result[k] < 0 for k in ('tokens', 'latency_ms')):
                raise ValueError('invalid measurement')
            total = totals[name]
            total['false_negative'] += row['human_issue'] and not result['issue']
            total['false_positive'] += not row['human_issue'] and result['issue']
            total['tokens'] += result['tokens']
            total['latency_ms'] += result['latency_ms']
    return {'samples': len(rows), 'human_positives': positives, 'results': totals,
            'accepted': False, 'status': 'HUMAN_REVIEW_REQUIRED'}


def _registry_labelled_rows(rows,path):
    """Join existing user confirmations to observations; never create predictions."""
    import hashlib
    import re
    from PIL import Image
    path=Path(path).resolve();content=path.read_bytes();registry=json.loads(content.decode('utf-8-sig'))
    if (not isinstance(registry,dict) or registry.get('schema')!='deduplicated-confirmed-label-registry/v1.3'
            or registry.get('model_predictions_used_as_truth') is not False or not isinstance(registry.get('samples'),list)):
        raise ValueError('REGISTRY_SCHEMA')
    confirmed={'USER_CONFIRMED','USER_CONFIRMED_ACTION','USER_CONFIRMED_EXACT_SHA_REUSE','HISTORICALLY_CONFIRMED'}
    labels={}
    for sample in registry['samples']:
        digest=sample.get('source_sha256') if isinstance(sample,dict) else None
        if not isinstance(digest,str) or re.fullmatch('[a-f0-9]{64}',digest) is None:raise ValueError('REGISTRY_SHA')
        image_path=sample.get('source')
        if not isinstance(image_path,str):raise ValueError('REGISTRY_IMAGE_REQUIRED')
        image_path=Path(image_path)
        if not image_path.is_absolute():image_path=path.parent/image_path
        if not image_path.is_file():raise ValueError('REGISTRY_IMAGE_REQUIRED')
        if hashlib.sha256(image_path.read_bytes()).hexdigest()!=digest:raise ValueError('REGISTRY_IMAGE_SHA')
        try:
            with Image.open(image_path) as image:image.verify()
        except (OSError,ValueError) as exc:raise ValueError('REGISTRY_IMAGE_DECODE') from exc
        confirmations=sample.get('confirmations')
        if not isinstance(confirmations,list):raise ValueError('REGISTRY_CONFIRMATIONS')
        confirmations=[c for c in confirmations if isinstance(c,dict) and c.get('label_status') in confirmed
                       and isinstance(c.get('label_source'),str) and c['label_source'].strip()]
        if not confirmations:raise ValueError('REGISTRY_CONFIRMATION_REQUIRED')
        truth=(sample.get('ground_truth') or {}).get('third_party_watermark')
        if truth is not None and type(truth) is not bool:raise ValueError('REGISTRY_LABEL_TYPE')
        values={truth} if truth is not None else set()
        for confirmation in confirmations:
            value=(confirmation.get('ground_truth') or {}).get('third_party_watermark')
            if value is not None:
                if type(value) is not bool:raise ValueError('REGISTRY_LABEL_TYPE')
                values.add(value)
        if len(values)>1:raise ValueError('REGISTRY_LABEL_CONFLICT')
        delete=any(c.get('confirmed_remedy')=='DELETE_WHOLE_IMAGE' or
                   (c.get('ground_truth') or {}).get('whole_image_delete_requested') is True for c in confirmations)
        label=labels.setdefault(digest,{'binary':None,'delete':False,'confirmation_ids':set()})
        label['confirmation_ids'].update(c['confirmation_id'] for c in confirmations if isinstance(c.get('confirmation_id'),str))
        if values:
            value=next(iter(values))
            if label['binary'] is not None and label['binary']!=value:raise ValueError('REGISTRY_LABEL_CONFLICT')
            label['binary']=value
        label['delete']|=delete
    matched=set();real_matched=set();action_matched=set();joined=[]
    binding=str(path)+'#sha256='+hashlib.sha256(content).hexdigest()+'; explicit user DELETE confirmation only'
    for source in rows:
        if not isinstance(source,dict):raise ValueError('V2_SAMPLE_FIELDS')
        row=dict(source);digest=row.get('image_sha256')
        if not isinstance(digest,str):raise ValueError('V2_SAMPLE_IDENTITY')
        if type(row.get('human_confirmed')) is not bool:raise ValueError('V2_SAMPLE_BOOLEAN')
        label=labels.get(digest)
        if label:
            matched.add(digest)
            if row.get('evidence_kind')=='REAL_SHADOW':real_matched.add(digest)
            if label['delete']:
                if row.get('ground_truth_action') not in (None,'DELETE'):raise ValueError('REGISTRY_ACTION_CONFLICT')
                if not row['human_confirmed']:
                    if any(row.get(k) is not None for k in ('ground_truth_retail_box','severe_error','repair_pass','sku_selection_correct')):
                        raise ValueError('REGISTRY_UNCONFIRMED_OUTCOMES')
                    row.update(human_confirmed=True,label_source=binding)
                elif not row.get('label_source'):row['label_source']=binding
                row['ground_truth_action']='DELETE';action_matched.add(digest)
        joined.append(row)
    return joined,dict(path=str(path),sha256=hashlib.sha256(content).hexdigest(),unique_images=len(labels),
        binary_watermark_labels=sum(v['binary'] is not None for v in labels.values()),
        explicit_delete_labels=sum(v['delete'] for v in labels.values()),matched_prediction_images=len(matched),
        matched_real_prediction_images=len(real_matched),matched_explicit_action_images=len(action_matched),
        matched_real_binary_watermark_images=sum(labels[d]['binary'] is not None for d in real_matched),
        matched_labels=[dict(image_sha256=d,third_party_watermark=labels[d]['binary'],
                            explicit_action='DELETE' if labels[d]['delete'] else None,
                            confirmation_ids=sorted(labels[d]['confirmation_ids'])) for d in sorted(matched)],
        images_without_real_predictions=len(labels)-len(real_matched),binary_labels_projected_to_actions=False)


def v2_quality_metrics(rows,*,remove_text_min_pass_rate=None,label_registry=None):
    """Offline five-action scoring. Input provenance is declared, not certified.

    A SHA is one independent image across all business positions. Synthetic
    observations have their own statistics and can never satisfy real gates.
    Even passing statistical checks never authorizes a model or site operation.
    """
    import hashlib
    import math
    import re
    from PIL import Image
    actions=('KEEP','DELETE','REMOVE_TEXT','AI_REGENERATE','REVIEW')
    automatic=('DELETE','REMOVE_TEXT','AI_REGENERATE')
    box_values={'PRESENT','ABSENT','UNKNOWN'}
    required={'schema','image_sha256','image_type','evidence_kind','human_confirmed','prediction_action','confidence','abstain'}
    allowed=required|{'label_source','ground_truth_action','ground_truth_retail_box','prediction_retail_box','repair_pass','severe_error','sku_selection_correct','source_image'}
    inventory=None
    if label_registry is not None:rows,inventory=_registry_labelled_rows(rows,label_registry)
    if remove_text_min_pass_rate is not None and (type(remove_text_min_pass_rate) not in (int,float) or not math.isfinite(remove_text_min_pass_rate) or not 0<=remove_text_min_pass_rate<=1):
        raise ValueError('INVALID_REMOVE_TEXT_THRESHOLD')
    unique={};duplicates=0
    for source in rows:
        if not isinstance(source,dict) or not required<=source.keys() or source.keys()-allowed:raise ValueError('V2_SAMPLE_FIELDS')
        row=dict(source);digest=row['image_sha256']
        if row['schema']!='v2-accuracy-sample/v1' or not isinstance(digest,str) or re.fullmatch('[a-f0-9]{64}',digest) is None:raise ValueError('V2_SAMPLE_IDENTITY')
        if row['image_type'] not in {'MAIN','DETAIL','SKU'} or row['evidence_kind'] not in {'FAKE','REAL_SHADOW'}:raise ValueError('V2_SAMPLE_SCOPE')
        if any(type(row.get(key)) is not bool for key in ('human_confirmed','abstain')):raise ValueError('V2_SAMPLE_BOOLEAN')
        if row['prediction_action'] not in actions or row.get('ground_truth_action') not in (*actions,None):raise ValueError('V2_SAMPLE_ACTION')
        if type(row['confidence']) not in (int,float) or not math.isfinite(row['confidence']) or not 0<=row['confidence']<=1:raise ValueError('V2_SAMPLE_CONFIDENCE')
        if row.get('ground_truth_retail_box') not in box_values|{None} or row.get('prediction_retail_box','UNKNOWN') not in box_values|{'UNCERTAIN'}:raise ValueError('V2_SAMPLE_BOX')
        for key in ('severe_error','repair_pass','sku_selection_correct'):
            if row.get(key) is not None and type(row[key]) is not bool:raise ValueError('V2_SAMPLE_OUTCOME')
        if (row['human_confirmed'] or row.get('ground_truth_action') is not None or row.get('ground_truth_retail_box') is not None) and (not isinstance(row.get('label_source'),str) or not row['label_source'].strip()):raise ValueError('LABEL_PROVENANCE_REQUIRED')
        fingerprint={key:row.get(key) for key in allowed-{'image_type','source_image'}}
        if digest in unique and unique[digest]['fingerprint']!=fingerprint:raise ValueError('DUPLICATE_SHA_CONFLICT')
        path=row.get('source_image')
        if row['evidence_kind']=='REAL_SHADOW' or path is not None:
            if not isinstance(path,str) or not Path(path).is_file():raise ValueError('SOURCE_IMAGE_REQUIRED')
            if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('SOURCE_IMAGE_SHA')
            try:
                with Image.open(path) as image:image.verify()
            except (OSError,ValueError) as exc:raise ValueError('SOURCE_IMAGE_DECODE') from exc
        if digest in unique:
            duplicates+=1;continue
        row['prediction_retail_box']=row.get('prediction_retail_box','UNKNOWN')
        if row['prediction_retail_box']=='UNCERTAIN':row['prediction_retail_box']='UNKNOWN'
        if row['abstain']:row['prediction_action']='REVIEW'
        unique[digest]={'row':row,'fingerprint':fingerprint}

    def ratio(n,d):return n/d if d else None
    def statistics(values,real):
        def truth(row,key):return row.get(key) if not real or row['human_confirmed'] else None
        groups={}
        for action in actions:
            proposed=[r for r in values if r['prediction_action']==action]
            labelled=[r for r in proposed if truth(r,'ground_truth_action') is not None]
            correct=sum(truth(r,'ground_truth_action')==action for r in labelled)
            severe=[r for r in labelled if r.get('severe_error') is not None]
            repaired=[r for r in labelled if r.get('repair_pass') is not None]
            repair_pass=sum(r['repair_pass'] and truth(r,'ground_truth_action')==action for r in repaired)
            groups[action]=dict(proposed=len(proposed),labeled=len(labelled),unlabeled_proposed=len(proposed)-len(labelled),correct=correct,
                precision=ratio(correct,len(labelled)) if action!='REVIEW' else None,
                severe_reviewed=len(severe),severe_errors=sum(r['severe_error'] for r in severe),severe_unknown=len(proposed)-len(severe),
                severe_error_rate=ratio(sum(r['severe_error'] for r in severe),len(severe)),
                repair_reviewed=len(repaired),repair_passed=repair_pass,repair_pass_rate=ratio(repair_pass,len(repaired)))
        box=dict(present_samples=0,absent_samples=0,present_decided=0,absent_decided=0,present_as_absent=0,absent_as_present=0,deferred=0,unlabeled=0)
        sku={group:dict(reviewed=0,correct=0) for group in ('WITH_RETAIL_BOX','WITHOUT_RETAIL_BOX')}
        for row in values:
            expected=truth(row,'ground_truth_retail_box');predicted=row['prediction_retail_box']
            if expected not in {'PRESENT','ABSENT'}:box['unlabeled']+=1;continue
            prefix='present' if expected=='PRESENT' else 'absent';box[prefix+'_samples']+=1
            if predicted=='UNKNOWN':box['deferred']+=1
            else:box[prefix+'_decided']+=1
            box['present_as_absent']+=expected=='PRESENT' and predicted=='ABSENT'
            box['absent_as_present']+=expected=='ABSENT' and predicted=='PRESENT'
            outcome=row.get('sku_selection_correct')
            if outcome is not None:
                group='WITH_RETAIL_BOX' if expected=='PRESENT' else 'WITHOUT_RETAIL_BOX'
                sku[group]['reviewed']+=1;sku[group]['correct']+=outcome
        box['present_as_absent_rate']=ratio(box['present_as_absent'],box['present_samples'])
        box['absent_as_present_rate']=ratio(box['absent_as_present'],box['absent_samples'])
        for group in sku.values():group['accuracy']=ratio(group['correct'],group['reviewed'])
        deferred=sum(r['prediction_action']=='REVIEW' for r in values)
        errors=sum(r['prediction_action']!='REVIEW' and truth(r,'ground_truth_action') is not None and r['prediction_action']!=truth(r,'ground_truth_action') for r in values)
        return dict(unique_images=len(values),actions=groups,retail_box=box,sku_selection=sku,deferred=deferred,deferred_rate=ratio(deferred,len(values)),decided_errors=errors)

    real=statistics([v['row'] for v in unique.values() if v['row']['evidence_kind']=='REAL_SHADOW'],True)
    synthetic=statistics([v['row'] for v in unique.values() if v['row']['evidence_kind']=='FAKE'],False)
    gates={}
    for action in automatic:
        group=real['actions'][action]
        common=group['labeled']>=30 and group['unlabeled_proposed']==0 and group['severe_unknown']==0 and group['severe_errors']==0
        if action=='DELETE':met=common and group['precision'] is not None and group['precision']>=.98
        elif action=='REMOVE_TEXT':met=common and remove_text_min_pass_rate is not None and group['repair_reviewed']==group['proposed'] and group['repair_pass_rate'] is not None and group['repair_pass_rate']>=remove_text_min_pass_rate
        else:met=common and group['repair_reviewed']==group['proposed'] and group['repair_passed']==group['proposed']
        gates[action]={'met':bool(met),'minimum_independent_images':30,'threshold':.98 if action=='DELETE' else remove_text_min_pass_rate if action=='REMOVE_TEXT' else None}
    box=real['retail_box']
    gates['RETAIL_BOX']={'met':box['present_decided']>=30 and box['absent_decided']>=30 and box['present_as_absent']==0 and box['absent_as_present']==0,'minimum_decided_per_group':30}
    gates['SKU_SELECTION']={'met':all(group['reviewed']>=30 and group['correct']==group['reviewed'] for group in real['sku_selection'].values()),'minimum_reviewed_per_group':30}
    passed=all(gate['met'] for gate in gates.values())
    status='NOT_EVALUATED' if not unique else 'SYNTHETIC_ONLY' if not real['unique_images'] else 'STATISTICS_COMPUTED' if passed else 'INCOMPLETE_REAL_EVIDENCE'
    report=dict(schema='v2-shadow-quality/v1',status=status,confidence_policy='RECORD_ONLY',real=real,synthetic=synthetic,duplicates_merged=duplicates,
        gates=gates,statistical_gates_met=passed,release_authorized=False,real_provenance_independently_verified=False,
        notes=['Only declared real samples with matching local image bytes and human-confirmed labels count toward real statistics.',
               'This tool cannot authenticate human/provider provenance or authorize Shadow, Canary or production.',
               'REVIEW is an abstention; unavailable labels/outcomes/rates remain unknown.',
               'Box/SKU checks conservatively require 30 decided/reviewed samples per group and no observed wrong mapping; this is not a population-error guarantee.'])
    if inventory is not None:
        report['label_registry']=inventory
        report['notes'].append('Registry watermark labels are inventoried only; only explicit DELETE instructions supply action truth. Missing predictions are never generated.')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('samples', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    kinds=parser.add_mutually_exclusive_group()
    kinds.add_argument('--quality',action='store_true',help='score per-type/category detector observations with label provenance')
    kinds.add_argument('--v2',action='store_true',help='offline five-action/box/SKU scoring, deduplicated by image SHA')
    parser.add_argument('--remove-text-min-pass-rate',type=float,help='Explicit project repair pass threshold; no default is invented')
    parser.add_argument('--label-registry',type=Path,help='With --v2, join the existing confirmed v1.3 user-label registry by image SHA')
    args = parser.parse_args()
    if args.label_registry and not args.v2:parser.error('--label-registry requires --v2')
    rows=[json.loads(line) for line in args.samples.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    report=v2_quality_metrics(rows,remove_text_min_pass_rate=args.remove_text_min_pass_rate,label_registry=args.label_registry) if args.v2 else quality_metrics(rows) if args.quality else evaluate(rows)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
