#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""publish_scan_daily.py — 把 AliExpressMonitor 扫描库里的「每日新品」发布成静态站。

流程位置：run-daily-scan.ps1 扫完（或带 -PublishOnly）→ 本脚本 → 渲染日页 → git 提交推送
          → https://lyt3905.github.io/aliexpress-scan-intel/

做什么：
  * 只读打开 products.db（uri mode=ro），按 UTC+8 的「入库日」把新品归日；
  * 每个有新品的日子渲染一页 `<YYYY-MM-DD>.html`（按店铺归集卡片 + 搜索/店铺筛选）；
  * `index.html` = 最新一天的日页（逐字节副本）；`archive.html` = 历史归档倒序；
  * 期号 `第 N / M 期` 按已发布日页的日期升序计算，M 随新页自动变大（老页一起改）；
  * 幂等：内容没变就不写文件、不提交；有新日期就按日期逐条 commit
    （message 与历史一致：`digest: <YYYY-MM-DD> 选品扫描简报`），最后 push。

统计口径（与历史 24 期逐页回归一致）：
  * `扫描 N 次`      = 该日 scan_runs 条数（**按 finished_at +8h 归日**，不是 started_at）
  * `（成功 M）`      = 其中 status='succeeded'
  * `覆盖店铺 N 家`   = 上述 run 的 scan_shop_results 行数合计，`（成功 M）` 同理
  * `涉及店铺 N 家`   = 当日新品按店铺去重
  * 某日没有 finished run 时，页面与归档都省略「扫描 / 覆盖店铺」两项

用法：
  python publish_scan_daily.py                     # 全量增量发布（日常就这一条）
  python publish_scan_daily.py --dry-run           # 只看会改哪些文件，不写不提交
  python publish_scan_daily.py --list              # 只列 DB 里的新品日与件数
  python publish_scan_daily.py --date 2026-11-13   # 只发布指定日（可重复/逗号分隔）
  python publish_scan_daily.py --no-push           # 只提交不推送

环境变量：
  ALM_DB            直接指定 products.db（优先）
  ALM_PROJECT       项目根，默认 D:\\GitHub\\AliExpressMonitor
  SCAN_INTEL_DIR    静态站仓库目录，默认 D:\\GitHub\\aliexpress-scan-intel
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

PROJECT = os.environ.get("ALM_PROJECT", r"D:\GitHub\AliExpressMonitor")
DB = os.environ.get("ALM_DB") or os.path.join(PROJECT, "data", "products.db")
OUT = os.environ.get("SCAN_INTEL_DIR", r"D:\GitHub\aliexpress-scan-intel")

CST = timezone(timedelta(hours=8))
SHOP_SUFFIX = " - Amazing products with exclusive discounts on AliExpress"
DOW = "一二三四五六日"
PAGE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.html$")

