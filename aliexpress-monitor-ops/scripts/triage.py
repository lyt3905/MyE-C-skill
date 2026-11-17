#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""triage.py — 新品关键词初筛 + 主图对照表（给「看图复核」这一步用）。

流程位置：scan 出新品（pending_review）→ 本脚本初筛分层并出对照表 → 看图定夺
          → alm.py set-state --ids ... --to to_process → picker-queue 采集。

子命令：
  classify  拉某轮扫描的新品 → 关键词分层 HIGH/MAYBE/SKIP → 下主图 → index.txt
            → markdown 报告 → 对照表 sheet-*.jpg（另出一份 SKIP 对照表 sheet-skip-*.jpg）
  sheet     把任意缩略图目录（%02d_<id>.jpg）拼成对照表，供单独复核

环境变量：
  ALM_PROJECT  项目根，默认 D:\\GitHub\\AliExpressMonitor
  ALM_DB       直接指定 products.db（优先于 ALM_PROJECT）

依赖：Pillow（项目 venv 已装）。只用 DB 只读 + 图片下载，**不写库、不改状态**。
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
import time
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

PROJECT = os.environ.get("ALM_PROJECT", r"D:\GitHub\AliExpressMonitor")
DB = os.environ.get("ALM_DB") or os.path.join(PROJECT, "data", "products.db")

# --------------------------------------------------------------------- 关键词词表
# 口径：只做「初筛」，最终由看图定夺。命中越多分越高，命中排除词直接 SKIP。
OFFICIAL = [
    r"transformers", r"变形金刚", r"\bg1\b", r"masterpiece", r"\bmpm?-?\d", r"\bmp\s?\d{2}", r"studio series",
    r"\bss\s?\d{2}\b", r"\blegacy\b", r"war for cybertron", r"\bsiege\b", r"earthrise", r"\bkingdom\b",
    r"\bss86\b", r"86-0\d", r"star saber", r"史达", r"titans return", r"combiner wars", r"power of the primes",
    r"hasbro", r"takara", r"tomy", r"t-spark", r"overgear", r"\bg2\b", r"\btf\d",
    r"transform(?:able|ing|er)?", r"beast wars", r"predaking", r"tfcon",
    r"\bmmc\b", r"\box\b", r"\bbt-?\d{2}", r"\bcs-?\d{2}", r"\bdw-e\d", r"\bbwm-?\d", r"booster",
]
BRANDS3P = [
    r"threezero", r"three zero", r"robo-dou", r"robodou", r"flame toys", r"铁机巧", r"blitzway", r"yolopark",
    r"\bms-?\d", r"magic square", r"魔方", r"newage", r"\bna-?\s?h?\d", r"ironfactory", r"iron factory",
    r"铁工厂", r"fanstoys", r"fans toys", r"dx9", r"\bmft\b", r"型模坊", r"toyworld", r"\bzeta\b",
    r"apc toys", r"dr\.?wu", r"\bdmk\b", r"mtcd", r"\bdna\b", r"\bdk-?\d{2}",
]
CHARS = [
    r"optimus", r"megatron", r"bumblebee", r"starscream", r"rodimus", r"soundwave", r"wheeljack", r"jetfire",
    r"grimlock", r"arcee", r"ultra magnus", r"galvatron", r"shockwave", r"skyfire", r"hot rod", r"cliffjumper",
    r"dinobot", r"perceptor", r"ratchet", r"ironhide", r"jazz", r"devastator", r"computron", r"spinister",
    r"擎天柱", r"威震天", r"大黄蜂", r"红蜘蛛", r"补天士", r"声波", r"千斤顶", r"天火", r"钢锁", r"阿尔西", r"爵士",
]
NEG = [
    r"gundam", r"高达", r"gunpla", r"figma", r"nendoroid", r"黏土人", r"dragon ball", r"龙珠", r"one piece",
    r"naruto", r"火影", r"marvel", r"漫威", r"star wars", r"星球大战", r"pokemon", r"宝可梦",
    r"hot wheels", r"风火轮", r"lego", r"乐高", r"barbie", r"funko", r"jada", r"mini gt", r"tomica",
    r"ghostbusters", r"ectomobile", r"ecto-1", r"warhammer", r"neca", r"figuarts",
    r"four horsemen", r"elvira", r"basketball", r"muscle bear", r"肌肉熊",
]
# 新口径（2026-11-16「属于变形玩具即可」）：非 TF 授权但本身能变形/合体的（盖塔、魔神 Z、
# 超机列传 SRL、Voltron/百兽王/Megazord、Power Rangers 合体机）不再直接排除，
# 改为软排除 —— 强制进 MAYBE 主对照表，交看图复核定夺。
NEG_SOFT = [
    r"voltron", r"golion", r"百兽王", r"战神金刚", r"zord", r"power rangers",
    r"getter", r"mazinger", r"魔神", r"盖塔", r"超机列传", r"super robot legend", r"\bsrl-?0\d",
]


