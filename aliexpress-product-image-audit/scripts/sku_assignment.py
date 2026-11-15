"""Packaging-aware SKU assignment from independently verified image observations."""
import json
import re

def select_v2(product, records, *, allow_snapshot_rows=False):
    """Select logical images first, then bind real IDs to the site's one URL field."""
    from ai_judge.image_action_decision import mark_disposition
    reasons=[];unique={r['sha256']:r for r in reversed(records)};rows=list(unique.values())
    def qualified(r):
        o=r.get('observation') or {}
        suitable=o.get('sku_suitability') or {}
        photo=suitable.get('is_retail_box_photo') if o.get('visual_class') in {'TOY_WITH_RETAIL_BOX','RETAIL_BOX_ONLY'} else suitable.get('is_toy_photo')
        return (r.get('decision')=='KEEP' and not o.get('abstain') and
                photo is True and
                o.get('subject_complete') is True and o.get('clear') is True and min(r.get('width',0),r.get('height',0))>=800 and
                not any(mark_disposition(m)=='REMOVABLE' for m in o.get('watermarks',[])))
    clean=[r for r in rows if qualified(r)]
    boxes=[r for r in clean if r['observation'].get('retail_box_status')=='PRESENT' and
           r['observation'].get('visual_class') in {'TOY_WITH_RETAIL_BOX','RETAIL_BOX_ONLY'}]
    selected=[];group='UNKNOWN'
    rank=lambda r:(r['observation']['visual_class']!='TOY_WITH_RETAIL_BOX',-r['width']*r['height'],r['sha256'])
    if boxes:
        group='WITH_RETAIL_BOX';selected=sorted(boxes,key=rank)[:1]
    elif rows and all(r.get('observation') and r['observation'].get('retail_box_status')=='ABSENT' and r.get('decision')!='REVIEW' for r in rows):
        group='WITHOUT_RETAIL_BOX'
        toys=sorted((r for r in clean if r['observation']['visual_class'] in {'TOY_PRODUCT','PRODUCT_MAIN','PRODUCT_DETAIL'}),key=lambda r:(-r['width']*r['height'],r['sha256']))
        if toys:
            selected=[toys[0]]
            second=next((r for r in toys[1:] if r['observation']['angle'] not in {'UNKNOWN',toys[0]['observation']['angle']}),None)
            if len(toys)>1:selected.append(second or toys[1])
        if len(selected)<2:reasons.append('SKU_IMAGE_SHORTAGE='+str(len(selected))+'_OF_2')
    else:reasons.append('RETAIL_BOX_UNKNOWN')
    skus=product.get('skus') or [];ids=[s.get('skuId',s.get('id')) for s in skus]
    valid=all(type(i) in (str,int) and str(i).strip() for i in ids) and len(set(map(str,ids)))==len(ids)
    expected='with_box' if group=='WITH_RETAIL_BOX' else 'without_box'
    eligible=[(s,str(i)) for s,i in zip(skus,ids) if packaging(s.get('skuName',s.get('name','')))==expected]
    if len(skus)==1 and packaging(skus[0].get('skuName',skus[0].get('name',''))) in {expected,'unknown'} and not _complex_contents(skus[0].get('skuName',skus[0].get('name',''))):eligible=[(skus[0],str(ids[0]))]
    assignments={};row_assignments=[];bindings={};bound=None
    # Two unboxed product photos may illustrate the two existing purchase
    # options; this does not change what packaging is visible in either photo.
    kinds=[packaging(s.get('skuName',s.get('name',''))) for s in skus]
    pair=(group=='WITHOUT_RETAIL_BOX' and len(selected)==2 and len({r['url'] for r in selected})==2 and
          len(skus)==2 and set(kinds)=={'without_box','with_box'} and
          all(not _complex_contents(s.get('skuName',s.get('name',''))) and
              (s.get('originalBox') is None or type(s['originalBox']) is bool and s['originalBox']==(kind=='with_box'))
              for s,kind in zip(skus,kinds)))
    pair_indices=[kinds.index(kind) for kind in ('without_box','with_box')] if pair else []
    def bind(indices):
        unused=list(selected)
        for index in indices:
            current=skus[index].get('skuImageUrl') or skus[index].get('imageUrl') or skus[index].get('image')
            chosen=next((r for r in unused if r['url']==current),unused[0])
            unused.remove(chosen);bindings[index]=chosen
            if valid:assignments[str(ids[index])]=chosen['url']
            else:row_assignments.append(dict(bound[index],url=chosen['url']))
    if selected and valid and len(eligible)==1:
        bind(pair_indices or [next(i for i,value in enumerate(ids) if str(value)==eligible[0][1])])
    elif selected and not valid and allow_snapshot_rows:
        from snapshot_sku import locators
        bound=locators(product)
        indices=[i for i,s in enumerate(skus) if packaging(s.get('skuName',s.get('name','')))==expected]
        if bound and len(indices)==1:
            bind(pair_indices or indices)
        else:reasons.append('SKU_MAPPING_UNRESOLVED')
    elif selected or skus:reasons.append('SKU_MAPPING_UNRESOLVED')
    second_assigned=len(bindings)==2 and len({r['sha256'] for r in bindings.values()})==2
    if len(selected)>1 and not second_assigned:reasons.append('SITE_SINGLE_IMAGE_REFERENCE')
    capabilities=dict(scope='CURRENT_WRITER_AND_INPUT_SNAPSHOT_ONLY',scalar_reference_fields=sorted({key for sku in skus for key in ('skuImageUrl','imageUrl','image') if isinstance(sku.get(key),str)}),writer_multi_reference_supported=False,other_interfaces_verified=False,second_reference_assigned=second_assigned,second_reference_scope='DISTINCT_SKU_ROWS' if second_assigned else None)
    images=[]
    for r in selected:
        index=next((i for i,candidate in bindings.items() if candidate['sha256']==r['sha256']),None)
        target_group=('WITH_RETAIL_BOX' if kinds[index]=='with_box' else 'WITHOUT_RETAIL_BOX') if index is not None else group
        images.append(dict(image_id=r['image_id'],sha256=r['sha256'],url=r['url'],logical_sku_group=target_group,
                           source_retail_box_status=r['observation'].get('retail_box_status'),
                           target_sku_id=str(ids[index]) if index is not None and valid else None,
                           target_sku_locator=bound[index] if index is not None and bound else None))
    return dict(sku_packaging_decision=group,selected_sku_images=images,assignments=assignments,row_assignments=row_assignments,reason_codes=reasons,site_multi_image_supported=False,capability_evidence=capabilities)

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