# ------------------------------------------------------------------ 模板静态片段
# 以下四段 CSS/JS 从已发布的 2026-11-10.html 逐字节提取，勿手改（改了页面样式会漂）。
CSS = r''':root{--bg:#f5f6f8;--card:#fff;--line:#e4e7ec;--ink:#16181d;--ink2:#5a6472;
--ink3:#8b95a3;--accent:#2f6fed;--accent-soft:#eaf1fe;--ok:#1a7a45;--ok-bg:#e6f3ea}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px}
.top{background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:9}
.top .inner{padding:12px 0 10px}
.toprow{display:flex;flex-wrap:wrap;align-items:baseline;gap:5px 12px}
h1{margin:0;font-size:19px;letter-spacing:.2px}
h1 .h1d{font-size:13.5px;color:var(--ink3);font-weight:400;margin-left:8px}
.sp{flex:1 1 auto}
.stat{display:flex;flex-wrap:wrap;gap:5px 14px;margin:0;font-size:12.5px;color:var(--ink3)}
.stat b{color:var(--ink2);font-weight:600}
.stat .pill{background:var(--accent-soft);border:1px solid #c9d8f5;color:var(--accent);
border-radius:999px;padding:3px 11px;font-size:12.5px}
.stat .pill b{color:var(--accent)}
.toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-top:9px;
padding-top:9px;border-top:1px dashed var(--line)}
.daynav{display:flex;flex-wrap:wrap;align-items:center;gap:7px}
.dn-btn{display:inline-flex;align-items:center;gap:5px;border:1px solid var(--line);
background:var(--card);color:var(--ink2);border-radius:8px;padding:4px 10px;font-size:12.5px;
white-space:nowrap;cursor:pointer}
.dn-btn:hover{border-color:var(--accent);color:var(--accent);background:var(--accent-soft);text-decoration:none}
.dn-btn.off{opacity:.45;cursor:not-allowed;background:var(--bg)}
.dn-btn.off:hover{border-color:var(--line);color:var(--ink2);background:var(--bg)}
.dn-w{color:var(--ink3);font-size:11.5px}
.dn-pos{font-size:12px;color:var(--ink3);white-space:nowrap}
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;flex:1 1 240px;justify-content:flex-end}
.chiprow{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:8px}
#q{flex:1 1 180px;min-width:150px;padding:7px 12px;border:1px solid var(--line);
border-radius:8px;font-size:13.5px;font-family:inherit;background:var(--bg)}
#q:focus{outline:2px solid var(--accent-soft);border-color:var(--accent);background:var(--card)}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{border:1px solid var(--line);background:var(--card);color:var(--ink2);border-radius:999px;
padding:5px 12px;font-size:12.5px;cursor:pointer;font-family:inherit}
.chip:hover{border-color:#c9d2de;color:var(--ink)}
.chip.on{background:var(--accent);border-color:var(--accent);color:#fff}
.chip .n{opacity:.6;margin-left:4px;font-size:11.5px}
.count{color:var(--ink3);font-size:12.5px;margin-left:auto;white-space:nowrap}
main{padding:20px 0 60px}
.sec{border-bottom:1px solid var(--line);margin:0 0 18px;padding-bottom:10px;
display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.sec h2{margin:0;font-size:15px;font-weight:650}
.sec .h{color:var(--ink3);font-size:12.5px;font-weight:400}
.sec .r{margin-left:auto;font-size:12.5px;color:var(--ink3)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(345px,1fr));gap:11px}
.it{display:flex;gap:12px;padding:11px;background:var(--card);border:1px solid var(--line);
border-radius:11px;color:var(--ink)}
.it:hover{border-color:#9ecbff;background:#f7fbff;text-decoration:none}
.it img{width:88px;height:88px;flex:0 0 88px;border-radius:8px;background:#eef1f5;object-fit:cover}
.it .tx{min-width:0;display:flex;flex-direction:column;gap:5px;flex:1}
.it .tt{font-size:13.5px;line-height:1.45;font-weight:550;
display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.it .mt{margin-top:auto;display:flex;flex-wrap:wrap;align-items:center;gap:6px;font-size:11.5px;color:var(--ink3)}
.shop{background:var(--bg);border:1px solid var(--line);border-radius:5px;padding:1px 7px;
color:var(--ink2);font-size:11.5px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.state{background:var(--ok-bg);color:var(--ok);border-radius:5px;padding:1px 7px;font-size:11.5px}
.empty{color:var(--ink3);font-size:13.5px;padding:30px 0}
.dayfoot{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:9px;
margin:22px 0 0;padding:18px 0 6px;border-top:1px solid var(--line)}
.dayfoot .df-t{font-size:12.5px;color:var(--ink3)}
footer{padding:0 0 40px;color:var(--ink3);font-size:12px;text-align:center}
@media(max-width:520px){.it img{width:72px;height:72px;flex-basis:72px}}'''

ARCHIVE_CSS = r'''  body{margin:0;padding:32px 20px;background:#f6f7f9;color:#1c2029;
    font:15px/1.7 system-ui,-apple-system,'Segoe UI','Microsoft YaHei',sans-serif}
  .w{max-width:640px;margin:0 auto}
  h1{font-size:20px;font-weight:600;margin:0 0 4px}
  p.sub{color:#6b7280;font-size:13px;margin:0 0 22px}
  ul{list-style:none;padding:0;margin:0}
  li{margin:0 0 8px}
  a{display:flex;align-items:baseline;gap:10px;padding:12px 16px;background:#fff;
    border:1px solid #e5e7eb;border-radius:10px;color:#1c2029;text-decoration:none}
  a:hover{border-color:#9ecbff;background:#f2f8ff}
  b{font-weight:600}
  .meta{color:#6b7280;font-size:12.5px}
  .go{margin-left:auto;color:#2563eb;font-size:12.5px;white-space:nowrap}
  .lv{font-size:11.5px;font-weight:600;color:#1a7a45;background:#e6f3ea;border-radius:5px;padding:1px 7px}
  li.empty{color:#9ca3af;font-size:13px}
  .back{display:inline-block;margin-top:18px;font-size:13px}'''

