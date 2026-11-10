# 注意：本文件是 ae-img-audit/vlmcheck.py 的通用副本，运行依赖同目录的 site_client.py。
# 项目专属的重型工具（pipeline.py 的 scan/apply/verify/OCR 判据库）不在 skill 里。
# -*- coding: utf-8 -*-
"""视觉大模型水印复核（SOP §W9）：cv 初筛之后的可疑图，交 glm-5v-turbo 首判 + kimi-k3-1 复核。

用法：
    python vlmcheck.py 4758                        # 现行全部图（main+detail+sku）
    python vlmcheck.py 4758 --kind main            # 只看主图
    python vlmcheck.py 4758 --models glm-5v-turbo  # 只跑一个模型（省一半时间）
    python vlmcheck.py --dir work/pp_4758/imgs     # 本地目录（不看站点）

口径（见 SOP §W9，别改）：
  * 只送**原图**，不送残差图（残差图 8/8 -> 6/8）
  * max_tokens=2000（推理型模型 400 会全空）、temperature=0、强制 JSON
  * 只采信「位置 + 有无」；模型给出的店名文字不入库（会幻觉成「异玩天阙」）
  * 左下角厂牌印章（易玩天明 / 钢铁战魂 / METAL SOULS / 铁鼠 MAUS / YW-2611）不算水印，prompt 里已声明
退出码：0 = 跑完（结论看表）；2 = 有 HIT/REVIEW 需要人看。
"""
import os, sys, json, re, time, base64, urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

BASE = os.environ.get("VLM_BASE", "http://127.0.0.1:8788/v1")
KEY = os.environ.get("VLM_API_KEY", "")


def _key():
    k = os.environ.get("VLM_API_KEY")
    if k:
        return k
    try:
        with open(os.path.join(ROOT, "bench_vl2.mjs"), "r", encoding="utf-8") as f:
            m = re.search(r'const KEY = "([0-9a-f]{16,})"', f.read())
            if m:
                return m.group(1)
    except Exception:
        pass
    raise SystemExit("缺 VLM_API_KEY（或 bench_vl2.mjs 里的 KEY）")


PROMPT = "\n".join([
    "这是速卖通(AliExpress)商品图。请判断：图中是否存在**其他卖家店铺**的水印或店铺标识"
    "（别的店铺的店名文字、店铺 logo、印着店名的横幅/边框/角标、微博号/微信号）。",
    "不算水印（不要报）：品牌名、商品型号、厂牌/厂商名、官方宣传文案、正品或授权标识、"
    "商品包装盒上印刷的文字、画面左下角或边缘的厂牌印章（例如 易玩天明 / 钢铁战魂 / METAL SOULS / 铁鼠 MAUS / YW-2611 这类）。",
    '只输出一行 JSON，不要解释：{"watermark": true 或 false, "location": "底部横幅|左下角|右下角|画面中部横贯|整幅重复|边缘角标|无", "text": "你读到的可疑文字，读不出就填空字符串", "confidence": 0到1之间的小数}',
])

LOCS = ("底部横幅", "左下角", "右下角", "画面中部横贯", "整幅重复", "边缘角标", "无")


BOX_PROMPT = "\n".join([
    "这是速卖通商品图。判断这张图的主体是什么：是【商品包装盒/彩盒/纸盒的照片】，还是【商品本体/人形/玩具本身的照片，或用本体排版的宣传图】。",
    "判据：画面主体是一个印刷过的长方体纸盒（能看到盒面图案/厂标/型号印刷）→ box；"
    "画面主体是玩具本体、人形、机器人、道具本体（哪怕背景是白底、哪怕带文字排版）→ figure。",
    '只输出一行 JSON，不要解释：{"kind": "box" 或 "figure", "reason": "10 字以内理由"}',
])


