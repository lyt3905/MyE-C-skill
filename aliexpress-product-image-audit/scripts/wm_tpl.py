# 注意：本文件是 ae-img-audit/wm_tpl.py 的通用副本，运行依赖同目录的 site_client.py。
# 项目专属的重型工具（pipeline.py 的 scan/apply/verify/OCR 判据库）不在 skill 里。
# -*- coding: utf-8 -*-
"""Store-watermark template scan (for the wide faint store-name class).

Build a template from ONE known-watermarked image, then screen a batch.
Template = high-pass residual patch of a single glyph (e.g. the leading letter that
sticks out at the left edge).

  python wm_tpl.py build  <known_bad.jpg> <x0> <y0> <x1> <y1>  -> work/wm_tpl.npy
  python wm_tpl.py scan   <dir_or_files...>                  -> per-image max NCC

Decision: >=0.80 = hit, <=0.65 = clean. Flat areas are excluded (zero-variance patches
otherwise score a degenerate 1.0). ~20 ms per 800x800 image, single core.
"""
import sys, os
import numpy as np, cv2

TPL = "work/wm_tpl.npy"
STD_FLOOR = 2.0

def resid(path):
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return g - cv2.GaussianBlur(g, (0, 0), 25)

def build(path, x0, y0, x1, y1):
    r = resid(path)
    tpl = r[int(y0):int(y1), int(x0):int(x1)]
    np.save(TPL, tpl)
    print("template", tpl.shape, "std %.2f" % tpl.std(), "->", TPL)

def scan(path, tpl):
    r = resid(path)
    if r is None or r.shape[0] < tpl.shape[0] or r.shape[1] < tpl.shape[1]:
        return None
    th, tw = tpl.shape
    res = cv2.matchTemplate(r, tpl, cv2.TM_CCOEFF_NORMED)
    k = np.ones((th, tw), np.float32) / (th * tw)
    m = cv2.filter2D(r, -1, k, borderType=cv2.BORDER_REPLICATE)
    m2 = cv2.filter2D(r * r, -1, k, borderType=cv2.BORDER_REPLICATE)
    sd = np.sqrt(np.maximum(m2 - m * m, 0))[:res.shape[0], :res.shape[1]]
    res = np.where(sd >= STD_FLOOR, res, -1.0)
    return float(res.max())

def main(argv):
    if not argv:
        print(__doc__); return
    if argv[0] == "build":
        build(argv[1], *argv[2:6]); return
    tpl = np.load(TPL)
    files = []
    for a in argv[1:]:
        if os.path.isdir(a):
            files += [os.path.join(a, f) for f in sorted(os.listdir(a))
                      if f.lower().endswith((".jpg", ".png", ".jpeg", ".webp", ".img"))]
        else:
            files.append(a)
    hits = 0
    for f in files:
        s = scan(f, tpl)
        tag = "CLEAN" if (s is None or s < 0.65) else ("HIT" if s >= 0.80 else "SUSPECT")
        if tag != "CLEAN":
            hits += 1
        print("%-40s %s  NCC=%s" % (os.path.basename(f), tag, "n/a" if s is None else "%.3f" % s))
    print("-- %d files, %d flagged" % (len(files), hits))

if __name__ == "__main__":
    main(sys.argv[1:])