JS_FILTER = r'''(function(){
  var q=document.getElementById('q'), chips=[].slice.call(document.querySelectorAll('.chip')),
      items=[].slice.call(document.querySelectorAll('.it')), cnt=document.getElementById('cnt'),
      cur='all';
  function apply(){
    var kw=(q.value||'').trim().toLowerCase(), shown=0;
    items.forEach(function(el){
      var okShop = cur==='all' || el.dataset.shop===cur;
      var okKw = !kw || (el.dataset.k||'').indexOf(kw)>=0;
      var on = okShop && okKw;
      el.style.display = on ? '' : 'none';
      if(on) shown++;
    });
    if(cnt) cnt.textContent = '显示 ' + shown + ' / ' + items.length + ' 件';
  }
  chips.forEach(function(c){ c.addEventListener('click', function(){
    chips.forEach(function(x){ x.classList.remove('on'); });
    c.classList.add('on'); cur = c.dataset.shop || 'all'; apply();
  }); });
  if(q){ q.addEventListener('input', apply); }
  apply();
})();'''

JS_SCROLL = r'''(function(){
  var t=document.querySelector('.top'), y0=window.scrollY;
  window.addEventListener('scroll', function(){
    var y=window.scrollY;
    if(y>120 && y>y0+6) t.classList.add('hide');
    else if(y<y0-6 || y<120) t.classList.remove('hide');
    y0=y;
  }, {passive:true});
})();'''

JS_IMG = r'''(function(){
  // 速卖通图床对同一 IP 的并发请求会 429：失败后退避重试两次，仍失败才隐藏
  document.querySelectorAll('.it img').forEach(function(im){
    var src = im.getAttribute('data-src') || im.getAttribute('src') || '', tries = 0;
    function fail(){
      tries++;
      if(tries <= 2 && src){
        setTimeout(function(){ im.src = src + (src.indexOf('?') >= 0 ? '&' : '?') + 'r=' + tries; }, 700 * tries);
      } else { im.style.visibility = 'hidden'; }
    }
    function ok(){ im.style.visibility = im.naturalWidth >= 40 ? '' : 'hidden'; }
    im.addEventListener('error', fail);
    im.addEventListener('load', ok);
    if(im.complete){ if(im.naturalWidth) ok(); }
  });
})();'''


# ---------------------------------------------------------------------- 小工具
def dow_cn(d: date) -> str:
    return "周" + DOW[d.weekday()]


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def shop_name(raw: str) -> str:
    raw = raw or ""
    if raw.endswith(SHOP_SUFFIX):
        raw = raw[: -len(SHOP_SUFFIX)]
    return raw.strip()


def parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CST)


# ---------------------------------------------------------------------- 读库
def load(conn: sqlite3.Connection):
    """返回 (按日分组的商品, 每日扫描统计, 店铺 id->名)。"""
    names = {r[0]: shop_name(r[1]) for r in conn.execute("select id, name from shops")}

    by_day: dict[str, list[dict]] = {}
    rows = conn.execute(
        "select id, shop_id, remote_product_id, title, image_url, first_seen_at "
        "from products order by id desc"
    )
    for pid, shop_id, rid, title, img, seen in rows:
        dt = parse_dt(seen)
        by_day.setdefault(dt.date().isoformat(), []).append(
            {
                "id": pid,
                "remote_product_id": rid or "",
                "title": title or "",
                "image_url": img or "",
                "shop": names.get(shop_id, ""),
                "hhmm": dt.strftime("%H:%M"),
            }
        )

    runs: dict[str, list[int]] = {}
    for d, n, ok in conn.execute(
        "select date(finished_at,'+8 hours') d, count(*), sum(status='succeeded') "
        "from scan_runs where finished_at is not null and finished_at <> '' group by d"
    ):
        if d:
            runs[d] = [n or 0, ok or 0]

    shops: dict[str, list[int]] = {}
    for d, n, ok in conn.execute(
        "select date(r.finished_at,'+8 hours') d, count(s.id), sum(s.status='succeeded') "
        "from scan_shop_results s "
        "join scan_attempts a on a.id = s.scan_attempt_id "
        "join scan_runs r on r.id = a.scan_run_id "
        "where r.finished_at is not null and r.finished_at <> '' group by d"
    ):
        if d:
            shops[d] = [n or 0, ok or 0]

    stats = {d: {"runs": runs.get(d, [0, 0])[0], "runs_ok": runs.get(d, [0, 0])[1],
                 "shops": shops.get(d, [0, 0])[0], "shops_ok": shops.get(d, [0, 0])[1]}
             for d in by_day}
    return by_day, stats, names


