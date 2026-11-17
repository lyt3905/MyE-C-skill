#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""alm.py — AliExpressMonitor 本地控制台操作 CLI。

覆盖：健康/概览、扫描、商品列表、批量改状态、picker 采集队列、库内计数与重复诊断。
鉴权：默认走「本地写」CSRF（自动从 GET / 取 token）；如设环境变量 ALM_AGENT_TOKEN 则改用 Bearer。

环境变量：
  ALM_BASE     控制台地址，默认 http://127.0.0.1:18765
  ALM_PROJECT  项目根，默认 D:\\GitHub\\AliExpressMonitor（读 products.db 用）

用法示例见 SKILL.md。运行： <项目>/.venv/Scripts/python.exe -X utf8 alm.py <cmd> [opts]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request

try:  # Windows 控制台尽量用 UTF-8 输出
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

BASE = os.environ.get("ALM_BASE", "http://127.0.0.1:18765").rstrip("/")
PROJECT = os.environ.get("ALM_PROJECT", r"D:\GitHub\AliExpressMonitor")
DB = os.path.join(PROJECT, "data", "products.db")

STATES_CN = {
    "pending_review": "待判断",
    "to_process": "待处理",
    "ignored": "已忽略",
    "completed": "已完成",
}


# ----------------------------------------------------------------------------- HTTP
class _Ctx:
    csrf: str | None = None


def _csrf() -> str:
    if _Ctx.csrf is None:
        with urllib.request.urlopen(BASE + "/", timeout=15) as r:
            html = r.read().decode("utf-8", "replace")
        m = re.search(r'\{"csrfToken":"([^"]+)"\}', html)
        if not m:
            raise SystemExit("无法从首页取到 csrfToken（服务没起？先 alm.py health）")
        _Ctx.csrf = m.group(1)
    return _Ctx.csrf


def api(method: str, path: str, body=None, agent: bool | None = None):
    url = BASE + path
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    token = os.environ.get("ALM_AGENT_TOKEN")
    use_agent = bool(token) if agent is None else agent
    if use_agent and token:
        req.add_header("Authorization", "Bearer " + token)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if method in ("POST", "PATCH", "PUT", "DELETE") and not (use_agent and token):
        req.add_header("x-csrf-token", _csrf())
        req.add_header("Origin", BASE)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw) if raw else None
        except Exception:
            return e.code, raw


def die_on(code, payload, what):
    if code >= 400:
        sys.stderr.write(f"[{what}] HTTP {code}: {json.dumps(payload, ensure_ascii=False)}\n")
        raise SystemExit(1)
    return payload


# ----------------------------------------------------------------------------- helpers
def today_local() -> str:
    return _dt.date.today().isoformat()


def build_filter(args, default_state="pending_review"):
    f = {}
    state = getattr(args, "state", None)
    if state:
        f["state"] = state
    elif default_state:
        f["state"] = default_state
    shop = getattr(args, "shop", None)
    if shop:
        f["shopId"] = shop
    fs = getattr(args, "from_state", None)
    if fs:
        f["state"] = fs
    fd = getattr(args, "from_date", None)
    if fd:
        f["discoveredFrom"] = today_local() if fd == "today" else fd
    td = getattr(args, "to_date", None)
    if td:
        f["discoveredTo"] = today_local() if td == "today" else td
    run = getattr(args, "run", None)
    if run:
        f["scanRunId"] = run
    title = getattr(args, "title", None)
    if title:
        f["title"] = title
    return {k: v for k, v in f.items() if v not in (None, "", "all")} if f.get("state") != "all" else \
        {k: v for k, v in f.items() if v not in (None, "")}


def _qs(f: dict) -> str:
    from urllib.parse import urlencode
    return ("?" + urlencode(f)) if f else ""


def db_versions(ids):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        q = "select id, state, state_version from products where id in (%s)" % ",".join("?" * len(ids))
        rows = con.execute(q, list(ids)).fetchall()
    finally:
        con.close()
    return {r[0]: (r[1], r[2]) for r in rows}


# ----------------------------------------------------------------------------- commands
def cmd_health(a):
    code, p = api("GET", "/api/health")
    die_on(code, p, "health")
    print(json.dumps(p, ensure_ascii=False))


