#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「精抽草稿」组装成规范的 intel JSON。

为什么要这个脚本：`url` / `blogger` / `posted_at` 过去靠 agent 手抄，
2026-09-12 那轮因此抄串了 12 条（URL 指向别人的微博），事后才靠人工比对发现。
改成本脚本后，这三个字段一律**从原始采集数据按 post_id 自动取**，agent 只写内容字段，
从流程上杜绝手抄错误。

用法：
    python assemble_intel.py --source data/filtered-20260915-100858.json \
                             --spec   data/_spec_20260915.json \
                             --out    data/intel-2026-09-15.json

spec 是一个 JSON 数组，每个元素必须有 `post_id`，其余为情报字段。
下列字段留空即自动从 source 填充：blogger / posted_at / url。
（转发类情报需要写原博作者时，显式给出 blogger + url 即可覆盖，脚本会提示哪些被覆盖。）

校验行为：
  · 未定义的字段名 → 报错退出（历史上的 `ip` 误打成 `iv` 会被静默丢弃，这里直接拦下）
  · post_id 在 source 中找不到 → 报错退出
  · intel_type / relevance 不在枚举内 → 报错退出
  · 必填字段缺失 → 报错退出
"""

import argparse
import json
import os
import sys
from datetime import datetime

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))

INTEL_TYPES = ["新品公布", "发售", "开订", "实物测评", "再版", "延期", "展会", "其他"]
RELEVANCE = ["高", "中", "低"]

# 与 references/intel-schema.md 保持一致
ALLOWED = {
    "post_id", "blogger", "posted_at", "url", "intel_type", "brand", "ip",
    "character", "line", "scale", "price", "preorder_date", "release_date",
    "channel", "summary", "relevance", "relevance_reason",
    "also_reposted_by", "tags",
}
REQUIRED = ["post_id", "intel_type", "summary", "relevance"]
AUTO = ["blogger", "posted_at", "url"]          # 从 source 自动填充
TEXT_FIELDS = ALLOWED - {"tags", "also_reposted_by"}   # tags 是数组，其余为字符串


def load_posts(path):
    """读 filtered-*.json 或 candidates-*.json，返回 {post_id: post}。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    posts = data.get("posts") if isinstance(data, dict) else data
    if not posts:
        sys.exit(f"✗ 源文件里找不到 posts：{path}")
    by_id = {}
    for p in posts:
        pid = str(p.get("post_id") or "")
        if pid:
            by_id[pid] = p
    return by_id, len(posts)


def die(msg, items=None):
    print(f"✗ {msg}")
    if items:
        for it in items:
            print(f"    · {it}")
    sys.exit(2)


def main():
    ap = argparse.ArgumentParser(description="组装 intel JSON（自动填 url/blogger/posted_at）")
    ap.add_argument("--source", required=True, help="filtered-*.json 或 candidates-*.json")
    ap.add_argument("--spec", required=True, help="精抽草稿 JSON（数组）")
    ap.add_argument("--out", required=True, help="输出 intel-YYYY-MM-DD.json")
    ap.add_argument("--date", help="简报日期，默认取 --out 文件名里的日期")
    ap.add_argument("--source-note", help="写进 source_note 的说明")
    args = ap.parse_args()

    by_id, total = load_posts(args.source)
    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)
    if not isinstance(spec, list) or not spec:
        sys.exit("✗ spec 必须是非空 JSON 数组")

    # ---------- 校验 ----------
    unknown, missing, notfound, bad_type, bad_rel = [], [], [], [], []
    for n, s in enumerate(spec, 1):
        bad = set(s) - ALLOWED
        if bad:
            unknown.append(f"第 {n} 条：{'、'.join(sorted(bad))}")
        for k in REQUIRED:
            if not str(s.get(k) or "").strip():
                missing.append(f"第 {n} 条缺 {k}")
        pid = str(s.get("post_id") or "")
        if pid not in by_id:
            notfound.append(f"第 {n} 条 post_id={pid}")
        if s.get("intel_type") and s["intel_type"] not in INTEL_TYPES:
            bad_type.append(f"第 {n} 条：{s['intel_type']} → 应为 {'/'.join(INTEL_TYPES)}")
        if s.get("relevance") and s["relevance"] not in RELEVANCE:
            bad_rel.append(f"第 {n} 条：{s['relevance']} → 应为 {'/'.join(RELEVANCE)}")

    if unknown:
        die("spec 里出现未定义字段（会被简报静默丢弃，故直接拦下）", unknown)
    if missing:
        die("必填字段缺失", missing)
    if notfound:
        die(f"post_id 在源文件中找不到（共 {total} 条可选）", notfound)
    if bad_type:
        die("intel_type 不在枚举内", bad_type)
    if bad_rel:
        die("relevance 不在枚举内", bad_rel)

    # ---------- 组装 ----------
    items, auto_filled, overridden = [], 0, []
    for s in spec:
        pid = str(s["post_id"])
        post = by_id[pid]
        item = {"post_id": pid}
        for k in AUTO:
            given = str(s.get(k) or "").strip()
            if given:
                if k in ("blogger", "url") and given != str(post.get(
                        "blogger" if k == "blogger" else "url") or "").strip():
                    overridden.append(f"post_id={pid} 的 {k} 手写为「{given}」，"
                                      f"源数据是「{post.get(k if k != 'posted_at' else 'created_at')}」")
                item[k] = given
            else:
                if k == "posted_at":
                    item[k] = str(post.get("created_at") or "").strip()
                else:
                    item[k] = str(post.get(k) or "").strip()
                auto_filled += 1
        for k, v in s.items():
            if k in AUTO or k == "post_id":
                continue
            if isinstance(v, list):
                if v:
                    item[k] = v
            elif str(v or "").strip():
                item[k] = v if not isinstance(v, str) else v.strip()
        items.append(item)

    # ---------- 输出 ----------
    date = args.date
    if not date:
        parts = os.path.basename(args.out).replace("intel-", "").replace(".json", "").split("-")
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            date = "-".join(parts)
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    out = {
        "date": date,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source_note": args.source_note or f"从 {total} 条粗筛候选中提取",
        "items": items,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    from collections import Counter
    rel = Counter(i["relevance"] for i in items)
    typ = Counter(i["intel_type"] for i in items)
    print(f"✓ 已写入 {args.out}")
    print(f"  情报 {len(items)} 条｜相关度 " +
          " ".join(f"{k}{rel.get(k, 0)}" for k in RELEVANCE) + "｜" +
          " ".join(f"{k}{v}" for k, v in typ.most_common()))
    print(f"  url/blogger/posted_at 自动填充 {auto_filled} 处")
    if overridden:
        print(f"  ⚠️ 手写覆盖 {len(overridden)} 处（若不是转发归因，请确认是否写错）：")
        for line in overridden:
            print(f"      · {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