def existing_pages(out: str) -> list[str]:
    if not os.path.isdir(out):
        return []
    return sorted(m.group(1) for m in (PAGE_RE.match(f) for f in os.listdir(out)) if m)


# ---------------------------------------------------------------------- 渲染
def daynav(day: str, prev: str | None, nxt: str | None) -> str:
    left = (f'<a class="dn-btn" href="{prev}.html">‹ 前一天<span class="dn-w">{prev}</span></a>'
            if prev else '<span class="dn-btn off">‹ 前一天</span>')
    right = (f'<a class="dn-btn" href="{nxt}.html">› 后一天<span class="dn-w">{nxt}</span></a>'
             if nxt else '<span class="dn-btn off">› 后一天</span>')
    return f'{left}<span class="dn-pos">{day} {dow_cn(date.fromisoformat(day))}</span>{right}'


def render_day(day: str, items: list[dict], st: dict, idx: int, total: int,
               prev: str | None, nxt: str | None) -> str:
    d = date.fromisoformat(day)
    dow = dow_cn(d)
    n = len(items)

    per_shop: dict[str, int] = {}
    for it in items:
        per_shop[it["shop"]] = per_shop.get(it["shop"], 0) + 1
    chips = "".join(
        f'<button class="chip" data-shop="{esc(s)}">{esc(s)}<span class="n">{c}</span></button>'
        for s, c in sorted(per_shop.items(), key=lambda kv: (-kv[1], kv[0]))
    )

    pill = f'<span class="pill">新增 <b>{n}</b> 件</span>'
    extra = ""
    if st["runs"]:
        extra = (f'<span>扫描 <b>{st["runs"]}</b> 次（成功 <b>{st["runs_ok"]}</b>）</span>'
                 f'<span>覆盖店铺 <b>{st["shops"]}</b> 家（成功 <b>{st["shops_ok"]}</b>）</span>')
    stat = f'{pill}{extra}<span>涉及店铺 <b>{len(per_shop)}</b> 家</span>'

    nav = daynav(day, prev, nxt)
    cards = []
    for it in items:
        kw = esc((it["title"] + " " + it["shop"]).lower())
        cards.append(
            f'<a class="it" href="https://www.aliexpress.com/item/{it["remote_product_id"]}.html"'
            f' target="_blank" rel="noopener" data-shop="{esc(it["shop"])}" data-k="{kw}">'
            f'<img src="{esc(it["image_url"])}" data-src="{esc(it["image_url"])}" alt=""'
            f' loading="lazy" decoding="async" referrerpolicy="no-referrer">'
            f'<div class="tx"><div class="tt">{esc(it["title"])}</div>'
            f'<div class="mt"><span class="shop">{esc(it["shop"])}</span>'
            f'<span>{it["hhmm"]}</span><span style="margin-left:auto">源商品 ↗</span>'
            f'</div></div></a>'
        )

    bar = ('<div style="display:flex;align-items:center;gap:12px;padding:9px 18px;'
           'background:#1f2430;color:#fff;font:13px/1.5 system-ui,-apple-system,'
           "'Segoe UI',sans-serif\"><span style=\"font-weight:600\">速卖通选品情报 · 每日更新</span>"
           f'<span style="opacity:.72">{day} {dow}</span>'
           f'<span class="dn-pos">第 {idx} / {total} 期</span>'
           '<a href="archive.html" style="margin-left:auto;color:#9ecbff;text-decoration:none">'
           '历史归档 →</a></div>')

    top = (
        f'<div class="top"><div class="wrap inner"><div class="toprow">'
        f'<h1>速卖通选品情报 · {day}<span class="h1d">{dow}</span></h1>'
        f'<span class="sp"></span><p class="stat">{stat}</p></div>'
        f'<div class="toolbar"><div class="daynav">{nav}</div>'
        '<div class="controls"><input id="q" type="search" placeholder="搜标题 / 店铺…">'
        '<span class="count" id="cnt"></span></div></div>'
        f'<div class="chiprow"><div class="chips">'
        f'<button class="chip on" data-shop="all">全部<span class="n">{n}</span></button>'
        f'{chips}</div></div></div></div>'
    )

    return (
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f'<title>速卖通选品情报 · {day}</title>\n<style>\n{CSS}\n</style>\n</head>\n<body>\n'
        f'{bar}\n{top}\n'
        '<main class="wrap">\n'
        f'  <div class="sec"><h2>{day} 新增商品</h2>'
        '<span class="h">按店铺归集，点击卡片打开速卖通原页</span>\n'
        '  <span class="r">数据源 AliExpressMonitor</span></div>\n'
        '  <div class="grid">\n'
        + "\n".join(cards) +
        '\n  </div>\n'
        f'  <div class="dayfoot"><span class="df-t">继续翻看</span><div class="daynav">{nav}</div></div>\n'
        '</main>\n'
        '<footer>由 AliExpressMonitor 的扫描库自动生成 · 每日扫描后更新</footer>\n'
        f'<script>\n{JS_FILTER}\n</script>\n'
        f'<script>\n{JS_SCROLL}\n</script>\n'
        f'<script>\n{JS_IMG}\n</script>\n'
        '</body>\n</html>\n'
    )


