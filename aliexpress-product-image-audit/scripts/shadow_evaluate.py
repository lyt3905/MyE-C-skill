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


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('samples', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--quality',action='store_true',help='score per-type/category detector observations with label provenance')
    args = parser.parse_args()
    scorer=quality_metrics if args.quality else evaluate
    report = scorer([json.loads(line) for line in args.samples.read_text(encoding='utf-8-sig').splitlines() if line.strip()])
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
