"""Pure validation of evidence-bound multi-image deletions."""
import copy
import hashlib
from pathlib import Path


def validate_batch(product, raw, queue, review_rows, change):
    targets = change.get('targets')
    ids = change.get('item_ids')
    if not isinstance(targets, list) or not targets or not isinstance(ids, list):
        raise ValueError('batch targets required')
    if len(set(ids)) != len(ids) or len(targets) != len(ids):
        raise ValueError('duplicate batch targets')
    expected = copy.deepcopy(product.get('images', {}))
    selected = set()
    urls = set()
    bound_ids = set()
    for target in targets:
        if set(target) != {'item_id', 'pool', 'index'}:
            raise ValueError('invalid batch target')
        key, pool, index = target['item_id'], target['pool'], target['index']
        if key not in ids or key in bound_ids or key not in queue:
            raise ValueError('unbound batch target')
        bound_ids.add(key)
        row, item = review_rows[key], queue[key]
        if row.get('decision') != 'REMOVE_CANDIDATE_CONFIRMED' or 'DELETE' not in row.get('authorized_actions', []):
            raise ValueError('ACTION_NOT_AUTHORIZED')
        if pool not in {'main', 'detail'} or type(index) is not int or index < 0 or index >= len(expected.get(pool, [])) or (pool, index) in selected:
            raise ValueError('invalid batch index')
        matches = [r for r in raw.get('images', []) if r.get('kind') == pool and r.get('index') == index]
        if len(matches) != 1:
            raise ValueError('original image evidence missing')
        source = matches[0]
        if source.get('file') != item.get('local') or source.get('url') != product['images'][pool][index]:
            raise ValueError('batch source mismatch')
        if not item.get('sha256') or hashlib.sha256(Path(item['local']).read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('original image changed')
        if ('kind' in item and item['kind'] != pool) or ('index' in item and item['index'] != index):
            raise ValueError('batch target mismatch')
        selected.add((pool, index))
        urls.add(source['url'])
    if bound_ids != set(ids):
        raise ValueError('unbound batch ids')
    for pool, index in sorted(selected, key=lambda t: (t[0], -t[1])):
        del expected[pool][index]
    normalize = change.get('preserve_existing_sku_refs', False)
    if type(normalize) is not bool:
        raise ValueError('invalid SKU reference normalization')
    if normalize:
        for sku in product.get('skus') or []:
            url = sku.get('skuImageUrl') or sku.get('imageUrl') or sku.get('image')
            if url and url not in expected.setdefault('sku', []):
                expected['sku'].append(url)
    if expected != change.get('value'):
        raise ValueError('unreviewed image target changed')
    return urls


def remove_description_images(document, urls):
    """Removed legacy operation: the fixed field must remain opaque."""
    raise ValueError('DESCRIPTION_OPERATION_FORBIDDEN')
