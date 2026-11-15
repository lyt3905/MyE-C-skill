"""Snapshot-scoped SKU row locators; never substitute row numbers for SKU IDs."""
import hashlib
from product_state import canonical_json


def row_hash(row):
    return hashlib.sha256(canonical_json(row).encode('utf-8')).hexdigest()


def locators(product):
    from sku_assignment import packaging
    rows=product.get('skus') or []
    if not 1<=len(rows)<=2:return None
    kinds=[]
    for row in rows:
        if not isinstance(row,dict) or any(row.get(k) not in (None,'') for k in ('id','skuId')):return None
        kind=packaging(row.get('skuName',row.get('name','')))
        if kind=='unknown':return None
        declared=row.get('originalBox')
        if declared is not None and (type(declared) is not bool or declared!=(kind=='with_box')):return None
        kinds.append(kind)
    if len(set(kinds))!=len(kinds):return None
    return [{'index':i,'source_sha256':row_hash(row)} for i,row in enumerate(rows)]


def validate_assignments(product, assignments):
    expected=locators(product)
    if expected is None or type(assignments) is not list or not assignments:
        raise ValueError('SNAPSHOT_SKU_BINDING_UNVERIFIED')
    seen=set()
    urls={url for pool in ('main','detail','sku') for url in (product.get('images') or {}).get(pool,[])}
    urls.update(row.get('skuImageUrl') or row.get('imageUrl') or row.get('image') for row in product.get('skus') or [])
    for assignment in assignments:
        if type(assignment) is not dict or set(assignment)!={'index','source_sha256','url'}:
            raise ValueError('INVALID_SNAPSHOT_SKU_ASSIGNMENT')
        index=assignment['index']
        if type(index) is not int or index<0 or index>=len(expected) or index in seen:
            raise ValueError('INVALID_SNAPSHOT_SKU_INDEX')
        if assignment['source_sha256']!=expected[index]['source_sha256']:
            raise ValueError('SNAPSHOT_SKU_SOURCE_CHANGED')
        if not isinstance(assignment['url'],str) or assignment['url'] not in urls:
            raise ValueError('SNAPSHOT_SKU_SOURCE_NOT_IN_PRODUCT')
        seen.add(index)
    return assignments
