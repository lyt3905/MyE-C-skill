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
import base64
import html as htmllib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, unquote

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


# --------------------------------------------------------------------------- 新品清单
# 用户最关心「微博里告诉了我有哪些新品」，因此把新品视角单列一档：
# NEW_MAIN_TYPES 是「新品本体」（首次露面的产品），NEW_ACT_TYPES 是它的可行动后续
# （开订 / 发售 / 再版），二者合起来构成「新品清单」，默认展示。

NEW_MAIN_TYPES = ("新品公布",)
NEW_ACT_TYPES = ("开订", "发售", "再版")
NEW_TYPES = NEW_MAIN_TYPES + NEW_ACT_TYPES

# 「实物测评」里属于**首次曝光**的也算新品。
#
# 2026-09-17 用户反馈漏报：FT-63 充电器、NA 漂移、TRANSBOTS 拦路虎、机械入侵大力神、
# HP-02 粉碎这类「实物 / 开箱 / 实测」帖，本质是新品首度实拍露面，但被归到实物测评后
# 就掉出了新品清单。
#
# 判据分两步，宁可多收也不要再漏：
#   ① 摘要明确写了首度语义（首度 / 首次 / 大货来了 / 实物来了 …）→ 直接算新品
#   ② 否则看是否「开箱 / 实测 / 实物」这类首曝动作帖
# 排除项：纯剧情回顾、老货复拍（摘要含「回顾 / 重温 / 情怀」等）。
FIRST_LOOK_PAT = re.compile(
    r"首度|首次|首曝|首发实拍|初公开|首度公开|"
    r"大货实测|大货实拍|大货来了|实物来了|实物首|"
    r"放出实物|实物亮相|实物曝光|首度亮相"
)

# 首曝动作词：开箱 / 实测 / 实物 等
FRESH_ACTION_PAT = re.compile(r"开箱|实测|实物|大货|首测|上手")

# 排除：明显不是新品的内容帖
NOT_FRESH_PAT = re.compile(r"回顾|重温|情怀|十年前|当年|老货|复刻已久|剧情|动画|电影预告")

# 展会类里的「特别发售 / 限定 / 首展」也是新品——会场限定本身就是新面市的产品。
# 纯展会信息（仅展位、售卖通知，不含新品的）不算。
EVENT_NEW_PAT = re.compile(
    r"特别发售|限量|限定|首展|全球首展|首次亮相|新品|现场售卖|推出"
)

# 新品清单内的顺序：先本体、后动作，各自按类型次序
NEW_KIND_ORDER = ["新品公布", "开订", "发售", "再版"]

# 同一款产品的不同微博合并成一张卡：厂商+角色 或 厂商+产品线 相同即视为同一款
_STOP_SUBJECT = {"", "-", "—", "无", "n/a"}
_STOP_LINE = {"", "-", "—", "无", "n/a", "限定", "限定版", "特别版", "会场限定"}


def make_key(brand, character, line):
    b = (brand or "").strip().lower()
    c = (character or "").strip().lower()
    ln = (line or "").strip().lower()
    ln = "" if ln in _STOP_LINE else ln
    if not b:
        return None
    subj = c or ln
    if not subj or subj in _STOP_SUBJECT:
        return None
    return f"{b}|{subj}"


def is_new(it):
    """是否算「新品」：新品公布 / 开订 / 发售 / 再版，或实物测评·展会里的首度曝光。"""
    if it["_type"] in NEW_TYPES:
        return True
    blob = " ".join(str(it.get(k) or "") for k in
                    ("summary", "line", "character", "scale", "channel"))
    if it["_type"] == "实物测评":
        if NOT_FRESH_PAT.search(blob):
            return False
        if FIRST_LOOK_PAT.search(blob):
            return True
        # 开箱 / 实测 / 实物 类帖：本质是新品首度实拍，一并计入
        return bool(FRESH_ACTION_PAT.search(blob))
    if it["_type"] == "展会":
        # 会场限定 / 特别发售 / 首展 = 新面市的产品
        return bool(EVENT_NEW_PAT.search(blob))
    return False


def new_reason(it):
    """新品清单里只保留一句「为什么值得看」，避免与摘要重复。"""
    if it["_type"] == "实物测评" and is_new(it):
        return "首次实物曝光"
    if it["_type"] == "展会" and is_new(it):
        return "会场限定"
    return ""


# 纯新品清单的展示列（脱离情报分类，按内容组织）
NEW_COLUMNS = ["#", "厂商", "产品 / 角色", "作品 & 产品线", "参考价",
               "发售 / 开订", "看点", "来源"]


def rel_rank(it):
    return RELEVANCE_ORDER.get(it["_rel"], 3)


