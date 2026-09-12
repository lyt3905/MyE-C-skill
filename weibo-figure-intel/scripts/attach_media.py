#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""为情报条目回填配图（images[]）

设计要点
--------
**优先离线**：scan 阶段已经把所有微博原文（含 pics / retweeted.pics）落进
`data/candidates-*.json` 与 `data/wb_state.sqlite`。因此回填默认不打网络请求，
零风控、秒级完成。只有当某条情报在本地找不到时，才回连微博 show 接口兜底。

三级匹配（依次尝试，命中即止）：
    1. url 完全一致（最可靠，mblogid 唯一）
    2. mblogid 一致（容忍 http/https、www、尾斜杠差异）
    3. (blogger, created_at) 一致（时间到分钟，用于 url 手抄出错的容错）

**一致性校验**：url 命中后必须再核对该微博的 `blogger` 与 `created_at` 是否与
情报条的 `blogger` / `posted_at` 对得上。对不上说明 URL 抄错了（历史上真出现过
12 条 URL 指向别人微博），此时改用 blogger+时间重新定位，并在结尾报告冲突数，
避免把别人的图贴到本条上。

取图顺序：
    - 本条 `pics`
    - 本条是转发且无图 → 取 `retweeted.pics`（转发的原博图）

写入字段：
    images       原图 URL 列表（用 /orj960/）
    image_source  "self" | "retweeted"

**务必下载到本地**（--download）
    新浪图床 wx*.sinaimg.cn 的防盗链判定很特殊：只要请求带浏览器特征头
    （真实 Chrome/Edge UA + Sec-Fetch-*），Referer 不是 weibo.com 域就直接 403。
    实测「真实 Chrome UA + Sec-Fetch-* + 无 Referer」= 403，
    「空 UA」或「带 Referer: https://weibo.com/」= 200。
    所以从本地 HTML（file:// 或 localhost）外链微博图片**必然打不开**，
    必须下载到 output/media/{thumb,view}/ 再用相对路径引用。

用法：
    python attach_media.py --input data/intel-2026-09-12.json
    python attach_media.py --input xxx.json --candidates data/candidates-*.json
    python attach_media.py --input xxx.json --dry-run
    python attach_media.py --input xxx.json --download          # 顺带抓图到本地
    python attach_media.py --input xxx.json --download --workers 8
"""

import argparse
import glob
import io
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(SKILL_DIR, "data")
CST = timezone(timedelta(hours=8))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 微博图床尺寸路径段：/orj360/ 缩略图 /orj960/ 中图 /large/ 原图 /mw690/ 等
_SIZE_SEG = re.compile(r"/(orj360|orj960|orj1080|large|mw690|thumbnail|thumb150|bmiddle|small|mw2000)/")


# --------------------------------------------------------------------------- 工具

def size_variant(url, seg):
    """把图床 URL 换成指定尺寸档。已是该档则原样返回。"""
    if not url:
        return ""
    return _SIZE_SEG.sub(f"/{seg}/", url, count=1)


def thumb_url(url):
    """缩略图：行内用，体积小加载快。"""
    return size_variant(url, "orj360")


def view_url(url):
    """放大预览：清晰度与体积折中（单张约 180KB）。"""
    return size_variant(url, "orj960")


def mblogid_of(url):
    """从 https://weibo.com/<uid>/<mblogid> 里取出 mblogid。"""
    if not url:
        return ""
    m = re.search(r"weibo\.com/(?:\d+/)?([A-Za-z0-9]+)(?:[/?#]|$)", url)
    return m.group(1) if m else ""


def norm_time(value):
    """把 2026-09-09 06:34 / 2026-09-09 06:34:52 之类归一成 'YYYY-MM-DD HH:MM'。"""
    s = (value or "").strip().replace("T", " ")
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})[ ]+(\d{2}):(\d{2})", s)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}" if m else s


# --------------------------------------------------------------------------- 数据源

