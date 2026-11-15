"""Deletion proposals require separate full-image semantics, never a watermark label alone."""
import json
from pathlib import Path
from PIL import Image
from candidate_quality import sha256
from job_manager import atomic_json

def deletion_description(product,deleted_urls,remaining_images):
    """Removed legacy operation: the fixed field must remain opaque."""
    raise ValueError('DESCRIPTION_OPERATION_FORBIDDEN')

def plan_deletion(directory,item,product,raw_images,inspector,comparison=None,*,decorated_refs=None):
    root=Path(directory);pool,index=item.get('pool'),item.get('index')
    urls=(product.get('images') or {}).get(pool,[])
    if pool not in {'main','detail'} or type(index) is not int or not 0<=index<len(urls) or len(urls)<=1:return None
    url=urls[index]
    decorated=decorated_refs is not None
    if decorated and (not decorated_refs or comparison is not None):return None
    if url!=item.get('source_url') or (not decorated and any(r.get('url')==url and (r.get('is_box') is True or r.get('image_type') in {'box','packaging'}) for r in raw_images)):return None
    if inspector is None or not callable(getattr(inspector,'inspect_deletion',None)):return None
    path=Path(item['local'])
    try:
        with Image.open(path) as image:
            image.verify()
            if min(image.size)<600:return None
        digest=sha256(path)
        if digest!=item.get('source_sha256',item.get('sha256')):return None
        reference=None
        if comparison is not None:
            reference=Path(comparison['file'])
            if not reference.is_absolute():reference=Path(__file__).parent/reference
            if comparison.get('source')=='skus' or comparison.get('error') or sha256(reference)!=digest or comparison.get('content_sha256') not in (None,digest):return None
            observed=inspector.inspect_deletion(path,product,comparison=reference)
            if observed.get('category')!='REDUNDANT' or observed.get('reference_sha256')!=digest or sha256(reference)!=digest or sha256(path)!=digest:return None
            observed=dict(observed,reference_url=comparison['url'])
        elif decorated:
            references=[]
            for raw in decorated_refs:
                ref=Path(raw['file'])
                if not ref.is_absolute():ref=Path(__file__).parent/ref
                ref_sha=sha256(ref)
                if ref_sha==digest or raw.get('content_sha256') not in (None,ref_sha) or raw.get('url')==url:return None
                if raw.get('url') not in (product.get('images') or {}).get(raw.get('kind'),[]):return None
                references.append({'pool':raw['kind'],'index':raw['index'],'url':raw['url'],'sha256':ref_sha})
            observed=inspector.inspect_deletion(path,product,decorated_refs=decorated_refs)
            if observed.get('decorated_composite') is not True or observed.get('retained_packaging_verified') is not True or observed.get('category')!='DECORATION':return None
        else:observed=inspector.inspect_deletion(path,product)
        if observed.get('ok') is not True or (not decorated and observed.get('is_box') is not False) or observed.get('is_official') is not False or observed.get('information_preserved') is not True or observed.get('category') not in {'REDUNDANT','DECORATION','STORE_BANNER'} or not observed.get('evidence_ids'):return None
        # Duplicate deletion needs a bound existing sibling, not a model's ungrounded adjective.
        if observed['category']=='REDUNDANT' and not observed.get('reference_url'):return None
        if observed['category']=='REDUNDANT' and not any(observed['reference_url'] in values for values in product['images'].values()):return None
        if observed['category']=='REDUNDANT':
            sibling=next((r for r in raw_images if r.get('url')==observed['reference_url'] and (r.get('kind'),r.get('index'))!=(pool,index)),None)
            if sibling is None:return None
            reference=Path(sibling['file'])
            if not reference.is_absolute():reference=Path(__file__).parent/reference
            import cv2,numpy as np
            from imgpool import _phash,_ham
            images=[cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_GRAYSCALE) for p in (path,reference)]
            if any(image is None for image in images) or _ham(_phash(images[0]),_phash(images[1]))>6:return None
        remaining={k:list(v) for k,v in product['images'].items()};del remaining[pool][index]
        checks={k:True for k in ('product_identity_match','candidate_visual_validation','protected_elements_preserved','source_bound','non_box_deletion','non_official_deletion','visual_evidence_600px')}
        row=dict(remedy_id='DEL_'+item['id'],item_id=item['id'],action='DELETE_REDUNDANT',target={'pool':pool,'index':index,'image_id':item['image_id']},source={'type':'existing_pool','url':url,'sha256':digest},candidate_asset=None,evidence_ids=item['evidence_ids']+observed['evidence_ids'],checks=checks,is_box=False,reason_codes=['INDEPENDENT_DELETION_VALIDATED'])
        if decorated:
            row['is_box']=observed['is_box']
            row['checks'].pop('non_box_deletion')
            row['checks'].update(decorated_composite=True,retained_packaging_verified=True)
            row['source']['retained_references']=references
            row['validation_scope']={'type':'AUTHORIZED_DECORATED_COMPOSITE_REMOVAL'}
            row['reason_codes']=['DECORATED_COMPOSITE_FULL_IMAGE_REVIEW_AND_RETAINED_PACKAGING']
        if comparison is not None:
            row['source']['reference']={'pool':comparison['kind'],'index':comparison['index'],'url':comparison['url'],'sha256':digest}
        record=root/'deletion_validation.json'
        records=json.loads(record.read_text(encoding='utf-8'))['items'] if record.exists() else []
        records.append({'candidate':row,'observation':observed,'source_sha256':digest})
        atomic_json(record,{'items':records})
        return row
    except Exception:return None