def dedupe_items(items):
    """同一款产品的重复条目合并：保留信息最全的一条，其余记为 also_reported_by。

    2026-09-17 实测：布鲁可「擎天柱 Ver.EVO」被 4 条微博分别报道，简报里成了 4 张
    几乎一样的卡。合并后 summary 取最长的一条，关键字段（价格 / 发售日 / 渠道 /
    比例 / 角色）从其余条目里补齐，来源链接全部保留成「另有 N 条报道」。
    """
    groups, order = {}, []
    for it in items:
        key = make_key(it.get("brand"), it.get("character"), it.get("line"))
        if key is None:
            order.append(("_solo", len(order), it))
            continue
        if key not in groups:
            groups[key] = []
            order.append((key, len(order), None))
        groups[key].append(it)

    out = []
    for key, _pos, solo in order:
        if solo is not None:
            out.append(solo)
            continue
        grp = groups[key]
        if len(grp) == 1:
            out.append(grp[0])
            continue

        # 主条：信息完整度优先（摘要长度 + 关键字段命中数），再比相关度与时间
        def richness(x):
            facts = sum(1 for k in ("price", "release_date", "channel", "scale")
                        if (x.get(k) or "").strip())
            return (facts, len(x.get("summary") or ""), -rel_rank(x))

        grp_sorted = sorted(grp, key=richness, reverse=True)
        main = dict(grp_sorted[0])
        rest = grp_sorted[1:]

        for x in rest:
            for k in ("price", "release_date", "channel", "scale",
                      "relevance_reason", "character", "ip", "line"):
                if not (main.get(k) or "").strip() and (x.get(k) or "").strip():
                    main[k] = x[k]
            if rel_rank(x) < rel_rank(main):
                main["_rel"] = x["_rel"]
                main["relevance"] = x.get("relevance")

        # 合并类型：本体优先（新品公布 > 开订 > 发售 > 再版），另记全部动作
        kinds = []
        for x in grp_sorted:
            if x["_type"] not in kinds:
                kinds.append(x["_type"])
        kinds.sort(key=lambda t: NEW_KIND_ORDER.index(t)
                   if t in NEW_KIND_ORDER else 99)
        if kinds and kinds[0] != main["_type"]:
            main["_type"] = kinds[0]
        if len(kinds) > 1:
            main["also_kinds"] = kinds[1:]

        # 合并来源：保留其余微博的链接与博主
        srcs = []
        for x in rest:
            if not x.get("url") and not x.get("post_id"):
                continue
            srcs.append({"blogger": x.get("blogger") or "原博",
                         "url": x.get("url") or "",
                         "posted_at": x.get("posted_at") or ""})
        if srcs:
            main["also_sources"] = srcs
        # 配图取并集（去重，保持主条优先）
        imgs, seen = [], set()
        for x in grp_sorted:
            for u in (x.get("images") or []):
                if u and u not in seen:
                    seen.add(u)
                    imgs.append(u)
        if imgs:
            main["images"] = imgs
        out.append(main)
    return out


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
        n_img = len(it.get("images") or [])
        if n_img:
            src += f"<br/>配图 {n_img} 张"
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
    items = dedupe_items(items)

    date = data.get("date") or datetime.now(CST).strftime("%Y-%m-%d")

    high = [i for i in items if i["_rel"] == "高"]
    new_items = [i for i in items if is_new(i)]
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
    if new_items:
        meta.append(f"其中新品清单 **{len(new_items)}** 条")
    if high:
        meta.append(f"其中 **{len(high)}** 条与选品高度相关")
    if data.get("generated_at"):
        meta.append(f"生成于 {data['generated_at']}")
    out.append("　".join(meta))
    out.append("")

    # ---- 新品清单：用户最关心「有哪些新品」，脱离情报分类单独成节 ----
    if new_items:
        new_sorted = sorted(new_items, key=lambda x: NEW_KIND_ORDER.index(x["_type"])
                           if x["_type"] in NEW_KIND_ORDER else 99)
        out.append("## 🆕 新品清单")
        out.append("")
        out.append("> 微博里出现的新品，按「首次亮相 → 可下单」的顺序排列；"
                   "同一款产品的多条微博已合并。")
        out.append("")
        out.append("| " + " | ".join(NEW_COLUMNS) + " |")
        out.append("|" + "---|" * len(NEW_COLUMNS))
        for n, it in enumerate(new_sorted, 1):
            subject = " / ".join(filter(None, [
                (it.get("character") or "").strip(),
                (it.get("brand") or "").strip() and "" or "",
            ])) or (it.get("character") or "—")
            works = " · ".join(filter(None, [
                (it.get("ip") or "").strip(),
                (it.get("line") or "").strip(),
            ])) or "—"
            when = " / ".join(filter(None, [
                (it.get("release_date") or "").strip(),
                (it.get("channel") or "").strip(),
            ])) or "—"
            # 看点：优先相关理由，其余用摘要
            look = (it.get("relevance_reason") or "").strip() or \
                   (it.get("summary") or "").strip()
            state = it["_type"]
            if it.get("also_kinds"):
                state += " · " + " / ".join(it["also_kinds"])
            if new_reason(it):
                state += f"（{new_reason(it)}）"
            source = it.get("url") or ""
            blogger = (it.get("blogger") or "原博").strip()
            src = f"[{blogger}]({source})" if source else blogger
            if it.get("posted_at"):
                src += f"<br/>{cell(it['posted_at'])}"
            n_img = len(it.get("images") or [])
            if n_img:
                src += f"<br/>配图 {n_img} 张"
            if it.get("also_sources"):
                src += f"<br/>另有 {len(it['also_sources'])} 条报道"
            out.append("| " + " | ".join([
                str(n),
                cell(it.get("brand")),
                cell(subject),
                cell(works),
                cell(it.get("price")),
                cell(when),
                cell(look),
                src,
            ]) + " |")
        out.append("")
        out.append("**状态说明**：" + "　".join(
            f"{t} {sum(1 for x in new_sorted if x['_type'] == t)}"
            for t in NEW_KIND_ORDER if any(x["_type"] == t for x in new_sorted)))
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
                tail = f"（{it['posted_at']}）" if it.get("posted_at") else ""
                n_img = len(it.get("images") or [])
                if n_img:
                    tail += f"　配图 {n_img} 张"
                out.append(f"  - 来源：[{it.get('blogger') or '原博'}]({it['url']}){tail}")
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

/* 视图切换：新品清单 / 全部情报 */
.view-new .group-all{display:none}
.views{display:flex;gap:4px;margin-top:14px;background:var(--bg);
  border:1px solid var(--line);border-radius:11px;padding:4px;width:fit-content}