def hits(title: str, pats):
    return [p for p in pats if re.search(p, title)]


def classify(title: str):
    """返回 (level, score, why)。硬排除词→SKIP；变形软词→MAYBE；否则分≥3=HIGH、≥2=MAYBE。"""
    t = (title or "").lower()
    off, br, ch, neg = hits(t, OFFICIAL), hits(t, BRANDS3P), hits(t, CHARS), hits(t, NEG)
    soft = hits(t, NEG_SOFT)
    score, why = 0, []
    if off:
        score += 3 + min(len(off) - 1, 2); why.append("官方线:" + ",".join(off[:3]))
    if br:
        score += 3 + min(len(br) - 1, 2); why.append("第三方:" + ",".join(br[:3]))
    if ch:
        score += 2; why.append("角色:" + ",".join(ch[:3]))
    if neg:
        score -= 8; why.append("排除词:" + ",".join(neg[:3]))
    if soft:
        why.append("变形软词(待看图):" + ",".join(soft[:3]))
    if not neg and soft:
        level = "MAYBE"
    elif not neg and score >= 3:
        level = "HIGH"
    elif not neg and score >= 2:
        level = "MAYBE"
    else:
        level = "SKIP"
    return level, score, "; ".join(why)


# --------------------------------------------------------------------- 取数
def load(run_id: int = 0):
    """按扫描轮次取新品；run_id=0 用最近一轮。返回 (run_id, items)。"""
    if not os.path.exists(DB):
        raise SystemExit(f"找不到数据库：{DB}（检查 ALM_PROJECT）")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        if not run_id:
            run_id = con.execute("select max(id) from scan_attempts").fetchone()[0]
        rows = con.execute("""
            select p.id, p.remote_product_id, p.title, p.state, p.state_version, p.image_url, s.name
            from scan_discoveries d
            join products p on p.id = d.product_id
            left join shops s on s.id = p.shop_id
            where d.scan_run_id = ?
            order by p.id
        """, (run_id,)).fetchall()
    finally:
        con.close()
    items = []
    for pid, rid, title, state, ver, img, shop in rows:
        level, score, why = classify(title)
        items.append({
            "productId": pid, "remoteId": rid, "title": title or "", "state": state,
            "version": ver, "image": img, "shop": (shop or "").split(" - ")[0],
            "level": level, "score": score, "why": why,
            "url": "https://www.aliexpress.com/item/%s.html" % rid,
        })
    return run_id, items


# --------------------------------------------------------------------- 主图
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36")


def download_thumbs(items, out_dir: str):
    """下载主图到 out_dir，文件名 %02d_<productId>.jpg；已存在则跳过。返回 (成功数, 失败原因)。"""
    os.makedirs(out_dir, exist_ok=True)
    ok, errors = 0, []
    for idx, it in enumerate(items, 1):
        dst = os.path.join(out_dir, "%02d_%d.jpg" % (idx, it["productId"]))
        if os.path.exists(dst) and os.path.getsize(dst) > 0:
            ok += 1; it["thumb"] = dst; continue
        if not it.get("image"):
            it["thumb"] = None; errors.append("%s 无主图 URL" % it["productId"]); continue
        data, last = None, ""
        for attempt in range(3):
            try:
                req = urllib.request.Request(it["image"], headers={
                    "User-Agent": UA,
                    "Referer": "https://www.aliexpress.com/",
                    "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
                })
                with urllib.request.urlopen(req, timeout=25) as resp:
                    data = resp.read()
                break
            except Exception as exc:
                last = "%s: %s" % (type(exc).__name__, exc)
                time.sleep(0.6 * (attempt + 1))
        if not data:
            it["thumb"] = None; errors.append("%s %s" % (it["productId"], last)); continue
        tmp = dst + ".raw"
        with open(tmp, "wb") as f:
            f.write(data)
        try:
            from PIL import Image
            with Image.open(tmp) as im:
                im.convert("RGB").save(dst, "JPEG", quality=88)
            os.remove(tmp)
        except Exception:
            os.replace(tmp, dst)
        it["thumb"] = dst; ok += 1
        time.sleep(0.1)
    return ok, errors