def call(model, b64, retries=2, prompt=None, max_tokens=2000):
    body = json.dumps({
        "model": model,
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt or PROMPT},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
        ]}],
    }).encode("utf-8")
    last = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(BASE + "/chat/completions", data=body, method="POST",
                                        headers={"Authorization": "Bearer " + (KEY or _key()),
                                                 "Content-Type": "application/json"})
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=150) as r:
                j = json.loads(r.read().decode("utf-8", "replace"))
            dt = int((time.time() - t0) * 1000)
            msg = (j.get("choices") or [{}])[0].get("message") or {}
            txt = msg.get("content") or msg.get("reasoning_content") or ""
            return parse_v(txt), dt, txt
        except Exception as e:  # 网络/超时/网关 5xx
            last = str(e)
            time.sleep(1.5)
    return {"wm": None, "loc": "", "text": "", "conf": None}, -1, "ERR " + str(last)


def parse_v(txt):
    m = re.search(r"\{[\s\S]*\}", txt or "")
    if not m:
        return {"wm": None, "loc": "", "text": "", "conf": None}
    try:
        o = json.loads(m.group(0))
    except Exception:
        return {"wm": None, "loc": "", "text": "", "conf": None}
    w = o.get("watermark")
    wm = True if w is True or str(w).lower() == "true" else False if w is False or str(w).lower() == "false" else None
    loc = str(o.get("location") or "")
    if loc and not any(l in loc for l in LOCS):
        loc = loc[:12]
    return {"wm": wm, "loc": loc, "text": str(o.get("text") or "")[:80],
            "conf": float(o["confidence"]) if isinstance(o.get("confidence"), (int, float)) else None}


def verdict(rs):
    """rs = {model: {wm,loc,conf}} -> (判定, 备注)"""
    hits = [m for m, r in rs.items() if r.get("wm") is True and (r.get("conf") or 0) >= 0.5]
    if len(hits) >= 2:
        return "HIT", "两个模型都判有水印"
    if len(hits) == 1:
        return "REVIEW", "%s 判有水印，另一模型不同意" % hits[0]
    if any(r.get("wm") is True for r in rs.values()):
        return "REVIEW", "低置信度有水印"
    return "CLEAN", ""


def kind_of(b64, model="glm-5v-turbo", retries=1):
    """SKU 图是盒照还是本体照 —— 返回 "box" / "figure" / None（判不出或网关不可用）。"""
    try:
        _r, _dt, txt = call(model, b64, retries=retries, prompt=BOX_PROMPT, max_tokens=800)
    except Exception:
        return None
    m = re.search(r"\{[\s\S]*\}", txt or "")
    if m:
        try:
            o = json.loads(m.group(0))
            k = str(o.get("kind") or "").strip().lower()
            if k in ("box", "figure"):
                return k
        except Exception:
            pass
    low = (txt or "").lower()
    if '"box"' in low or low.strip().startswith("box"):
        return "box"
    if '"figure"' in low or low.strip().startswith("figure"):
        return "figure"
    return None


def kind_of_file(path, model="glm-5v-turbo"):
    try:
        import base64
        with open(path, "rb") as f:
            return kind_of(base64.b64encode(f.read()).decode(), model)
    except Exception:
        return None


def fetch_pid(pid, kind=None):
    from site_client import Site
    site = getattr(Site, "instance", None) or Site()
    d = site.product(pid)
    imgs = d.get("images") or {}
    out = []
    dst_dir = os.path.join(ROOT, "work", "pp_%s" % pid, "vlm")
    os.makedirs(dst_dir, exist_ok=True)
    for k in ("main", "detail", "sku"):
        if kind and k != kind:
            continue
        for i, u in enumerate(imgs.get(k) or []):
            if not isinstance(u, str) or not u:
                continue
            dst = os.path.join(dst_dir, "%s_%d.img" % (k, i))
            try:
                if not (os.path.exists(dst) and os.path.getsize(dst) > 1024):
                    site.download(u, dst)
                out.append(("%s_%d" % (k, i), dst, u))
            except Exception as e:
                print("[warn] 下载失败 %s_%d: %s" % (k, i, e))
    return out, dst_dir


def fetch_dir(d):
    out = []
    EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".img")
    for f in sorted(os.listdir(d)):
        p = os.path.join(d, f)
        if os.path.isfile(p) and f.lower().endswith(EXTS) and os.path.getsize(p) > 1024:
            out.append((os.path.splitext(f)[0], p, ""))
    return out, d


