# 注意：本文件是 ae-img-audit/erase24b.py 的通用副本，运行依赖同目录的 site_client.py。
# 项目专属的重型工具（pipeline.py 的 scan/apply/verify/OCR 判据库）不在 skill 里。
# -*- coding: utf-8 -*-
"""v2：只在文字矩形 ROI 内做 3x 超分修补，ROI 外像素保持原样（输出无损 PNG）"""
import sys, os, re, json, urllib.request, traceback; sys.path.insert(0,'.'); sys.stdout.reconfigure(encoding='utf-8')
import cv2, numpy as np
from rapidocr_onnxruntime import RapidOCR
r=RapidOCR()
WMPAT=('store','products','transformers','genuine','aliexpress','dp robot','dprobot')
os.makedirs('work/wm24b/out',exist_ok=True)
def det(b, thr=0.30):
    h,w=b.shape[:2]; big=cv2.resize(b,(w*2,h*2),interpolation=cv2.INTER_CUBIC)
    res,_=r(big); out=[]
    for box,t,c in (res or []):
        if c<thr: continue
        if any(k.replace(' ','') in t.lower().replace(' ','') for k in WMPAT):
            xs=[p[0]/2 for p in box]; ys=[p[1]/2 for p in box]
            out.append((int(min(xs)),int(min(ys)),int(max(xs)),int(max(ys)),t))
    return out
def fix(b, bx, scale=3, pad=4, vpad=18, hpad=10, radius=9):
    h,w=b.shape[:2]
    x0=max(0,min(v[0] for v in bx)-hpad); x1=min(w,max(v[2] for v in bx)+hpad)
    y0=max(0,min(v[1] for v in bx)-vpad); y1=min(h,max(v[3] for v in bx)+vpad)
    roi=b[y0:y1,x0:x1].copy(); rh,rw=roi.shape[:2]
    up=cv2.resize(roi,(rw*scale,rh*scale),interpolation=cv2.INTER_CUBIC)
    m=np.zeros((rh*scale,rw*scale),np.uint8)
    for v in bx:
        ax0=max(0,(v[0]-pad-x0))*scale; ay0=max(0,(v[1]-pad-y0))*scale
        ax1=min(rw,(v[2]+pad-x0))*scale; ay1=min(rh,(v[3]+pad-y0))*scale
        m[ay0:ay1, ax0:ax1]=255
    inp=cv2.inpaint(up,m,radius,cv2.INPAINT_TELEA)
    back=cv2.resize(inp,(rw,rh),interpolation=cv2.INTER_AREA)
    # 羽化：只把 ROI 内 mask 覆盖处及边缘 2px 混入
    small=np.zeros((rh,rw),np.float32)
    for v in bx:
        ax0=max(0,v[0]-pad-x0); ay0=max(0,v[1]-pad-y0); ax1=min(rw,v[2]+pad-x0); ay1=min(rh,v[3]+pad-y0)
        small[ay0:ay1,ax0:ax1]=1.0
    a=cv2.GaussianBlur(small,(0,0),1.2)[:,:,None]
    out=b.copy(); out[y0:y1,x0:x1]=(back.astype(np.float32)*a+roi.astype(np.float32)*(1-a)).clip(0,255).astype(np.uint8)
    return out,(x0,y0,x1,y1)
S=json.load(open('work/wm24/summary.json',encoding='utf-8'))
rep=[]
for it in S:
    try:
        b=cv2.imread('work/wm24/src/%s.png'%it['tag'])
        bx=det(b)
        if not bx: print(it['tag'],'重新检测无命中'); continue
        out,roi=fix(b,bx)
        left=det(out)
        f='work/wm24b/out/%s.png'%it['tag']
        cv2.imwrite(f,out)
        d=cv2.absdiff(b,out).max(axis=2)
        ys=slice(roi[1],roi[3]); xs=slice(roi[0],roi[2])
        outside=int(np.delete(np.delete(d,range(roi[1],roi[3]),0),range(roi[0],roi[2]),1).max())
        kb=os.path.getsize(f)//1024
        print('%-16s roi=%dx%d outside=%d %dKB 复查=%s'%(it['tag'],roi[2]-roi[0],roi[3]-roi[1],outside,kb,[x[4] for x in left] or '干净'),flush=True)
        rep.append({'tag':it['tag'],'pid':it['pid'],'kind':it['kind'],'i':it['i'],'file':f,'roi':roi,'left':[x[4] for x in left],'kb':kb})
    except Exception:
        traceback.print_exc()
json.dump(rep,open('work/wm24b/summary.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('done',len(rep),'剩余命中',sum(1 for x in rep if x['left']))
