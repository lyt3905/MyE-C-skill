"""A clean result requires actual byte evidence for every referenced source URL."""
from pathlib import Path
from PIL import Image
from mye_c_automation.audit_one import _image_urls
from mye_c_automation.candidate_quality import sha256
from mye_c_automation.job_manager import atomic_json

def verify_sources(directory,product,images):
    required={r['url'] for r in _image_urls(product)}
    audited=set();files=[];errors=[]
    for row in images:
        if row.get('error'):continue
        try:
            path=Path(row['file'])
            if not path.is_absolute():path=Path(__file__).parent/path
            digest=sha256(path)
            if row.get('content_sha256') not in (None,digest):raise ValueError('SOURCE_SHA_CHANGED')
            with Image.open(path) as image:
                image.verify();width,height=image.size
                if min(width,height)<800:raise ValueError('LEGACY_SMALL_IMAGE')
            audited.add(row['url'])
            files.append({'path':str(path.resolve()),'sha256':digest,'url':row['url'],'pool':row.get('kind'),'index':row.get('index'),'width':width,'height':height})
        except Exception as exc:errors.append({'url':row.get('url'),'reason':type(exc).__name__+': '+str(exc)})
    missing=sorted(required-audited)
    result={'ok':not missing and not errors,'required_urls':sorted(required),'missing_urls':missing,'errors':errors,'files':files}
    atomic_json(Path(directory)/'mye_c_automation.audit_coverage.json',result)
    return result

def complete_readonly(directory,job,reader=None):
    import json
    from mye_c_automation.product_state import canonical_state_hash
    from mye_c_automation.executor.service import ExecutorService
    root=Path(directory)
    read=lambda name:json.loads((root/name).read_text(encoding='utf-8'))
    before=read('before.json');coverage=read('mye_c_automation.audit_coverage.json');plan=read('plan.v2.json')
    if not coverage['ok']:raise ValueError('AUDIT_COVERAGE_INCOMPLETE')
    if reader is not None:
        current=reader.product(job['pid']);ExecutorService(None,reader,root)._identity(current,plan)
        if canonical_state_hash(current)!=canonical_state_hash(before):raise ValueError('STATE_DRIFT_AFTER_READONLY_AUDIT')
    items=[{'image_id':str(r['pool']).upper()+'_'+str(r['index']).zfill(3),'url':r['url'],'source_sha256':r['sha256'],'candidate_sha256':r['sha256'],'ok':True} for r in coverage['files']]
    content={'ok':True,'read_only':True,'scope':'unchanged_audited_sources','items':items}
    atomic_json(root/'expected_after.json',before);atomic_json(root/'after.json',before)
    atomic_json(root/'content_validation.json',content)
    atomic_json(root/'verification.json',{'ok':True,'read_only':True,'source_state_sha256':canonical_state_hash(before),'content_validation':content})
    return content