def load_local_posts(candidates_path=None):
    """从 candidates JSON 与 sqlite 读全部微博原文，返回 {post_id: post}。"""
    posts = {}

    # sqlite：scan 的长期去重库
    db = os.path.join(DATA_DIR, "wb_state.sqlite")
    if os.path.exists(db):
        try:
            con = sqlite3.connect(db)
            for row in con.execute(
                "SELECT post_id, uid, blogger, created_at, text, pics, url, retweeted FROM posts"
            ):
                pid, uid, blogger, created_at, text, pics, url, rt = row
                try:
                    pics = json.loads(pics) if pics else []
                except Exception:
                    pics = []
                try:
                    rt = json.loads(rt) if rt else None
                except Exception:
                    rt = None
                posts[pid] = {
                    "post_id": pid, "uid": uid, "blogger": blogger,
                    "created_at": created_at, "text": text,
                    "pics": pics, "url": url, "retweeted": rt,
                }
            con.close()
        except Exception as e:
            print(f"  ⚠️ 读 sqlite 失败（忽略）：{e}")

    # candidates JSON：覆盖 sqlite 缺失的（通常更全，且带 route 信息）
    paths = [candidates_path] if candidates_path else sorted(
        glob.glob(os.path.join(DATA_DIR, "candidates-*.json")))
    for p in paths:
        if not p or not os.path.exists(p):
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  ⚠️ 读 {os.path.basename(p)} 失败（忽略）：{e}")
            continue
        for post in (data.get("posts") or []):
            pid = str(post.get("post_id") or "")
            if not pid:
                continue
            posts[pid] = post          # candidates 覆盖 sqlite（字段更全）
    return posts


def build_index(posts):
    """建三套索引：url / mblogid / (blogger, 分钟级时间)。"""
    by_url, by_mblogid, by_key = {}, {}, {}
    for pid, p in posts.items():
        u = (p.get("url") or "").strip()
        if u:
            by_url[u] = p
            by_url[u.rstrip("/")] = p
            uu = u.replace("http://", "https://").replace("://www.", "://")
            by_url[uu.rstrip("/")] = p
        mid = mblogid_of(u)
        if mid:
            by_mblogid[mid] = p
        key = ((p.get("blogger") or "").strip(), norm_time(p.get("created_at")))
        if key[0] and key[1]:
            by_key.setdefault(key, p)
    return by_url, by_mblogid, by_key


def _time_delta_min(a, b):
    """两个 'YYYY-MM-DD HH:MM' 之间的分钟差；解析失败返回 None。"""
    fmt = "%Y-%m-%d %H:%M"
    try:
        return abs((datetime.strptime(a, fmt) - datetime.strptime(b, fmt)).total_seconds()) / 60
    except Exception:
        return None


def is_consistent(post, item, tol_min=3):
    """核对命中的微博是否真是这条情报的来源（防 URL 抄错贴错图）。"""
    pb = (post.get("blogger") or "").strip()
    ib = (item.get("blogger") or "").strip()
    if pb and ib and pb != ib:
        return False, f"博主不符（库中 {pb} ≠ 情报 {ib}）"
    pt = norm_time(post.get("created_at"))
    it_ = norm_time(item.get("posted_at"))
    d = _time_delta_min(pt, it_)
    if d is not None and d > tol_min:
        return False, f"时间不符（库中 {pt} ≠ 情报 {it_}）"
    return True, ""


def lookup(item, by_url, by_mblogid, by_key, tol_min=3):
    """三级匹配 + 一致性校验。返回 (post, 命中方式, 冲突说明)。"""
    key = ((item.get("blogger") or "").strip(), norm_time(item.get("posted_at")))
    alt = by_key.get(key) if key[0] and key[1] else None

    u = (item.get("url") or "").strip()
    candidates = []
    if u:
        for cand in (u, u.rstrip("/"),
                     u.replace("http://", "https://").replace("://www.", "://").rstrip("/")):
            if cand in by_url and by_url[cand] not in candidates:
                candidates.append(by_url[cand])
    if not candidates:
        mid = mblogid_of(u) or str(item.get("post_id") or "").strip()
        if mid and mid in by_mblogid:
            candidates.append(by_mblogid[mid])

    for post in candidates:
        ok, why = is_consistent(post, item, tol_min)
        if ok:
            return post, "url", ""
        # URL 指向的微博与情报条对不上 → 改用 blogger+时间 兜底
        if alt is not None and alt is not post:
            return alt, "blogger+time（URL 存疑，已纠正）", why
        return post, "url（未通过校验，仅供核对）", why

    if alt is not None:
        return alt, "blogger+time", ""
    return None, "", ""


def pick_images(post):
    """取图：优先本条 pics，其次转发原博 pics。返回 (images, source)。"""
    own = [u for u in (post.get("pics") or []) if u]
    if own:
        return own, "self"
    rt = post.get("retweeted") or {}
    if isinstance(rt, dict):
        rp = [u for u in (rt.get("pics") or []) if u]
        if rp:
            return rp, "retweeted"
    return [], ""


