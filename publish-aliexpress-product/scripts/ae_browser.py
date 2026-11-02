#!/usr/bin/env python3
"""Persistent-Edge browser hands for agent use (CDP over a dedicated profile).

Why a persistent browser instead of one-shot Playwright: seller flows take many
short commands (open -> read -> screenshot -> edit -> submit) and the login
session must survive between them. We launch Microsoft Edge once with a
dedicated --user-data-dir and --remote-debugging-port, then every later command
reconnects to the same running browser.

Commands
  launch                 start Edge (dedicated profile) with CDP on 9222
  state                  print open pages: index, url, title
  go <url> [--new]       navigate the first page (or open a new tab)
  eval "<js>"            run JS in the page and print the JSON result
  shot [name]            screenshot the first page to shots/<name>.png
  click "<selector>"     click an element (requires --yes, refuses by default)
  mouse <x> <y>          coordinate click inside the page (canvas / no selector)
  osclick <x> <y>        real Win32 mouse click at screen coords (native dialogs)
  type "<selector>" "<text>"
  close                  close the browser

Notes
  - Never pass secrets on the command line; log into the seller site by hand in
    the visible Edge window on first run.
  - `click`/`type` are gated: they do nothing without --yes, so a read-only
    exploration can never change the account state by accident.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

CDP_PORT = int(os.environ.get("AE_CDP_PORT", "9222"))
CDP = f"http://127.0.0.1:{CDP_PORT}"
PROFILE = Path(os.environ.get("AE_PROFILE", str(Path(os.environ["LOCALAPPDATA"]) / "ae-seller-browser-profile")))
SHOTS = Path(os.environ.get("AE_SHOTS", str(Path(__file__).resolve().parent.parent / "shots")))
EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def cdp_alive(timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"{CDP}/json/version", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def edge_exe() -> str:
    for c in EDGE_CANDIDATES:
        if Path(c).exists():
            return c
    raise SystemExit("找不到 msedge.exe")


def connect():
    from playwright.sync_api import sync_playwright

    if not cdp_alive():
        raise SystemExit("浏览器没在跑：先执行 ae_browser.py launch")
    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp(CDP)
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return p, browser, ctx, page


def cmd_launch(args) -> int:
    if cdp_alive():
        print("已在运行，复用现有浏览器")
        return 0
    data_dir = Path(getattr(args, "data_dir", None) or PROFILE)
    prof_dir = getattr(args, "profile_directory", None)
    data_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        edge_exe(),
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=msEdgeSidebarV2",
    ]
    if prof_dir:
        cmd.append(f"--profile-directory={prof_dir}")
    cmd.append("about:blank")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        if cdp_alive():
            print(f"已启动 Edge (pid {proc.pid}) user-data-dir={data_dir} profile={prof_dir or '默认'}")
            return 0
        time.sleep(0.5)
    raise SystemExit(
        "Edge 启动后 CDP 没起来：可能是该 user-data-dir 已被另一个 Edge 占用，"
        "或 Edge 拒绝在默认配置目录上开调试端口（那就用 clone-profile 复制一份）"
    )


EDGE_UD_DEFAULT = Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "Edge" / "User Data"
SKIP_DIRS = {
    "Cache", "Code Cache", "GPUCache", "DawnCache", "DawnGraphiteCache", "DawnWebGPUCache",
    "GraphiteDawnCache", "ShaderCache", "GrShaderCache", "Media Cache", "optimization_guide_hint_cache",
    "Edge Sidebar", "EdgeScreenshot", "Thumbnails",
}


def cmd_clone_profile(args) -> int:
    """把真实 Edge 配置里的登录态搬进一个可开调试端口的副本目录。"""
    src_ud = Path(args.src or EDGE_UD_DEFAULT)
    prof = args.profile or "Profile 1"
    dst = Path(args.dst or (Path(os.environ["LOCALAPPDATA"]) / "edge-dsh-profile"))
    src = src_ud / prof
    cookies = src / "Network" / "Cookies"
    if not src.exists():
        raise SystemExit(f"找不到配置目录：{src}")
    try:
        with open(cookies, "rb") as fh:
            fh.read(1)
    except Exception as e:
        raise SystemExit(
            f"Cookie 数据库被占用（{type(e).__name__}）：请先完全退出 Edge"
            "（含托盘/后台进程）再执行 clone-profile"
        )
    if dst.exists():
        if not args.force:
            raise SystemExit(f"目标已存在：{dst}（加 --force 覆盖）")
        shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_ud / "Local State", dst / "Local State")
    copied = 0
    total = 0
    for root, dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        dirs[:] = [d for d in dirs if not (f"{rel}\\{d}" in SKIP_DIRS or str((rel / d)) in SKIP_DIRS)]
        out_root = dst / prof / rel
        out_root.mkdir(parents=True, exist_ok=True)
        for name in files:
            s = Path(root) / name
            try:
                shutil.copy2(s, out_root / name)
                copied += 1
                total += s.stat().st_size
            except Exception:
                pass
    print(json.dumps({"cloned_from": str(src), "to": str(dst), "files": copied,
                      "MB": round(total / 1048576, 1)}, ensure_ascii=False, indent=2))
    return 0


def cmd_state(args) -> int:
    p, browser, ctx, page = connect()
    try:
        rows = []
        for i, pg in enumerate(ctx.pages):
            try:
                rows.append({"index": i, "url": pg.url, "title": pg.title()})
            except Exception as e:  # page may be closing
                rows.append({"index": i, "url": "?", "title": f"<{type(e).__name__}>"})
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    finally:
        browser.close()
        p.stop()


def cmd_go(args) -> int:
    p, browser, ctx, page = connect()
    try:
        target = ctx.new_page() if args.new else ctx.pages[0]
        target.goto(args.url, wait_until="domcontentloaded", timeout=60000)
        target.wait_for_timeout(1500)
        print(json.dumps({"url": target.url, "title": target.title()}, ensure_ascii=False, indent=2))
        return 0
    finally:
        browser.close()
        p.stop()


def cmd_eval(args) -> int:
    p, browser, ctx, page = connect()
    try:
        result = page.evaluate(args.js)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        browser.close()
        p.stop()


def cmd_shot(args) -> int:
    p, browser, ctx, page = connect()
    try:
        SHOTS.mkdir(parents=True, exist_ok=True)
        name = args.name or time.strftime("%Y%m%d-%H%M%S")
        out = SHOTS / f"{name}.png"
        page.screenshot(path=str(out), full_page=args.full_page)
        print(json.dumps({"path": str(out), "url": page.url, "title": page.title()}, ensure_ascii=False))
        return 0
    finally:
        browser.close()
        p.stop()


def cmd_click(args) -> int:
    if not args.yes:
        print("dry-run：读取页面上匹配到的元素，不点击。确认无误后加 --yes。")
        p, browser, ctx, page = connect()
        try:
            info = page.evaluate(
                "(sel) => [...document.querySelectorAll(sel)].slice(0, 5).map(e => ({tag: e.tagName, text: (e.innerText||e.value||'').trim().slice(0,80), visible: !!(e.offsetWidth||e.offsetHeight)}))",
                args.selector,
            )
            print(json.dumps(info, ensure_ascii=False, indent=2))
            return 0
        finally:
            browser.close()
            p.stop()
    p, browser, ctx, page = connect()
    try:
        page.click(args.selector, timeout=15000)
        page.wait_for_timeout(1200)
        print(json.dumps({"clicked": args.selector, "url": page.url, "title": page.title()}, ensure_ascii=False))
        return 0
    finally:
        browser.close()
        p.stop()


def cmd_type(args) -> int:
    if not args.yes:
        print("dry-run：未输入。确认目标输入框后加 --yes。")
        return 0
    p, browser, ctx, page = connect()
    try:
        page.fill(args.selector, args.text, timeout=15000)
        print(json.dumps({"filled": args.selector, "url": page.url}, ensure_ascii=False))
        return 0
    finally:
        browser.close()
        p.stop()


def cmd_mouse(args) -> int:
    """Coordinate click inside the page (CDP input) - works on canvas / no-selector UI."""
    p, browser, ctx, page = connect()
    try:
        vp = page.evaluate(
            "() => ({w: innerWidth, h: innerHeight, dpr: devicePixelRatio,"
            " sx: scrollX, sy: scrollY})"
        )
        if not args.yes:
            print(json.dumps({"dry-run": "坐标已换算，未点击。加 --yes 执行。",
                              "click_point_css": [args.x, args.y], "viewport": vp},
                             ensure_ascii=False, indent=2))
            print(json.dumps({"element_at_point": page.evaluate(
                "([x,y]) => { const e = document.elementFromPoint(x,y);"
                " return e ? {tag:e.tagName, text:(e.innerText||'').trim().slice(0,80)} : null }",
                [args.x, args.y])}, ensure_ascii=False))
            return 0
        import random
        page.mouse.move(args.x + random.uniform(-6, 6), args.y + random.uniform(-6, 6), steps=12)
        page.mouse.click(args.x, args.y, click_count=2 if args.double else 1)
        page.wait_for_timeout(800)
        print(json.dumps({"clicked_at": [args.x, args.y], "url": page.url, "title": page.title()},
                         ensure_ascii=False))
        return 0
    finally:
        browser.close()
        p.stop()


def cmd_osclick(args) -> int:
    """Real Win32 mouse click at screen coordinates (for native dialogs / extension popups)."""
    import ctypes
    import ctypes.wintypes  # noqa: F401  (defines POINT)
    import random
    import time as _t

    u = ctypes.windll.user32
    try:  # make this process DPI aware so coordinates match physical pixels
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

    gx, gy = args.x, args.y
    if not args.yes:
        print(f"dry-run：将把鼠标移到屏幕 ({gx}, {gy}) 并单击。确认窗口位置后加 --yes。")
        return 0
    _t.sleep(0.2)
    pt = ctypes.wintypes.POINT()
    u.GetCursorPos(ctypes.byref(pt))
    sx, sy = pt.x, pt.y
    steps = max(6, args.steps)
    for i in range(1, steps + 1):
        cx = int(sx + (gx - sx) * i / steps + random.uniform(-2, 2))
        cy = int(sy + (gy - sy) * i / steps + random.uniform(-2, 2))
        u.SetCursorPos(cx, cy)
        _t.sleep(args.delay_ms / 1000.0)
    u.SetCursorPos(gx, gy)
    _t.sleep(0.05)
    u.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
    _t.sleep(random.uniform(0.04, 0.09))
    u.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP
    print(json.dumps({"osclicked_at": [gx, gy]}, ensure_ascii=False))
    return 0


def cmd_probe(args) -> int:
    """One-shot: (launch if needed) -> open url -> screenshot -> report. Low process churn."""
    launched = False
    if not cdp_alive():
        cmd_launch(args)
        launched = True
    p, browser, ctx, page = connect()
    try:
        page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1800)
        SHOTS.mkdir(parents=True, exist_ok=True)
        name = args.name or time.strftime("%Y%m%d-%H%M%S")
        out = SHOTS / f"{name}.png"
        page.screenshot(path=str(out))
        info = page.evaluate(
            "() => ({w: innerWidth, h: innerHeight, dpr: devicePixelRatio,"
            " title: document.title, h1: document.querySelector('h1')?.innerText || ''})"
        )
        info.update({"url": page.url, "shot": str(out), "launched_now": launched})
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0
    finally:
        # 只断开 CDP 连接，不关掉浏览器：登录/后续交互还要用同一个窗口
        p.stop()


def cmd_close(args) -> int:
    if not cdp_alive():
        print("浏览器本来就没在跑")
        return 0
    os.system(f'powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \\"Name=\'msedge.exe\'\\" | Where-Object {{ $_.CommandLine -like \'*{PROFILE}*\' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}" 2>NUL')
    time.sleep(1.0)
    print("已关闭自动化浏览器" if not cdp_alive() else "还有残留进程，稍等再 close 一次")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Persistent Edge hands for seller flows")
    sub = ap.add_subparsers(dest="cmd", required=True)

    l = sub.add_parser("launch")
    l.add_argument("--data-dir", default=None, help="User Data 目录（默认独立 profile）")
    l.add_argument("--profile-directory", default=None, help="如 'Profile 1'")
    l.set_defaults(fn=cmd_launch)
    cp = sub.add_parser("clone-profile", help="把真实 Edge 配置（含登录态）复制成可调试的副本")
    cp.add_argument("--src", default=None); cp.add_argument("--profile", default=None)
    cp.add_argument("--dst", default=None); cp.add_argument("--force", action="store_true")
    cp.set_defaults(fn=cmd_clone_profile)
    sub.add_parser("state").set_defaults(fn=cmd_state)

    g = sub.add_parser("go"); g.add_argument("url"); g.add_argument("--new", action="store_true"); g.set_defaults(fn=cmd_go)
    e = sub.add_parser("eval"); e.add_argument("js"); e.set_defaults(fn=cmd_eval)
    s = sub.add_parser("shot"); s.add_argument("name", nargs="?", default=None); s.add_argument("--full-page", action="store_true"); s.set_defaults(fn=cmd_shot)
    c = sub.add_parser("click"); c.add_argument("selector"); c.add_argument("--yes", action="store_true"); c.set_defaults(fn=cmd_click)
    m = sub.add_parser("mouse", help="页面内坐标点击（canvas/无选择器时用）")
    m.add_argument("x", type=float); m.add_argument("y", type=float)
    m.add_argument("--double", action="store_true"); m.add_argument("--yes", action="store_true")
    m.set_defaults(fn=cmd_mouse)
    pr = sub.add_parser("probe", help="一条命令：启动→开页→截图→报告")
    pr.add_argument("url"); pr.add_argument("name", nargs="?", default=None)
    pr.set_defaults(fn=cmd_probe)
    o = sub.add_parser("osclick", help="系统级真实鼠标点击（原生弹窗/扩展弹层用）")
    o.add_argument("x", type=int); o.add_argument("y", type=int)
    o.add_argument("--steps", type=int, default=18); o.add_argument("--delay-ms", type=int, default=12)
    o.add_argument("--yes", action="store_true")
    o.set_defaults(fn=cmd_osclick)
    t = sub.add_parser("type"); t.add_argument("selector"); t.add_argument("text"); t.add_argument("--yes", action="store_true"); t.set_defaults(fn=cmd_type)
    sub.add_parser("close").set_defaults(fn=cmd_close)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
