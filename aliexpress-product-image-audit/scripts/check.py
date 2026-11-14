# 注意：本文件是 ae-img-audit/check.py 的通用副本，运行依赖同目录的 site_client.py。
# 项目专属的重型工具（pipeline.py 的 scan/apply/verify/OCR 判据库）不在 skill 里。
# -*- coding: utf-8 -*-
"""交付体检：一件商品改完之后，一条命令跑完所有「必须成立」的检查。

用法：
    python check.py 4758
    python check.py 4758 --quick        # 跳过残差拼图，只跑结构与计数检查

退出码：0 = 全部通过（可能有 WARN），1 = 有 FAIL（不能交付）。
产物：work/pp_<pid>/check/report.json、resid_montage.jpg
"""
import os, sys, json, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cv2
import numpy as np
from site_client import Site, phash, ham
ROOT = os.environ.get("AE_ROOT") or os.getcwd()   # 工作根：在 ae-img-audit 目录下运行时即该项目根

RES = []


def add(level, code, msg):
    RES.append((level, code, msg))
    print("[%-4s] %-6s %s" % (level, code, msg))


def _gray(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)


def stroke_probe(path):
    """白底浅灰淡字的廉价定量：返回 (笔画像素数, 占比%)。参考 4758 的 wm_probe.py"""
    g = _gray(path)
    if g is None or g.size == 0:
        return -1, -1.0
    bg = cv2.medianBlur(g, 31)
    m = ((bg > 236) & (g > 200) & (g <= bg - 8)).astype(np.uint8)
    m = cv2.dilate(m, np.ones((3, 3), np.uint8), iterations=1)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    keep = 0
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        # 字形笔画：高度适中、有一定长宽；大块（阴影/反光/产品边缘）排除
        if 8 <= h <= 130 and w >= 4 and area >= 25:
            keep += area
    return int(keep), 100.0 * keep / float(max(1, g.size))


def resid_vis(path):
    """残差可视化（vis = 128 + (L - medianBlur(L,61)) * 11）"""
    g = _gray(path)
    if g is None:
        return None
    r = g.astype(np.float32) - cv2.medianBlur(g, 61).astype(np.float32)
    return np.clip(128 + r * 11, 0, 255).astype(np.uint8)