def cmd_overview(a):
    code, p = api("GET", "/api/overview")
    die_on(code, p, "overview")
    if a.json:
        print(json.dumps(p, ensure_ascii=False, indent=2)); return
    ls = p.get("lastScan") or {}
    print(f"启用店铺     : {p.get('enabledShopCount')}")
    print(f"今日新增     : {p.get('todayNewCount')}")
    print(f"最近扫描     : runId={ls.get('runId')} {ls.get('status')} new={ls.get('newCount')} {ls.get('finishedAt')}")
    print("趋势(近7)    :", ", ".join(f"{t['date']}={t['newCount']}" for t in (p.get("trend") or [])[-7:]))
    snc = p.get("shopNewCounts") or []
    top = sorted(snc, key=lambda x: x.get("newCount", 0), reverse=True)[:10]
    if top:
        print("今日新增Top  :", ", ".join(f"{s.get('shopName')}={s.get('newCount')}" for s in top))


def cmd_scan_start(a):
    shops = None
    if a.shops:
        shops = [int(x) for x in a.shops.split(",") if x.strip()]
    code, p = api("POST", "/api/scans", {"shopIds": shops})
    die_on(code, p, "scan-start")
    print(json.dumps(p, ensure_ascii=False))


def cmd_scan_status(a):
    code, p = api("GET", f"/api/scans/{a.run}")
    die_on(code, p, "scan-status")
    print(json.dumps(p, ensure_ascii=False, indent=2 if a.json else None))


def cmd_scan_watch(a):
    while True:
        code, p = api("GET", f"/api/scans/{a.run}")
        die_on(code, p, "scan-watch")
        print(f"{time.strftime('%H:%M:%S')} {p.get('status'):8s} phase={p.get('phase')} "
              f"{p.get('shopIndex')}/{p.get('shopTotal')} ok={p.get('succeeded')} fail={p.get('failed')} "
              f"new={p.get('newCount')} shop={p.get('currentShop')} err={p.get('errorCode')}")
        if p.get("status") not in ("running", "pending"):
            break
        time.sleep(a.interval)


def cmd_scan_retry(a):
    code, p = api("POST", f"/api/scans/{a.run}/retry", {})
    die_on(code, p, "scan-retry")
    print(json.dumps(p, ensure_ascii=False))


def cmd_scan_history(a):
    code, p = api("GET", f"/api/scans?page={a.page}&pageSize={a.page_size}")
    die_on(code, p, "scan-history")
    for it in p.get("items", []):
        print(f"run {it['id']:>3} {it['status']:9s} new={it['newCount']:>4} {it['startedAt']} -> {it['finishedAt']}")


def cmd_products(a):
    f = build_filter(a)
    rows = []
    page = a.page
    while True:
        q = dict(f); q["page"] = page; q["pageSize"] = a.page_size
        code, p = api("GET", "/api/products" + _qs(q))
        die_on(code, p, "products")
        rows.extend(p.get("items", []))
        if not a.all or not p.get("hasMore"):
            break
        page += 1
        if page > 500:
            break
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2)); return
    print(f"共 {len(rows)} 条（筛选 {f}）")
    for r in rows:
        print(f"{r['id']:>6} {STATES_CN.get(r['state'], r['state']):4s} shop{r['shopId']:<3} "
              f"{(r['title'] or '')[:60]:60s} {r['remoteProductId']}")


def _apply_state(scope_body, what):
    code, p = api("PATCH", "/api/products/state", scope_body)
    die_on(code, p, "set-state")
    print(f"{what}: updatedCount={p.get('updatedCount')}")
    return p


def cmd_set_state(a):
    to_state = a.to
    if to_state not in STATES_CN:
        raise SystemExit(f"--to 必须是 {list(STATES_CN)} 之一")
    if a.ids:
        ids = [int(x) for x in a.ids.split(",") if x.strip()]
        vers = db_versions(ids)
        missing = [i for i in ids if i not in vers]
        if missing:
            raise SystemExit(f"库里找不到这些 id: {missing}")
        body = {"scope": "page", "state": to_state, "productIds": ids,
                "expectedVersions": {str(i): vers[i][1] for i in ids}}
    else:
        # filter scope：先取一致性快照
        f = build_filter(a, default_state="pending_review")
        code, sel = api("GET", "/api/products/selection" + _qs(f))
        die_on(code, sel, "selection")
        items = sel.get("items", [])
        if not items:
            print("没有匹配的商品，未改动。"); return
        body = {"scope": "filter", "state": to_state, "productIds": [],
                "expectedVersions": {str(it["id"]): it["stateVersion"] for it in items},
                "filter": {**{k: v for k, v in f.items()}, "includeDisabledShops": True},
                "filterSignature": sel["filterSignature"]}
    if a.dry_run:
        print("[dry-run] 将提交:", json.dumps(body, ensure_ascii=False)[:400]); return
    _apply_state(body, f"改状态 -> {to_state}")


