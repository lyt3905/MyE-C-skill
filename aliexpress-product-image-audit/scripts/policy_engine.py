"""AI classifications never directly authorize image removal."""
import json
from pathlib import Path
POLICY = json.loads((Path(__file__).parent / 'config' / 'policy.v2.json').read_text(encoding='utf-8-sig'))
KEEP = {key for key,value in POLICY['watermark'].items() if value == 'KEEP'}
REMOVE = {key for key,value in POLICY['watermark'].items() if value == 'REMOVE_CANDIDATE'}
def evaluate(judgement):
    rows=judgement.get('results',[])
    if judgement.get('status') in {'REVIEW','NEEDS_REVIEW'} or not rows:
        return 'NEEDS_REVIEW'
    if rows and all(r.get('task_type')=='watermark' and r.get('schema_version')=='watermark/v3' for r in rows):
        from ai_judge.watermark_contract import aggregate_watermarks
        audit=aggregate_watermarks(judgement,judgement.get('evidence_spec'))
        return 'KEEP' if audit['review_status']=='PASS' else 'REMOVE_CANDIDATE' if audit['review_status']=='FAIL' else 'NEEDS_REVIEW'
    if any(r.get('abstain') or r.get('confidence',0) < .9 for r in rows): return 'NEEDS_REVIEW'
    for row in rows:
        if row.get('task_type') == 'sku_match':
            # Explicit semantic conflicts cannot be overridden by a MATCH label.
            if row.get('missing_image') or row.get('image_type') == 'box' and row.get('shared_across_skus'):
                return 'NEEDS_REVIEW'
            if row.get('sku_packaging') == 'without_box' and row.get('image_type') == 'box':
                return 'NEEDS_REVIEW'
            if row.get('sku_packaging') == 'with_box' and row.get('image_type') == 'product_only':
                return 'NEEDS_REVIEW'
    if all(r.get('task_type') != 'watermark' for r in rows):
        return 'KEEP' if all(r.get('decision') == 'MATCH' for r in rows) else 'NEEDS_REVIEW'
    classes={r.get('classification') for r in rows}
    if len(classes)==1 and classes <= KEEP: return 'KEEP'
    if classes <= REMOVE: return 'REMOVE_CANDIDATE'
    return 'NEEDS_REVIEW'
