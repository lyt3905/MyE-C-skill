#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""手办情报简报生成器

读取结构化情报 JSON（由 agent 精抽后写入），渲染成按情报类型分组的 Markdown 简报。

用法：
    python build_digest.py --input data/intel-2026-09-12.json
    python build_digest.py --input xxx.json --validate-only
"""

import argparse
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
    return out, date, len(items)


def main():
    ap = argparse.ArgumentParser(description="生成手办情报 Markdown 简报")
    ap.add_argument("--input", required=True, help="结构化情报 JSON")
    ap.add_argument("--out", help="输出 Markdown 路径")
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

    lines, date, count = build(data)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out = args.out or os.path.join(OUTPUT_DIR, f"手办情报-{date}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"简报已生成：{out}")
    print(f"共 {count} 条情报")
    return 0


if __name__ == "__main__":
    sys.exit(main())