def write_index(items, out_dir: str):
    """编号 → 商品映射，供看图时对照：编号 TAB 商品id TAB 等级 TAB 店铺 TAB 标题。"""
    path = os.path.join(out_dir, "index.txt")
    with open(path, "w", encoding="utf-8") as f:
        for idx, it in enumerate(items, 1):
            f.write("%02d\t%d\t%s\t%s\t%s\n" % (idx, it["productId"], it["level"], it["shop"], it["title"]))
    return path


# --------------------------------------------------------------------- 对照表
def make_sheets(thumb_dir: str, out_prefix: str, cols: int = 5, cell: int = 300):
    """把 %02d_<id>.jpg 拼成 5 列 × 300px 对照表，每表 20 图，编号黑底黄字。返回生成的文件列表。"""
    from PIL import Image, ImageDraw, ImageFont
    if not os.path.isdir(thumb_dir):
        return []
    files = sorted(f for f in os.listdir(thumb_dir) if re.match(r"^\d{2}_\d+\.jpg$", f))
    if not files:
        return []
    rows = 4
    per = cols * rows
    try:
        font = ImageFont.truetype("arial.ttf", 34)
    except Exception:
        font = ImageFont.load_default()
    made = []
    for s in range(0, len(files), per):
        chunk = files[s:s + per]
        canvas = Image.new("RGB", (cols * cell, rows * cell), "white")
        draw = ImageDraw.Draw(canvas)
        for i, name in enumerate(chunk):
            cx, cy = (i % cols) * cell, (i // cols) * cell
            try:
                with Image.open(os.path.join(thumb_dir, name)) as im:
                    im = im.convert("RGB")
                    im.thumbnail((cell - 6, cell - 6))
                    canvas.paste(im, (cx + (cell - im.width) // 2, cy + (cell - im.height) // 2))
            except Exception:
                pass
            label = name.split("_")[0]
            draw.rectangle([cx, cy, cx + 52, cy + 40], fill="black")
            draw.text((cx + 8, cy + 2), label, fill="yellow", font=font)
        out = "%s-%02d.jpg" % (out_prefix, len(made) + 1)
        canvas.save(out, "JPEG", quality=82)
        made.append(out)
    return made


# --------------------------------------------------------------------- 报告
def write_report(path: str, run_id: int, items):
    hi = [i for i in items if i["level"] == "HIGH"]
    mb = [i for i in items if i["level"] == "MAYBE"]
    sk = [i for i in items if i["level"] == "SKIP"]
    with open(path, "w", encoding="utf-8") as f:
        f.write("# 扫描 %d 变形金刚筛选报告\n\n" % run_id)
        f.write("新品 %d ｜ HIGH %d ｜ MAYBE %d ｜ SKIP %d\n\n" % (len(items), len(hi), len(mb), len(sk)))
        f.write("> 本报告只是**关键词初筛**，必须按对照表逐张看图定夺后再改状态。\n\n")
        for name, sel in (("HIGH（初筛通过，待看图确认）", hi), ("MAYBE（需重点看）", mb)):
            f.write("## %s — %d 条\n\n" % (name, len(sel)))
            if not sel:
                f.write("_无_\n\n"); continue
            f.write("| 店铺 | 商品 | 命中 | 链接 |\n|---|---|---|---|\n")
            for i in sel:
                f.write("| %s | %s | %s | [打开](%s) |\n" % (
                    i["shop"], i["title"].replace("|", "｜"), i["why"], i["url"]))
            f.write("\n")
        f.write("## SKIP — %d 条\n\n" % len(sk))
        for i in sk:
            f.write("- [%s] %s\n" % (i["shop"], i["title"]))


# --------------------------------------------------------------------- 子命令
def cmd_classify(a):
    run_id, items = load(a.run)
    if not items:
        raise SystemExit(f"run {run_id} 没有新品记录（换 --run 或先跑扫描）")
    out = a.out or "triage-%d" % run_id
    os.makedirs(out, exist_ok=True)
    want = tuple(x.strip().upper() for x in a.levels.split(",") if x.strip())
    main_items = [i for i in items if i["level"] in want]
    skip_items = [i for i in items if i["level"] not in want]

    print("run %d 新品 %d ｜ HIGH %d ｜ MAYBE %d ｜ SKIP %d" % (
        run_id, len(items),
        len([i for i in items if i["level"] == "HIGH"]),
        len([i for i in items if i["level"] == "MAYBE"]),
        len([i for i in items if i["level"] == "SKIP"])))

    thumb_dir = os.path.join(out, "thumbs")
    n, errs = download_thumbs(main_items, thumb_dir)
    print("主图 %d/%d -> %s" % (n, len(main_items), thumb_dir))
    for e in errs[:5]:
        print("  失败:", e)
    idx = write_index(main_items, thumb_dir)
    sheets = [] if a.no_sheet else make_sheets(thumb_dir, os.path.join(out, "sheet"))
    print("对照表 %d 张 -> %s\\sheet-NN.jpg" % (len(sheets), out))
    print("映射 -> %s" % idx)

    skip_dir = os.path.join(out, "thumbs-skip")
    if skip_items and not a.no_skip:
        n2, errs2 = download_thumbs(skip_items, skip_dir)
        print("排除项主图 %d/%d -> %s" % (n2, len(skip_items), skip_dir))
        write_index(skip_items, skip_dir)
        if not a.no_sheet:
            s2 = make_sheets(skip_dir, os.path.join(out, "sheet-skip"))
            print("排除对照表 %d 张 -> %s\\sheet-skip-NN.jpg（抽查有没有被误排除的）" % (len(s2), out))

    report = os.path.join(out, "report-%d-tf.md" % run_id)
    write_report(report, run_id, items)
    print("报告 -> %s" % report)
    print()
    print("下一步：")
    print("  1) 用 read_image 逐张看 %s\\sheet-*.jpg，编号对照 index.txt" % out)
    print("  2) 判定标准见 references/tf-classification.md（含通过/排除清单与误判案例）")
    print("  3) 抽查 %s\\sheet-skip-*.jpg，找只写代号被误排除的" % out)
    print("  4) 确认通过后一次性标记：")
    print("     & $py -X utf8 $alm set-state --ids <id,id,...> --to to_process")
    print("     （看图判为误判的用 --to pending_review 回退）")
    print("  5) 再采集：& $py -X utf8 $alm picker-queue --state to_process --from-date today")
    if a.json:
        import json as _json
        print(_json.dumps({"run": run_id, "out": out, "thumbs": thumb_dir,
                           "sheets": sheets, "items": [
                               {"id": i["productId"], "level": i["level"], "shop": i["shop"],
                                "title": i["title"], "url": i["url"]} for i in main_items]},
                          ensure_ascii=False))


def cmd_sheet(a):
    made = make_sheets(a.dir, a.prefix, cols=a.cols, cell=a.cell)
    if not made:
        raise SystemExit(f"{a.dir} 里没有 %02d_<id>.jpg，没法拼表")
    for p in made:
        print(p)


def main(argv=None):
    p = argparse.ArgumentParser(description="AliExpressMonitor 新品初筛 + 对照表")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("classify", help="按扫描轮次初筛 + 下主图 + 出对照表")
    sp.add_argument("--run", type=int, default=0, help="scan_run_id，0=最近一轮")
    sp.add_argument("--out", default="", help="产物目录，默认 triage-<runId>")
    sp.add_argument("--levels", default="HIGH,MAYBE", help="进主对照表的等级，默认 HIGH,MAYBE")
    sp.add_argument("--no-skip", dest="no_skip", action="store_true", help="不下载/不拼排除项对照表")
    sp.add_argument("--no-sheet", dest="no_sheet", action="store_true", help="只下主图不拼表")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_classify)

    sp = sub.add_parser("sheet", help="把已有缩略图目录拼成对照表")
    # 注意：argparse 的 help 会走 % 格式化，字面 % 必须写成 %%
    sp.add_argument("dir", help="含 %%02d_<id>.jpg 的目录")
    sp.add_argument("prefix", help="输出前缀，生成 <prefix>-NN.jpg")
    sp.add_argument("--cols", type=int, default=5)
    sp.add_argument("--cell", type=int, default=300)
    sp.set_defaults(func=cmd_sheet)

    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    main()
