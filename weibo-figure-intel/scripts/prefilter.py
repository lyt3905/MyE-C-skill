#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""手办情报粗筛器

读取 weibo_fetch.py 导出的候选微博，用 lexicon.json 打分过滤，
输出通过粗筛的微博供 agent 做结构化精抽。

白名单账号（route=whitelist）直接放行，不过关键词。
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")
DATA_DIR = os.path.join(SKILL_DIR, "data")
LEXICON_FILE = os.path.join(SCRIPTS_DIR, "lexicon.json")
CST = timezone(timedelta(hours=8))

LATIN_RE = re.compile(r"^[a-z0-9 ./_+\-:]+$")

# 转发时不带评论的几种形态：纯 @提及、纯链接、占位文本、纯 emoji
MENTION_RE = re.compile(r"@[^\s@#]{1,30}")
URL_RE = re.compile(r"https?://\S+|t\.cn/\S+")
TOPIC_RE = re.compile(r"#([^#\n]{1,40})#")
NOISE_RE = re.compile(r"[\s\W_]+")
PLACEHOLDERS = {"转发微博", "轉發微博", "转发", "轉發", "repost", "Repost", "REPOST"}


def substance_len(text):
    """去掉 @提及、链接、话题符号、标点与空白后剩余的「实质内容」长度。

    话题词（#变形金刚#）内部文字算实质内容，因为话题本身就是情报线索。
    """
    t = MENTION_RE.sub(" ", text or "")
    t = URL_RE.sub(" ", t)
    t = TOPIC_RE.sub(r"\1", t)
    t = NOISE_RE.sub("", t)
    for ph in PLACEHOLDERS:
        if t == ph or t == ph * 2:
            return 0
    return len(t)


def is_empty_comment(post, min_chars=4):
    """无实质评论的转发：典型如 `@A @B @C`、`转发微博`、`[doge]`。

    这类微博的正文不含任何信息，只是把原博搬运过来；若原博本身有情报，
    也应由原博作者那条承载，而不是在此处重复计数。
    """
    if not post.get("is_repost"):
        return False
    return substance_len(post.get("text")) < min_chars


def load_lexicon():
    with open(LEXICON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def build_matchers(lexicon):
    """把每个类别编译成 (term, 匹配函数) 列表。

    纯 ASCII 且较短的词（如 MP、SS86）用边界匹配，避免在 MPM、SS860 里误命中；
    中文词直接用子串匹配。
    """
    matchers = {}
    for cat, terms in lexicon["terms"].items():
        if not isinstance(terms, list):
            continue
        compiled = []
        for term in terms:
            t = term.strip()
            if not t:
                continue
            tl = t.lower()
            if LATIN_RE.match(tl) and len(tl) <= 6 and tl.isalnum():
                pat = re.compile(rf"(?<![a-z0-9]){re.escape(tl)}(?![a-z0-9])")
                compiled.append((t, lambda text, p=pat: bool(p.search(text))))
            else:
                compiled.append((t, lambda text, t=tl: t in text))
        matchers[cat] = compiled
    return matchers


def score_post(post, matchers, weights):
    text = " ".join(filter(None, [
        post.get("blogger") or "",
        post.get("text") or "",
        (post.get("retweeted") or {}).get("text") or "",
    ])).lower()

    matched = {}
    score = 0
    for cat, pairs in matchers.items():
        hits = [term for term, fn in pairs if fn(text)]
        if hits:
            matched[cat] = hits
            if cat == "negative":
                # 负分只计一次：营销词存在即降权，不随命中词数叠加。
                # 否则「开订公告 + 抽奖福利」这类真情报会被 抽奖+开奖 的
                # 双重负分（-12）压死（2026-09-16 实测 DLX 钢铁侠 Mark 1 开订被埋）。
                score += weights.get(cat, 0)
            else:
                score += weights.get(cat, 0) * min(len(hits), 3)

    # 核心词与厂商/产品线同时命中，额外加权（大概率是真情报而非泛泛提到）
    if matched.get("core") and (matched.get("brand") or matched.get("line")):
        score += 2
    return score, matched


def is_intel(score, matched, threshold, require_any):
    """总分达标 + 至少命中一个实质类别，才算一条情报。

    只出现「手办」「人偶」这类泛词（如「今天买了个手办」）不算情报。
    """
    if score < threshold:
        return False
    return any(matched.get(cat) for cat in require_any)


def parse_stamp(value):
    """把 created_at（YYYY-MM-DD HH:MM）解析成 datetime，失败返回 None。"""
    if not value:
        return None
    raw = value.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:16], fmt).replace(tzinfo=CST)
        except ValueError:
            continue
    return None


def is_too_old(post, max_age_days, now=None):
    """max_age_days<=0 表示不过滤；时间无法解析时保守放行。"""
    if not max_age_days or max_age_days <= 0:
        return False
    dt = parse_stamp(post.get("created_at"))
    if dt is None:
        return False
    now = now or datetime.now(CST)
    return (now - dt).days > max_age_days