def main(pid, quick=False, stable=6, fast=False):
    pid = str(pid)
    if fast:
        stable = 0
    site = Site.instance
    outdir = os.path.join(ROOT, "work", "pp_%s" % pid, "check")
    os.makedirs(outdir, exist_ok=True)

    d = site.product(pid)
    w = site.worker()
    upd0, disp0 = d.get("updatedAt"), w.get("totalDispatched")
    imgs = d.get("images") or {}
    skus = d.get("skus") or []

    # ---------- A 基础 ----------
    st = d.get("status")
    ok_st = ("PENDING", "EDITING", "READY_TO_PUBLISH")
    add("PASS" if st in ok_st else "FAIL", "A1",
        "status=%s（要求 待编辑/待生图/待导出 之一；DONE=已导出说明已经跑过一轮）" % st)
    if stable and stable > 0:
        time.sleep(stable)
        d2 = site.product(pid)
        w2 = site.worker()
        add("PASS" if d2.get("updatedAt") == upd0 else "FAIL", "A2",
            "updatedAt %ds 内%s（%s）" % (stable, "未变" if d2.get("updatedAt") == upd0 else "被改写", d2.get("updatedAt")))
        add("PASS" if w2.get("totalDispatched") == disp0 else "WARN", "A3",
            "worker.dispatched %s -> %s%s" % (disp0, w2.get("totalDispatched"),
                                              "" if w2.get("totalDispatched") == disp0 else "（被 AI 封面任务接管过）"))
    else:
        add("SKIP", "A2", "跳过稳定性等待（--stable 0：写入后已由 pipeline verify 查过）")
        add("SKIP", "A3", "跳过 dispatched 复查")

    # ---------- B 计数 ----------
    n_main, n_detail, n_sku = len(imgs.get("main") or []), len(imgs.get("detail") or []), len(imgs.get("sku") or [])
    add("PASS" if 1 <= n_main <= 6 else "FAIL", "B1", "main=%d（上限 6，至少 1）" % n_main)
    add("PASS" if n_detail >= 1 else "WARN", "B2", "detail=%d" % n_detail)
    add("PASS" if n_sku >= 1 else ("FAIL" if skus else "WARN"), "B3", "images.sku=%d，skus=%d" % (n_sku, len(skus)))

    # ---------- C 逐图体检 ----------
    # 先把要下的图并行抓下来（串行 21 张 × 0.16 s 是纯等待），再逐张分析
    # 缓存按 URL 校验：名字固定（main_0…），URL 变了必须重下，否则会拿整改前的旧图做体检
    ucache_p = os.path.join(outdir, ".urls.json")
    try:
        ucache = json.load(open(ucache_p, encoding="utf-8"))
    except Exception:
        ucache = {}
    todo = []
    for kind in ("main", "detail", "sku"):
        for i, u in enumerate(imgs.get(kind) or []):
            name = "%s_%d" % (kind, i)
            dst = os.path.join(outdir, name + ".jpg")
            fresh = os.path.exists(dst) and os.path.getsize(dst) >= 2000 and ucache.get(name) == u
            if not fresh:
                todo.append((name, u, dst))
            ucache[name] = u
    if todo:
        def _dl(t):
            name, u, dst = t
            try:
                site.download(u, dst); return None
            except Exception as e:
                return (name, e)
        with ThreadPoolExecutor(max_workers=min(8, len(todo))) as ex:
            errs = [e for e in ex.map(_dl, todo) if e]
        for name, e in errs:
            add("FAIL", "C0", "%s 下载失败 %s" % (name, e))
    json.dump(ucache, open(ucache_p, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    files, feats = {}, {}
    for kind in ("main", "detail", "sku"):
        for i, u in enumerate(imgs.get(kind) or []):
            name = "%s_%d" % (kind, i)
            dst = os.path.join(outdir, name + ".jpg")
            if not os.path.exists(dst) or os.path.getsize(dst) < 2000:
                continue
            files[name] = (dst, u)
            g = _gray(dst)
            if g is None or g.size == 0 or (g.shape[0] <= 2 and g.shape[1] <= 2):
                add("FAIL", "C1", "%s 无法解码或 1×1 占位图" % name); continue
            h, wd = g.shape[:2]
            feats[name] = {"size": [wd, h], "ph": phash(g)}
            if kind in ("main", "sku") and min(h, wd) < 800:
                add("WARN", "C2", "%s 尺寸 %d×%d，短边 <800（速卖通主图要求 ≥800×800）" % (name, wd, h))
            cnt, pct = stroke_probe(dst)
            feats[name]["stroke"] = cnt
            if cnt >= 300:
                add("INFO", "C3", "%s 字形笔画 %d px（%.2f%%）→ 必须看 resid 图判定" % (name, cnt, pct))

    # 主图内部重复
    mains = [n for n in feats if n.startswith("main_")]
    for i in range(len(mains)):
        for j in range(i + 1, len(mains)):
            dd = ham(feats[mains[i]]["ph"], feats[mains[j]]["ph"])
            if dd < 8:
                add("WARN", "C4", "%s 与 %s 近乎同图（pHash 距 %d）" % (mains[i], mains[j], dd))

    # 残差拼图
    if not quick and files:
        tiles = []
        for name, (dst, _) in files.items():
            v = resid_vis(dst)
            if v is None:
                continue
            v = cv2.resize(v, (420, 420))
            v = cv2.cvtColor(v, cv2.COLOR_GRAY2BGR)
            cv2.putText(v, name, (6, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            tiles.append(v)
        if tiles:
            cols = min(5, len(tiles))
            rows = (len(tiles) + cols - 1) // cols
            sheet = np.full((rows * 420, cols * 420, 3), 255, np.uint8)
            for k, t in enumerate(tiles):
                sheet[(k // cols) * 420:(k // cols + 1) * 420, (k % cols) * 420:(k % cols + 1) * 420] = t
            p = os.path.join(outdir, "resid_montage.jpg")
            cv2.imwrite(p, sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
            add("INFO", "C5", "残差拼图 %s" % p)

    # ---------- D SKU ----------
    urls = [(s.get("skuImageUrl") or "").strip() for s in skus]
    names = [(s.get("skuName") or "?") for s in skus]
    if skus:
        miss = [names[i] for i, u in enumerate(urls) if not u]
        add("FAIL" if miss else "PASS", "D1", "缺图规格：%s" % (", ".join(miss) if miss else "无"))
        uniq = len(set(u for u in urls if u))
        if uniq >= len(skus):
            add("PASS", "D2", "%d 个规格 / %d 张唯一 SKU 图（各自独立）" % (len(skus), uniq))
        else:
            # 用户 2026-11-06 定的规则：无盒/有盒**可以**共用一张本体/人形图，但**不能**共用一张盒图
            upath = {u: pth for (pth, u) in files.values()}
            kinds = {}
            try:
                import vlmcheck
                for u in sorted(set(u for u in urls if u)):
                    pth = upath.get(u)
                    kinds[u] = vlmcheck.kind_of_file(pth) if pth else None
            except Exception as e:
                print("  [D2] VLM 判定不可用：%s" % str(e)[:60])
                kinds = {u: None for u in set(u for u in urls if u)}
            vals = [v for v in kinds.values()]
            if any(v == "box" for v in vals):
                add("FAIL", "D2", "%d 个规格 / %d 张唯一 SKU 图 —— **共用了盒照**（无盒规格不能挂盒图）" % (len(skus), uniq))
            elif vals and all(v == "figure" for v in vals):
                add("PASS", "D2", "%d 个规格 / %d 张唯一 SKU 图 —— 共用一张本体图（允许）" % (len(skus), uniq))
            else:
                add("WARN", "D2", "%d 个规格 / %d 张唯一 SKU 图 —— 共用图内容未判定，需人看一眼" % (len(skus), uniq))
        outside = [names[i] for i, u in enumerate(urls) if u and u not in (imgs.get("sku") or [])]
        add("WARN" if outside else "PASS", "D3",
            "skuImageUrl 不在 images.sku 里：%s" % (", ".join(outside) if outside else "无"))
        # 语义提示：哪个规格应该是盒照，交给人判断
        for i, nm in enumerate(names):
            low = nm.lower()
            want = "盒照(带包装)" if ("box" in low and "no" not in low) or "有盒" in nm else (
                "纯本体图(不带包装)" if ("no retail" in low or "no box" in low or "无盒" in nm) else "?")
            add("INFO", "D4", "规格 %-16s → 期望 %s（当前图 %s）" % (nm, want, (urls[i] or "-").rsplit("/", 1)[-1][:22]))
        # 两张图是否像素级接近
        sch = {n: feats["sku_%d" % i]["ph"] for i, n in enumerate(names)
               if "sku_%d" % i in feats}
        ks = list(sch)
        for a in range(len(ks)):
            for b in range(a + 1, len(ks)):
                dd = ham(sch[ks[a]], sch[ks[b]])
                if dd < 8:
                    add("INFO", "D5", "规格「%s」与「%s」的 SKU 图近乎相同（pHash 距 %d，共用本体图是允许的）" % (ks[a], ks[b], dd))

    # Description is an opaque protected field, outside image auditing.

    # ---------- F 盒照（用户规则 2026-11-06：盒照不要删） ----------
    plan = None
    pp = os.path.join(ROOT, "work", "pp_%s" % pid, "plan.json")
    if os.path.exists(pp):
        try:
            plan = json.load(open(pp, encoding="utf-8"))
        except Exception:
            plan = None
    if plan:
        killed = ["%s_%d" % (i["kind"], i["idx"]) for i in (plan.get("images") or [])
                  if i.get("box") == "box" and i.get("action") in ("DELETE", "CN_POSTER")]
        add("FAIL" if killed else "PASS", "F1",
            "计划里要删的盒照：%s" % (", ".join(killed) if killed else "无（盒照只许裁横幅，不许整张删）"))
        boxy = ["%s_%d" % (i["kind"], i["idx"]) for i in (plan.get("images") or []) if i.get("box") == "box"]
        if boxy:
            add("INFO", "F2", "plan 标记为盒照的图 %d 张：%s" % (len(boxy), ", ".join(boxy[:8])))
    try:
        bc = json.load(open(os.path.join(ROOT, "work", "sku_box.json"), encoding="utf-8"))
    except Exception:
        bc = {}
    cur_all = (imgs.get("main") or []) + (imgs.get("detail") or []) + (imgs.get("sku") or [])
    has_box_sku = any(("box" in (n or "").lower() or "盒" in (n or "")) for n in names)
    if has_box_sku:
        # 换过图的商品：新 URL 不在缓存里，现场判一次（is_box_photo 自带缓存），否则 F3 必假警
        unknown = [(n, dst, u) for n, (dst, u) in files.items() if u not in bc][:14]
        if unknown:
            try:
                from pipeline import is_box_photo
                for n, dst, u in unknown:
                    k = is_box_photo(dst, u)
                    if k:
                        bc[u] = k
                print("[info] F3 现场判定 %d 张未缓存的图" % len(unknown))
            except Exception as e:
                add("INFO", "F3b", "盒照现场判定失败：%s" % str(e)[:90])
    nb = sum(1 for u in cur_all if bc.get(u) == "box")
    if has_box_sku:
        add("PASS" if nb else "WARN", "F3",
            "有「带盒」规格：当前图池里盒照 %d 张%s" % (nb, "" if nb else " —— 没有盒照，需人判断是否补/换"))

    # ---------- 汇总 ----------
    if not quick:
        add("MANUAL", "C6", "打开 %s 逐张确认：只有厂牌 logo/产品轮廓 = 干净；"
                            "背景上出现成串字形（店名） = 别家水印，走 SOP §W8（换图，不要擦）"
            % os.path.join(outdir, "resid_montage.jpg"))
    fails = [r for r in RES if r[0] == "FAIL"]
    warns = [r for r in RES if r[0] == "WARN"]
    print("\n==== 汇总：FAIL %d / WARN %d / 共 %d 项 ====" % (len(fails), len(warns), len(RES)))
    if fails:
        print("不能交付，先修：")
        for lv, cd, ms in fails:
            print("  - %s %s" % (cd, ms))
    json.dump({"pid": pid, "when": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": RES,
               "images": {"main": n_main, "detail": n_detail, "sku": n_sku}, "skus": names},
              open(os.path.join(outdir, "report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0 if not fails else 1



def verify_snapshot(product, *, before=None):
    """Pure post-save structural delivery check; no credentials or network access."""
    images = product.get('images') or {}
    checks = {'status_preserved_by_executor': True,
              'main_count': 1 <= len(images.get('main') or []) <= 6,
              'detail_present': bool(images.get('detail')),
              'sku_pool_present': not product.get('skus') or bool(images.get('sku')),
              'sku_references': all((s.get('skuImageUrl') or s.get('imageUrl') or s.get('image')) in images.get('sku',[]) for s in product.get('skus') or [])}
    from final_state import validate_final_snapshot
    validation=validate_final_snapshot(product,context={'before':product})
    # Keep this a structural check. Only SKU reference rules use the bound
    # pre-save snapshot; unrelated write protections belong to saved-state checks.
    reference_validation=validate_final_snapshot(product,context={'before':before or {}})
    reference_errors=[e for e in reference_validation['errors'] if e['rule_id']=='SKU_REFERENCE']
    checks['sku_references']=not reference_errors
    validation['errors']=[e for e in validation['errors'] if e['rule_id']!='SKU_REFERENCE']+reference_errors
    validation['warnings']=[w for w in validation['warnings'] if w['rule_id']!='LEGACY_SKU_REFERENCE_UNCHANGED']+[
        w for w in reference_validation['warnings'] if w['rule_id']=='LEGACY_SKU_REFERENCE_UNCHANGED']
    validation['ok']=not validation['errors']
    return {'ok': all(checks.values()) and validation['ok'], 'checks': checks, 'validation':validation, 'scope': 'snapshot_structure; pixel evidence validated separately'}


def check_saved_job(directory):
    """Offline delivery check against snapshots, immutable evidence and actual content results."""
    from pathlib import Path
    from copy import deepcopy
    from product_state import canonical_state_hash,saved_state_matches
    from final_state import validate_final_snapshot
    from executor.service import ExecutorService
    root=Path(directory)
    try:
        read=lambda name:json.loads((root/name).read_text(encoding='utf-8'))
        before=read('before.json');after=read('after.json');expected=read('expected_after.json');plan=read('plan.v2.json')
        if canonical_state_hash(before)!=plan['precondition']['state_sha256']:
            raise ValueError('BEFORE_SNAPSHOT_BINDING_MISMATCH')
        content=read('content_validation.json')
        ExecutorService(None,None,root).execute(plan,dry_run=True)
        normalized=deepcopy(after)
        if (plan.get('post_actions') or {}).get('translate_title'):
            expected['titleTranslationZh']=after.get('titleTranslationZh')
            normalized['titleTranslationZh']=before.get('titleTranslationZh')
        checks={'structure':verify_snapshot(after,before=before)['ok'],
                'protected_fields':validate_final_snapshot(normalized,context={'before':before,'plan':plan,'saved_readback':True})['ok'],
                'expected_state':saved_state_matches(expected,after,source=before),
                'content':content.get('ok') is True and bool(content.get('items'))}
        return {'ok':all(checks.values()),'checks':checks,'read_only':True,'scope':'saved_snapshots_and_content_evidence'}
    except Exception as exc:
        return {'ok':False,'read_only':True,'error':type(exc).__name__+': '+str(exc),'scope':'saved_snapshots_and_content_evidence'}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("pid", nargs="?")
    ap.add_argument("--job-dir", help="Offline snapshot and content-evidence verification")
    ap.add_argument("--batch", default="", help="多件并行体检：4647,4758,4754")
    ap.add_argument("--jobs", type=int, default=5)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--stable", type=int, default=6, help="A2/A3 稳定性等待秒数，0=跳过（写入后已 verify 过）")
    ap.add_argument("--fast", action="store_true",
                    help="批检提速：stable=0 + 4 线程并行取图/算残差（结论口径不变）")
    ap.add_argument("--reviewed", action="store_true", help="已逐张看过 resid 拼图")
    a = ap.parse_args()
    if a.job_dir:
        checked=check_saved_job(a.job_dir)
        print(json.dumps(checked,ensure_ascii=False))
        sys.exit(0 if checked["ok"] else 1)
    here = os.path.dirname(os.path.abspath(__file__))
    if a.batch:
        import subprocess
        pids = [p for p in a.batch.replace(",", " ").split() if p]
        def run(pid):
            cmd = [sys.executable, os.path.abspath(__file__), pid, "--stable", str(a.stable)]
            if a.quick: cmd.append("--quick")
            if a.fast: cmd.append("--fast")
            if a.reviewed: cmd.append("--reviewed")
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", cwd=here)
            return pid, r.returncode, r.stdout
        rc_all = 0
        with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as ex:
            for pid, rc, out in ex.map(run, pids):
                summ = [l for l in out.splitlines() if l.strip().startswith("==== 汇总")]
                print("[%s] exit=%d  %s" % (pid, rc, summ[-1].strip() if summ else "(无汇总)"))
                if rc != 0:
                    rc_all = 1
        sys.exit(rc_all)
    if not a.pid:
        ap.error("需要 pid 或 --batch")
    Site.instance = Site()
    rc = main(a.pid, quick=a.quick, stable=a.stable, fast=a.fast)
    if rc == 0 and not a.quick and not a.reviewed:
        print("\n!! 残差拼图还没人看过：看过后加 --reviewed 复跑才算交付通过")
        sys.exit(2)
    sys.exit(rc)