def cmd_picker_status(a):
    code, p = api("GET", "/api/picker/status")
    die_on(code, p, "picker-status")
    print(json.dumps(p, ensure_ascii=False))


def cmd_picker_queue(a):
    if a.ids:
        ids = [int(x) for x in a.ids.split(",") if x.strip()]
    elif a.all_to_process:
        code, p = api("GET", "/api/products" + _qs({"state": "to_process", "page": 1, "pageSize": 100}))
        die_on(code, p, "products")
        ids = [it["id"] for it in p.get("items", [])]
        page = 2
        while p.get("hasMore") and page <= 500:
            code, p = api("GET", "/api/products" + _qs({"state": "to_process", "page": page, "pageSize": 100}))
            ids += [it["id"] for it in p.get("items", [])]; page += 1
    else:
        f = build_filter(a)
        code, sel = api("GET", "/api/products/selection" + _qs(f))
        die_on(code, sel, "selection")
        ids = [it["id"] for it in sel.get("items", [])]
    if not ids:
        print("没有可入队的商品。"); return
    if len(ids) > 500:
        print(f"注意：{len(ids)} 件，单次接口上限 500，将分批提交。")
    total_queued = 0
    for i in range(0, len(ids), 500):
        batch = ids[i:i + 500]
        code, p = api("POST", "/api/picker/queue", {"productIds": batch})
        die_on(code, p, "picker-queue")
        total_queued += p.get("queued", 0)
        print(f"queued={p.get('queued')} skipped={p.get('skipped')} queueLength={p.get('queueLength')}")
    print(f"合计入队 {total_queued} / 目标 {len(ids)}")


def cmd_picker_clear(a):
    code, p = api("POST", "/api/picker/clear", {})
    die_on(code, p, "picker-clear")
    print(json.dumps(p, ensure_ascii=False))


def cmd_picker_watch(a):
    last = None
    while True:
        code, p = api("GET", "/api/picker/status")
        die_on(code, p, "picker-watch")
        key = (p.get("phase"), p.get("inFlight"), p.get("queued"), p.get("online"))
        if key != last:
            print(f"{time.strftime('%H:%M:%S')} online={p.get('online')} q={p.get('queued')} "
                  f"inflight={p.get('inFlight')} phase={p.get('phase')} ver={p.get('version')}")
            last = key
        if p.get("queued") == 0 and p.get("inFlight") == 0:
            print("队列已清空 / 全部处理完毕。")
            break
        time.sleep(a.interval)


def cmd_db_stats(a):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        total = con.execute("select count(*) from products").fetchone()[0]
        by = con.execute("select state,count(*) from products group by state").fetchall()
        today_total = con.execute(
            "select count(*) from products where date(first_seen_at,'localtime')=date('now','localtime')").fetchone()[0]
        today_by = con.execute(
            "select state,count(*) from products where date(first_seen_at,'localtime')=date('now','localtime') group by state").fetchall()
    finally:
        con.close()
    print(f"库内总数 : {total}")
    for s, c in sorted(by, key=lambda x: -x[1]):
        print(f"  {s:14s}({STATES_CN.get(s,'?')}) {c}")
    print(f"今日入库 : {today_total}")
    for s, c in sorted(today_by, key=lambda x: -x[1]):
        print(f"  {s:14s}({STATES_CN.get(s,'?')}) {c}")


