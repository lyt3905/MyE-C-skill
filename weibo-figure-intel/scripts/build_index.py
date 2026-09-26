#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""手办情报总览页生成器（跨天汇总单页）

把 data/intel-*.json 里所有日期的情报合并到**一个页面**，顶部一条日期切换器，
点某一天就看那天的简报，点「全部」看累计视图。解决「每天一个 HTML、要翻好几个
文件才能对比」的问题。

与 build_digest.py 的分工：
  build_digest.py  单日简报（每天一份 HTML + MD）
  build_index.py   跨天总览（一个 HTML，内部含所有日期）

渲染层完全复用 build_digest：is_new / dedupe_items / render_card / thumb_src
等直接 import，因此两个页面的卡片样式、新品判定、同款合并规则永远一致。

用法：
    python build_index.py                       # 扫描 data/intel-*.json 全量
    python build_index.py --days 7              # 只收最近 7 天
    python build_index.py --open-view all       # 默认落在「全部情报」视图
"""

import argparse
import glob
import html as htmllib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import build_digest as bd  # noqa: E402  渲染层复用，勿复制粘贴

OUTPUT_DIR = os.path.join(SKILL_DIR, "output")
DATA_DIR = os.path.join(SKILL_DIR, "data")
CST = timezone(timedelta(hours=8))

# data/ 下的日期化产物：intel-2026-09-26.json 以及 intel-20260917-rescue.json。
# 后者带后缀（补跑），也要认得——用宽松正则抓出日期部分。
_FNAME_PAT = re.compile(r"^intel-(\d{4})-?(\d{2})-?(\d{2})")


def collect_inputs(days=None, include_suffix=True):
    """扫描 data/intel-*.json，返回按日期升序的 [(date, path)]。

    同一天有多个文件（如 intel-20260917.json + intel-20260917-run2.json）时全部收下，
    页面里合并展示——总览页要的是「这一天出现过什么」，不是文件粒度。
    """
    out = []
    for p in sorted(glob.glob(os.path.join(DATA_DIR, "intel-*.json"))):
        name = os.path.basename(p)
        m = _FNAME_PAT.match(name)
        if not m:
            continue
        y, mo, d = m.groups()
        date = f"{y}-{mo}-{d}"
        out.append((date, p))

    if days and out:
        latest = max(d for d, _ in out)
        try:
            cutoff = (datetime.strptime(latest, "%Y-%m-%d")
                      - timedelta(days=days - 1)).strftime("%Y-%m-%d")
            out = [(d, p) for d, p in out if d >= cutoff]
        except ValueError:
            pass
    return out


def load_days(pairs):
    """读取并归一化每一天的情报，返回 {date: [items]}（日期升序的 dict）。"""
    days = {}
    for date, path in pairs:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as ex:
            print(f"⚠️ 跳过 {os.path.basename(path)}：{ex}")
            continue
        problems = bd.validate(data)
        if problems:
            print(f"⚠️ {os.path.basename(path)} 校验有问题，仍尝试渲染：")
            for p in problems:
                print(f"   - {p}")
        items = []
        for it in data.get("items", []):
            if not isinstance(it, dict):
                continue
            it = dict(it)
            it["_type"] = bd.norm_type(it.get("intel_type"))
            it["_rel"] = (it.get("relevance") or "").strip()
            it["_date"] = date
            items.append(it)
        if items:
            days[date] = items
    return days


def merge_across_days(days):
    """跨天合并同款产品：同一款在不同天被多次报道，合成一张卡。

    以「天」为单位先各自去重（吸收日内重复），再把各天的同键条目并到一起，
    主卡取信息最全的一条；其余来源收进 also_sources，并记录出现过的日期区间，
    让主人一眼看出「这款是 09-17 首报、09-25 还在被报道」。
    """
    merged = {}        # key -> main item
    solo = []          # 无法成键的条目（品牌缺失等），原样保留
    order = []         # 保持稳定顺序

    for date in sorted(days):
        for it in bd.dedupe_items(days[date]):
            key = bd.make_key(it.get("brand"), it.get("character"), it.get("line"))
            if key is None:
                # 无法成键（品牌缺失、或品牌有但角色/产品线是泛词）。
                # 同样要补 _dates，否则日期标记与按天筛选都会漏掉这批条目
                # （2026-09-26 踩坑：28 条 solo 条目全都没有日期）。
                it = dict(it)
                it["_dates"] = [date]
                solo.append(it)
                continue
            if key not in merged:
                it = dict(it)
                it["_dates"] = [date]
                merged[key] = it
                order.append(key)
                continue
            main = merged[key]

            # 补齐主卡缺失的关键字段
            for k in ("price", "release_date", "channel", "scale",
                      "relevance_reason", "character", "ip", "line"):
                if not (main.get(k) or "").strip() and (it.get(k) or "").strip():
                    main[k] = it[k]
            if bd.rel_rank(it) < bd.rel_rank(main):
                main["_rel"] = it["_rel"]
                main["relevance"] = it.get("relevance")

            # 主卡类型：本体优先（新品公布 > 开订 > 发售 > 再版）
            kinds = [main["_type"]] + list(main.get("also_kinds") or [])
            if it["_type"] not in kinds:
                kinds.append(it["_type"])
            kinds.sort(key=lambda t: bd.NEW_KIND_ORDER.index(t)
                       if t in bd.NEW_KIND_ORDER else 99)
            if kinds and kinds[0] != main["_type"]:
                main["_type"] = kinds[0]
            if len(kinds) > 1:
                main["also_kinds"] = kinds[1:]

            # 其余报道：并入 also_sources，跨天去重
            srcs = list(main.get("also_sources") or [])
            seen = {(s.get("url") or "") + "|" + (s.get("blogger") or "") for s in srcs}
            seen.add((main.get("url") or "") + "|" + (main.get("blogger") or ""))
            sig = (it.get("url") or "") + "|" + (it.get("blogger") or "")
            if (it.get("url") or it.get("post_id")) and sig not in seen:
                srcs.append({"blogger": it.get("blogger") or "原博",
                             "url": it.get("url") or "",
                             "posted_at": it.get("posted_at") or ""})
            if srcs:
                main["also_sources"] = srcs

            # 配图并集
            imgs = list(main.get("images") or [])
            have = set(imgs)
            for u in (it.get("images") or []):
                if u and u not in have:
                    have.add(u)
                    imgs.append(u)
            if imgs:
                main["images"] = imgs

            if date not in main["_dates"]:
                main["_dates"].append(date)
            # 首报时间取更早的一条
            if (it.get("posted_at") or "") and (
                    not main.get("posted_at") or it["posted_at"] < main["posted_at"]):
                main["posted_at"] = it.get("posted_at")

    items = [merged[k] for k in order] + solo
    # 排序：最新报道时间倒序，其次新报道日期倒序，最后用 key 兜底保证稳定
    # （原来用 (posted_at, _dates[0]) 元组，posted_at 为空时会把新条目挤到最后）
    def sort_key(x):
        ds = sorted(x.get("_dates") or [])
        return (x.get("posted_at") or "", ds[-1] if ds else "",
                (x.get("brand") or "") + (x.get("character") or ""))
    items.sort(key=sort_key, reverse=True)
    return items


def date_span(it):
    """跨天合并后的日期区间文案：09-17 首报 · 09-25 最新。"""
    ds = sorted(it.get("_dates") or [])
    if not ds:
        return ""
    def short(d):
        parts = d.split("-")
        return f"{parts[1]}-{parts[2]}" if len(parts) == 3 else d
    if len(ds) == 1:
        return short(ds[0])
    return f"{short(ds[0])} → {short(ds[-1])}"


def attach_media_paths(days, all_items):
    """让总览页的缩略图走**本地相对路径**，而不是 base64 内嵌。

    为什么必须这样（2026-09-26 实测）：
      单日简报一天只有 ~20 张卡，把缩略图 base64 内嵌进 HTML 换来「单文件也能看图」，
      80KB 的图换 35KB 文本，划算。但总览页是跨天累计——13 天 1045 张卡、2233 个
      缩略图槽位，同样的做法直接顶到 **80MB**，浏览器打开要卡好几秒，滚动也掉帧。
      而且总览页本来就必须连 media/ 目录一起交付（放大预览走 media/view/ 相对路径），
      既然媒体目录无论如何都要给，缩略图就没必要内嵌。

      实测拆分：78.2MB 是 base64（平均每张 35.9KB，且三个视图重复内嵌同一张图，
      780 张唯一图被塞了 2233 次），去掉后页面只剩约 2MB。

    缩略图取图顺序：
      ① media/thumb/<name>（15–30KB，省流量）
      ② media/view/<name> （70KB，日更时只给前 3 张下过 thumb，绝大多数图只有 view）
    """
    def thumb_path(url):
        name = bd._img_name(url)
        if not name:
            return ""
        if os.path.exists(os.path.join(bd.MEDIA_DIR, "thumb", name)):
            return f"{bd.MEDIA_REL}/thumb/{name}"
        if os.path.exists(os.path.join(bd.MEDIA_DIR, "view", name)):
            return f"{bd.MEDIA_REL}/view/{name}"
        return bd.img_variant(url, "orj360")     # 本地没有才回退外链

    def thumb_src_local(url):
        return thumb_path(url)

    # 渲染期改用本地路径版本（build_digest 的 thumb_src 保持原样，单日简报不受影响）
    bd.thumb_src = thumb_src_local

    missing = set()
    for items in days.values():
        for it in items:
            for u in (it.get("images") or []):
                n = bd._img_name(u)
                if n and not os.path.exists(os.path.join(bd.MEDIA_DIR, "thumb", n)) \
                        and not os.path.exists(os.path.join(bd.MEDIA_DIR, "view", n)):
                    missing.add(n)
    return missing


# --------------------------------------------------------------------------- CSS

EXTRA_CSS = """
/* 日期切换器：总览页的入口控件 */
.datebar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;
  margin-top:14px;padding-bottom:12px;border-bottom:1px solid var(--line)}
