"""Bind proposed actions to independent validation records and current input bytes."""
import json
from pathlib import Path
from candidate_quality import sha256
from product_state import canonical_state_hash

def verify(root,row,product):
    root=Path(root)
    def read(name):return json.loads((root/name).read_text(encoding='utf-8'))
    if row['action'] in {'TITLE_REWRITE','SKU_ASSIGN','BRAND_CODE'}:
        record=read('semantic_validation.json')
        if record.get('source_product_sha256')!=canonical_state_hash(product) or row['source']['sha256']!=canonical_state_hash(product):
            raise ValueError('SEMANTIC_SOURCE_CHANGED')
        proposed={k:v for k,v in row.items() if k not in {'decision','automation_policy_sha256'}}
        if proposed not in record.get('candidates',[]):raise ValueError('SEMANTIC_VALIDATION_UNBOUND')
        return
    raw=read('audit_raw.json')['images']
    target=row['target']
    original=next((r for r in raw if r.get('kind')==target['pool'] and r.get('index')==target['index']),None)
    if original is None:raise ValueError('ORIGINAL_IMAGE_EVIDENCE_MISSING')
    def actual_path(value):
        path=Path(value)
        return path if path.is_absolute() else Path(__file__).parent/path
    original_sha=sha256(actual_path(original['file']))
    if row['action']=='BOX_NORMALIZE':
        proposed={k:v for k,v in row.items() if k not in {'decision','automation_policy_sha256'}}
        proof=next((p for p in read('box_validation.json')['items'] if p.get('candidate')==proposed),None)
        if not proof:raise ValueError('BOX_VALIDATION_UNBOUND')
        observation=proof['observation']
        from product_state import identity_object
        if observation.get('verified') is not True or observation.get('clean') is not True or observation.get('image_type')!='BOX' or observation.get('sha256')!=original_sha or observation.get('model')!=identity_object(product.get('identityJson') or {}).get('modelCode'):raise ValueError('BOX_OBSERVATION_CONFLICT')
    if original.get('content_sha256') not in (None,original_sha):raise ValueError('ORIGINAL_IMAGE_CHANGED')
    if row['action']=='DELETE_REDUNDANT':
        proposed={k:v for k,v in row.items() if k not in {'decision','automation_policy_sha256'}}
        records=read('deletion_validation.json').get('items',[])
        proof=next((r for r in records if r.get('candidate')==proposed and r.get('source_sha256')==original_sha),None)
        if not proof or row['source']['sha256']!=original_sha or row['source'].get('url')!=original.get('url'):raise ValueError('DELETION_VALIDATION_UNBOUND')
        if any(r.get('url')==original.get('url') and (r.get('is_box') is True or r.get('image_type') in {'box','packaging'}) for r in raw):raise ValueError('BOX_DELETION_FORBIDDEN')
        observed=proof.get('observation',{})
        if observed.get('ok') is not True or observed.get('is_box') is not False or observed.get('is_official') is not False or observed.get('information_preserved') is not True:raise ValueError('DELETION_QUALITY_CONFLICT')
        reference=row['source'].get('reference')
        if reference:
            sibling=next((r for r in raw if r.get('kind')==reference['pool'] and r.get('index')==reference['index'] and r.get('url')==reference['url']),None)
            if sibling is None or sha256(actual_path(sibling['file']))!=reference['sha256'] or reference['sha256']!=original_sha or observed.get('reference_sha256')!=reference['sha256']:
                raise ValueError('DUPLICATE_REFERENCE_UNBOUND')
            cleanup=read('main_cleanup.json')
            if reference['pool']!='main' or reference['index'] not in cleanup['retained_main_indices'] or target['index'] not in cleanup['selected_delete_indices']:
                raise ValueError('DUPLICATE_REFERENCE_NOT_RETAINED')
        return
    if row['action']=='REPLACE_TWIN':
        source=next((r for r in raw if r.get('url')==row['source'].get('url')),None)
        if source is None or sha256(actual_path(source['file']))!=row['source']['sha256']:
            raise ValueError('TWIN_SOURCE_SHA_UNBOUND')
    else:
        asset=row.get('candidate_asset') or {};path=(root/asset.get('path','')).resolve()
        if not path.is_relative_to(root.resolve()) or sha256(path)!=row['source']['sha256'] or asset.get('sha256')!=row['source']['sha256']:
            raise ValueError('CANDIDATE_SOURCE_SHA_UNBOUND')
        if row['action']=='REPLACE_LOCAL':
            if row['source'].get('target_original_sha256')!=original_sha or sha256(Path(row['source']['original_path']))!=row['source'].get('original_sha256'):
                raise ValueError('OFFICIAL_SOURCE_SHA_UNBOUND')
        elif row['source'].get('original_sha256')!=original_sha:raise ValueError('ORIGINAL_SOURCE_SHA_UNBOUND')
    records=read('candidate_quality.json').get('items',[])
    checked=next((r for r in records if r.get('item_id')==row['item_id'] and r.get('action')==row['action'] and r.get('ok') is True and r.get('source_sha256')==original_sha and r.get('candidate_sha256')==row['source']['sha256']),None)
    if not checked or not checked.get('evidence_ids') or not set(checked['evidence_ids'])<=set(row['evidence_ids']):
        raise ValueError('INDEPENDENT_QUALITY_RECORD_UNBOUND')
    from remedy_schema import COMMON_CHECKS,ACTION_CHECKS
    required=COMMON_CHECKS|ACTION_CHECKS.get(row['action'],set())
    for key in required-{'mask_background_only','outside_mask_unchanged'}:
        if checked.get('checks',{}).get(key) is not True or row['checks'].get(key) is not True:raise ValueError('QUALITY_CHECK_CONFLICT')
