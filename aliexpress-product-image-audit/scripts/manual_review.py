"""Evidence-bound review validation. File edits are not authorization to write."""
import hashlib
import json
from pathlib import Path

def evidence_hash(root):
    root=Path(root)
    names={'audit_product.json','audit_flags.json','audit_raw.json','ai_judgements.json','ai_queue.json'}
    manifest=root/'evidence_manifest.json'
    sources=[]
    if manifest.exists():
        data=json.loads(manifest.read_text(encoding='utf-8'))
        names.add('evidence_manifest.json')
        names.update(row['path'] for row in data.get('files',[]))
        sources=data.get('sources',[])
    bound=[]
    for name in sorted(names):
        path=(root/name).resolve()
        if not path.is_relative_to(root.resolve()): raise ValueError('unsafe manifest path')
        bound.append((name,hashlib.sha256(path.read_bytes()).hexdigest()))
    for row in sources:
        path=Path(row['source'])
        bound.append((str(path),hashlib.sha256(path.read_bytes()).hexdigest()))
    return hashlib.sha256(json.dumps(bound,sort_keys=True).encode()).hexdigest()

def validate_review(root,job,review):
    manifest=Path(root)/'evidence_manifest.json'
    if not manifest.exists(): raise ValueError('EVIDENCE_MANIFEST_REQUIRED: legacy review must be renewed')
    envelope=json.loads(manifest.read_text(encoding='utf-8'))
    if envelope.get('schema')!='evidence-manifest/v1' or not isinstance(envelope.get('files'),list) or not isinstance(envelope.get('sources'),list):
        raise ValueError('invalid evidence manifest')
    if review.get('schema') != 'manual-review/v1' or any(review.get(k)!=job[k] for k in ('job_id','pid','shop_id')):
        raise ValueError('review identity mismatch')
    if review.get('evidence_sha256') != evidence_hash(root): raise ValueError('review evidence changed')
    queue=json.loads((Path(root)/'ai_queue.json').read_text(encoding='utf-8'))
    known={row['id']:set(row.get('evidence_ids',[])) for row in queue['items']}
    known['MACHINE_ANOMALIES']={'audit_flags.json'}
    decisions={}
    for row in review.get('items',[]):
        if row.get('decision') not in {'KEEP','REMOVE_CANDIDATE','REMOVE_CANDIDATE_CONFIRMED','REPLACE_LOCAL','CROP_BANNER','WEB_DEFER','SKU_ASSIGN_CONFIRMED','NEEDS_MORE_EVIDENCE','NEEDS_REVIEW'} or not row.get('reviewed_at') or not row.get('reviewer') or not row.get('reason') or not row.get('evidence_ids'):
            raise ValueError('incomplete review')
        if row['item_id'] not in known or not set(row['evidence_ids']) <= known[row['item_id']]: raise ValueError('unbound review evidence')
        if row['item_id'] in decisions: raise ValueError('duplicate review')
        decisions[row['item_id']]=row['decision']
    return decisions

def submit(manager,job_id,review):
    """Explicit review submission recompiles; it never authorizes Executor."""
    from job_manager import atomic_json
    from plan_compiler import compile_plan
    job=manager.load(job_id); root=manager.directory(job_id)
    state=json.loads((root/'state.json').read_text(encoding='utf-8'))
    if state['state']!='NEEDS_REVIEW': raise ValueError('job is not awaiting review')
    validate_review(root,job,review)
    result=compile_plan(root,job,review)
    atomic_json(root/'manual_review.json',review)
    manager.resolve_review(job_id,result)
    return result