.datebar .lab{font-size:12.5px;color:var(--ink3);margin-right:2px;
  white-space:nowrap}
.dchip{border:1px solid var(--line);background:var(--card);color:var(--ink2);
  border-radius:8px;padding:5px 11px;font-size:12.5px;cursor:pointer;
  font-family:inherit;transition:.12s;white-space:nowrap;
  display:inline-flex;align-items:center;gap:5px}
.dchip:hover{border-color:#c9d2de;color:var(--ink)}
.dchip.on{background:var(--accent);border-color:var(--accent);color:#fff}
.dchip .n{font-size:11px;opacity:.68}
.dchip.on .n{opacity:.85}
.dchip.allday{font-weight:600}

/* 跨天出现标记 */
.span{font-size:11.5px;color:var(--ink3);background:var(--bg);
  border:1px dashed var(--line);border-radius:6px;padding:1px 7px;
  white-space:nowrap}

/* 按天分组时的天标题 */
.dayhead{display:flex;align-items:center;gap:10px;margin:24px 0 12px;
  padding-bottom:9px;border-bottom:1px solid var(--line);flex-wrap:wrap}
.dayhead h2{margin:0;font-size:16px;font-weight:650;letter-spacing:.2px}
.dayhead .dh{color:var(--ink3);font-size:12.5px;font-weight:400}
.dayhead .dlink{margin-left:auto;font-size:12.5px}

/* 日期跳转区（按天分组视图的快速导航） */
.daynav{position:sticky;top:0;z-index:5;background:var(--card);
  border-bottom:1px solid var(--line);padding:8px 0;display:none}
.daynav.on{display:block}
.daynav .wrap{display:flex;flex-wrap:wrap;gap:6px;align-items:center;
  padding-top:0;padding-bottom:0}
.daynav a{font-size:12.5px;padding:3px 9px;border-radius:7px;
  background:var(--bg);border:1px solid var(--line);color:var(--ink2)}
.daynav a:hover{color:var(--accent);border-color:var(--accent);text-decoration:none}
"""


# --------------------------------------------------------------------------- 渲染

def render_index(days, all_items, default_view="new"):
    """渲染总览单页。

    结构：
      #groups
        section.group-days        ← 「按天浏览」视图：一天一节，节内按类型分组
        section.group-new         ← 「跨天新品清单」视图：脱离日期与分类的纯清单
        section.group-all         ← 「全部情报」视图：跨天合并后按类型分组
    """
    dates = sorted(days)                       # 升序

    # ---- 统计 ----
    new_items = [it for it in all_items if bd.is_new(it)]
    high_n = sum(1 for it in all_items if it["_rel"] == "高")

    # ---- 日期切换器 ----
    dchips = ['<button class="dchip allday on" type="button" data-day="全部">'
              f'全部 <span class="n">{len(all_items)}</span></button>']
    for d in reversed(dates):                  # 新日期排前面
        n = len(days[d])
        label = d[5:]                          # 09-26
        dchips.append(
            f'<button class="dchip" type="button" data-day="{htmllib.escape(d, quote=True)}">'
            f'{label} <span class="n">{n}</span></button>')

    # ---- 视图切换 ----
    views = [f'<button class="view on" type="button" data-view="new">'
             f'<b>🆕 新品清单</b><span class="vh">{len(new_items)} 件</span></button>',
             f'<button class="view" type="button" data-view="all">'
             f'全部情报<span class="vh">{len(all_items)} 条</span></button>',
             f'<button class="view" type="button" data-view="days">'
             f'按天浏览<span class="vh">{len(dates)} 天</span></button>']

    # ---- 类型 / 相关度筛选条（跨天合并后的全量统计）----
    groups = {}
    for it in all_items:
        groups.setdefault(it["_type"], []).append(it)
    ordered_types = [t for t in bd.TYPE_ORDER if t in groups]
    ordered_types += [t for t in groups if t not in bd.TYPE_ORDER]

    chips = ['<button class="chip on" data-type-chip="全部">全部</button>']
    for t in ordered_types:
        chips.append(
            f'<button class="chip" data-type-chip="{htmllib.escape(t, quote=True)}">'
            f'{htmllib.escape(t)} <span style="opacity:.6">{len(groups[t])}</span></button>')
    rel_chips = ['<button class="chip on" data-rel-chip="全部">不限相关度</button>']
    if high_n:
        rel_chips.append(f'<button class="chip" data-rel-chip="高">仅高相关 {high_n}</button>')

    sections = []

    # ① 跨天新品清单
    new_sorted = sorted(new_items, key=lambda x: bd.NEW_KIND_ORDER.index(x["_type"])
                        if x["_type"] in bd.NEW_KIND_ORDER else 99)
    if new_sorted:
        inner = "\n".join(render_card_merged(it, idx=i)
                          for i, it in enumerate(new_sorted, 1))
        sections.append(
            '<section class="group group-new" data-group="__new__">'
            '<div class="newhead"><h2>🆕 新品清单</h2>'
            f'<span class="nh">{len(new_sorted)} 件 · 跨 {len(dates)} 天累计、同款已合并</span>'
            '<span class="gbar"></span></div>'
            f'<div class="newlist">{inner}</div></section>')

    # ② 全部情报：跨天合并后按类型分组
    for t in ordered_types:
        inner = "\n".join(render_card_merged(it)
                          for it in sorted(groups[t], key=bd.rel_rank))
        sections.append(
            f'<section class="group group-all" data-group="{htmllib.escape(t, quote=True)}">'
            f'<h2><span class="badge {bd.TYPE_CLASS.get(t, "t-other")}">'
            f'{htmllib.escape(t)}</span>'
            f'<span class="gn">{len(groups[t])} 条</span>'
            f'<span class="gbar"></span></h2><div class="grid">{inner}</div></section>')

    # ③ 按天浏览：一天一节，节内按类型分组
    daynav = []
    for d in reversed(dates):                  # 新日期在前
        items_d = days[d]
        dnew = sum(1 for it in items_d if bd.is_new(it))
        anchor = "day-" + d.replace("-", "")
        daynav.append(f'<a href="#{anchor}">{d[5:]} · {len(items_d)} 条</a>')

    for d in reversed(dates):
        items_d = days[d]
        dnew = sum(1 for it in items_d if bd.is_new(it))
        anchor = "day-" + d.replace("-", "")
        dgroups = {}
        for it in bd.dedupe_items(items_d):
            dgroups.setdefault(it["_type"], []).append(it)
        dorder = [t for t in bd.TYPE_ORDER if t in dgroups]
        dorder += [t for t in dgroups if t not in bd.TYPE_ORDER]

        body = []
        for t in dorder:
            cards = "\n".join(bd.render_card(it, allow_new_in_main=True)
                              for it in sorted(dgroups[t], key=bd.rel_rank))
            body.append(
                f'<div class="group sub" data-group="{htmllib.escape(t, quote=True)}">'
                f'<h2><span class="badge {bd.TYPE_CLASS.get(t, "t-other")}">'
                f'{htmllib.escape(t)}</span>'
                f'<span class="gn">{len(dgroups[t])} 条</span>'
                f'<span class="gbar"></span></h2><div class="grid">{cards}</div></div>')

        sections.append(
            f'<section class="group group-days" id="{anchor}" '
            f'data-day="{htmllib.escape(d, quote=True)}">'
            f'<div class="dayhead"><h2>{d}</h2>'
            f'<span class="dh">{len(items_d)} 条情报 · 其中新品 {dnew} 件</span>'
            f'<a class="dlink" href="手办情报-{d}.html" target="_blank" '
            f'rel="noopener noreferrer">打开当日完整简报 ↗</a></div>'
            + "".join(body) + '</section>')

    stats = [f'累计 <b>{len(dates)}</b> 天', f'共 <b>{len(all_items)}</b> 条情报']
    if new_items:
        stats.append(f'其中新品清单 <b>{len(new_items)}</b> 条')
    if high_n:
        stats.append(f'其中 <b>{high_n}</b> 条高相关')
    stats.append(f'统计口径：同款跨天合并后')

    legend = ('<span data-only-view="new">当前为 <b>跨天新品清单</b>：'
              '把各天出现的新品合并成一份清单，同一款产品在不同天被多次报道的'
              '已合并成一张卡，卡上标注首次报道的日期。</span>'
              '<span data-only-view="all" hidden>当前为 <b>全部情报</b>：'
              '跨天合并后按类型分组，含实物测评、展会等全部类别。</span>'
              '<span data-only-view="days" hidden>当前为 <b>按天浏览</b>：'
              '一天一节，跟着日期倒序往下看，点右上角可打开当天的独立简报。</span>'
              '　·　点击右栏缩略图可放大看原图，点标题或按钮可跳转原博（需登录微博）。')

    counts_line = f"共 {len(dates)} 天 · {len(all_items)} 条情报"

    html = (TPL
            .replace("__CSS__", bd.HTML_CSS + EXTRA_CSS)
            .replace("__JS__", bd.HTML_JS + INDEX_JS)
            .replace("__TITLE__", "手办情报总览")
            .replace("__H1__", '手办 / 可动人偶情报　<span style="font-size:15px;'
                               'color:#8b95a3;font-weight:400">跨天总览</span>')
            .replace("__SUBTITLE__", htmllib.escape(counts_line))
            .replace("__STATS__", "".join(f"<span>{s}</span>" for s in stats))
            .replace("__DATES__", "".join(dchips))
            .replace("__VIEWS__", "".join(views))
            .replace("__TYPECHIPS__", "".join(chips))
            .replace("__RELCHIPS__", "".join(rel_chips))
            .replace("__DAYNAV__", "".join(daynav))
            .replace("__SECTIONS__", "\n".join(sections))
            .replace("__LEGEND__", legend))
    cls = "view-new" if default_view == "new" else \
          ("view-all" if default_view == "all" else "view-days")
    html = html.replace("<body>", f'<body class="{cls}">', 1)
    return html


def render_card_merged(it, idx=None):
    """跨天合并卡片：在标准卡片上补一个「首次报道日期」标记。"""
    card = bd.render_card(it, idx=idx)
    span = date_span(it)
    if not span:
        return card
    tag = f'<span class="span" title="这款产品在哪些天被报道过">📅 {htmllib.escape(span)}</span>'
    # 塞进卡片头部行的末尾（head 内最后一个元素之后）
    m = re.search(r'(<div class="head">.*?)(</div>)', card, re.S)
    if not m:
        return card
    return card[:m.end(1)] + tag + card[m.end(1):]


# --------------------------------------------------------------------------- JS

INDEX_JS = r"""
/* 总览页扩展：日期切换器 + 按天浏览视图
 *
 * 与 build_digest 的 HTML_JS 协同：那边的 apply() 负责类型 / 相关度 / 搜索 / 视图，
 * 本段负责日期维度和视图标记。两边都要生效，所以这里把 build_digest 的 apply
 * 包一层（monkey patch），日期过滤挂进同一个函数里统一跑——否则两边各自算一遍，
 * 计数会互相覆盖，日期筛选看起来「点了没反应」。
 */
(function(){
  var dayChips = [].slice.call(document.querySelectorAll('[data-day]'));
  var viewBtns = [].slice.call(document.querySelectorAll('[data-view]'));
  var body = document.body;

  function currentView(){
    if (body.classList.contains('view-days')) return 'days';
    if (body.classList.contains('view-all'))  return 'all';
    return 'new';
  }
  function currentDay(){
    var on = dayChips.filter(function(c){ return c.classList.contains('on'); })[0];
    return on ? on.dataset.day : '全部';
  }
  function dayOk(card){
    var sel = currentDay();
    if (sel === '全部') return true;
    var ds = (card.dataset.days || '').split(',');
    return ds.indexOf(sel) !== -1;
  }

  // 按天浏览视图里，天段落整体显隐（卡片已在天段落内部，不需要再逐个判）
  function applyDays(){
    var sel = currentDay();
    document.querySelectorAll('.group-days[data-day]').forEach(function(sec){
      sec.style.display = (sel === '全部' || sec.dataset.day === sel) ? '' : 'none';
    });
  }

  function setView(v){
    body.classList.remove('view-new','view-all','view-days');
    body.classList.add('view-' + v);
    viewBtns.forEach(function(b){ b.classList.toggle('on', b.dataset.view === v); });
    document.querySelectorAll('[data-only-view]').forEach(function(el){
      el.hidden = el.dataset.onlyView !== v;
    });
    var nav = document.getElementById('daynav');
    if (nav) nav.classList.toggle('on', v === 'days');
    var chipBox = document.getElementById('typeChips');
    if (chipBox) chipBox.style.display = (v === 'new') ? 'none' : '';
    applyDays();
  }

  dayChips.forEach(function(b){
    b.addEventListener('click', function(){
      dayChips.forEach(function(x){ x.classList.toggle('on', x === b); });
      applyDays();
      if (window.__apply) window.__apply();
    });
  });
  viewBtns.forEach(function(b){
    b.addEventListener('click', function(){
      setView(b.dataset.view);
      if (window.__apply) window.__apply();
    });
  });

  // 把日期维度插进 build_digest 的 match()：包一层 apply，先跑原逻辑，
  // 再对「当前视图真正可见」的卡片叠加日期条件，并把计数改成日期过滤后的数。
  function patch(){
    var origApply = window.__apply;
    if (typeof origApply !== 'function') return false;
    window.__apply = function(){
      origApply.apply(this, arguments);
      var v = currentView();
      var n = 0, total = 0;
      document.querySelectorAll('.card').forEach(function(c){
        // 按天浏览视图的卡片由天段落整体控制显隐，本身不参与日期筛选
        var inDays = !!(c.closest && c.closest('.group-days'));
        if (inDays !== (v === 'days')) return;      // 只数当前视图的那份 DOM
        if (!inDays && !dayOk(c)) { c.style.display = 'none'; return; }
        if (c.style.display === 'none') return;
        n++; total++;
      });
      var out = document.getElementById('count');
      if (out) out.textContent = '显示 ' + n + ' / ' + total + ' 条';
      var empty = document.getElementById('empty');
      if (empty) empty.style.display = n ? 'none' : '';
    };
    return true;
  }

  var nav = document.getElementById('daynav');
  if (nav){
    nav.addEventListener('click', function(e){
      var a = e.target.closest ? e.target.closest('a') : null;
      if (!a) return;
      var el = document.getElementById(a.getAttribute('href').slice(1));
      if (!el) return;
      e.preventDefault();
      el.scrollIntoView({behavior:'smooth', block:'start'});
    });
  }

  setView('__DEFAULT_VIEW__');
  if (!patch()){
    // HTML_JS 尚未执行完时兜底：等一拍再补
    setTimeout(function(){ patch(); if (window.__apply) window.__apply(); }, 0);
  }
  if (window.__apply) window.__apply();
})();
"""


TPL = """<!DOCTYPE html>
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
    <div class="datebar"><span class="lab">📅 日期</span>__DATES__</div>
    <div class="views" id="views">__VIEWS__</div>
    <div class="controls">
      <input id="q" type="search" placeholder="搜索厂商 / 角色 / 产品线 / 摘要…（按 / 聚焦）">
      <div class="chips" id="typeChips">__TYPECHIPS__</div>
      <div class="chips" id="relChips">__RELCHIPS__</div>
      <span class="count" id="count"></span>
    </div>
  </div>
</header>
<div class="daynav" id="daynav">
  <div class="wrap"><span class="lab" style="font-size:12.5px;color:#8b95a3">跳到</span>__DAYNAV__</div>
</div>
<main class="wrap">
  <div id="groups">__SECTIONS__</div>
  <div class="empty" id="empty" style="display:none">没有匹配的情报，换个关键词或筛选条件试试。</div>
  <div class="legend">__LEGEND__</div>
</main>

<div class="lb" id="lb" role="dialog" aria-modal="true" aria-label="配图放大预览">
  <button class="lb-btn lb-close" type="button" aria-label="关闭预览">×</button>
  <button class="lb-btn lb-nav lb-prev" type="button" aria-label="上一张">‹</button>
  <button class="lb-btn lb-nav lb-next" type="button" aria-label="下一张">›</button>
  <img id="lb-img" alt="">
  <div class="lb-hint" id="lb-hint" style="display:none">⚠️ 图片没加载出来 —— 请确认这个 HTML 同目录下存在 <b>media/</b> 文件夹（由 <code>attach_media.py --download</code> 生成）。</div>
  <div class="cap" id="lb-cap"></div>
  <div class="lb-idx" id="lb-idx"></div>
  <a class="lb-ori" id="lb-ori" target="_blank" rel="noopener noreferrer"
     referrerpolicy="no-referrer">查看原图 ↗</a>
</div>

<script>__JS__</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="生成手办情报跨天总览页")
    ap.add_argument("--days", type=int, help="只收最近 N 天（默认全量）")
    ap.add_argument("--out", help="输出 HTML 路径")
    ap.add_argument("--md-out", help="输出 Markdown 路径")
    ap.add_argument("--open-view", choices=["new", "all", "days"], default="new",
                    help="页面默认落在哪个视图，默认 new（新品清单）")
    ap.add_argument("--format", choices=["md", "html", "both"], default="both")
    args = ap.parse_args()

    pairs = collect_inputs(days=args.days)
    if not pairs:
        print(f"❌ data/ 目录下没有找到 intel-*.json（当前 {DATA_DIR}）")
        return 1

    days = load_days(pairs)
    if not days:
        print("❌ 所有 intel 文件都没有可用条目")
        return 1

    all_items = merge_across_days(days)
    new_n = sum(1 for it in all_items if bd.is_new(it))
    dates = sorted(days)
    print(f"收录 {len(dates)} 天（{dates[0]} ~ {dates[-1]}）"
          f"，合并后 {len(all_items)} 条情报，其中新品 {new_n} 件")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    written = []

    if args.format in ("md", "both"):
        out = args.md_out or os.path.join(OUTPUT_DIR, "手办情报-总览.md")
        with open(out, "w", encoding="utf-8") as f:
            f.write(render_md(days, all_items))
        written.append(out)

    if args.format in ("html", "both"):
        out = args.out or os.path.join(OUTPUT_DIR, "手办情报-总览.html")
        bd.MEDIA_REL = os.path.relpath(bd.MEDIA_DIR,
                                       os.path.dirname(os.path.abspath(out))
                                       ).replace("\\", "/")
        attach_media_paths(days, all_items)
        html = render_index(days, all_items, default_view=args.open_view)
        html = html.replace("__DEFAULT_VIEW__", args.open_view)
        # 总览页缩略图走本地相对路径（非 base64），且同一张图会在多个视图里重复出现，
        # 必须加 lazy 加载，否则一开页面就是 2000+ 个图片请求。
        html = html.replace('<img src="' + bd.MEDIA_REL, '<img loading="lazy" src="' + bd.MEDIA_REL)
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        written.append(out)

        size_mb = os.path.getsize(out) / 1024 / 1024
        print(f"页面体积 {size_mb:.1f} MB")
        n_img = sum(1 for it in all_items if it.get("images"))
        if n_img:
            local = os.path.join(bd.MEDIA_DIR, "view")
            have = len(os.listdir(local)) if os.path.isdir(local) else 0
            print(f"配图：{n_img} 条带图，本地 media/view 已有 {have} 张")

    for p in written:
        print(f"总览已生成：{p}")
    return 0


def render_md(days, all_items):
    """总览 Markdown：新品清单表 + 按天索引。"""
    lines = ["# 手办 / 可动人偶情报 · 跨天总览", "",
             f"收录 **{len(days)}** 天（{min(days)} ~ {max(days)}），"
             f"合并后 **{len(all_items)}** 条情报。", ""]

    new_items = [it for it in all_items if bd.is_new(it)]
    if new_items:
        new_sorted = sorted(new_items, key=lambda x: bd.NEW_KIND_ORDER.index(x["_type"])
                            if x["_type"] in bd.NEW_KIND_ORDER else 99)
        lines += ["## 🆕 跨天新品清单", "",
                  "| " + " | ".join(bd.NEW_COLUMNS) + " |",
                  "|" + "---|" * len(bd.NEW_COLUMNS)]
        for n, it in enumerate(new_sorted, 1):
            subject = (it.get("character") or "").strip() or "—"
            works = " · ".join(filter(None, [(it.get("ip") or "").strip(),
                                             (it.get("line") or "").strip()])) or "—"
            when = " / ".join(filter(None, [(it.get("release_date") or "").strip(),
                                            (it.get("channel") or "").strip()])) or "—"
            look = (it.get("relevance_reason") or "").strip() or \
                   (it.get("summary") or "").strip()
            state = it["_type"]
            if it.get("also_kinds"):
                state += " · " + " / ".join(it["also_kinds"])
            src = it.get("url") or ""
            blogger = (it.get("blogger") or "原博").strip()
            srct = f"[{blogger}]({src})" if src else blogger
            srct += f"<br/>{date_span(it)}"
            lines.append("| " + " | ".join([
                str(n), bd.cell(it.get("brand")), bd.cell(subject), bd.cell(works),
                bd.cell(it.get("price")), bd.cell(when), bd.cell(look), srct,
            ]) + " |")
        lines.append("")

    lines += ["## 按天索引", "", "| 日期 | 情报条数 | 新品 | 当日简报 |", "|---|---|---|---|"]
    for d in sorted(days, reverse=True):
        items_d = days[d]
        dn = sum(1 for it in items_d if bd.is_new(it))
        lines.append(f"| {d} | {len(items_d)} | {dn} | "
                     f"[手办情报-{d}.html](手办情报-{d}.html) |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
