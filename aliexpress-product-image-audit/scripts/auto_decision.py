"""Per-action conservative decisions; unrelated deferred items remain unchanged."""
from copy import deepcopy
from remedy_schema import validate_candidate

def decide(candidates, policy, *, pid, shop, integrity_ok=True, execution=True):
    results=[]
    upload_assets=set()
    for candidate in candidates:
        row=deepcopy(candidate)
        if not integrity_ok:
            row.update(decision='BLOCKED_FATAL',reason_codes=['GLOBAL_INTEGRITY_ERROR'])
        elif row.get('action') in {'WEB_DEFER','KEEP'}:
            row['decision']='DEFERRED' if row['action']=='WEB_DEFER' else 'KEEP'
        else:
            try:
                validate_candidate(row)
                if row.get('validation_scope',{}).get('type')=='AUTHORIZED_DECORATED_COMPOSITE_REMOVAL' and policy.config.get('delete_decorated_composites') is not True:
                    raise ValueError('COMPOSITE_DELETION_NOT_ENABLED')
                accepted={r['remedy_id'] for r in results if r.get('decision')=='AUTO_SAFE'}
                if not set(row.get('requires_remedy_ids',[]))<=accepted:
                    raise ValueError('REMEDY_DEPENDENCY_NOT_AUTHORIZED')
                next_assets=set(upload_assets)
                if row['action'] in {'REPLACE_LOCAL','CROP_BANNER','BOX_NORMALIZE','ERASE_LOCAL','REMOVE_TEXT','AI_REGENERATE'}:
                    asset=row.get('candidate_asset') or {}
                    digest=asset.get('sha256') or (row.get('source') or {}).get('sha256')
                    if not digest:
                        raise ValueError('UPLOAD_ASSET_HASH_REQUIRED')
                    next_assets.add(digest)
                policy.authorize(pid,shop,[row['action']],execution=execution,uploads=len(next_assets))
                upload_assets=next_assets
                row.update(decision='AUTO_SAFE',automation_policy_sha256=policy.sha256)
            except (ValueError,KeyError,TypeError) as exc:
                row.update(decision='DEFERRED',reason_codes=list(dict.fromkeys(row.get('reason_codes',[])+[str(exc)])))
        results.append(row)
    return results
