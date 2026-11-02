#!/usr/bin/env python3
"""Screen-level eyes and hands: capture the real screen, click real pixels.

Design goal: work on ANY already-open browser window (the user's own Edge, a
cloned profile, an Electron app) without a debug port, without DOM selectors and
without launching a new browser.

  info                 screen size / DPI / scaling
  windows              list visible top-level windows with rects
  focus <title-substr> bring a window to the front, print its rect
  shot [name]          capture the whole screen -> shots/<name>.png
  wshot <substr> [name] focus + capture just that window
  click <x> <y>        real mouse click at screen pixels (needs --yes)
  dclick <x> <y>       double click (needs --yes)
  type <text>          type text into the focused window (needs --yes)

Coordinates are physical screen pixels of a 1920x1080 desktop; the script sets
per-monitor DPI awareness so screenshot pixels == click pixels.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import random
import sys
import time
from pathlib import Path

SHOTS = Path(__file__).resolve().parent.parent / "shots"

user32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor v2
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def _rect(hwnd):
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return {"x": r.left, "y": r.top, "w": r.right - r.left, "h": r.bottom - r.top}


def _title(hwnd) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def list_windows():
    out = []

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        t = _title(hwnd)
        if not t:
            return True
        r = _rect(hwnd)
        if r["w"] < 120 or r["h"] < 80:
            return True
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        out.append({"hwnd": hwnd, "title": t, "cls": cls.value, **r})
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return out


def _norm(s: str) -> str:
    for ch in ("\u200b", "\u200e", "\u200f", "\u00a0"):
        s = s.replace(ch, "")
    return " ".join(s.split())


def find_window(substr: str):
    needle = _norm(substr).lower()
    cands = [w for w in list_windows() if needle in _norm(w["title"]).lower()]
    # 兜底：按类名找浏览器主窗口（Edge 标题里有零宽字符，容易匹配不上）
    if not cands and needle in ("edge", "浏览器", "browser"):
        cands = [w for w in list_windows() if w["cls"] == "Chrome_WidgetWin_1" and w["w"] > 1200]
    return cands[0] if cands else None


def _raise(hwnd):
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    # 前台锁的常规绕法：AttachThreadInput 到前台线程再 SetForegroundWindow
    fg = user32.GetForegroundWindow()
    tid_fg = user32.GetWindowThreadProcessId(fg, None)
    tid_me = ctypes.windll.kernel32.GetCurrentThreadId()
    attached = False
    if tid_fg and tid_fg != tid_me:
        attached = bool(user32.AttachThreadInput(tid_fg, tid_me, True))
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    if attached:
        user32.AttachThreadInput(tid_fg, tid_me, False)


def focus(substr: str, tries: int = 4):
    """把窗口抢到前台并【验证】真的抢到了，抢不到就退回 ALT 解锁再抢一次。"""
    w = find_window(substr)
    if not w:
        raise SystemExit(f"没找到标题含 {substr!r} 的窗口")
    hwnd = w["hwnd"]
    for _ in range(tries):
        _raise(hwnd)
        time.sleep(0.25)
        if user32.GetForegroundWindow() == hwnd:
            break
        user32.keybd_event(0x12, 0, 0, 0)  # ALT down：解除前台锁
        user32.keybd_event(0x12, 0, 2, 0)  # ALT up
        time.sleep(0.12)
    ok = user32.GetForegroundWindow() == hwnd
    return {"hwnd": hwnd, "title": w["title"], "foreground": ok, **_rect(hwnd)}


def grab(name: str, box=None):
    from PIL import ImageGrab

    SHOTS.mkdir(parents=True, exist_ok=True)
    img = ImageGrab.grab(bbox=box, all_screens=True) if box else ImageGrab.grab(all_screens=True)
    out = SHOTS / f"{name}.png"
    img.save(out)
    return {"shot": str(out), "size": img.size}


def screen_metrics():
    w = user32.GetSystemMetrics(0)
    h = user32.GetSystemMetrics(1)
    dpi = user32.GetDpiForSystem() if hasattr(user32, "GetDpiForSystem") else 96
    return {"screen": [w, h], "dpi": dpi, "scale": round(dpi / 96, 3)}


def preguard(target: str):
    """动作前先把目标窗口抢到前台并验证。抢不到就中止，宁可不做也别打到别的窗口。"""
    w = focus(target)
    print(json.dumps({"focused": w["title"][:60], "foreground": w["foreground"]}, ensure_ascii=False))
    if not w["foreground"]:
        raise SystemExit("抢不到前台，已放弃操作（避免打到别的窗口）")
    return w


def click(x: int, y: int, double: bool = False, yes: bool = False, target: str | None = None):
    if not yes:
        print(json.dumps({"dry_run": True, "would_click": [x, y], "double": double,
                          "would_focus": target, **screen_metrics()}, ensure_ascii=False))
        return 0
    if target:
        preguard(target)
    sx, sy = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    if not (0 <= x < sx and 0 <= y < sy):
        raise SystemExit(f"坐标越界: ({x},{y}) 不在 {sx}x{sy} 内")
    start = user32.GetCursorPos
    pt = wt.POINT()
    start(ctypes.byref(pt))
    steps = 14
    for i in range(1, steps + 1):
        nx = int(pt.x + (x - pt.x) * i / steps + random.uniform(-1.5, 1.5))
        ny = int(pt.y + (y - pt.y) * i / steps + random.uniform(-1.5, 1.5))
        user32.SetCursorPos(nx, ny)
        time.sleep(0.012)
    user32.SetCursorPos(x, y)
    time.sleep(0.05)
    if double:
        for _ in range(2):
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
            time.sleep(0.04)
    else:
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.03)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
    print(json.dumps({"clicked": [x, y], "double": double}, ensure_ascii=False))
    return 0


def drag(x1: int, y1: int, x2: int, y2: int, yes: bool = False, steps: int = 30,
         target: str | None = None):
    """按住左键从 (x1,y1) 拖到 (x2,y2)。用于拖拽排序（例如把图拖成主图）。"""
    if not yes:
        print(json.dumps({"dry_run": True, "would_drag": [[x1, y1], [x2, y2]],
                          "would_focus": target}, ensure_ascii=False))
        return 0
    if target:
        preguard(target)
    user32.SetCursorPos(x1, y1)
    time.sleep(0.25)
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # left down
    time.sleep(0.2)
    for i in range(1, steps + 1):
        nx = int(x1 + (x2 - x1) * i / steps + random.uniform(-1, 1))
        ny = int(y1 + (y2 - y1) * i / steps + random.uniform(-1, 1))
        user32.SetCursorPos(nx, ny)
        time.sleep(0.02)
    time.sleep(0.3)
    user32.SetCursorPos(x2, y2)
    time.sleep(0.2)
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # left up
    print(json.dumps({"dragged": [[x1, y1], [x2, y2]]}, ensure_ascii=False))
    return 0


def wheel(x: int, y: int, notches: int, yes: bool = False, target: str | None = None):
    """把光标移到 (x,y) 后滚动鼠标滚轮。notches>0 向下，<0 向上。"""
    if not yes:
        print(json.dumps({"dry_run": True, "would_scroll": [x, y, notches],
                          "would_focus": target}, ensure_ascii=False))
        return 0
    if target:
        preguard(target)
    user32.SetCursorPos(x, y)
    time.sleep(0.15)
    delta = -120 if notches > 0 else 120
    for _ in range(abs(notches)):
        user32.mouse_event(0x0800, 0, 0, delta, 0)  # MOUSEEVENTF_WHEEL
        time.sleep(0.06)
    print(json.dumps({"scrolled": [x, y, notches]}, ensure_ascii=False))
    return 0


def type_text(text: str, yes: bool = False, target: str | None = None):
    if not yes:
        print(json.dumps({"dry_run": True, "would_type": text[:60],
                          "would_focus": target}, ensure_ascii=False))
        return 0
    if target:
        preguard(target)
    import subprocess

    ps = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "[System.Windows.Forms.SendKeys]::SendWait(" + json.dumps(text) + ")"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)
    print(json.dumps({"typed": text[:60]}, ensure_ascii=False))
    return 0


VK = {
    "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
    "enter": 0x0D, "esc": 0x1B, "tab": 0x09, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "pgup": 0x21, "pgdn": 0x22, "f5": 0x74,
}
for _ch in "abcdefghijklmnopqrstuvwxyz":
    VK[_ch] = ord(_ch.upper())
for _d in "0123456789":
    VK[_d] = ord(_d)


def hotkey(combo: str):
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    codes = []
    for p in parts:
        if p not in VK:
            raise SystemExit(f"不认识的键: {p}（可用: {', '.join(sorted(VK))}）")
        codes.append(VK[p])
    for c in codes:
        user32.keybd_event(c, 0, 0, 0)
        time.sleep(0.03)
    for c in reversed(codes):
        user32.keybd_event(c, 0, 2, 0)
        time.sleep(0.03)
    return {"hotkey": combo}


def set_clipboard(text: str):
    """写入剪贴板。必须走 base64 + UTF8 解码，否则中文经 stdin 会被按 GBK 解码成乱码。"""
    import subprocess, base64

    b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    cmd = (
        "[Console]::InputEncoding=[Text.Encoding]::UTF8;"
        "$s=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('%s'));"
        "Set-Clipboard -Value $s" % b64
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", cmd], check=False, capture_output=True)


def find_leave_dialog():
    """找 Chromium 的「是否离开网站?」beforeunload 模态窗。"""
    for w in list_windows():
        t = _norm(w["title"])
        if "离开" in t and w["w"] < 2200 and w["h"] < 900:
            return w
    return None


def dismiss_leave_dialog(yes: bool = True, shot: bool = True):
    """点掉 beforeunload 对话框里的「离开」。

    ★ 有副作用：离开 = 放弃当前页未保存的改动，调用前必须有用户同意。
    按钮位置按对话框自身矩形比例算（实测 0.79 / 0.81），点完验证窗口是否消失。
    """
    w = find_leave_dialog()
    if not w:
        return {"dialog": None, "note": "没有待处理的离开对话框"}
    x = int(w["x"] + w["w"] * 0.794)
    y = int(w["y"] + w["h"] * 0.806)
    info = {"dialog": {"title": _norm(w["title"]),
                       "rect": [w["x"], w["y"], w["w"], w["h"]],
                       "leave_button": [x, y]}}
    if shot:
        info["evidence"] = grab("leave-dialog")["shot"]
    if not yes:
        info["dry_run"] = True
        return info
    click(x, y, yes=True)
    time.sleep(1.2)
    info["dismissed"] = find_leave_dialog() is None
    return info


def navurl(url: str, yes: bool = False, target: str | None = None, auto_leave: bool = True):
    if not yes:
        print(json.dumps({"dry_run": True, "would_navigate": url}, ensure_ascii=False))
        return 0
    if target:
        w = focus(target)
        print(json.dumps({"focused": w["title"][:60]}, ensure_ascii=False))
    set_clipboard(url)
    time.sleep(0.15)
    hotkey("ctrl+l")
    time.sleep(0.25)
    hotkey("ctrl+v")
    time.sleep(0.25)
    hotkey("enter")
    time.sleep(1.5)
    if auto_leave:
        d = dismiss_leave_dialog(yes=True)
        if d.get("dialog"):
            print(json.dumps({"leave_dialog": d}, ensure_ascii=False))
    time.sleep(2.0)
    print(json.dumps({"navigated": url}, ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="screen capture + real mouse clicks")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info").set_defaults(fn=lambda a: print(json.dumps(screen_metrics(), ensure_ascii=False)))
    sub.add_parser("windows").set_defaults(
        fn=lambda a: print(json.dumps(list_windows(), ensure_ascii=False, indent=2)))

    f = sub.add_parser("focus"); f.add_argument("substr")
    f.set_defaults(fn=lambda a: print(json.dumps(focus(a.substr), ensure_ascii=False, indent=2)))

    s = sub.add_parser("shot"); s.add_argument("name", nargs="?", default=None)
    s.add_argument("--target", default=None, help="先聚焦这个标题片段的窗口再截图")
    def _shot(a):
        if a.target:
            preguard(a.target)
        print(json.dumps(grab(a.name or time.strftime("%H%M%S")), ensure_ascii=False, indent=2))
    s.set_defaults(fn=_shot)

    ws = sub.add_parser("wshot"); ws.add_argument("substr"); ws.add_argument("name", nargs="?", default=None)
    def _wshot(a):
        w = focus(a.substr)
        pad = 0
        box = (max(0, w["x"] - pad), max(0, w["y"] - pad), w["x"] + w["w"] + pad, w["y"] + w["h"] + pad)
        info = grab(a.name or time.strftime("%H%M%S"), box=box)
        info.update({"window": w, "box": box})
        print(json.dumps(info, ensure_ascii=False, indent=2))
    ws.set_defaults(fn=_wshot)

    for name, dbl in (("click", False), ("dclick", True)):
        c = sub.add_parser(name); c.add_argument("x", type=int); c.add_argument("y", type=int)
        c.add_argument("--yes", action="store_true")
        c.add_argument("--focus", dest="target", default=None, help="先聚焦这个标题片段的窗口再点")
        c.set_defaults(fn=lambda a, dbl=dbl: click(a.x, a.y, double=dbl, yes=a.yes, target=a.target))

    dg = sub.add_parser("drag")
    dg.add_argument("x1", type=int); dg.add_argument("y1", type=int)
    dg.add_argument("x2", type=int); dg.add_argument("y2", type=int)
    dg.add_argument("--yes", action="store_true")
    dg.add_argument("--focus", dest="target", default=None)
    dg.set_defaults(fn=lambda a: drag(a.x1, a.y1, a.x2, a.y2, yes=a.yes, target=a.target))

    wh = sub.add_parser("wheel")
    wh.add_argument("x", type=int); wh.add_argument("y", type=int); wh.add_argument("notches", type=int)
    wh.add_argument("--yes", action="store_true")
    wh.add_argument("--focus", dest="target", default=None)
    wh.set_defaults(fn=lambda a: wheel(a.x, a.y, a.notches, yes=a.yes, target=a.target))

    t = sub.add_parser("type"); t.add_argument("text"); t.add_argument("--yes", action="store_true")
    t.add_argument("--focus", dest="target", default=None)
    t.set_defaults(fn=lambda a: type_text(a.text, a.yes, a.target))

    hk = sub.add_parser("hotkey"); hk.add_argument("combo")
    hk.set_defaults(fn=lambda a: print(json.dumps(hotkey(a.combo), ensure_ascii=False)))

    nv = sub.add_parser("navurl"); nv.add_argument("url"); nv.add_argument("--yes", action="store_true")
    nv.add_argument("--target", default=None, help="先聚焦这个标题片段的窗口再导航")
    nv.add_argument("--no-auto-leave", dest="auto_leave", action="store_false",
                    help="不自动处理「是否离开网站」对话框")
    nv.set_defaults(fn=lambda a: navurl(a.url, a.yes, a.target, a.auto_leave))

    lv = sub.add_parser("leave", help="查看/点掉 Chromium「是否离开网站」对话框")
    lv.add_argument("--yes", action="store_true", help="真正点「离开」（会丢弃当前页未保存改动）")
    lv.set_defaults(fn=lambda a: print(json.dumps(dismiss_leave_dialog(yes=a.yes),
                                                  ensure_ascii=False, indent=2)))

    args = ap.parse_args()
    return args.fn(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
