# 注意：本文件是 ae-img-audit/livechk24.py 的通用副本，运行依赖同目录的 site_client.py。
# 项目专属的重型工具（pipeline.py 的 scan/apply/verify/OCR 判据库）不在 skill 里。
# -*- coding: utf-8 -*-
"""写回后线上复检：4 件全部图片 OCR"""
import sys, os, json, urllib.request; sys.path.insert(0,'.'); sys.stdout.reconfigure(encoding='utf-8')
import cv2, numpy as np
from rapidocr_onnxruntime import RapidOCR
from site_client import Site, UA
Site.instance=Site(); s=Site.instance
r=RapidOCR()
WMPAT=('store','products','transformers','genuine','aliexpress','dp robot','dprobot')
def fetch(u):
    req=urllib.request.Request(u,headers={'User-Agent':UA})
    raw=urllib.request.urlopen(req,timeout=90).read()
    return cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
os.makedirs('work/wm24b/live',exist_ok=True)
tot=0; hits=[]
for pid in (4835,4864,4867,4868):
    p=s.product(pid); print(pid,p.get('status'),{k:len(v or []) for k,v in p['images'].items() if v})
    for kind in ('main','detail','sku','ai','scene'):
        for i,u in enumerate(p['images'].get(kind) or []):
            b=fetch(u); tot+=1
            h,w=b.shape[:2]
            big=cv2.resize(b,(w*2,h*2),interpolation=cv2.INTER_CUBIC)
            res,_=r(big); hit=[]
            for box,t,c in (res or []):
                if c>0.30 and any(k in t.lower().replace(' ','') for k in WMPAT): hit.append((t,round(float(c),2)))
            cv2.imwrite('work/wm24b/live/%d_%s_%d.png'%(pid,kind,i),b)
            if hit: hits.append((pid,kind,i,hit)); print('   !! %s[%d] %s'%(kind,i,hit))
print('检查图数',tot,'命中',len(hits))
json.dump(hits,open('work/wm24b/live_hits.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
