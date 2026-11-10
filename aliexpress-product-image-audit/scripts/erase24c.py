# 注意：本文件是 ae-img-audit/erase24c.py 的通用副本，运行依赖同目录的 site_client.py。
# 项目专属的重型工具（pipeline.py 的 scan/apply/verify/OCR 判据库）不在 skill 里。
# -*- coding: utf-8 -*-
"""对仍有命中的图做迭代修补（最多 4 轮，阈值降到 0.2）"""
import sys, os, json; sys.path.insert(0,'.'); sys.stdout.reconfigure(encoding='utf-8')
import cv2, numpy as np
from rapidocr_onnxruntime import RapidOCR
r=RapidOCR()
WMPAT=('store','products','transformers','genuine','aliexpress','dp robot','dprobot')
def det(b, thr):
    h,w=b.shape[:2]; big=cv2.resize(b,(w*2,h*2),interpolation=cv2.INTER_CUBIC)
    res,_=r(big); out=[]
    for box,t,c in (res or []):
        if c<thr: continue
        if any(k.replace(' ','') in t.lower().replace(' ','') for k in WMPAT):
            xs=[p[0]/2 for p in box]; ys=[p[1]/2 for p in box]
            out.append((int(min(xs)),int(min(ys)),int(max(xs)),int(max(ys)),t,float(c)))
    return out
def fix(b,bx,scale=3,vpad=22,hpad=14,radius=10,wpad=8):
    h,w=b.shape[:2]
    x0=max(0,min(v[0] for v in bx)-hpad); x1=min(w,max(v[2] for v in bx)+hpad)
    y0=max(0,min(v[1] for v in bx)-vpad); y1=min(h,max(v[3] for v in bx)+vpad)
    roi=b[y0:y1,x0:x1].copy(); rh,rw=roi.shape[:2]
    up=cv2.resize(roi,(rw*scale,rh*scale),interpolation=cv2.INTER_CUBIC)
    m=np.zeros((rh*scale,rw*scale),np.uint8)
    for v in bx:
        ax0=max(0,(v[0]-wpad-x0))*scale; ay0=max(0,(v[1]-wpad-y0))*scale
        ax1=min(rw,(v[2]+wpad-x0))*scale; ay1=min(rh,(v[3]+wpad-y0))*scale
        m[ay0:ay1,ax0:ax1]=255
    inp=cv2.inpaint(up,m,radius,cv2.INPAINT_TELEA)
    back=cv2.resize(inp,(rw,rh),interpolation=cv2.INTER_AREA)
    small=np.zeros((rh,rw),np.float32)
    for v in bx:
        ax0=max(0,v[0]-wpad-x0); ay0=max(0,v[1]-wpad-y0); ax1=min(rw,v[2]+wpad-x0); ay1=min(rh,v[3]+wpad-y0)
        small[ay0:ay1,ax0:ax1]=1.0
    a=cv2.GaussianBlur(small,(0,0),1.5)[:,:,None]
    out=b.copy(); out[y0:y1,x0:x1]=(back.astype(np.float32)*a+roi.astype(np.float32)*(1-a)).clip(0,255).astype(np.uint8)
    return out
S=json.load(open('work/wm24b/summary.json',encoding='utf-8'))
for it in S:
    f=it['file']; b=cv2.imread(f)
    for it_no in range(4):
        bx=det(b,0.20)
        if not bx: break
        print(it['tag'],'pass%d 命中 %s'%(it_no+1,[x[4] for x in bx]))
        b=fix(b,bx)
    left=det(b,0.20)
    cv2.imwrite(f,b)
    it['left']=[x[4] for x in left]; it['kb']=os.path.getsize(f)//1024
    if left: print('  !! 仍残留',it['tag'],left)
json.dump(S,open('work/wm24b/summary.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
bad=[x['tag'] for x in S if x['left']]
print('仍有残留:',bad or '无')