def cmd_db_dups(a):
    """按 (shop_id, /kf/<hash>) 找重复组；同图再分标题是否相同。"""
    def img_key(u):
        if not u:
            return ""
        m = re.search(r"/kf/([^./?#]+)", u)
        return m.group(1) if m else u
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "select id,shop_id,title,image_url,first_seen_at,state from products").fetchall()
    finally:
        con.close()
    groups = {}
    for rid, sid, title, img, first, state in rows:
        groups.setdefault((sid, img_key(img)), []).append((rid, title, first, state))
    dup_groups = {k: v for k, v in groups.items() if len(v) > 1 and k[1]}
    redundant = sum(len(v) - 1 for v in dup_groups.values())
    same_title = sum(1 for v in dup_groups.values()
                     if len({(t or "").strip().lower() for _, t, _, _ in v}) == 1)
    print(f"总行数          : {len(rows)}")
    print(f"唯一(店铺+图)组 : {len(groups)}")
    print(f"重复组          : {len(dup_groups)}  (其中整组标题一致 {same_title} 组)")
    print(f"冗余行(可去重)  : {redundant}")
    print(f"估算唯一商品数  : {len(groups)}")
    if a.show:
        for (sid, key), v in list(dup_groups.items())[: a.show]:
            print(f"  shop{sid} img={key[:16]}… 行数={len(v)}: " +
                  "; ".join(f"id{rid}[{st}]({t[:24]})" for rid, t, f, st in v[:4]))


# ----------------------------------------------------------------------------- parser
def main(argv=None):
    p = argparse.ArgumentParser(description="AliExpressMonitor 控制台操作 CLI")
    p.add_argument("--json", action="store_true", help="尽量输出原始 JSON")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health")
    sp = sub.add_parser("overview")
    sp.set_defaults(func=cmd_overview)

    sp = sub.add_parser("scan-start"); sp.add_argument("--shops"); sp.set_defaults(func=cmd_scan_start)
    sp = sub.add_parser("scan-status"); sp.add_argument("run", type=int); sp.set_defaults(func=cmd_scan_status)
    sp = sub.add_parser("scan-watch"); sp.add_argument("run", type=int)
    sp.add_argument("--interval", type=float, default=5.0); sp.set_defaults(func=cmd_scan_watch)
    sp = sub.add_parser("scan-retry"); sp.add_argument("run", type=int); sp.set_defaults(func=cmd_scan_retry)
    sp = sub.add_parser("scan-history"); sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--page-size", dest="page_size", type=int, default=20); sp.set_defaults(func=cmd_scan_history)

    sp = sub.add_parser("products")
    sp.add_argument("--state", default="pending_review")
    sp.add_argument("--shop", type=int)
    sp.add_argument("--from-date", dest="from_date")
    sp.add_argument("--to-date", dest="to_date")
    sp.add_argument("--run", type=int)
    sp.add_argument("--title")
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--page-size", dest="page_size", type=int, default=100)
    sp.add_argument("--all", action="store_true", help="翻页取全部")
    sp.set_defaults(func=cmd_products)

    sp = sub.add_parser("set-state")
    sp.add_argument("--to", required=True)
    sp.add_argument("--ids")
    sp.add_argument("--from-state", dest="from_state")
    sp.add_argument("--shop", type=int)
    sp.add_argument("--from-date", dest="from_date")
    sp.add_argument("--to-date", dest="to_date")
    sp.add_argument("--run", type=int)
    sp.add_argument("--title")
    sp.add_argument("--dry-run", dest="dry_run", action="store_true")
    sp.set_defaults(func=cmd_set_state)

    sub.add_parser("picker-status").set_defaults(func=cmd_picker_status)
    sp = sub.add_parser("picker-queue")
    sp.add_argument("--ids")
    sp.add_argument("--all-to-process", dest="all_to_process", action="store_true")
    sp.add_argument("--state", default="to_process")
    sp.add_argument("--shop", type=int)
    sp.add_argument("--from-date", dest="from_date")
    sp.add_argument("--to-date", dest="to_date")
    sp.add_argument("--run", type=int)
    sp.add_argument("--title")
    sp.set_defaults(func=cmd_picker_queue)
    sub.add_parser("picker-clear").set_defaults(func=cmd_picker_clear)
    sp = sub.add_parser("picker-watch"); sp.add_argument("--interval", type=float, default=5.0)
    sp.set_defaults(func=cmd_picker_watch)

    sub.add_parser("db-stats").set_defaults(func=cmd_db_stats)
    sp = sub.add_parser("db-dups"); sp.add_argument("--show", type=int, default=0)
    sp.set_defaults(func=cmd_db_dups)

    # health needs func too
    for name in ("health",):
        pass
    a = p.parse_args(argv)
    if a.cmd == "health":
        return cmd_health(a)
    return a.func(a)


if __name__ == "__main__":
    main()