.view{border:0;background:transparent;color:var(--ink2);font-family:inherit;
  font-size:13.5px;font-weight:600;padding:7px 16px;border-radius:8px;
  cursor:pointer;transition:.15s;white-space:nowrap}
.view:hover{color:var(--ink)}
.view.on{background:var(--card);color:var(--accent);
  box-shadow:0 1px 4px rgba(20,30,50,.1)}
.view b{font-weight:700}
.view .vh{font-weight:400;opacity:.62;font-size:12px;margin-left:3px}

/* 新品清单：同一款产品的多条报道 */
.reports{margin:0;font-size:12.5px;color:var(--ink2);background:var(--bg);
  border:1px dashed var(--line);border-radius:8px;padding:7px 10px;
  display:flex;flex-wrap:wrap;gap:6px 12px}
.reports span{display:inline-flex;align-items:center;gap:4px}
.reports .k{color:var(--ink3);font-size:12px}
.kinds{display:inline-flex;gap:4px}
.kinds em{font-style:normal;font-size:11.5px;color:var(--ink3);
  background:var(--bg);border:1px solid var(--line);border-radius:5px;
  padding:1px 6px}

/* 纯新品清单：脱离情报分类的单列编号列表 */
.newlist{display:flex;flex-direction:column;gap:11px}
.newlist .card{position:relative;padding-left:52px}
.newlist .idx{position:absolute;left:15px;top:15px;width:24px;height:24px;
  border-radius:50%;background:var(--accent-soft);color:var(--accent);
  font-size:12.5px;font-weight:700;display:flex;align-items:center;
  justify-content:center;line-height:1}
.rank{display:inline-flex;align-items:center;gap:5px;font-size:12px;
  font-weight:600;border-radius:6px;padding:2px 9px;letter-spacing:.2px}
