#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""微博手办情报采集器

职责：带登录 Cookie 调 weibo.com 桌面端 Ajax 接口，拉取关注列表 / 指定账号
的增量微博，落库 SQLite 去重，并导出候选微博 JSON 供后续粗筛与情报抽取。

接口选择（2026-09 实测）：
  * m.weibo.cn 移动端接口对 `.weibo.com` 域名签发的 SUB 一律返回未登录，
    故本脚本全部走 weibo.com 桌面端 Ajax 接口。
  * `friendships/friends` 不带 uid 时返回**登录者本人**的关注列表，
    因此无需预先知道自己的 uid。
  * `statuses/mymblog` 不支持服务端 since_id（传了也会被忽略），
    增量改由客户端按 post_id 单调递增比较实现。

仅使用 Python 标准库，无需安装依赖。
"""

import argparse
import html
import json
import os
import random
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")
DATA_DIR = os.path.join(SKILL_DIR, "data")
COOKIE_FILE = os.path.join(SCRIPTS_DIR, "wb_cookie.json")
WATCHLIST_FILE = os.path.join(SCRIPTS_DIR, "watchlist.json")
STATE_DB = os.path.join(DATA_DIR, "wb_state.sqlite")

UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

BASE = "https://weibo.com"
API_FRIENDS = BASE + "/ajax/friendships/friends"
API_MYBLOG = BASE + "/ajax/statuses/mymblog"

CST = timezone(timedelta(hours=8))


class CookieInvalid(Exception):
    """登录态失效：需要用户重新提供 SUB Cookie。"""


class RateLimited(Exception):
    """触发频率风控：应降低请求频率或缩小抓取范围。"""


class FetchError(Exception):
    """其他抓取失败。"""


# --------------------------------------------------------------------------
# 网络层
# --------------------------------------------------------------------------

def load_cookie():
    """读取 wb_cookie.json，返回可直接放进请求头的 Cookie 字符串。"""
    if not os.path.exists(COOKIE_FILE):
        raise CookieInvalid(
            f"未找到 {COOKIE_FILE}。请先创建该文件并写入微博登录 Cookie，"
            '格式为 {"cookie": "SUB=xxx"}。'
        )
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    raw = (cfg.get("cookie") or "").strip()
    if raw:
        return raw

    # 兼容按字段分开填写的情况
    parts = [f"{k}={v}" for k, v in cfg.items() if not k.startswith("_") and v]
    if not parts:
        raise CookieInvalid("wb_cookie.json 中没有读到 Cookie 内容。")
    return "; ".join(parts)


def _http_get(url, cookie, referer, ua, timeout=25):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": ua,
            "Referer": referer,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "X-Requested-With": "XMLHttpRequest",
            "Cookie": cookie,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


def polite_get(url, cookie, referer, ua=UA_DESKTOP, retries=3,
               gap=(2.0, 4.0), backoff=(10.0, 20.0)):
    """带随机间隔与退避的 GET。432/403/401/418 视为风控并退避重试。"""
    last_err = None
    for attempt in range(retries):
        try:
            body = _http_get(url, cookie, referer, ua)
            time.sleep(random.uniform(*gap))
            return body
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (432, 403, 401, 418):
                time.sleep(random.uniform(*backoff))
                continue
            time.sleep(random.uniform(*gap))
        except urllib.error.URLError as e:
            last_err = e
            time.sleep(random.uniform(*gap))
    if isinstance(last_err, urllib.error.HTTPError) and last_err.code in (403, 401):
        raise CookieInvalid(f"接口返回 {last_err.code}，登录 Cookie 可能已失效。")
    raise RateLimited(f"多次请求失败（最后一次：{last_err}），疑似触发频率风控。")


def get_json(url, cookie, referer, ua=UA_DESKTOP, **kw):
    body = polite_get(url, cookie, referer, ua=ua, **kw)
    if not body.strip():
        raise RateLimited("接口返回空响应，疑似被风控。")
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise FetchError(f"响应不是合法 JSON：{e}")


# --------------------------------------------------------------------------
# 接口封装
# --------------------------------------------------------------------------

def check_login(cookie):
    """校验登录态：请求本人关注列表，返回 (self_uid, screen_name, following_total)。

    桌面端没有直接返回自身 uid 的接口，但 `friendships/friends` 不带 uid 时
    返回的就是登录者本人的关注列表，足以完成校验与身份识别。
    """
    data = get_json(f"{API_FRIENDS}?page=1", cookie, referer=f"{BASE}/",
                    retries=2)
    if data.get("ok") != 1:
        raise CookieInvalid(
            f"接口返回 ok={data.get('ok')}，未通过登录校验，请重新获取 SUB。"
        )
    name = data.get("screenName") or ""
    total = data.get("total_number")
    return "", name, total


def pull_following(cookie, max_pages=50):
    """拉取本人关注列表。不带 uid 参数即代表本人，分页 20 人/页。"""
    users, page, total = [], 1, None
    while page <= max_pages:
        url = f"{API_FRIENDS}?" + urllib.parse.urlencode({"page": page})
        data = get_json(url, cookie, referer=f"{BASE}/", retries=2)
        if data.get("ok") != 1:
            raise CookieInvalid(f"关注列表接口返回 ok={data.get('ok')}，请重新获取 SUB。")
        batch = data.get("users") or []
        if total is None:
            total = data.get("total_number")
            if data.get("screenName"):
                print(f"  当前账号：{data['screenName']}")
        if not batch:
            break
        for u in batch:
            users.append({
                "uid": str(u.get("id") or u.get("idstr") or ""),
                "screen_name": u.get("screen_name") or "",
                "remark": u.get("remark") or "",
                "followers_count": u.get("followers_count") or 0,
                "description": (u.get("description") or "").replace("\n", " ")[:120],
            })
        print(f"  关注列表 第 {page} 页，累计 {len(users)} 人")
        if total and len(users) >= int(total):
            break
        page += 1
    return users, total


def fetch_user_posts(cookie, uid, last_id=None, pages=1, gap=(2.0, 4.0)):
    """拉取某账号的微博。

    last_id 为上次见过的最大 post_id：只保留比它更新的微博，并在追到旧微博的
    那一页停止翻页（微博 id 随时间是单调递增的）。
    """
    posts = []
    boundary = int(last_id) if last_id else None
    for page in range(1, pages + 1):
        url = f"{API_MYBLOG}?" + urllib.parse.urlencode(
            {"uid": uid, "page": page, "feature": 0}
        )
        data = get_json(url, cookie, referer=f"{BASE}/u/{uid}", retries=2, gap=gap)
        if data.get("ok") != 1:
            raise FetchError(f"接口返回 ok={data.get('ok')}")
        batch = (data.get("data") or {}).get("list") or []
        if not batch:
            break

        fresh_count = 0
        for mblog in batch:
            pid = str(mblog.get("idstr") or mblog.get("id") or "")
            if not pid:
                continue
            if boundary is not None and int(pid) <= boundary:
                continue
            parsed = parse_mblog(mblog, uid)
            if parsed:
                posts.append(parsed)
                fresh_count += 1

        # 增量模式下，本页已出现旧微博 => 边界已到，不必再翻页
        if boundary is not None and fresh_count < len(batch):
            break

    newest = max((p["post_id"] for p in posts), key=int) if posts else last_id
    return posts, newest


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------

TAG_RE = re.compile(r"<[^>]+>")
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
_DESKTOP_TIME = re.compile(
    r"^[A-Za-z]{3}\s+([A-Za-z]{3})\s+(\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})\s+([+-]\d{4})\s+(\d{4})$"
)


def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = TAG_RE.sub("", text)
    return html.unescape(text).strip()


def parse_created(mblog):
    """桌面端 created_at 形如 `Thu Aug 13 12:26:52 +0800 2026`。"""
    raw = (mblog.get("created_at") or "").strip()
    m = _DESKTOP_TIME.match(raw)
    if m:
        mon, day, hh, mm, ss, tz, year = m.groups()
        try:
            dt = datetime(int(year), _MONTHS[mon.capitalize()], int(day),
                          int(hh), int(mm), int(ss), tzinfo=CST)
            return dt.strftime("%Y-%m-%d %H:%M")
        except (KeyError, ValueError):
            pass
    return raw


def _pics_of(mblog):
    """从 pic_infos 取大图；退化时用 pic_ids 拼 URL。"""
    urls = []
    infos = mblog.get("pic_infos") or {}
    for pid in (mblog.get("pic_ids") or []):
        info = infos.get(pid) or {}
        url = ((info.get("large") or {}).get("url")
               or (info.get("largest") or {}).get("url")
               or (info.get("bmiddle") or {}).get("url"))
        if url:
            urls.append(url)
        elif pid:
            urls.append(f"https://wx1.sinaimg.cn/large/{pid}.jpg")
    return urls


def parse_mblog(mblog, uid):
    post_id = str(mblog.get("idstr") or mblog.get("id") or "")
    if not post_id:
        return None

    # text_raw 是去标签的纯文本，直接用；缺失时回退到 HTML 清洗
    text = (mblog.get("text_raw") or "").strip() or strip_html(mblog.get("text"))

    retweeted = None
    rt = mblog.get("retweeted_status")
    if rt:
        rt_user = rt.get("user") or {}
        retweeted = {
            "post_id": str(rt.get("idstr") or rt.get("id") or ""),
            "author": rt_user.get("screen_name") or "",
            "text": (rt.get("text_raw") or "").strip() or strip_html(rt.get("text")),
            "pics": _pics_of(rt),
        }

    user = mblog.get("user") or {}
    author_id = str(user.get("idstr") or user.get("id") or uid)
    mblogid = mblog.get("mblogid") or ""

    return {
        "post_id": post_id,
        "uid": str(uid),
        "blogger": user.get("screen_name") or "",
        "created_at": parse_created(mblog),
        "text": text,
        "pics": _pics_of(mblog),
        "is_repost": bool(rt),
        "is_long_text": bool(mblog.get("isLongText")),
        "retweeted": retweeted,
        "reposts_count": mblog.get("reposts_count") or 0,
        "comments_count": mblog.get("comments_count") or 0,
        "attitudes_count": mblog.get("attitudes_count") or 0,
        "url": f"{BASE}/{author_id}/{mblogid}" if mblogid else f"{BASE}/detail/{post_id}",
    }


# --------------------------------------------------------------------------
# 存储
# --------------------------------------------------------------------------

def db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(STATE_DB)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS posts (
            post_id     TEXT PRIMARY KEY,
            uid         TEXT,
            blogger     TEXT,
            created_at  TEXT,
            text        TEXT,
            pics        TEXT,
            is_repost   INTEGER,
            retweeted   TEXT,
            url         TEXT,
            first_seen  TEXT
        );
        CREATE TABLE IF NOT EXISTS accounts (
            uid          TEXT PRIMARY KEY,
            screen_name  TEXT,
            note         TEXT,
            list_type    TEXT,
            last_post_id TEXT,
            last_checked TEXT
        );
        CREATE TABLE IF NOT EXISTS following (
            uid             TEXT PRIMARY KEY,
            screen_name     TEXT,
            remark          TEXT,
            followers_count INTEGER,
            description     TEXT,
            updated_at      TEXT
        );
        """
    )
    return conn


