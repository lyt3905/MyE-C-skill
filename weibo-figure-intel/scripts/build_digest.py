#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""手办情报简报生成器

读取结构化情报 JSON（由 agent 精抽后写入），渲染成简报。
默认同时产出 Markdown（存档/粘贴）与 HTML（浏览器阅读、可点链接跳原博）。

用法：
    python build_digest.py --input data/intel-2026-09-12.json
    python build_digest.py --input xxx.json --format html
    python build_digest.py --input xxx.json --validate-only
"""

import argparse
import html as htmllib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(SKILL_DIR, "output")
CST = timezone(timedelta(hours=8))

TYPE_ORDER = [
    "新品公布", "开订", "发售", "再版", "延期", "展会",
    "实物测评", "促销", "其他",
]

RELEVANCE_ORDER = {"高": 0, "中": 1, "低": 2, "": 3}

COLUMNS = ["厂商", "角色 / 作品", "产品线", "参考价", "发售", "情报摘要", "来源"]


def norm_type(value):
    v = (value or "").strip()
    for t in TYPE_ORDER:
        if t == v:
            return t
    # 容忍近义写法
    alias = {
        "预定": "开订", "预订": "开订", "开预定": "开订", "新品": "新品公布",
        "公布": "新品公布", "新品情报": "新品公布", "发售情报": "发售",
        "再版/复刻": "再版", "复刻": "再版", "测评": "实物测评", "评测": "实物测评",
        "延期通知": "延期", "砍单": "延期",
    }
    return alias.get(v, "其他")


def cell(value):
    if value is None:
        return "—"
    s = str(value).strip()
    if not s:
        return "—"
    return s.replace("|", "\\|").replace("\n", " ")


def validate(data):
    problems = []
    if not isinstance(data, dict):
        return ["顶层不是 JSON 对象"]
    items = data.get("items")
    if not isinstance(items, list):
        problems.append("缺少 items 数组")
        return problems
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            problems.append(f"items[{i}] 不是对象")
            continue
        if not (it.get("summary") or it.get("intel_type")):
            problems.append(f"items[{i}] 既没有 summary 也没有 intel_type")
        if not it.get("url") and not it.get("post_id"):
            problems.append(f"items[{i}] 缺少 url 与 post_id，无法回溯来源")
    return problems


def render_group(name, items):
    lines = [f"### {name}（{len(items)} 条）", ""]
    lines.append("| " + " | ".join(COLUMNS) + " |")
    lines.append("|" + "---|" * len(COLUMNS))
    for it in items:
        subject = " / ".join(filter(None, [
            (it.get("character") or "").strip(),
            (it.get("ip") or "").strip(),
        ])) or "—"
        source = it.get("url") or ""
        blogger = (it.get("blogger") or "原博").strip()
        src = f"[{blogger}]({source})" if source else blogger
        if it.get("posted_at"):
            src += f"<br/>{cell(it['posted_at'])}"
        lines.append("| " + " | ".join([
            cell(it.get("brand")),
            cell(subject),
            cell(it.get("line")),
            cell(it.get("price")),
            cell(it.get("release_date")),
            cell(it.get("summary")),
            src,
        ]) + " |")
    lines.append("")
    return lines


def build(data):
    items = [dict(it) for it in data.get("items", [])]
    for it in items:
        it["_type"] = norm_type(it.get("intel_type"))
        it["_rel"] = (it.get("relevance") or "").strip()

    date = data.get("date") or datetime.now(CST).strftime("%Y-%m-%d")

    high = [i for i in items if i["_rel"] == "高"]
    groups = {}
    for it in items:
        groups.setdefault(it["_type"], []).append(it)

    ordered_types = [t for t in TYPE_ORDER if t in groups]
    ordered_types += [t for t in groups if t not in TYPE_ORDER]

    out = [f"# 手办 / 可动人偶情报 · {date}", ""]
    meta = []
    if data.get("source_note"):
        meta.append(data["source_note"])
    meta.append(f"共提取 **{len(items)}** 条情报")
    if high:
        meta.append(f"其中 **{len(high)}** 条与选品高度相关")
    if data.get("generated_at"):
        meta.append(f"生成于 {data['generated_at']}")
    out.append("　".join(meta))
    out.append("")

    if high:
        out.append("## 重点关注")
        out.append("")
        for it in sorted(high, key=lambda x: (TYPE_ORDER.index(x["_type"])
                                             if x["_type"] in TYPE_ORDER else 99,
                                             RELEVANCE_ORDER.get(x["_rel"], 3))):
            reason = (it.get("relevance_reason") or "").strip()
            head = " · ".join(filter(None, [
                (it.get("brand") or "").strip(),
                " / ".join(filter(None, [(it.get("character") or "").strip(),
                                         (it.get("ip") or "").strip()])),
                (it.get("line") or "").strip(),
            ]))
            out.append(f"- **[{it['_type']}] {head or it.get('summary', '')}**")
            if it.get("summary") and head:
                out.append(f"  - {it['summary']}")
            facts = []
            for label, key in (("参考价", "price"), ("发售", "release_date"),
                               ("渠道", "channel"), ("比例", "scale")):
                if (it.get(key) or "").strip():
                    facts.append(f"{label} {it[key]}")
            if facts:
                out.append(f"  - {'　'.join(facts)}")
            if reason:
                out.append(f"  - 相关理由：{reason}")
            if it.get("url"):
                out.append(f"  - 来源：[{it.get('blogger') or '原博'}]({it['url']})"
                           + (f"（{it['posted_at']}）" if it.get("posted_at") else ""))
        out.append("")

    out.append("## 全部情报")
    out.append("")
    for t in ordered_types:
        group = sorted(groups[t], key=lambda x: RELEVANCE_ORDER.get(x["_rel"], 3))
        out.extend(render_group(t, group))

    out.append("---")
    out.append("")
    out.append("*由 weibo-figure-intel skill 生成；原始微博见 data/ 目录下的采集结果。*")
    return out, date, len(items), items


# --------------------------------------------------------------------------- HTML

TYPE_CLASS = {
    "新品公布": "t-new", "开订": "t-open", "发售": "t-sale", "再版": "t-reprint",
    "延期": "t-delay", "展会": "t-event", "实物测评": "t-review",
    "促销": "t-promo", "其他": "t-other",
}
REL_CLASS = {"高": "r-high", "中": "r-mid", "低": "r-low"}

HTML_CSS = """
:root{
  --bg:#f5f6f8; --card:#fff; --line:#e4e7ec; --ink:#16181d; --ink2:#5a6472;
  --ink3:#8b95a3; --accent:#2f6fed; --accent-soft:#eaf1fe;
  --high:#c5221f; --high-bg:#fdeceb; --mid:#1558c0; --mid-bg:#e8f0fe;
  --low:#5f6b7a; --low-bg:#eef0f3;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",
       "PingFang SC","Hiragino Sans GB",sans-serif;
}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px}