def fetch_remote(url, cookie):
    """兜底：回连微博 show 接口取单条原文。失败返回 None。"""
    mid = mblogid_of(url) or url
    api = f"https://weibo.com/ajax/statuses/show?id={mid}"
    req = urllib.request.Request(api, headers={
        "User-Agent": UA,
        "Referer": "https://weibo.com/",
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": cookie,
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("ok") == 0:
        return None
    pics = []
    for pi in (data.get("pic_infos") or {}).values():
        u = ((pi.get("largest") or pi.get("large") or {}).get("url")) or ""
        if u:
            pics.append(u)
    if not pics:
        for m in (data.get("pics") or []):
            u = (m.get("large") or {}).get("url") or m.get("url") or ""
            if u:
                pics.append(u)
    rt = data.get("retweeted_status") or {}
    rpics = []
    for m in (rt.get("pics") or []):
        u = (m.get("large") or {}).get("url") or m.get("url") or ""
        if u:
            rpics.append(u)
    if pics:
        return pics, "self"
    if rpics:
        return rpics, "retweeted"
    return [], ""


# --------------------------------------------------------------------------- 下载

THUMB_SEG = "orj360"     # 行内缩略图
VIEW_SEG = "orj960"      # 放大预览
MAX_THUMBS = 3           # 每条卡片显示几张（与 build_digest.MAX_THUMBS 一致）

MEDIA_DIR = os.path.join(SKILL_DIR, "output", "media")


def _basename(url):
    return os.path.basename(url.split("?")[0]) or "img.jpg"


def download_one(task):
    """下载单张图。task = (url, dest)。已存在则跳过。"""
    url, dest = task
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return dest, os.path.getsize(dest), True
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": "https://weibo.com/",      # 关键：必须带微博域 Referer
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = r.read()
    except Exception as e:
        return dest, 0, False
    if not data:
        return dest, 0, False
    with open(dest, "wb") as f:
        f.write(data)
    return dest, len(data), False


def download_media(items, workers=8):
    """抓取缩略图（每条第 1..MAX_THUMBS 张）与预览大图（全部）到本地。"""
    from concurrent.futures import ThreadPoolExecutor

    tasks, seen = [], set()
    for it in items:
        for i, u in enumerate(it.get("images") or []):
            if not u:
                continue
            name = _basename(u)
            if i < MAX_THUMBS:
                t = os.path.join(MEDIA_DIR, "thumb", name)
                if t not in seen:
                    seen.add(t)
                    tasks.append((size_variant(u, THUMB_SEG), t))
            v = os.path.join(MEDIA_DIR, "view", name)
            if v not in seen:
                seen.add(v)
                tasks.append((size_variant(u, VIEW_SEG), v))

    for sub in ("thumb", "view"):
        os.makedirs(os.path.join(MEDIA_DIR, sub), exist_ok=True)

    print(f"\n开始下载 {len(tasks)} 张图到 {MEDIA_DIR} …")
    ok = cached = fail = 0
    total_bytes = 0
    failures = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        done = 0
        for dest, size, is_cached in ex.map(download_one, tasks):
            done += 1
            if size:
                ok += 1
                total_bytes += size
                if is_cached:
                    cached += 1
            else:
                fail += 1
                failures.append(dest)
            if done % 80 == 0 or done == len(tasks):
                print(f"  进度 {done}/{len(tasks)}"
                      f"　累计 {total_bytes / 1048576:.1f} MB")

    print(f"下载完成：成功 {ok}（其中复用本地 {cached}），失败 {fail}"
          f"，共 {total_bytes / 1048576:.1f} MB")
    if failures:
        print(f"  ⚠️ 失败示例：{failures[:3]}")
    return ok, fail


def load_cookie():
    p = os.path.join(SKILL_DIR, "scripts", "wb_cookie.json")
    if not os.path.exists(p):
        return ""
    try:
        with open(p, "r", encoding="utf-8") as f:
            return (json.load(f).get("SUB") or "").strip()
    except Exception:
        return ""


# --------------------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(description="为情报条目回填配图 images[]")
    ap.add_argument("--input", required=True, help="结构化情报 JSON（原地更新）")
    ap.add_argument("--candidates", help="指定 candidates JSON（默认自动找最新）")
    ap.add_argument("--out", help="输出到新文件（默认原地覆盖，会先备份 .bak）")
    ap.add_argument("--dry-run", action="store_true", help="只统计不写文件")
    ap.add_argument("--remote", action="store_true",
                    help="本地未命中时回连微博取图（默认关闭，纯离线）")
    ap.add_argument("--max-notice", type=int, default=12,
                    help="未命中条目最多详细列出几条")
    ap.add_argument("--download", action="store_true",
                    help="把缩略图与预览图抓到 output/media/（本地 HTML 外链会被图床 403）")
    ap.add_argument("--media-dir", help="图片落地目录（默认 output/media）")
    ap.add_argument("--workers", type=int, default=8, help="下载并发数")
    args = ap.parse_args()

    global MEDIA_DIR
    if args.media_dir:
        MEDIA_DIR = args.media_dir

    if not os.path.exists(args.input):
        print(f"❌ 找不到输入文件：{args.input}")
        return 1

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("items") or []
    if not items:
        print("❌ 情报 JSON 里没有 items")
        return 1

    posts = load_local_posts(args.candidates)
    by_url, by_mblogid, by_key = build_index(posts)
    print(f"本地库：{len(posts)} 条微博原文"
          f"（其中 {sum(1 for p in posts.values() if p.get('pics'))} 条带图）")

    cookie = load_cookie() if args.remote else ""
    hit_method, with_img, no_img, missed = {}, 0, 0, []
    conflicts, total_pics = [], 0

    for it in items:
        post, how, why = lookup(it, by_url, by_mblogid, by_key)
        imgs, src = ([], "")
        if post:
            hit_method[how] = hit_method.get(how, 0) + 1
            imgs, src = pick_images(post)
            if why:
                conflicts.append((it, how, why,
                                  (post.get("url") or "").strip()))
        elif args.remote and cookie and it.get("url"):
            got = fetch_remote(it["url"], cookie)
            if got:
                imgs, src = got
                hit_method["remote"] = hit_method.get("remote", 0) + 1

        if imgs:
            it["images"] = imgs
            it["image_source"] = src
            with_img += 1
            total_pics += len(imgs)
        else:
            it.pop("images", None)
            it.pop("image_source", None)
            if post:
                no_img += 1
            else:
                missed.append(it)

    print(f"\n匹配成功：{with_img + no_img} / {len(items)}"
          f"　命中方式 {hit_method or '—'}")
    print(f"  带图：{with_img} 条（共 {total_pics} 张）")
    print(f"  无图：{no_img} 条（原博本身没配图）")
    print(f"  未匹配：{len(missed)} 条（本地库找不到该微博）")

    if conflicts:
        print(f"\n⚠️ 来源存疑 {len(conflicts)} 条（URL 与情报条对不上，已按博主+时间纠正）：")
        for it, how, why, lib_url in conflicts[:args.max_notice]:
            print(f"  - {it.get('blogger','?')} {it.get('posted_at','?')}")
            print(f"      {why}")
            print(f"      情报 URL {it.get('url','(无)')}")
            if lib_url:
                print(f"      库中 URL {lib_url}")
        if len(conflicts) > args.max_notice:
            print(f"  … 另有 {len(conflicts) - args.max_notice} 条")
        print("  建议：核对以上条目并回写正确 URL（改 data/*.json 后重跑本脚本）。")

    if missed:
        print(f"\n未匹配明细（最多 {args.max_notice} 条）：")
        for it in missed[:args.max_notice]:
            print(f"  - {it.get('blogger','?')} {it.get('posted_at','?')} "
                  f"{it.get('url','(无 url)')}")
        if len(missed) > args.max_notice:
            print(f"  … 另有 {len(missed) - args.max_notice} 条")

    if args.dry_run:
        print("\n（--dry-run，未写入文件）")
        return 0

    out = args.out or args.input
    if out == args.input and not os.path.exists(args.input + ".bak"):
        with open(args.input, "r", encoding="utf-8") as f:
            raw = f.read()
        with open(args.input + ".bak", "w", encoding="utf-8") as f:
            f.write(raw)
        print(f"\n已备份原文件：{args.input}.bak")

    data["media_attached_at"] = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    data["media_note"] = (f"{with_img} 条带配图（共 {total_pics} 张），"
                          f"取自本地采集库；缩略图 /orj360/，预览 /orj960/")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已写入：{out}")

    if args.download:
        ok, fail = download_media(items, max(1, args.workers))
        data["media_local"] = {
            "dir": os.path.relpath(MEDIA_DIR, SKILL_DIR).replace("\\", "/"),
            "downloaded": ok, "failed": fail,
            "note": "本地 HTML 通过相对路径引用；图床对浏览器请求校验 Referer，外链会 403",
        }
        data["media_note"] += "；已落地本地媒体目录"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"已更新：{out}（补记 media_local）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