def save_posts(conn, posts):
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    new = []
    cur = conn.cursor()
    for p in posts:
        cur.execute("SELECT 1 FROM posts WHERE post_id = ?", (p["post_id"],))
        if cur.fetchone():
            continue
        cur.execute(
            "INSERT INTO posts (post_id, uid, blogger, created_at, text, pics,"
            " is_repost, retweeted, url, first_seen) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (p["post_id"], p["uid"], p["blogger"], p["created_at"], p["text"],
             json.dumps(p["pics"], ensure_ascii=False), int(p["is_repost"]),
             json.dumps(p["retweeted"], ensure_ascii=False) if p["retweeted"] else None,
             p["url"], now),
        )
        new.append(p)
    conn.commit()
    return new


def save_following(conn, users):
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    conn.executemany(
        "INSERT INTO following (uid, screen_name, remark, followers_count, description,"
        " updated_at) VALUES (?,?,?,?,?,?)"
        " ON CONFLICT(uid) DO UPDATE SET screen_name=excluded.screen_name,"
        " remark=excluded.remark, followers_count=excluded.followers_count,"
        " description=excluded.description, updated_at=excluded.updated_at",
        [(u["uid"], u["screen_name"], u.get("remark", ""), u.get("followers_count", 0),
          u.get("description", ""), now) for u in users if u["uid"]],
    )
    conn.commit()