def plan_decorated_cleanup(directory,product,raw_images,inspector):
    """Classify whole shop posters before attempting local watermark repair."""
    rows=[]
    for image in raw_images:
        if image.get('kind') not in {'main','detail'} or image.get('source')=='skus' or image.get('error'):continue
        try:
            path=Path(image['file'])
            if not path.is_absolute():path=Path(__file__).parent/path
            digest=sha256(path);refs={}
            for ref in raw_images:
                if ref.get('kind') not in {'main','detail','sku'} or ref.get('source')=='skus' or ref.get('error'):continue
                refpath=Path(ref['file'])
                if not refpath.is_absolute():refpath=Path(__file__).parent/refpath
                other=sha256(refpath)
                if other!=digest:refs.setdefault(other,ref)
            item={'id':'FULL_'+image['kind'].upper()+'_'+str(image['index']).zfill(3),
                  'image_id':image['kind'].upper()+'_'+str(image['index']).zfill(3),'pool':image['kind'],
                  'index':image['index'],'local':str(path),'source_url':image['url'],
                  'source_sha256':digest,'evidence_ids':['audit_raw.json']}
            candidate=plan_deletion(directory,item,product,raw_images,inspector,decorated_refs=list(refs.values()))
            if candidate:rows.append(candidate)
        except (OSError,ValueError,KeyError):continue
    proposed_hashes={row['source']['sha256'] for row in rows}
    if len(proposed_hashes)>1:
        # Recheck against the actual retained material, not another poster that
        # the same plan would remove. Keep both sets of observations as evidence.
        confirmed=[]
        for row in rows:
            target=row['target']
            image=next(r for r in raw_images if r.get('kind')==target['pool'] and r.get('index')==target['index'] and r.get('source')!='skus')
            refs={}
            for ref in raw_images:
                if ref.get('kind') not in {'main','detail','sku'} or ref.get('source')=='skus' or ref.get('error'):continue
                path=Path(ref['file'])
                if not path.is_absolute():path=Path(__file__).parent/path
                digest=sha256(path)
                if digest not in proposed_hashes:refs.setdefault(digest,ref)
            item={'id':row['item_id'],'image_id':target['image_id'],'pool':target['pool'],'index':target['index'],
                  'local':image['file'],'source_url':image['url'],'source_sha256':row['source']['sha256'],'evidence_ids':['audit_raw.json']}
            candidate=plan_deletion(directory,item,product,raw_images,inspector,decorated_refs=list(refs.values()))
            if candidate:confirmed.append(candidate)
        rows=confirmed
    return rows


def validated_composite_deletion(directory,row):
    if row.get('action')!='DELETE_REDUNDANT' or row.get('validation_scope',{}).get('type')!='AUTHORIZED_DECORATED_COMPOSITE_REMOVAL':return False
    path=Path(directory)/'deletion_validation.json'
    if not path.is_file():return False
    proposed={k:v for k,v in row.items() if k not in {'decision','automation_policy_sha256'}}
    for proof in json.loads(path.read_text(encoding='utf-8')).get('items',[]):
        observed=proof.get('observation',{})
        if proof.get('candidate')==proposed and observed.get('ok') is True and observed.get('decorated_composite') is True and observed.get('retained_packaging_verified') is True:return True
    return False