def render_archive(days: list[str], counts: dict[str, int], stats: dict[str, dict]) -> str:
    lis = []
    for i, day in enumerate(days):
        d = date.fromisoformat(day)
        meta = f'{dow_cn(d)} · '
        st = stats.get(day) or {}
        if st.get("runs"):
            meta += f'扫描 {st["runs"]} 次 · '
        meta += f'新增 {counts.get(day, 0)} 件'
        lv = '<span class="lv">最新</span>' if i == 0 else ""
        lis.append(f'<li><a href="{day}.html"><b>{day}</b>{lv}'
                   f'<span class="meta">{meta}</span><span class="go">阅读 →</span></a></li>')
    return (
        '<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<title>速卖通选品情报 · 历史归档</title>\n<style>\n'
        f'{ARCHIVE_CSS}\n</style></head>\n<body><div class="w">\n'
        '<h1>速卖通选品情报 · 历史归档</h1>\n'
        '<p class="sub">每天扫描到的新品各占一页；入口页永远是最新一天。</p>\n'
        '<ul>\n'
        + "\n".join(lis) + "\n"
        '</ul>\n<a class="back" href="index.html">← 回到最新一天</a>\n'
        '</div></body></html>\n'
    )


# ---------------------------------------------------------------------- git
def git(repo: str, *args: str) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("git %s 失败：%s" % (" ".join(args), (r.stderr or r.stdout).strip()))
    return r


def is_repo(path: str) -> bool:
    try:
        return git(path, "rev-parse", "--is-inside-work-tree").stdout.strip() == "true"
    except Exception:
        return False