def dedupe_reposts(posts):
    """同一条原博被多个账号转发时只保留一条，避免同一则公告重复入简报。

    保留规则：转发的评论文本最长者；等长时取更新时间较新者。
    被合并掉的账号名记入 `also_reposted_by`，便于简报里注明传播面。
    """
    groups = {}
    order = []
    for r in posts:
        rt_id = (r.get("retweeted") or {}).get("post_id")
        if not rt_id:
            continue
        groups.setdefault(rt_id, []).append(r)
        if rt_id not in order:
            order.append(rt_id)

    removed_ids = set()
    for rt_id in order:
        members = groups[rt_id]
        if len(members) < 2:
            continue
        winner = max(members, key=lambda r: (len(r.get("text") or ""),
                                             r.get("created_at") or ""))
        losers = [r for r in members if r is not winner]
        winner["also_reposted_by"] = [r.get("blogger") or "" for r in losers]
        for r in losers:
            removed_ids.add(r["post_id"])
    return [r for r in posts if r["post_id"] not in removed_ids], len(removed_ids)


def latest_candidates(explicit=None):
    if explicit:
        return explicit
    files = sorted(glob.glob(os.path.join(DATA_DIR, "candidates-*.json")))
    if not files:
        raise SystemExit("data/ 下没有 candidates-*.json，请先运行 weibo_fetch.py scan。")
    return files[-1]


def main():
    ap = argparse.ArgumentParser(description="手办情报粗筛")
    ap.add_argument("--input", help="候选微博 JSON，默认取最新的 candidates-*.json")
    ap.add_argument("--threshold", type=int, default=None, help="覆盖词库里的阈值")
    ap.add_argument("--preview", type=int, default=8, help="终端预览条数")
    ap.add_argument("--show-dropped", action="store_true", help="同时打印被丢弃的微博，用于调词库")
    ap.add_argument("--include-whitelist", action="store_true", default=True)
    ap.add_argument("--max-age-days", type=int, default=0,
                    help="丢弃早于 N 天的微博（0=不过滤）。首次全量抓取时建议设 14~30")
    ap.add_argument("--no-dedupe", action="store_true",
                    help="关闭同源转发去重（默认开启：同一原博的多条转发只留一条）")
    args = ap.parse_args()

    src = latest_candidates(args.input)
    with open(src, "r", encoding="utf-8") as f:
        payload = json.load(f)

    lexicon = load_lexicon()
    matchers = build_matchers(lexicon)
    weights = lexicon["weights"]
    threshold = args.threshold if args.threshold is not None else lexicon["threshold"]
    require_any = lexicon.get("require_any") or ("brand", "line", "event")

    passed, dropped, stale, empty_comment = [], [], [], []
    for post in payload.get("posts", []):
        if is_too_old(post, args.max_age_days):
            stale.append(post)
            continue
        score, matched = score_post(post, matchers, weights)
        record = dict(post)
        record["score"] = score
        record["matches"] = matched
        if post.get("route") == "whitelist":
            record["passed_by"] = "whitelist"
            passed.append(record)
        elif is_empty_comment(post):
            record["passed_by"] = None
            record["drop_reason"] = "无实质评论的转发"
            empty_comment.append(record)
        elif is_intel(score, matched, threshold, require_any):
            record["passed_by"] = "keyword"
            passed.append(record)
        else:
            record["passed_by"] = None
            dropped.append(record)

    passed.sort(key=lambda r: (-r["score"], r.get("created_at") or ""))
    merged = 0
    if not args.no_dedupe:
        passed, merged = dedupe_reposts(passed)

    stamp = datetime.now(CST).strftime("%Y%m%d-%H%M%S")
    out = os.path.join(DATA_DIR, f"filtered-{stamp}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "source": os.path.basename(src),
            "filtered_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M"),
            "threshold": threshold,
            "total": len(payload.get("posts", [])),
            "passed": len(passed),
            "dropped": len(dropped),
            "stale": len(stale),
            "empty_comment": len(empty_comment),
            "merged_reposts": merged,
            "posts": passed,
        }, f, ensure_ascii=False, indent=2)

    by_route = {}
    for r in passed:
        by_route[r["passed_by"]] = by_route.get(r["passed_by"], 0) + 1

    print(f"输入 {payload.get('count', 0)} 条微博（来自 {os.path.basename(src)}）")
    print(f"通过粗筛 {len(passed)} 条 / 丢弃 {len(dropped)} 条"
          f"（阈值 {threshold}）")
    if stale:
        print(f"  · 超出 {args.max_age_days} 天已剔除：{len(stale)} 条")
    if empty_comment:
        print(f"  · 无实质评论的转发已剔除：{len(empty_comment)} 条")
    if merged:
        print(f"  · 同源转发合并：{merged} 条")
    for k, v in by_route.items():
        print(f"  · {k}: {v} 条")
    print(f"\n结果已保存：{out}")

    if passed:
        print(f"\n--- 前 {min(args.preview, len(passed))} 条预览 ---")
        for r in passed[: args.preview]:
            tags = []
            for cat in ("core", "brand", "line", "line_weak", "event", "scale", "ip"):
                if r["matches"].get(cat):
                    tags.append(f"{cat}:{'/'.join(r['matches'][cat][:3])}")
            print(f"[{r['score']:>2}分] {r.get('blogger') or r.get('uid')}  "
                  f"{r.get('created_at') or ''}")
            print(f"       {tags}")
            print(f"       {(r.get('text') or '')[:90]}")

    if dropped and args.show_dropped:
        print(f"\n--- 被丢弃的 {len(dropped)} 条（用于调词库） ---")
        for r in dropped[: args.preview]:
            hits = {k: v for k, v in r["matches"].items() if v}
            why = "无实质命中" if not hits else f"仅命中 {list(hits)}"
            print(f"[{r['score']:>2}分] {r.get('blogger') or r.get('uid')}  {why}")
            print(f"       {(r.get('text') or '')[:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
