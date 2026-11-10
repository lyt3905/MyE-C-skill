# 注意：本文件是 ae-img-audit/live26.py 的通用副本，运行依赖同目录的 site_client.py。
# 项目专属的重型工具（pipeline.py 的 scan/apply/verify/OCR 判据库）不在 skill 里。
# -*- coding: utf-8 -*-
"""终检：拉线上主图/详情图，OCR 扫店名与促销字（自家 PureSun 横幅除外）。"""
import sys, os, json, re, urllib.request
sys.path.insert(0,'.'); sys.stdout.reconfigure(encoding='utf-8')
import cv2, numpy as np
from concurrent.futures import ThreadPoolExecutor
from rapidocr_onnxruntime import RapidOCR
from site_client import Site, UA
Site.instance=Site(); s=Site.instance
KW=re.compile(r'store|shop|aliexpress|alibaba|seller|contact|wholesale|taobao|1688|淘宝|批发|微店|preorder|pre-order|exclusive|custom made|coupon|元', re.I)
OUT='work/reingest/live26'; os.makedirs(OUT,exist_ok=True)
IDS=[4847,4848,4849,4850,4851,4852,4853,4854,4855,4856,4857,4858,4859,4860,4861,4862,4863,4864,4865,4866,4867,4868,4869,4870,4871,4872]
jobs=[]
for pid in IDS:
    p=s.product(pid)
    for kind in ('main','detail','sku'):
        for i,u in enumerate(p['images'].get(kind) or []):
            jobs.append((pid,kind,i,u))
print('images', len(jobs), flush=True)
def dl(j):
    pid,kind,i,u=j
    f=os.path.join(OUT,'%d_%s_%d.jpg'%(pid,kind,i))
    if not (os.path.exists(f) and os.path.getsize(f)>1000):
        try:
            req=urllib.request.Request(u, headers={'User-Agent':UA})
            data=urllib.request.urlopen(req, timeout=60).read()
            open(f,'wb').write(data)
        except Exception as e:
            return (pid,kind,i,None,'DLERR '+str(e)[:40])
    b=cv2.imdecode(np.fromfile(f,dtype=np.uint8),cv2.IMREAD_COLOR)
    return (pid,kind,i,b,'')
_ocr=None
def ocr():
    global _ocr
    if _ocr is None: _ocr=RapidOCR()
    return _ocr
def scan(r):
    pid,kind,i,b,err=r
    if b is None: return (pid,kind,i,err)
    h,w=b.shape[:2]
    sc=min(2.0, 1000.0/max(h,w))
    if sc>1.0: b=cv2.resize(b,(int(w*sc),int(h*sc)),interpolation=cv2.INTER_CUBIC)
    try: res,_=ocr()(b)
    except Exception as e: return (pid,kind,i,'OCRERR '+str(e)[:40])
    hits=[t for box,t,c in (res or []) if c>0.6 and KW.search(t)]
    hits=[t for t in hits if 'PureSun' not in t]
    return (pid,kind,i,' | '.join(hits) if hits else '')
with ThreadPoolExecutor(max_workers=6) as ex:
    res=list(ex.map(lambda j: scan(dl(j)), jobs))
bad=[r for r in res if r[3]]
print('scanned %d, hits %d' % (len(res), len(bad)))
for pid,kind,i,h in sorted(bad): print('%-5d %-6s %d  %s' % (pid,kind,i,h[:100]))
json.dump([{'pid':r[0],'kind':r[1],'i':r[2],'hit':r[3]} for r in res], open('work/reingest/livecheck26.json','w',encoding='utf-8'), ensure_ascii=False, indent=1)