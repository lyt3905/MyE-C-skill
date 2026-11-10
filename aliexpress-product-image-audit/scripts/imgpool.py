# 注意：本文件是 ae-img-audit/imgpool.py 的通用副本，运行依赖同目录的 site_client.py。
# 项目专属的重型工具（pipeline.py 的 scan/apply/verify/OCR 判据库）不在 skill 里。
# -*- coding: utf-8 -*-
"""本地官方图池（不联网的换源来源，SOP §9.2）。

思路：我们为了找官方图，历史上下载过上千张干净图（web/web2/src/fixed/up/detail 目录）。
把这些图建成 pHash 索引后，同款商品再遇到「水印图需要换源」时，先查本地池命中就换 —— 不用联网、
不用等 finder 跑 10 分钟；池里没有才登记 WEB_DEFER 等用户批准搜网。

用法：
    python imgpool.py build                 # 增量入库（默认目录集）
    python imgpool.py build --dirs "work/pp_4755/web,work/src*"
    python imgpool.py stat
    python imgpool.py find work/pp_4758/imgs/main_4.img --max 12

口径（重要）：
  * 默认**只收外部下载/官方渠道/人工裁好的图**，不收 work/pp_*/imgs（那是站内原图，可能自带水印，
    命中后等于「拿带水印的图换带水印的图」）。
  * 文件名含 mask/resid/wm_ 的中间产物不收。
  * 长边 < 600 的图不收（速卖通主图要求 >=800，太小没意义）。
"""
import os, sys, json, glob, time

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
IDX = os.path.join(ROOT, "work", "imgpool", "index.json")
EXTS = (".jpg", ".jpeg", ".png", ".webp", ".img", ".bmp")

DEFAULT_DIRS = [
    "work/*/web", "work/*/web2", "work/src*", "work/fixed*", "work/up*",
    "work/detail*", "work/review*/web*", "work/pool*", "work/*/pool", "work/*/web*/cand*",
]
SKIP_SUB = ("mask", "resid", "residcheck", "wm", "wm_out", "vlbench", "sweep")
BAD_NAME = ("mask", "resid", "_wm", "wm_", "sheet", "montage", "check_main", "before_after")


def _phash(gray):
    g = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    d = cv2.dct(g)[:8, :8]
    med = np.median(d[1:, 1:])
    v = 0
    for b in (d > med).flatten():
        v = (v << 1) | int(bool(b))
    return "%016x" % v


def _ham(a, b):
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def _load():
    try:
        return json.load(open(IDX, encoding="utf-8"))
    except Exception:
        return {"updated": None, "items": []}


def _save(o):
    os.makedirs(os.path.dirname(IDX), exist_ok=True)
    o["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    json.dump(o, open(IDX, "w", encoding="utf-8"), ensure_ascii=False, indent=0)


def _cand_files(dirs, min_side=600):
    out = []
    for d in dirs:
        for p in glob.glob(os.path.join(ROOT, d)):
            base = os.path.basename(p.rstrip("\\/"))
            if any(s in p.replace("/", "\\").lower() for s in SKIP_SUB):
                continue
            for f in glob.glob(os.path.join(p, "*")):
                if not f.lower().endswith(EXTS):
                    continue
                fn = os.path.basename(f).lower()
                if any(b in fn for b in BAD_NAME):
                    continue
                out.append(f)
    return out


def build(dirs=None, verbose=True):
    pats = dirs or DEFAULT_DIRS
    o = _load()
    have = {it["file"] for it in o["items"]}
    files = _cand_files(pats)
    t0 = time.time()
    add = skip = small = bad = 0
    for f in files:
        rel = os.path.relpath(f, ROOT)
        if rel in have:
            skip += 1
            continue
        img = cv2.imdecode(np.fromfile(f, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is None or img.size == 0:
            bad += 1
            continue
        h, w = img.shape[:2]
        if max(w, h) < 600:
            small += 1
            continue
        o["items"].append({"file": rel, "phash": _phash(img), "w": w, "h": h,
                           "dir": os.path.dirname(rel)})
        have.add(rel)
        add += 1
        if verbose and add % 200 == 0:
            print("  ... %d 张（%.0fs）" % (add, time.time() - t0))
    _save(o)
    if verbose:
        print("[imgpool] 新增 %d，已有跳过 %d，太小 %d，坏图 %d，共 %d 张（%.1fs）"
              % (add, skip, small, bad, len(o["items"]), time.time() - t0))
    return o


def stat(verbose=True):
    o = _load()
    by = {}
    for it in o["items"]:
        by[it["dir"]] = by.get(it["dir"], 0) + 1
    if verbose:
        print("[imgpool] %d 张（更新 %s）" % (len(o["items"]), o.get("updated")))
        for k, v in sorted(by.items(), key=lambda kv: -kv[1]):
            print("  %-44s %d" % (k, v))
    return o


def find_phash(fp, max_dist=10, min_side=0):
    """给一个 pHash，从本地池里找最近的干净图；命中返回 {file, dist}，否则 None。"""
    o = _load()
    best = None
    for it in o["items"]:
        if min_side and max(it.get("w", 0), it.get("h", 0)) < min_side:
            continue
        try:
            d = _ham(fp, it["phash"])
        except Exception:
            continue
        if best is None or d < best["dist"]:
            best = {"file": os.path.join(ROOT, it["file"]), "dist": d, "w": it["w"], "h": it["h"]}
        if best["dist"] == 0:
            break
    if best and best["dist"] <= max_dist:
        return best
    return None


def main(argv):
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    cmd = argv[1] if len(argv) > 1 else "stat"
    if cmd == "build":
        dirs = None
        if "--dirs" in argv:
            dirs = [x.strip() for x in argv[argv.index("--dirs") + 1].split(",") if x.strip()]
        build(dirs)
    elif cmd == "stat":
        stat()
    elif cmd == "find":
        src = argv[2]
        mx = int(argv[argv.index("--max") + 1]) if "--max" in argv else 12
        if os.path.exists(src):
            img = cv2.imdecode(np.fromfile(src, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise SystemExit("读不出这张图")
            fp = _phash(img)
        else:
            fp = src
        hit = find_phash(fp, max_dist=mx)
        print("[imgpool] %s -> %s" % (fp, hit or "未命中"))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
