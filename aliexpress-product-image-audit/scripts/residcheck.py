# 注意：本文件是 ae-img-audit/residcheck.py 的通用副本，运行依赖同目录的 site_client.py。
# 项目专属的重型工具（pipeline.py 的 scan/apply/verify/OCR 判据库）不在 skill 里。
# -*- coding: utf-8 -*-
"""residcheck.py <pid> [--detail] —— 淡字水印「残差图」体检

原理：半透明淡字水印压在白/灰棚拍背景上，亮度只比背景高 5~20 级，
肉眼在缩略图上几乎看不见，但 L - medianBlur(L,61) 的高通残差里会变成清晰的字形。
产物：work/pp_<pid>/residcheck/{imgN.jpg, resid_montage.jpg}
用法：
  python residcheck.py 4758            # 只看 main
  python residcheck.py 4758 --all      # main + detail
阈值：残差增益 11、尺寸 800 长边、medianBlur 61 是 800px 主图的经验值。
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cv2, numpy as np
from site_client import Site

GAIN = 11
K = 61

def resid(g, size=800):
    h, w = g.shape[:2]
    s = size / float(max(h, w))
    if s < 1:
        g = cv2.resize(g, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
    L = cv2.cvtColor(g, cv2.COLOR_BGR2GRAY).astype(np.float32)
    med = cv2.medianBlur(L.astype(np.uint8), K).astype(np.float32)
    vis = np.clip(128 + (L - med) * GAIN, 0, 255).astype(np.uint8)
    return cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR), float(np.abs(L - med).mean())

def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    pid = sys.argv[1]
    want_detail = "--all" in sys.argv
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work", "pp_%s" % pid, "residcheck")
    os.makedirs(out, exist_ok=True)
    s = Site(); s.login()
    imgs = s.product(pid)["images"]
    tiles, names = [], []
    for kind in (["main", "detail"] if want_detail else ["main"]):
        for i, u in enumerate(imgs.get(kind) or []):
            dst = os.path.join(out, "%s_%02d.jpg" % (kind, i))
            s.download(u, dst)
            g = cv2.imdecode(np.fromfile(dst, dtype=np.uint8), cv2.IMREAD_COLOR)
            if g is None:
                print("!! 无法解码", kind, i); continue
            vis, score = resid(g)
            cv2.putText(vis, "%s%d" % (kind[0], i), (8, 28), 0, 0.9, (0, 0, 255), 2)
            tiles.append(cv2.resize(vis, (400, 400))); names.append((kind, i, round(score, 2)))
    if not tiles:
        print("没有图"); return
    while len(tiles) % 5:
        tiles.append(np.full((400, 400, 3), 255, np.uint8))
    rows = [np.hstack(tiles[i:i + 5]) for i in range(0, len(tiles), 5)]
    mp = os.path.join(out, "resid_montage.jpg")
    cv2.imwrite(mp, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 90])
    print("[resid] %s" % mp)
    print("看图规则：背景上出现成串「字」= 有淡字水印；只剩厂牌 logo（钢铁战魂/METAL SOULS/易玩天明）与产品轮廓 = 干净")
    for n in names:
        print("  %s%d  mean|resid|=%.2f" % (n[0][0], n[1], n[2]))

if __name__ == "__main__":
    main()