.rank-1{background:#e3f5ea;color:#1a7a45}
.rank-2{background:#fdf3dc;color:#8a6412}
.rank-3{background:#ede7fd;color:#5b3ec8}
.rank-4{background:#eef0f3;color:#5f6b7a}
.newhead{display:flex;align-items:baseline;gap:10px;margin:0 0 13px;
  padding-bottom:9px;border-bottom:1px solid var(--line);flex-wrap:wrap}
.newhead h2{margin:0;font-size:15px;font-weight:650;letter-spacing:.2px}
.newhead .nh{color:var(--ink3);font-size:12.5px;font-weight:400}
.newhead .gbar{margin-left:auto;height:3px;width:38px;border-radius:2px;
  background:#e9edf3}

/* 卡片 */
main{padding:20px 0 60px}
.group{margin-bottom:26px}
.group h2{display:flex;align-items:center;gap:9px;margin:0 0 13px;
  padding-bottom:9px;border-bottom:1px solid var(--line);font-size:15px;
  font-weight:650;letter-spacing:.2px}
.group h2 .gn{color:var(--ink3);font-size:12.5px;font-weight:400}
.group h2 .gbar{margin-left:auto;height:3px;width:38px;border-radius:2px;
  background:#e9edf3}
.group.off{display:none}
.grid{display:grid;grid-template-columns:1fr;gap:11px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:14px 17px 15px;display:flex;flex-direction:column;gap:9px}
.card:hover{border-color:#cfd8e5;box-shadow:0 2px 10px rgba(20,30,50,.06)}
.body{display:grid;grid-template-columns:minmax(0,1fr) 258px;gap:20px;
  align-items:start}
.main{display:flex;flex-direction:column;gap:8px;min-width:0}
.side{display:flex;flex-direction:column;gap:10px;align-items:stretch;
  border-left:1px solid var(--line);padding-left:17px;min-width:0}
.side .src{align-self:flex-start}
.side .tags{align-self:flex-start}
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
/* 标题本身即链接：点标题也能跳原博 */
.card h3 a{color:inherit;text-decoration:none;cursor:pointer}
.card h3 a:hover{color:var(--accent);text-decoration:underline;
  text-underline-offset:3px}
.card h3 a:focus-visible{outline:2px solid var(--accent-soft);
  border-radius:3px}
.sum{margin:0;color:var(--ink2);font-size:13.5px}
.facts{display:flex;flex-wrap:wrap;gap:6px;margin:1px 0 0}
.facts i{font-style:normal;background:var(--bg);border:1px solid var(--line);
  border-radius:6px;padding:2px 8px;font-size:12.5px;color:var(--ink2)}
.facts i b{color:var(--ink);font-weight:600;margin-right:3px}
.why{background:#fbfaf4;border-left:3px solid #e0c98a;border-radius:4px;
  padding:7px 10px;font-size:12.5px;color:#6b5a24}
.src{display:inline-flex;align-items:center;gap:5px;font-size:13px;
  font-weight:600;background:var(--accent-soft);border-radius:8px;
  padding:6px 12px}
.src:hover{background:#dce8fd;text-decoration:none}
.tags{display:flex;gap:5px;flex-wrap:wrap}
.tags em{font-style:normal;font-size:11.5px;color:var(--ink3)}

/* 缩略图（右栏顶部，方案 A）：点击放大预览 */
.thumbs{display:flex;flex-wrap:wrap;gap:6px;align-self:flex-start}
.thumb{position:relative;width:74px;height:74px;padding:0;flex:0 0 auto;
  border:1px solid var(--line);border-radius:9px;overflow:hidden;
  background:var(--bg);cursor:zoom-in;display:block;font:inherit;
  transition:border-color .15s,box-shadow .15s}
.thumb img{width:100%;height:100%;object-fit:cover;display:block;
  transition:transform .28s ease}
.thumb:hover{border-color:var(--accent);box-shadow:0 2px 8px rgba(20,30,50,.12)}
.thumb:hover img{transform:scale(1.07)}
.thumb:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.thumb .more{position:absolute;right:3px;bottom:3px;background:rgba(12,15,20,.74);
  color:#fff;font-size:11px;font-weight:600;line-height:1.45;
  padding:0 6px;border-radius:999px;pointer-events:none}
.thumb.tre{box-shadow:inset 0 0 0 2px #f0d9a0}
.thumb.tre::after{content:"转";position:absolute;left:3px;top:3px;
  background:rgba(180,140,30,.88);color:#fff;font-size:10px;
  padding:0 5px;border-radius:5px;line-height:1.5}

/* 放大预览（lightbox） */
.lb{position:fixed;inset:0;z-index:100;display:none;
  background:rgba(10,13,18,.93);-webkit-backdrop-filter:blur(4px);
  backdrop-filter:blur(4px);flex-direction:column;align-items:center;
  justify-content:center;padding:56px 76px 64px}
.lb.on{display:flex}
.lb img{max-width:100%;max-height:calc(100vh - 172px);object-fit:contain;
  border-radius:6px;background:#101318;box-shadow:0 12px 44px rgba(0,0,0,.5)}
.lb .cap{color:#e9edf4;font-size:13.5px;margin-top:14px;text-align:center;
  max-width:min(90vw,900px);line-height:1.6}
.lb .cap a{color:#9dc0ff}
.lb .cap .k{color:#98a2b3;font-size:12.5px}
.lb-btn{border:0;cursor:pointer;font-family:inherit;color:#fff;
  background:rgba(255,255,255,.12);border-radius:10px;transition:.15s}
.lb-btn:hover{background:rgba(255,255,255,.26)}
.lb-btn:disabled{opacity:.22;cursor:default}
.lb-close{position:absolute;top:18px;right:22px;width:40px;height:40px;
  font-size:22px;line-height:1;border-radius:50%}
.lb-nav{position:absolute;top:50%;transform:translateY(-50%);width:46px;height:70px;
  font-size:24px;line-height:1}
.lb-prev{left:18px}.lb-next{right:18px}
.lb-hint{color:#ffd9a8;font-size:13.5px;text-align:center;line-height:1.75;
  max-width:560px;padding:26px 18px;background:rgba(255,255,255,.06);
  border-radius:10px}
.lb-hint code{background:rgba(255,255,255,.14);padding:1px 6px;border-radius:4px;
  font-size:12.5px}
.lb-idx{position:absolute;bottom:22px;left:50%;transform:translateX(-50%);
  color:#aab3c2;font-size:12.5px;letter-spacing:.4px}
.lb-ori{position:absolute;bottom:18px;right:22px;color:#9dc0ff;font-size:12.5px}
body.lb-lock{overflow:hidden}

@media(max-width:860px){
  .lb{padding:52px 12px 60px}
  .lb-nav{width:38px;height:56px;font-size:20px}
  .lb-prev{left:6px}.lb-next{right:6px}
  .lb .cap{font-size:12.5px}
}
.empty{text-align:center;color:var(--ink3);padding:60px 0;font-size:14px}
.legend{margin:18px 0 10px;color:var(--ink3);font-size:12.5px}
@media(max-width:860px){
  .body{grid-template-columns:1fr;gap:0}
  .side{border-left:0;border-top:1px solid var(--line);padding-left:0;
    padding-top:11px;margin-top:11px;flex-direction:row;flex-wrap:wrap;
    align-items:center;gap:9px;width:100%}
  .side .facts{flex:1 1 100%}
  .side .thumbs{flex:1 1 100%}
  .views{width:100%}
  .view{flex:1;text-align:center}
}
@media(max-width:640px){
  h1{font-size:19px}
  .count{margin-left:0;width:100%}
  .card{padding:13px 14px 14px}
}
@media print{
  .top{position:static}.controls{display:none}
  body{background:#fff}.card{break-inside:avoid;box-shadow:none}
}
"""

HTML_JS = r"""
(function(){
  var q = document.getElementById('q');
  var cards = [].slice.call(document.querySelectorAll('.card'));
  var groups = [].slice.call(document.querySelectorAll('.group'));
  var typeChips = [].slice.call(document.querySelectorAll('[data-type-chip]'));
  var relChips  = [].slice.call(document.querySelectorAll('[data-rel-chip]'));
  var viewBtns  = [].slice.call(document.querySelectorAll('[data-view]'));
  var out = document.getElementById('count');
  var empty = document.getElementById('empty');
  var state = {type:'全部', rel:'全部', view:'new'};

  function match(c){
    // 两个视图各渲染一份 DOM：新品清单容器里的卡片只属于新品视图，
    // 分类分组里的卡片只属于「全部情报」视图
    var inNew = !!(c.closest && c.closest('.group-new'));
    if (inNew !== (state.view === 'new')) return false;
    // 新品视图下是纯清单、无分类，类型筛选只在「全部情报」视图生效
    if (state.type !== '全部' && c.dataset.type !== state.type) return false;
    if (state.rel === '高' && c.dataset.rel !== '高') return false;
    var t = (q.value || '').trim().toLowerCase();
    if (t && (c.dataset.search || '').indexOf(t) === -1) return false;
    return true;
}
  function apply(){
    var n = 0, shown = 0, total = 0;
    cards.forEach(function(c){
      var inNew = !!(c.closest && c.closest('.group-new'));
      // 分母跟随当前视图：新品视图数 group-new 里的卡片，
      // 全部情报视图数 group-all 里的卡片（否则全部视图会显示 N/新品数）
      if (inNew === (state.view === 'new')) total++;
      var ok = match(c);
      c.style.display = ok ? '' : 'none';
      if (ok) n++;
      // 计数只统计当前视图真正可见的那份卡片
      // （新品清单与分类分组里各渲染一份 DOM，靠所在容器区分）
      if (ok) shown++;
    });
    // 分组标题随筛选联动：组内没有可见卡片就整组隐藏
    // （纯新品清单不参与类型筛选，整体显隐由视图决定）
    groups.forEach(function(g){
      if (g.dataset.group === '__new__') return;
      var vis = 0;
      [].slice.call(g.querySelectorAll('.card')).forEach(function(c){
        if (c.style.display !== 'none') vis++;
      });
      g.classList.toggle('off', vis === 0);
    });
    var newSec = document.querySelector('.group-new');
    if (newSec) newSec.style.display = (state.view === 'new') ? '' : 'none';
    out.textContent = '显示 ' + shown + ' / ' + total + ' 条';
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
  viewBtns.forEach(function(b){
    b.addEventListener('click', function(){
      state.view = b.dataset.view;
      viewBtns.forEach(function(x){ x.classList.toggle('on', x === b); });
      document.body.classList.toggle('view-new', state.view === 'new');
      // 两个视图的类型筛选语义不同，切视图时把类型筛选重置回「全部」
      state.type = '全部';
      typeChips.forEach(function(x){
        x.classList.toggle('on', x.dataset.typeChip === '全部');
      });
      // 纯新品清单没有分类，类型筛选条在「新品清单」视图下隐藏
      var chipBox = document.getElementById('typeChips');
      if (chipBox) chipBox.style.display = (state.view === 'new') ? 'none' : '';
      apply();
      syncViewNotes();
    });
  });
  q.addEventListener('input', function(){ apply(); syncViewNotes(); });
  function syncViewNotes(){
    // 视图相关小字（如「当前为新品清单」提示）随视图显隐
    document.querySelectorAll('[data-only-view]').forEach(function(el){
      el.hidden = el.dataset.onlyView !== state.view;
    });
  }
  // 初始状态：默认新品清单，类型筛选条隐藏
  (function init(){
    var chipBox = document.getElementById('typeChips');
    if (chipBox) chipBox.style.display = (state.view === 'new') ? 'none' : '';
    syncViewNotes();
  })();
  document.addEventListener('keydown', function(e){
    // 放大预览打开时把键盘让给它，避免 Esc / 数字键冲突
    if (document.body.classList.contains('lb-lock')) return;
    if (e.key === '/' && document.activeElement !== q){ e.preventDefault(); q.focus(); }
    if (e.key === 'Escape' && document.activeElement === q){ q.value=''; apply(); q.blur(); }
  });
  apply();
  // 暴露给总览页（build_index.py）：它要在筛选链上再叠一层「按日期过滤」，
  // 直接把 apply 包一层即可，不必复制这段逻辑。
  window.__apply = apply;
})();

/* 配图放大预览：点缩略图弹出，同一条情报的全部配图可左右翻 */
(function(){
  var lb = document.getElementById('lb');
  if (!lb) return;
  var img  = document.getElementById('lb-img');
  var cap  = document.getElementById('lb-cap');
  var idx  = document.getElementById('lb-idx');
  var ori  = document.getElementById('lb-ori');
  var hint = document.getElementById('lb-hint');
  var prev = lb.querySelector('.lb-prev');
  var next = lb.querySelector('.lb-next');

  var gallery = [];   // 预览图地址（本地相对路径优先，构建时已算好）
  var caption = '';   // 「博主 · 标题」
  var origin  = '';   // 原博链接
  var pos = 0, opener = null;

  function paint(){
    if (!gallery.length) return;
    var u = gallery[pos];
    img.hidden = false;
    if (hint) hint.style.display = 'none';
    img.src = u;
    img.alt = caption;

    cap.textContent = '';
    cap.appendChild(document.createTextNode(
      caption + '　（' + (pos + 1) + '/' + gallery.length + '）'));
    if (gallery.length > 1){
      var k = document.createElement('span');
      k.className = 'k';
      k.textContent = '　← → 切换';
      cap.appendChild(k);
    }
    if (origin){
      var a = document.createElement('a');
      a.href = origin;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.textContent = '　查看原博 ↗';
      cap.appendChild(a);
    }

    idx.textContent = (pos + 1) + ' / ' + gallery.length;
    var multi = gallery.length > 1;
    prev.disabled = !multi;
    next.disabled = !multi;
    ori.href = u;                     // 「查看原图」直达未压缩原图
  }
  function open(list, i, capText, href, el){
    if (!list.length) return;
    gallery = list;
    caption = capText || '';
    origin  = href || '';
    pos = Math.min(Math.max(0, i), list.length - 1);
    opener = el || null;
    lb.classList.add('on');
    document.body.classList.add('lb-lock');
    paint();
    (list.length > 1 ? next : lb.querySelector('.lb-close')).focus();
  }
  function close(){
    lb.classList.remove('on');
    document.body.classList.remove('lb-lock');
    img.removeAttribute('src');
    if (opener && opener.focus) opener.focus();
  }
  function step(d){
    if (gallery.length < 2) return;
    pos = (pos + d + gallery.length) % gallery.length;
    paint();
  }

  // 点缩略图：从所属卡片的 data-gallery 取出完整图集（含未显示的 +N 张）
  document.addEventListener('click', function(e){
    var t = e.target.closest ? e.target.closest('.thumb') : null;
    if (!t) return;
    e.preventDefault();
    var card = t.closest('.card');
    if (!card) return;
    var box = card.querySelector('.thumbs');
    if (!box) return;

    var list = [];
    try { list = JSON.parse(box.dataset.gallery || '[]'); } catch (err) { list = []; }
    if (!list.length) return;
    open(list, parseInt(t.dataset.i || '0', 10) || 0,
         box.dataset.cap || '', box.dataset.href || '', t);
  });

  // 本地图片缺失时给出明确提示，而不是只留一块空白
  img.addEventListener('error', function(){
    img.hidden = true;
    if (hint) hint.style.display = '';
  });

  lb.querySelector('.lb-close').addEventListener('click', close);
  prev.addEventListener('click', function(e){ e.stopPropagation(); step(-1); });
  next.addEventListener('click', function(e){ e.stopPropagation(); step(1); });
  ori.addEventListener('click', function(e){ e.stopPropagation(); });
  lb.addEventListener('click', function(e){
    if (e.target === lb) close();   // 点背景关闭；点图片本身不关
  });

  // 键盘：capture 阶段拦截，避免与搜索框的 Esc 清空冲突
  document.addEventListener('keydown', function(e){
    if (!lb.classList.contains('on')) return;
    if (e.key === 'Escape'){ e.stopPropagation(); close(); }
    else if (e.key === 'ArrowLeft'){ e.stopPropagation(); step(-1); }
    else if (e.key === 'ArrowRight'){ e.stopPropagation(); step(1); }
  }, true);

  // 触屏左右滑动
  var x0 = null;
  lb.addEventListener('touchstart', function(e){
    x0 = e.changedTouches[0].clientX;
  }, {passive:true});
  lb.addEventListener('touchend', function(e){
    if (x0 === null) return;
    var dx = e.changedTouches[0].clientX - x0;
    if (Math.abs(dx) > 45) step(dx < 0 ? 1 : -1);
    x0 = null;
  }, {passive:true});
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
    <div class="views" id="views">__VIEWS__</div>
    <div class="controls">
      <input id="q" type="search" placeholder="搜索厂商 / 角色 / 产品线 / 摘要…（按 / 聚焦）">
      <div class="chips" id="typeChips">__TYPECHIPS__</div>
      <div class="chips" id="relChips">__RELCHIPS__</div>
      <span class="count" id="count"></span>
    </div>
  </div>
</header>
<main class="wrap">
  <div id="groups">__SECTIONS__</div>
  <div class="empty" id="empty" style="display:none">没有匹配的情报，换个关键词或筛选条件试试。</div>
  <div class="legend">__LEGEND__　·　点击右栏缩略图可放大看原图，点标题或按钮可跳转原博（需登录微博）。</div>
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


def render_html(data, items, date):
    """把结构化情报渲染成单文件 HTML（无外部依赖，双击即可看）。"""
    groups = {}
    for it in items:
        groups.setdefault(it["_type"], []).append(it)
    ordered_types = [t for t in TYPE_ORDER if t in groups]
    ordered_types += [t for t in groups if t not in TYPE_ORDER]

    high_n = sum(1 for it in items if it["_rel"] == "高")
    new_items = [it for it in items if is_new(it)]
    new_n = len(new_items)

    chips = ['<button class="chip on" data-type-chip="全部">全部</button>']
    for t in ordered_types:
        chips.append(f'<button class="chip" data-type-chip="{htmllib.escape(t, quote=True)}">'
                     f'{htmllib.escape(t)} <span style="opacity:.6">{len(groups[t])}</span></button>')
    rel_chips = ['<button class="chip on" data-rel-chip="全部">不限相关度</button>']
    if high_n:
        rel_chips.append(f'<button class="chip" data-rel-chip="高">仅高相关 {high_n}</button>')

    # 视图切换：默认「新品清单」——用户最关心微博里有哪些新品
    views = [f'<button class="view on" type="button" data-view="new">'
             f'<b>🆕 新品清单</b><span class="vh">{new_n} 件</span></button>']
    views.append(f'<button class="view" type="button" data-view="all">'
                 f'全部情报<span class="vh">{len(items)} 条</span></button>')

    sections = []
    # ① 纯新品清单：脱离情报分类，单一连续列表（用户主视图，默认展开）
    new_sorted = sorted(new_items, key=lambda x: NEW_KIND_ORDER.index(x["_type"])
                        if x["_type"] in NEW_KIND_ORDER else 99)
    if new_sorted:
        inner = "\n".join(
            render_card(it, idx=i) for i, it in enumerate(new_sorted, 1)
        )
        sections.append(
            '<section class="group group-new" data-group="__new__">'
            '<div class="newhead">'
            '<h2>🆕 新品清单</h2>'
            f'<span class="nh">{len(new_sorted)} 件新品</span>'
            '<span class="gbar"></span></div>'
            f'<div class="newlist">{inner}</div></section>'
        )

    # ② 全部情报：按类型分组（切到「全部情报」视图才显示）
    for t in ordered_types:
        inner = "\n".join(
            render_card(it)
            for it in sorted(groups[t], key=lambda x: RELEVANCE_ORDER.get(x["_rel"], 3))
        )
        badge = TYPE_CLASS.get(t, "t-other")
        sections.append(
            f'<section class="group group-all" data-group="{htmllib.escape(t, quote=True)}">'
            f'<h2><span class="badge {badge}">{htmllib.escape(t)}</span>'
            f'<span class="gn">{len(groups[t])} 条</span>'
            f'<span class="gbar"></span></h2>'
            f'<div class="grid">{inner}</div></section>'
        )

    stats = [f'共 <b>{len(items)}</b> 条情报']
    if new_n:
        stats.append(f'其中新品清单 <b>{new_n}</b> 条')
    if high_n:
        stats.append(f'其中 <b>{high_n}</b> 条高相关')
    for t in ordered_types:
        stats.append(f'{htmllib.escape(t)} <b>{len(groups[t])}</b>')
    if data.get("generated_at"):
        stats.append(f'生成于 {htmllib.escape(str(data["generated_at"]))}')

    subtitle = htmllib.escape(data.get("source_note") or "微博关注列表情报采集")

    # 视图提示：页面加载即处于「新品清单」，需把 body 标记与提示同步置位
    legend = ('<span data-only-view="new">当前为 <b>新品清单</b>：'
              '只列微博里出现的新品与它们的开订 / 发售 / 再版动向，'
              '按「首次亮相 → 可下单」排序，同一款产品的多条微博已合并。</span>'
              '<span data-only-view="all" hidden>当前为 <b>全部情报</b>：'
              '含实物测评、展会限定等全部类别，按类型分组。</span>'
              '　·　点击右栏缩略图可放大看原图，点标题或按钮可跳转原博（需登录微博）。')

    html = (HTML_TPL
            .replace("__CSS__", HTML_CSS)
            .replace("__JS__", HTML_JS)
            .replace("__TITLE__", f"手办情报 · {date}")
            .replace("__H1__", f"手办 / 可动人偶情报　<span style=\"font-size:15px;color:#8b95a3;font-weight:400\">{htmllib.escape(date)}</span>")
            .replace("__SUBTITLE__", subtitle)
            .replace("__STATS__", "".join(f"<span>{s}</span>" for s in stats))
            .replace("__VIEWS__", "".join(views))
            .replace("__TYPECHIPS__", "".join(chips))
            .replace("__RELCHIPS__", "".join(rel_chips))
            .replace("__SECTIONS__", "\n".join(sections))
            .replace("__LEGEND__", legend))
    # 默认视图为「新品清单」：body 带上标记，供 CSS / JS 初始状态对齐
    return html.replace("<body>", '<body class="view-new">', 1)


# 图床尺寸路径段（与 attach_media.py 保持一致）
_SIZE_SEG = re.compile(r"/(orj360|orj960|orj1080|large|mw690|thumbnail|thumb150|bmiddle|small|mw2000)/")

MEDIA_DIR = os.path.join(SKILL_DIR, "output", "media")
MEDIA_REL = "media"          # 相对 HTML 文件的路径，由 main() 按输出位置改写

MAX_THUMBS = 3


def img_variant(url, seg):
    """把图床 URL 换成指定尺寸档：orj360 缩略图 / orj960 预览大图。"""
    if not url:
        return ""
    return _SIZE_SEG.sub(f"/{seg}/", url, count=1)


def _img_name(url):
    return os.path.basename((url or "").split("?")[0])


def thumb_src(url):
    """缩略图：本地已下载则内嵌 base64（HTML 单文件也永远有图），否则回退外链。"""
    p = os.path.join(MEDIA_DIR, "thumb", _img_name(url))
    if os.path.exists(p):
        try:
            with open(p, "rb") as f:
                return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
        except Exception:
            pass
    return img_variant(url, "orj360")


def view_src(url):
    """预览大图：本地已下载则用相对路径（图床外链会被 403），否则回退外链。"""
    name = _img_name(url)
    if os.path.exists(os.path.join(MEDIA_DIR, "view", name)):
        return f"{MEDIA_REL}/view/{name}"
    return img_variant(url, "orj960")


def render_thumbs(it, e, url):
    """方案 A：缩略图放右栏顶部。最多显示 MAX_THUMBS 张，多余用 +N 角标，
    完整图集另存到卡片的 data-gallery，供放大预览左右翻页。"""
    imgs = [u for u in (it.get("images") or []) if u]
    if not imgs:
        return ""

    title = " · ".join(filter(None, [e("brand"), e("character") or e("ip")]))
    if not title:
        title = e("summary")[:22]
    cap = " · ".join(filter(None, [e("blogger"), title]))

    # 图集存最终可用地址（本地相对路径优先），供放大预览直接使用
    gal = htmllib.escape(json.dumps([view_src(u) for u in imgs], ensure_ascii=False),
                         quote=True)
    href = f' data-href="{htmllib.escape(url, quote=True)}"' if url else ""
    tre = " tre" if (it.get("image_source") or "") == "retweeted" else ""

    out = ['<div class="thumbs"']
    out.append(f' data-gallery="{gal}"')
    out.append(f' data-cap="{htmllib.escape(cap, quote=True)}"')
    out.append(f'{href}>')
    for i, u in enumerate(imgs[:MAX_THUMBS]):
        more = (f'<span class="more">+{len(imgs) - MAX_THUMBS}</span>'
                if i == MAX_THUMBS - 1 and len(imgs) > MAX_THUMBS else "")
        out.append(
            f'<button class="thumb{tre}" type="button" data-i="{i}"'
            f' aria-label="放大预览第 {i + 1} 张配图（共 {len(imgs)} 张）"'
            f' title="点击放大预览（共 {len(imgs)} 张）">'
            f'<img src="{htmllib.escape(thumb_src(u), quote=True)}" alt=""'
            f" onerror=\"this.closest('.thumb').style.display='none'\">"
            f'{more}</button>'
        )
    out.append('</div>')
    return "".join(out)


def render_card(it, idx=None, allow_new_in_main=False):
    """渲染一张情报卡。

    allow_new_in_main：默认 False。单日简报里新品清单与分类分组各渲染一份 DOM，
    靠 .group-new 容器区分归属（JS 的 match() 依赖这一点），所以分类分组里的卡片
    不能再带 isnew 归属标记。总览页的「按天浏览」视图只有一份 DOM、不参与新品归属
    判定，传 True 让新品标记正常显示即可。
    """
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

    is_new_it = is_new(it)
    # data-days：这款产品被报道过的日期（总览页跨天合并后才有；单日简报为空）。
    # 总览页的日期切换器靠它把卡片按天过滤。
    it_days = ",".join(str(x) for x in (it.get("_dates") or []) if x)
    parts = ['<article class="card"',
             f' data-type="{htmllib.escape(t, quote=True)}"',
             f' data-rel="{htmllib.escape(rel, quote=True)}"',
             f' data-isnew="{"1" if is_new_it else "0"}"']
    if it_days:
        parts.append(f' data-days="{htmllib.escape(it_days, quote=True)}"')
    parts.append(f' data-search="{htmllib.escape(search, quote=True)}">')
    if allow_new_in_main:
        # 供单页总览的「按天浏览」视图使用
        parts[0] = '<article class="card" data-in-main="1"'
    # 纯新品清单：左上角编号（仅在清单视图出现）
    if idx is not None:
        parts.append(f'<span class="idx">{idx}</span>')
    # 第一行：类型 / 相关度 / 时间
    parts.append('<div class="head">')
    parts.append(f'<span class="badge {TYPE_CLASS.get(t, "t-other")}">{htmllib.escape(t)}</span>')
    for k in (it.get("also_kinds") or []):
        parts.append(f'<span class="badge {TYPE_CLASS.get(k, "t-other")}"'
                     f' style="opacity:.62">{htmllib.escape(k)}</span>')
    nr = new_reason(it)
    if nr:
        parts.append(f'<span class="rank rank-1">{htmllib.escape(nr)}</span>')
    if rel:
        parts.append(f'<span class="rel {REL_CLASS.get(rel, "r-low")}">{htmllib.escape(rel)}相关</span>')
    if e("posted_at"):
        parts.append(f'<span class="time">{e("posted_at")}</span>')
    parts.append('</div>')

    # 第二行：左栏正文，右栏固定宽度放元信息与来源按钮
    parts.append('<div class="body"><div class="main">')
    if url:
        href = htmllib.escape(url, quote=True)
        title = (f'<a href="{href}" target="_blank" rel="noopener noreferrer"'
                 f' title="打开原博查看原文与原图">{title}</a>')
    parts.append(f'<h3>{title}</h3>')
    if e("summary"):
        parts.append(f'<p class="sum">{e("summary")}</p>')
    if e("relevance_reason"):
        parts.append(f'<div class="why">相关理由：{e("relevance_reason")}</div>')
    # 同一款产品的其他报道：保留全部来源链接，避免合并后丢线索
    alsos = [x for x in (it.get("also_sources") or []) if x.get("url")]
    if alsos:
        items_html = []
        for x in alsos:
            b = htmllib.escape((x.get("blogger") or "原博"), quote=True)
            u = htmllib.escape(x.get("url"), quote=True)
            when = x.get("posted_at") or ""
            tail = f'<span class="k">{htmllib.escape(when)}</span>' if when else ""
            items_html.append(f'<span><a href="{u}" target="_blank" '
                              f'rel="noopener noreferrer">@{b} ↗</a>{tail}</span>')
        parts.append(f'<div class="reports"><span class="k">另有 '
                     f'{len(alsos)} 条报道：</span>' + "".join(items_html) + '</div>')
    parts.append('</div><div class="side">')
    thumbs = render_thumbs(it, e, url)     # 方案 A：缩略图在右栏最顶部
    if thumbs:
        parts.append(thumbs)
    if facts:
        parts.append('<div class="facts">' + "".join(facts) + '</div>')
    parts.append(src)
    if tags:
        parts.append(f'<span class="tags">{tags}</span>')
    parts.append('</div></div></article>')
    return "".join(parts)


def main():
    ap = argparse.ArgumentParser(description="生成手办情报简报（Markdown / HTML）")
    ap.add_argument("--input", required=True, help="结构化情报 JSON")
    ap.add_argument("--out", help="输出 Markdown 路径（--format md/both 时生效）")
    ap.add_argument("--html-out", help="输出 HTML 路径（--format html/both 时生效）")
    ap.add_argument("--format", choices=["md", "html", "both"], default="both",
                    help="输出格式，默认 both（Markdown + HTML）")
    ap.add_argument("--media-dir", help="本地配图目录（默认 output/media）")
    ap.add_argument("--validate-only", action="store_true")
    args = ap.parse_args()

    global MEDIA_DIR, MEDIA_REL
    if args.media_dir:
        MEDIA_DIR = args.media_dir

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
            # 配图相对路径按 HTML 实际落地位置算，避免 HTML 换目录后图全丢
            MEDIA_REL = os.path.relpath(MEDIA_DIR,
                                        os.path.dirname(os.path.abspath(out))
                                        ).replace("\\", "/")
            with open(out, "w", encoding="utf-8") as f:
                f.write(render_html(data, items, date))
            written.append(out)
            n_img = sum(1 for it in items if it.get("images"))
            if n_img:
                local = os.path.join(MEDIA_DIR, "view")
                have = len(os.listdir(local)) if os.path.isdir(local) else 0
                print(f"配图：{n_img} 条带图，本地 media/view 已有 {have} 张"
                      + ("" if have else "（跑 attach_media.py --download 可补齐）"))

    for p in written:
        print(f"简报已生成：{p}")
    print(f"共 {count} 条情报")
    return 0


if __name__ == "__main__":
    sys.exit(main())