def plan_main_cleanup(directory,product,raw_images,inspector,existing=(),enabled=False):
    """Global count/retention decision. Hash equality proposes, never authorizes."""
    urls=(product.get('images') or {}).get('main') or []
    if len(urls)<=6:return list(existing)
    root=Path(directory)
    old_deletes=[r for r in existing if r.get('action')=='DELETE_REDUNDANT' and r.get('target',{}).get('pool')=='main']
    others=[r for r in existing if r not in old_deletes]
    occupied={r.get('target',{}).get('index') for r in existing if r.get('target',{}).get('pool')=='main' and r.get('action')!='WEB_DEFER'}
    references={s.get('skuImageUrl') or s.get('imageUrl') or s.get('image') for s in product.get('skus',[]) if isinstance(s,dict)}
    references.update((product.get('images') or {}).get('sku',[]));references.discard(None)
    groups={};sources=[];findings=[];candidates=[]
    for index,url in enumerate(urls):
        matches=[r for r in raw_images if r.get('kind')=='main' and r.get('index')==index and r.get('source')!='skus' and r.get('url')==url and not r.get('error')]
        try:
            if len(matches)!=1:raise ValueError('SOURCE_NOT_UNIQUELY_BOUND')
            row=matches[0];path=Path(row['file'])
            if not path.is_absolute():path=Path(__file__).parent/path
            digest=sha256(path)
            if row.get('content_sha256') not in (None,digest):raise ValueError('SOURCE_SHA_CHANGED')
            groups.setdefault(digest,[]).append(row)
            sources.append({'pool':'main','index':index,'url':url,'sha256':digest})
        except (OSError,KeyError,ValueError) as exc:findings.append({'index':index,'reason':str(exc)})
    if enabled:
        for digest,members in groups.items():
            available=[r for r in members if r['index'] not in occupied]
            if len(available)<2:continue
            keep=min(available,key=lambda r:(r['url'] not in references,r['index']))
            for row in available:
                if row['index']==keep['index']:continue
                if row['url'] in references and row['url']!=keep['url']:
                    findings.append({'index':row['index'],'reason':'SKU_REFERENCED_URL_PRESERVED'});continue
                item={'id':'DUP_MAIN_'+str(row['index']).zfill(3),'image_id':'MAIN_'+str(row['index']).zfill(3),
                      'pool':'main','index':row['index'],'source_url':row['url'],'source_sha256':digest,
                      'local':row['file'],'evidence_ids':['audit_raw.json']}
                candidate=plan_deletion(root,item,product,raw_images,inspector,comparison=keep)
                if candidate:candidates.append(candidate)
                else:findings.append({'index':row['index'],'reason':'INDEPENDENT_DUPLICATE_REVIEW_NOT_PASSED'})
    selected=old_deletes+candidates
    deleted={r['target']['index'] for r in selected}
    retained=[i for i in range(len(urls)) if i not in deleted]
    # A retained comparison or referenced URL must remain. A partial set of
    # deletes that still leaves >6 images is not an executable global solution.
    retained_urls={urls[i] for i in retained}
    valid=enabled and 1<=len(retained)<=6 and all(
        urls[i] not in references or urls[i] in retained_urls for i in deleted)
    if not valid:selected=[];deleted=set();retained=list(range(len(urls)))
    report={'schema':'main-cleanup/v1.3','original_count':len(urls),'required_deletions':len(urls)-6,
            'exact_duplicate_groups':[[r['index'] for r in group] for group in groups.values() if len(group)>1],
            'sources':sources,'sku_reference_urls':sorted(references),'findings':findings,
            'selected_delete_indices':sorted(deleted),'retained_main_indices':retained,
            'decision':'AUTO_CONDITIONAL' if valid else 'DEFERRED','enabled':bool(enabled),
            'reason':'GLOBAL_RETAINED_CONTENT_AND_INDEPENDENT_REVIEW' if valid else 'NO_COMPLETE_AUTHORIZED_SAFE_GLOBAL_SOLUTION'}
    atomic_json(root/'main_cleanup.json',report)
    if not valid:others.append({'remedy_id':'MAIN_CLEANUP_DEFER','item_id':'MAIN_CLEANUP_DEFER','action':'WEB_DEFER',
                               'target':{},'source':{},'checks':{},'evidence_ids':['main_cleanup.json'],
                               'reason_codes':[report['reason']]})
    return others+selected