# ---------------------------------------------------------------------- 主流程
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="把扫描库的每日新品发布到 GitHub Pages")
    ap.add_argument("--db", default=DB, help="products.db 路径")
    ap.add_argument("--out", default=OUT, help="静态站仓库目录")
    ap.add_argument("--date", action="append", default=None,
                    help="只发布指定日期（可重复，或用逗号分隔）")
    ap.add_argument("--list", action="store_true", help="只列出 DB 里的新品日与件数")
    ap.add_argument("--dry-run", action="store_true", help="只报告会改哪些文件，不写不提交")
    ap.add_argument("--no-commit", action="store_true", help="写文件但不提交")
    ap.add_argument("--no-push", action="store_true", help="提交但不推送")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.db):
        print("[ERROR] 找不到数据库：%s" % args.db)
        return 2

    conn = sqlite3.connect("file:%s?mode=ro" % args.db.replace("\\", "/"), uri=True)
    try:
        by_day, stats, _ = load(conn)
    finally:
        conn.close()

    if args.list:
        print("DB 新品日共 %d 天：" % len(by_day))
        for d in sorted(by_day):
            print("  %s  新增 %3d 件  扫描 %d 次" % (d, len(by_day[d]), stats[d]["runs"]))
        return 0

    old_pages = existing_pages(args.out)
    all_days = sorted(set(by_day) | set(old_pages))     # 已发布过的页永不消失
    counts = {d: len(by_day.get(d, [])) for d in all_days}
    total = len(all_days)

    targets = list(all_days)
    if args.date:
        want = set()
        for v in args.date:
            want.update(x.strip() for x in v.split(",") if x.strip())
        targets = [d for d in all_days if d in want]
        missing = sorted(want - set(all_days))
        if missing:
            print("[WARN] 这些日期在库里没有新品，跳过：%s" % ", ".join(missing))
        if not targets:
            print("没有要发布的日期。")
            return 0

    print("发布目录：%s" % args.out)
    print("已发布日页 %d 期，DB 新品日 %d 期，合并后共 %d 期" % (len(old_pages), len(by_day), total))

    files: dict[str, str] = {}
    for day in targets:
        items = by_day.get(day)
        if not items:                      # 只有旧页、库里没有明细 → 保留原文件不动
            continue
        i = all_days.index(day)
        prev = all_days[i - 1] if i > 0 else None
        nxt = all_days[i + 1] if i + 1 < total else None
        files[day + ".html"] = render_day(day, items, stats[day], i + 1, total, prev, nxt)

    # index.html = 最新一天；archive 列出全部
    newest = all_days[-1]
    if newest + ".html" in files:
        files["index.html"] = files[newest + ".html"]
    elif os.path.isfile(os.path.join(args.out, newest + ".html")):
        with open(os.path.join(args.out, newest + ".html"), encoding="utf-8") as f:
            files["index.html"] = f.read()
    files["archive.html"] = render_archive(list(reversed(all_days)), counts, stats)

    changed = []
    for name, text in files.items():
        p = os.path.join(args.out, name)
        old = None
        if os.path.isfile(p):
            with open(p, encoding="utf-8", newline="") as f:
                old = f.read()
        if old != text:
            changed.append(name)

    new_days = [d for d in targets if d not in old_pages and (d + ".html") in files]
    if not changed:
        print("无变化，跳过提交。")
        return 0

    print("需要更新 %d 个文件%s" % (
        len(changed), ("，新增日页：" + ", ".join("%s(%d 件)" % (d, counts[d]) for d in new_days))
        if new_days else ""))

    if args.dry_run:
        for name in sorted(changed):
            print("  ~ %s" % name)
        print("[dry-run] 未写入。")
        return 0

    os.makedirs(args.out, exist_ok=True)
    for name in changed:
        with open(os.path.join(args.out, name), "w", encoding="utf-8", newline="") as f:
            f.write(files[name])
    print("已写入 %d 个文件。" % len(changed))

    if args.no_commit:
        print("已跳过 git 提交。")
        return 0
    if not is_repo(args.out):
        print("[WARN] %s 不是 git 仓库，只写了文件。" % args.out)
        return 0

    # 逐期提交：一期一条 commit，message 与历史一致
    commits = []
    page_files = [c for c in changed if PAGE_RE.match(c)]
    tail_files = [c for c in changed if not PAGE_RE.match(c)]
    if new_days:
        for k, day in enumerate(new_days):
            batch = [f for f in page_files
                     if PAGE_RE.match(f).group(1) <= day]
            batch = [f for f in batch if f not in sum((b for _, b in commits), [])]
            if k == len(new_days) - 1:
                batch += tail_files
            if not batch:
                continue
            git(args.out, "add", "--", *batch)
            git(args.out, "commit", "-m", "digest: %s 选品扫描简报" % day)
            commits.append((day, batch))
            print("commit: digest: %s 选品扫描简报（%d 个文件）" % (day, len(batch)))
    else:
        day = targets[-1]
        git(args.out, "add", "--", *changed)
        git(args.out, "commit", "-m", "digest: %s 选品扫描简报" % day)
        commits.append((day, changed))
        print("commit: digest: %s 选品扫描简报（%d 个文件）" % (day, len(changed)))

    if args.no_push:
        print("已跳过 git push。")
        return 0
    try:
        git(args.out, "push", "origin", "HEAD")
        print("已推送到 origin（%s）" % git(args.out, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip())
    except RuntimeError as exc:
        print("[WARN] push 失败：%s" % exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