def load_watchlist():
    if not os.path.exists(WATCHLIST_FILE):
        return {"whitelist": [], "blacklist": []}
    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------

def cmd_login_check(args):
    cookie = load_cookie()
    _, name, total = check_login(cookie)
    print(f"登录态有效 ✅  账号={name}  关注={total} 人")
    return 0


def cmd_pull_following(args):
    cookie = load_cookie()
    print("开始拉取关注列表…")
    users, total = pull_following(cookie, max_pages=args.max_pages)
    conn = db()
    save_following(conn, users)

    out = os.path.join(DATA_DIR, f"following-{datetime.now(CST).strftime('%Y-%m-%d')}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"total": total, "count": len(users), "users": users},
                  f, ensure_ascii=False, indent=2)
    print(f"\n共关注 {len(users)} 人（接口报告 total={total}）")
    print(f"名单已保存：{out}")
    return 0


def cmd_scan(args):
    cookie = load_cookie()
    conn = db()
    wl = load_watchlist()
    whitelist = {str(x) for x in wl.get("whitelist", [])}
    blacklist = {str(x) for x in wl.get("blacklist", [])}

    rows = conn.execute(
        "SELECT f.uid, f.screen_name, a.last_post_id FROM following f"
        " LEFT JOIN accounts a ON a.uid = f.uid"
    ).fetchall()
    if not rows:
        print("关注列表为空，请先执行 pull-following。")
        return 1

    if args.list == "whitelist":
        if not whitelist:
            print("watchlist.json 的 whitelist 是空的，没有可抓取的账号。")
            return 1
        rows = [r for r in rows if str(r[0]) in whitelist]
        if not rows:
            print("白名单里的 UID 在关注列表中匹配不到，请确认 UID 填写正确。")
            return 1

    targets = [r for r in rows if str(r[0]) not in blacklist]
    blocked = len(rows) - len(targets)
    if args.max_accounts:
        targets = targets[: args.max_accounts]
    note = f"，黑名单跳过 {blocked} 个" if blocked else ""
    if args.max_accounts and len(rows) - blocked > len(targets):
        note += f"，本次仅试跑前 {len(targets)} 个"
    print(f"待抓取 {len(targets)} 个账号{note}，"
          f"每个账号最多 {args.pages} 页，{'全量' if args.full else '增量'}模式")

    collected, ok, limited, failed, broken = [], 0, 0, 0, False
    for i, (uid, name, last_id) in enumerate(targets, 1):
        uid = str(uid)
        boundary = None if args.full else last_id
        try:
            posts, newest = fetch_user_posts(cookie, uid, boundary, pages=args.pages)
            new = save_posts(conn, posts)
            route = "whitelist" if uid in whitelist else "keyword"
            for p in new:
                p["route"] = route
            collected.extend(new)
            conn.execute(
                "INSERT INTO accounts (uid, screen_name, list_type, last_post_id, last_checked)"
                " VALUES (?,?,?,?,datetime('now','+8 hours'))"
                " ON CONFLICT(uid) DO UPDATE SET screen_name=excluded.screen_name,"
                " last_post_id=COALESCE(excluded.last_post_id, accounts.last_post_id),"
                " last_checked=excluded.last_checked",
                (uid, name, "whitelist" if uid in whitelist else "auto", newest or last_id),
            )
            conn.commit()
            ok += 1
            print(f"  [{i}/{len(targets)}] {name or uid}  新增 {len(new)} 条")
        except CookieInvalid as e:
            print(f"\n❌ {e}\n已抓到的结果已落库，更新 Cookie 后可重跑。")
            broken = True
            break
        except RateLimited:
            limited += 1
            print(f"  [{i}/{len(targets)}] {name or uid}  ⚠️ 风控跳过")
        except FetchError as e:
            failed += 1
            print(f"  [{i}/{len(targets)}] {name or uid}  ⚠️ {e}")

    stamp = datetime.now(CST).strftime("%Y%m%d-%H%M%S")
    out = os.path.join(DATA_DIR, f"candidates-{stamp}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "fetched_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M"),
            "accounts_ok": ok, "accounts_ratelimited": limited, "accounts_failed": failed,
            "count": len(collected), "posts": collected,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n抓取完成：成功 {ok} / 风控 {limited} / 失败 {failed}")
    print(f"新增微博 {len(collected)} 条 → {out}")
    if limited:
        print("提示：风控较多时，减小 --max-accounts 或稍后重跑，本脚本会自动接着增量抓。")
    return 2 if broken else 0


def cmd_stats(args):
    conn = db()
    f = conn.execute("SELECT COUNT(*) FROM following").fetchone()[0]
    p = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    a = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    print(f"关注列表缓存：{f} 人\n已见微博：{p} 条\n已扫描账号：{a} 个")
    return 0


def main():
    ap = argparse.ArgumentParser(description="微博手办情报采集器")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login-check", help="校验 Cookie 登录态").set_defaults(func=cmd_login_check)

    p = sub.add_parser("pull-following", help="拉取并缓存关注列表")
    p.add_argument("--max-pages", type=int, default=50)
    p.set_defaults(func=cmd_pull_following)

    p = sub.add_parser("scan", help="抓取微博增量并导出候选")
    p.add_argument("--list", choices=["all", "whitelist"], default="all")
    p.add_argument("--pages", type=int, default=1, help="每个账号最多抓取页数")
    p.add_argument("--max-accounts", type=int, default=0, help="限制账号数，用于试跑")
    p.add_argument("--full", action="store_true", help="忽略增量边界，全量抓取")
    p.set_defaults(func=cmd_scan)

    sub.add_parser("stats", help="查看本地状态").set_defaults(func=cmd_stats)

    args = ap.parse_args()
    try:
        return args.func(args)
    except CookieInvalid as e:
        print(f"❌ {e}")
        return 2
    except KeyboardInterrupt:
        print("\n已中断。")
        return 130


if __name__ == "__main__":
    sys.exit(main())
