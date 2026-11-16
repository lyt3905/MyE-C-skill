"""Fake independently validated bytes for narrow compiler-unit fixtures."""
from pathlib import Path
from PIL import Image
from mye_c_automation.job_manager import atomic_json
from mye_c_automation.candidate_quality import sha256
from mye_c_automation.product_state import canonical_state_hash

def bind_image(root,product,row):
    root=Path(root);raw=[]
    for pool,urls in product['images'].items():
        for index,url in enumerate(urls):
            path=root/(pool+str(index)+'.png');Image.new('RGB',(800,800),'white').save(path)
            raw.append({'kind':pool,'index':index,'url':url,'file':str(path),'content_sha256':sha256(path)})
    atomic_json(root/'audit_raw.json',{'images':raw})
    original=next(r for r in raw if r['kind']==row['target']['pool'] and r['index']==row['target']['index'])
    source=next(r for r in raw if r['url']==row['source']['url'])
    row['source']['sha256']=source['content_sha256']
    atomic_json(root/'mye_c_automation.candidate_quality.json',{'items':[{'item_id':row['item_id'],'action':row['action'],'ok':True,'source_sha256':original['content_sha256'],'candidate_sha256':source['content_sha256'],'evidence_ids':row['evidence_ids'],'checks':row['checks']}]})

def bind_semantic(root,product,row):
    row['source']['sha256']=canonical_state_hash(product)
    atomic_json(Path(root)/'semantic_validation.json',{'source_product_sha256':canonical_state_hash(product),'candidates':[row]})