/* 顶栏 */
.top{background:var(--card);border-bottom:1px solid var(--line);
     position:sticky;top:0;z-index:9}
.top .inner{padding:22px 0 14px}
h1{margin:0 0 6px;font-size:22px;letter-spacing:.2px}
.sub{color:var(--ink2);font-size:13.5px}
.stat{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.stat span{background:var(--bg);border:1px solid var(--line);border-radius:999px;
  padding:3px 11px;font-size:12.5px;color:var(--ink2)}
.stat span b{color:var(--ink);font-weight:600}

/* 控件 */
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;
  margin-top:14px;padding-bottom:12px}
#q{flex:1 1 260px;min-width:200px;padding:8px 12px;border:1px solid var(--line);
  border-radius:8px;font-size:14px;font-family:inherit;background:var(--bg)}
#q:focus{outline:2px solid var(--accent-soft);border-color:var(--accent);
  background:var(--card)}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{border:1px solid var(--line);background:var(--card);color:var(--ink2);
  border-radius:999px;padding:5px 12px;font-size:12.5px;cursor:pointer;
  font-family:inherit;transition:.12s}
.chip:hover{border-color:#c9d2de;color:var(--ink)}
.chip.on{background:var(--accent);border-color:var(--accent);color:#fff}
.count{color:var(--ink3);font-size:12.5px;margin-left:auto;white-space:nowrap}

/* 卡片 */
main{padding:20px 0 60px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));
  gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:16px 17px 14px;display:flex;flex-direction:column;gap:9px}