def main(argv):
    pid = None
    kind = None
    d = None
    pids = None
    models = ["glm-5v-turbo", "kimi-k3-1"]
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--dir":
            d = argv[i + 1]; i += 2
        elif a == "--kind":
            kind = argv[i + 1]; i += 2
        elif a == "--models":
            models = [m.strip() for m in argv[i + 1].split(",") if m.strip()]; i += 2
        elif a == "--pids":
            pids = [x.strip() for x in argv[i + 1].split(",") if x.strip()]; i += 2
        elif a == "--limit":
            globals()["LIMIT"] = int(argv[i + 1]); i += 2
        else:
            pid = a; i += 1
    if not KEY:
        globals()["KEY"] = _key()
    if d:
        items, outdir = fetch_dir(d)
        tag = os.path.basename(d.rstrip("\\/"))
    elif pids:
        items, outdir = [], os.path.join(ROOT, "work", "vlm_batch")
        os.makedirs(outdir, exist_ok=True)
        t_f = time.time()
        for p in pids:
            its, _od = fetch_pid(p, kind)
            items += [("%s:%s" % (p, n), path, url) for n, path, url in its]
        tag = "batch%d" % len(pids)
        print("[batch] %d 件 / %d 张取图 %.1fs（下载串行，判定并发）" % (len(pids), len(items), time.time() - t_f))
    elif pid:
        items, outdir = fetch_pid(pid, kind)
        tag = "pp_%s" % pid
    else:
        raise SystemExit(__doc__)
    lim = globals().get("LIMIT")
    if lim:
        items = items[:lim]
    print("items=%d models=%s base=%s" % (len(items), ",".join(models), BASE))

    jobs = []
    for name, path, url in items:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        for m in models:
            jobs.append((name, m, b64, path))
    t0 = time.time()
    res = {}
    nw = 8 if pids else 4
    with ThreadPoolExecutor(max_workers=nw) as ex:
        futs = {ex.submit(call, m, b64): (name, m) for name, m, b64, _ in jobs}
        for fut in futs:
            name, m = futs[fut]
            r, dt, raw = fut.result()
            r["ms"] = dt
            res.setdefault(name, {})[m] = r
            res[name]["_raw_" + m] = raw[:600]

    rows, need = [], []
    for name, path, url in items:
        rs = {m: res[name][m] for m in models}
        v, why = verdict(rs)
        if v != "CLEAN":
            need.append(name)
        rows.append({"tag": name, "pid": name.split(":")[0] if ":" in name else "",
                     "verdict": v, "why": why, "file": path, "url": url,
                     "models": {m: {k: rs[m][k] for k in ("wm", "loc", "text", "conf", "ms")} for m in models}})
    print("\n%-10s %-7s %-30s %s" % ("图", "判定", "模型结论", "位置/文字"))
    for r in rows:
        brief = " | ".join("%s:%s" % (m, "Y" if r["models"][m]["wm"] else "n" if r["models"][m]["wm"] is False else "?")
                            for m in models)
        ev = " ".join("%s/%s" % (r["models"][m]["loc"], r["models"][m]["text"][:26]) for m in models)
        print("%-10s %-7s %-30s %s" % (r["tag"], r["verdict"], brief, ev[:90]))

    rep = {"tag": tag, "models": models, "elapsed_s": round(time.time() - t0, 1), "rows": rows}
    rp = os.path.join(outdir, "vlm_report.json")
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    n = len(rows)
    print("\n==== 汇总：%d 张 | CLEAN %d / REVIEW %d / HIT %d | %.1fs ====" % (
        n, sum(1 for r in rows if r["verdict"] == "CLEAN"),
        sum(1 for r in rows if r["verdict"] == "REVIEW"),
        sum(1 for r in rows if r["verdict"] == "HIT"), time.time() - t0))
    if need:
        print("需要人看残差图: " + ", ".join(need))
    print("报告: " + rp)
    return 2 if need else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
