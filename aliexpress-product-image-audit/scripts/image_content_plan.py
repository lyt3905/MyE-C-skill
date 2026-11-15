"""Shared content-SHA operations for V2 simulation, save and readback."""
from copy import deepcopy
from description_images import body_image_nodes,edit_body_images


def compile_groups(inventory,safe,rows):
    groups=[]
    for digest,content in inventory['contents'].items():
        matches=[r for r in safe if r.get('v2_contract') and r['action'] in {'DELETE','REMOVE_TEXT','AI_REGENERATE','REPLACE_TWIN'} and r['source'].get('original_sha256',r['source']['sha256'])==digest]
        if not matches:continue
        conflicting=[r for r in rows if r.get('v2_contract') and r.get('source',{}).get('original_sha256',r.get('source',{}).get('sha256'))==digest and r['decision'] not in {'AUTO_SAFE','KEEP'}
                     and not (r.get('reason_codes')==['SKU_MAPPING_UNRESOLVED'] and ('sku_row_index' in r['target'] or r['target'].get('pool')=='sku'))]
        if conflicting:raise ValueError('CONTENT_GROUP_PARTIALLY_DEFERRED')
        actions={r['action'] for r in matches}
        candidates={r['source']['sha256'] if r['action']=='REPLACE_TWIN' else r.get('candidate_asset',{}).get('sha256') for r in matches}
        if len(actions)!=1 or len(candidates)!=1:raise ValueError('CONTENT_GROUP_CONFLICT')
        group=dict(source_sha256=digest,urls=list(content['urls']),action=matches[0]['action'],candidate_sha256=next(iter(candidates)))
        if group['action']=='REPLACE_TWIN':
            urls={r['source']['url'] for r in matches}
            if len(urls)!=1:raise ValueError('CONTENT_GROUP_CONFLICT')
            group['replacement_url']=next(iter(urls))
        groups.append(group)
    return groups


def content_changes(plan,uploaded_urls=None):
    uploads=(plan.get('post_actions') or {}).get('uploads',[])
    resolved={r['sha256']:url for r,url in zip(uploads,uploaded_urls or [])}
    deletions=[];replacements={}
    for group in (plan.get('post_actions') or {}).get('content_groups',[]):
        if group['action']=='DELETE':deletions.extend(group['urls'])
        elif group['action']=='REPLACE_TWIN':replacements.update({u:group['replacement_url'] for u in group['urls']})
        elif group['candidate_sha256'] in resolved:
            replacements.update({u:resolved[group['candidate_sha256']] for u in group['urls']})
    return deletions,replacements


def apply_groups(before,result,plan,uploaded_urls=None):
    deleted,replaced=content_changes(plan,uploaded_urls)
    preserved=set((plan.get('post_actions') or {}).get('preserve_reference_urls',[]))
    for pool in ('main','detail','sku'):
        if pool in result.get('images',{}):result['images'][pool]=[u if pool=='sku' and u in preserved else replaced.get(u,u) for u in result['images'][pool] if u not in deleted]
    for sku in result.get('skus') or []:
        for field in ('skuImageUrl','imageUrl','image'):
            if sku.get(field) in deleted:raise ValueError('CONTENT_DELETION_BREAKS_SKU')
            if sku.get(field) in replaced and sku[field] not in preserved:sku[field]=replaced[sku[field]]
    if body_image_nodes(before.get('descriptionJson')):
        result['descriptionJson']=edit_body_images(before['descriptionJson'],deleted,replaced)
    return result


def uploaded_from_snapshot(before,plan,snapshot):
    """Resolve approved upload positions, including nodes shifted by body deletes."""
    deleted,_=content_changes(plan)
    removed=[r['index'] for r in body_image_nodes(before.get('descriptionJson')) if r['url'] in deleted]
    nodes={r['index']:r['url'] for r in body_image_nodes(snapshot.get('descriptionJson'))}
    urls=[]
    for ref in (plan.get('post_actions') or {}).get('uploads',[]):
        if ref['pool']=='description':urls.append(nodes[ref['index']-sum(i<ref['index'] for i in removed)])
        else:urls.append(snapshot['images'][ref['pool']][ref['index']])
    return urls


def save_scope(before,plan,snapshot):
    return content_changes(plan,uploaded_from_snapshot(before,plan,snapshot))