.card:hover{border-color:#cfd8e5;box-shadow:0 2px 10px rgba(20,30,50,.06)}
.head{display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.badge{font-size:11.5px;padding:2px 9px;border-radius:6px;font-weight:600;
  letter-spacing:.2px}
.t-new{background:#ede7fd;color:#5b3ec8}
.t-open{background:#e3f5ea;color:#1a7a45}
.t-sale{background:#fdeee2;color:#a8541a}
.t-reprint{background:#e6f1f7;color:#1a6285}
.t-delay{background:#fdeceb;color:#b3261e}
.t-event{background:#fdf3dc;color:#8a6412}
.t-review{background:#eaeaf0;color:#4d5364}
.t-promo{background:#fce8f3;color:#a1336e}
.t-other{background:#eef0f3;color:#5f6b7a}
.rel{font-size:11.5px;padding:2px 8px;border-radius:6px;font-weight:600}
.r-high{background:var(--high-bg);color:var(--high)}
.r-mid{background:var(--mid-bg);color:var(--mid)}
.r-low{background:var(--low-bg);color:var(--low)}
.time{margin-left:auto;color:var(--ink3);font-size:12px;white-space:nowrap}
.card h3{margin:0;font-size:15.5px;line-height:1.45;font-weight:650}
.card h3 .brand{color:var(--ink)}
.card h3 .line{color:var(--ink2);font-weight:500;font-size:13.5px}
.sum{margin:0;color:var(--ink2);font-size:13.5px}
.facts{display:flex;flex-wrap:wrap;gap:6px;margin:1px 0 0}
.facts i{font-style:normal;background:var(--bg);border:1px solid var(--line);
  border-radius:6px;padding:2px 8px;font-size:12.5px;color:var(--ink2)}
.facts i b{color:var(--ink);font-weight:600;margin-right:3px}
.why{background:#fbfaf4;border-left:3px solid #e0c98a;border-radius:4px;
  padding:7px 10px;font-size:12.5px;color:#6b5a24}
.foot{margin-top:auto;padding-top:4px;display:flex;align-items:center;
  gap:10px;flex-wrap:wrap}
.src{display:inline-flex;align-items:center;gap:5px;font-size:13px;
  font-weight:600;background:var(--accent-soft);border-radius:8px;
  padding:6px 12px}
.src:hover{background:#dce8fd;text-decoration:none}
.tags{display:flex;gap:5px;flex-wrap:wrap}
.tags em{font-style:normal;font-size:11.5px;color:var(--ink3)}
.empty{text-align:center;color:var(--ink3);padding:60px 0;font-size:14px}
.legend{margin:18px 0 10px;color:var(--ink3);font-size:12.5px}
@media(max-width:640px){
  .grid{grid-template-columns:1fr}
  h1{font-size:19px}
  .count{margin-left:0;width:100%}
}
@media print{
  .top{position:static}.controls{display:none}
  body{background:#fff}.card{break-inside:avoid;box-shadow:none}
}
"""

HTML_JS = """
(function(){
  var q = document.getElementById('q');
  var cards = [].slice.call(document.querySelectorAll('.card'));
  var typeChips = [].slice.call(document.querySelectorAll('[data-type-chip]'));
  var relChips  = [].slice.call(document.querySelectorAll('[data-rel-chip]'));
  var out = document.getElementById('count');
  var empty = document.getElementById('empty');
  var state = {type:'全部', rel:'全部'};

  function match(c){
    if (state.type !== '全部' && c.dataset.type !== state.type) return false;
    if (state.rel === '高' && c.dataset.rel !== '高') return false;
    var t = (q.value || '').trim().toLowerCase();
    if (t && (c.dataset.search || '').indexOf(t) === -1) return false;
    return true;
  }
  function apply(){
    var n = 0;
    cards.forEach(function(c){
      var ok = match(c);
      c.style.display = ok ? '' : 'none';
      if (ok) n++;
    });
    out.textContent = '显示 ' + n + ' / ' + cards.length + ' 条';
    empty.style.display = n ? 'none' : '';
  }
  typeChips.forEach(function(b){
    b.addEventListener('click', function(){
      state.type = b.dataset.typeChip;
      typeChips.forEach(function(x){ x.classList.toggle('on', x === b); });
      apply();
    });
  });
  relChips.forEach(function(b){
    b.addEventListener('click', function(){
      state.rel = b.dataset.relChip;
      relChips.forEach(function(x){ x.classList.toggle('on', x === b); });
      apply();
    });
  });
  q.addEventListener('input', apply);
  document.addEventListener('keydown', function(e){
    if (e.key === '/' && document.activeElement !== q){ e.preventDefault(); q.focus(); }
    if (e.key === 'Escape' && document.activeElement === q){ q.value=''; apply(); q.blur(); }
  });
  apply();
})();
"""

HTML_TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>__CSS__</style>
</head>
<body>
<header class="top">
  <div class="wrap inner">
    <h1>__H1__</h1>
    <div class="sub">__SUBTITLE__</div>
    <div class="stat">__STATS__</div>
    <div class="controls">
      <input id="q" type="search" placeholder="搜索厂商 / 角色 / 产品线 / 摘要…（按 / 聚焦）">
      <div class="chips" id="typeChips">__TYPECHIPS__</div>
      <div class="chips" id="relChips">__RELCHIPS__</div>
      <span class="count" id="count"></span>
    </div>
  </div>
</header>
<main class="wrap">
  <div class="grid" id="grid">__CARDS__</div>
  <div class="empty" id="empty" style="display:none">没有匹配的情报，换个关键词或筛选条件试试。</div>
  <div class="legend">__LEGEND__　·　点击卡片底部的按钮可跳转原始微博（需在浏览器登录微博）。</div>
</main>
<script>__JS__</script>
</body>
</html>
"""


def render_html(data, items, date):
    """把结构化情报渲染成单文件 HTML（无外部依赖，双击即可看）。"""
    groups = {}
    for it in items:
        groups.setdefault(it["_type"], []).append(it)
    ordered_types = [t for t in TYPE_ORDER if t in groups]
    ordered_types += [t for t in groups if t not in TYPE_ORDER]

    high_n = sum(1 for it in items if it["_rel"] == "高")

    chips = ['<button class="chip on" data-type-chip="全部">全部</button>']
    for t in ordered_types:
        chips.append(f'<button class="chip" data-type-chip="{htmllib.escape(t, quote=True)}">'
                     f'{htmllib.escape(t)} <span style="opacity:.6">{len(groups[t])}</span></button>')
    rel_chips = ['<button class="chip on" data-rel-chip="全部">不限相关度</button>']
    if high_n:
        rel_chips.append(f'<button class="chip" data-rel-chip="高">仅高相关 {high_n}</button>')

    cards = []
    for t in ordered_types:
        for it in sorted(groups[t], key=lambda x: RELEVANCE_ORDER.get(x["_rel"], 3)):
            cards.append(render_card(it))

    stats = [f'共 <b>{len(items)}</b> 条情报']
    if high_n:
        stats.append(f'其中 <b>{high_n}</b> 条高相关')
    for t in ordered_types:
        stats.append(f'{htmllib.escape(t)} <b>{len(groups[t])}</b>')
    if data.get("generated_at"):
        stats.append(f'生成于 {htmllib.escape(str(data["generated_at"]))}')

    subtitle = htmllib.escape(data.get("source_note") or "微博关注列表情报采集")

    return (HTML_TPL
            .replace("__CSS__", HTML_CSS)
            .replace("__JS__", HTML_JS)
            .replace("__TITLE__", f"手办情报 · {date}")
            .replace("__H1__", f"手办 / 可动人偶情报　<span style=\"font-size:15px;color:#8b95a3;font-weight:400\">{htmllib.escape(date)}</span>")
            .replace("__SUBTITLE__", subtitle)
            .replace("__STATS__", "".join(f"<span>{s}</span>" for s in stats))
            .replace("__TYPECHIPS__", "".join(chips))
            .replace("__RELCHIPS__", "".join(rel_chips))
            .replace("__CARDS__", "\n".join(cards))
            .replace("__LEGEND__", "*由 weibo-figure-intel 生成，数据取自微博关注列表*"))


def render_card(it):
    t, rel = it["_type"], it["_rel"]
    e = lambda k: htmllib.escape(str(it.get(k) or "").strip())

    subject = " / ".join(filter(None, [e("character"), e("ip")]))
    head_bits = []
    if e("brand"):
        head_bits.append(f'<span class="brand">{e("brand")}</span>')
    if subject:
        head_bits.append(f'<span class="brand">{subject}</span>')
    if e("line"):
        head_bits.append(f'<span class="line">{e("line")}</span>')
    title = " · ".join(head_bits) if head_bits else e("summary")

    facts = []
    for label, key in (("参考价", "price"), ("发售", "release_date"),
                       ("渠道", "channel"), ("比例", "scale")):
        if e(key):
            facts.append(f'<i><b>{label}</b>{e(key)}</i>')

    url = (it.get("url") or "").strip()
    blogger = e("blogger") or "原博"
    if url:
        src = (f'<a class="src" href="{htmllib.escape(url, quote=True)}" '
               f'target="_blank" rel="noopener noreferrer">打开原博 ↗'
               f'<span style="font-weight:400;opacity:.75">@{blogger}</span></a>')
    else:
        pid = e("post_id")
        src = f'<span class="src" style="background:#eef0f3;color:#5f6b7a">post_id {pid}</span>'

    tags = "".join(f"<em>#{htmllib.escape(str(x))}</em>"
                   for x in (it.get("tags") or []) if x)

    search = " ".join(str(it.get(k) or "") for k in
                      ("brand", "ip", "character", "line", "summary", "blogger",
                       "price", "release_date", "channel", "scale", "intel_type")
                      ).lower()

    parts = ['<article class="card"',
             f' data-type="{htmllib.escape(t, quote=True)}"',
             f' data-rel="{htmllib.escape(rel, quote=True)}"',
             f' data-search="{htmllib.escape(search, quote=True)}">']
    parts.append('<div class="head">')
    parts.append(f'<span class="badge {TYPE_CLASS.get(t, "t-other")}">{htmllib.escape(t)}</span>')
    if rel:
        parts.append(f'<span class="rel {REL_CLASS.get(rel, "r-low")}">{htmllib.escape(rel)}相关</span>')
    if e("posted_at"):
        parts.append(f'<span class="time">{e("posted_at")}</span>')
    parts.append('</div>')
    parts.append(f'<h3>{title}</h3>')
    if e("summary"):
        parts.append(f'<p class="sum">{e("summary")}</p>')
    if facts:
        parts.append('<div class="facts">' + "".join(facts) + '</div>')
    if e("relevance_reason"):
        parts.append(f'<div class="why">相关理由：{e("relevance_reason")}</div>')
    parts.append('<div class="foot">')
    parts.append(src)
    if tags:
        parts.append(f'<span class="tags">{tags}</span>')
    parts.append('</div></article>')
    return "".join(parts)


def main():
    ap = argparse.ArgumentParser(description="生成手办情报简报（Markdown / HTML）")
    ap.add_argument("--input", required=True, help="结构化情报 JSON")
    ap.add_argument("--out", help="输出 Markdown 路径（--format md/both 时生效）")
    ap.add_argument("--html-out", help="输出 HTML 路径（--format html/both 时生效）")
    ap.add_argument("--format", choices=["md", "html", "both"], default="both",
                    help="输出格式，默认 both（Markdown + HTML）")
    ap.add_argument("--validate-only", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ 找不到输入文件：{args.input}")
        return 1

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    problems = validate(data)
    if problems:
        print("❌ 情报 JSON 校验未通过：")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"校验通过：{len(data.get('items', []))} 条情报")

    if args.validate_only:
        return 0

    lines, date, count, items = build(data)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    written = []
    if args.format in ("md", "both"):
        out = args.out or os.path.join(OUTPUT_DIR, f"手办情报-{date}.md")
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        written.append(out)

    if args.format in ("html", "both"):
        if not items:
            print("⚠️ 没有情报条目，跳过 HTML 输出")
        else:
            out = args.html_out or os.path.join(OUTPUT_DIR, f"手办情报-{date}.html")
            with open(out, "w", encoding="utf-8") as f:
                f.write(render_html(data, items, date))
            written.append(out)

    for p in written:
        print(f"简报已生成：{p}")
    print(f"共 {count} 条情报")
    return 0


if __name__ == "__main__":
    sys.exit(main())
