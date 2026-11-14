"""Packaging-aware SKU assignment from independently verified image observations."""
import json
import re

def packaging(name):
    name=str(name).lower()
    if re.search(r'without\s*(retail\s*)?box|no\s*(retail\s*)?box|无盒|不带盒',name): return 'without_box'
    if re.search(r'with\s*(retail\s*)?box|有盒|带盒',name): return 'with_box'
    return 'unknown'

def _complex_contents(name):
    """The basic BOX/FIGURE observation does not prove a bundle's contents."""
    text=str(name).lower()
    if re.search(r'\b(?:bundle|combo|set|upgrade\s+kit|accessory\s+pack)\b|组合|套装|配件包',text):return True
    counts=re.findall(r'(?<![a-z0-9])(\d+)\s*(?:pcs?\b|pieces?\b|件|只)',text)
    counts+=re.findall(r'\bpack\s+of\s+(\d+)\b',text)
    counts+=re.findall(r'(?<![a-z0-9])(\d+)(?:\s*-\s*|\s+)packs?\b',text)
    return any(int(value)>1 for value in counts)

def plan_assignments(product, verified_images, *, allow_snapshot_rows=False):
    identity=product.get('identityJson') or {}
    if isinstance(identity,str):
        try: identity=json.loads(identity)
        except ValueError: identity={}
    model=identity.get('modelCode') if isinstance(identity,dict) else None
    assignments={};deferred=[];evidence=[];deferred_reasons={}
    rows=product.get('skus') or []
    raw_ids=[r.get('skuId',r.get('id','')) for r in rows]
    ids=[str(value) for value in raw_ids]
    invalid_ids=len(ids)!=len(set(ids)) or any(type(value) not in (str,int) or not str(value).strip() for value in raw_ids)
    snapshot=None
    if invalid_ids and allow_snapshot_rows:
        from snapshot_sku import locators
        snapshot=locators(product)
    if invalid_ids and snapshot is None:
        return {'assignments':{},'deferred':ids,'evidence_ids':[],
                'deferred_reasons':{sku_id:'SKU_IDENTIFIER_UNVERIFIED' for sku_id in ids}}
    row_assignments=[];deferred_rows=[]
    def defer(sku_id,index,reason='SKU_ASSIGNMENT_UNCERTAIN'):
        deferred.append(sku_id);deferred_reasons[sku_id]=reason
        if snapshot is not None:deferred_rows.append({'index':index,'reason':reason})
    for index,(sku,sku_id) in enumerate(zip(rows,ids)):
        declared=sku.get('modelCode')
        compact=lambda value:re.sub(r'[-\s]','',value.upper())
        if declared not in (None,'') and (type(declared) is not str or type(model) is not str or compact(declared)!=compact(model)):
            defer(sku_id,index,'SKU_MODEL_CONFLICT' if isinstance(declared,str) and isinstance(model,str) else 'SKU_MODEL_UNVERIFIED')
            continue
        if _complex_contents(sku.get('skuName',sku.get('name',''))):
            defer(sku_id,index,'SKU_COMPLEX_CONTENTS_UNVERIFIED');continue
        expected=packaging(sku.get('skuName',sku.get('name','')))
        current=sku.get('skuImageUrl') or sku.get('imageUrl') or sku.get('image')
        candidates=[r for r in verified_images if model and r.get('model')==model and r.get('verified') is True and r.get('clean') is True and r.get('evidence_ids') and r.get('sha256') and r.get('image_type') in {'BOX','FIGURE'}]
        if sku.get('color'): candidates=[r for r in candidates if r.get('color')==sku['color']]
        if expected=='unknown': defer(sku_id,index);continue
        compatible=[r for r in candidates if r['image_type']=='FIGURE' or expected=='with_box']
        prior=next((r for r in compatible if r['url']==current),None)
        # Existing correct references are stable, including shared body images.
        if prior:
            evidence.extend(prior['evidence_ids']);continue
        # Keep an existing with-box reference when it cannot be independently
        # confirmed and no verified box replacement exists. A safe body image
        # for the without-box row does not justify changing both rows.
        if expected=='with_box' and current and not any(r['image_type']=='BOX' for r in compatible):
            defer(sku_id,index,'SKU_EXISTING_REFERENCE_UNVERIFIED');continue
        if expected=='with_box' and any(r['image_type']=='BOX' for r in compatible):
            compatible=[r for r in compatible if r['image_type']=='BOX']
        by_url={r['url']:r for r in compatible}
        # Main/detail can host byte-identical copies at different URLs. Only
        # exact SHA identity merges choices; similar-looking poses stay distinct.
        if len(by_url)>1 and len({r['sha256'] for r in by_url.values()})==1:
            chosen_url=min(by_url)
            by_url={chosen_url:by_url[chosen_url]}
        if len(by_url)!=1: defer(sku_id,index);continue
        chosen=next(iter(by_url.values()))
        if snapshot is not None:row_assignments.append(dict(snapshot[index],url=chosen['url']))
        else:assignments[sku_id]=chosen['url']
        evidence.extend(chosen['evidence_ids'])
    result={'assignments':assignments,'deferred':deferred,'evidence_ids':sorted(set(evidence)),'deferred_reasons':deferred_reasons}
    if snapshot is not None:result.update(row_assignments=row_assignments,deferred_rows=deferred_rows)
    return result
