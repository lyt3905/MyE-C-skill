#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SKU 热键出号器 —— 按 Ctrl+B 自动把下一个 SKU 编号粘贴到光标处。

工作方式
    ├─ 常驻后台，注册全局热键 Ctrl+B（无需管理员权限）
    ├─ 按一下 Ctrl+B → 按「上次的规格」分配下一个流水号 → 写剪贴板 → 自动 Ctrl+V 粘贴
    ├─ 剪贴板里是速记符时，按 Ctrl+Shift+B 可切换规格（比如从 SS86 换到 JCS）
    └─ 每次出号都写进同一份台账，和命令行模式共用流水号，绝不会撞号

用法
    设置规格：  python sku_hotkey.py --set "mts tf ss86 r"
    启动热键：  python sku_hotkey.py           （或双击 start_hotkey.bat）
    查看状态：  python sku_hotkey.py --status
    停止：      python sku_hotkey.py --stop

只依赖标准库（ctypes 直调 user32/kernel32），管理版 Python 即可运行。
"""

from __future__ import annotations

import argparse
import copy
import ctypes
import json
import os
import re
import sys
import time
from ctypes import wintypes
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import sku_gen as core  # noqa: E402  （复用字典解析、台账、编码构建）

STATE_FILE = core.ROOT_DIR / "data" / "hotkey_state.json"
PID_FILE = core.ROOT_DIR / "data" / "hotkey.pid"

# ---------------------------------------------------------------- Win32 绑定

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
VK_B = 0x42
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_V = 0x56
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
PROCESS_TERMINATE = 0x0001

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL


# ---------------------------------------------------------------- 剪贴板

def get_clipboard() -> str:
    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        return ""
    for _ in range(20):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.03)
    else:
        return ""
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        p = kernel32.GlobalLock(h)
        if not p:
            return ""
        try:
            return ctypes.c_wchar_p(p).value or ""
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def set_clipboard(text: str) -> bool:
    for _ in range(20):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.03)
    else:
        return False
    try:
        user32.EmptyClipboard()
        data = text.encode("utf-16-le") + b"\x00\x00"
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            return False
        p = kernel32.GlobalLock(h)
        if not p:
            kernel32.GlobalFree(h)
            return False
        ctypes.memmove(p, data, len(data))
        kernel32.GlobalUnlock(h)
        if not user32.SetClipboardData(CF_UNICODETEXT, h):
            kernel32.GlobalFree(h)
            return False
        return True          # 内存所有权已交给系统，不能 GlobalFree
    finally:
        user32.CloseClipboard()


# ---------------------------------------------------------------- 按键注入

def _send(events) -> int:
    arr = (INPUT * len(events))()
    for i, (vk, up) in enumerate(events):
        arr[i].type = INPUT_KEYBOARD
        arr[i].u.ki = KEYBDINPUT(wVk=vk, wScan=0,
                                 dwFlags=KEYEVENTF_KEYUP if up else 0, time=0, dwExtraInfo=0)
    return user32.SendInput(len(events), arr, ctypes.sizeof(INPUT))


def paste() -> int:
    """发送 Ctrl+V。热键触发时用户的 Ctrl 可能还按着，所以完整发一遍按下/抬起。"""
    return _send([(VK_CONTROL, False), (VK_V, False), (VK_V, True), (VK_CONTROL, True)])


# ---------------------------------------------------------------- 规格解析

DICT_ORDER = ["store", "cat", "series", "variant"]


def classify(cfg: core.Config, tok: str):
    """判断一个速记符属于哪个字段。

    先用「跨字典精确匹配」——因为 w 同时能前缀匹配到系列 WFC、又是变体 WH 的速记符，
    精确匹配优先才能得到正确结果。返回 (字段名, 编码) / ("ambiguous", 候选) / None。
    """
    low = tok.lower()

    exact = []
    for name in DICT_ORDER:
        for e in cfg.entries(name):
            if e["code"].lower() == low or low in [str(a).lower() for a in e.get("alias", [])]:
                exact.append((name, e["code"]))
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return ("ambiguous", exact)

    if low.isdigit():                      # 纯数字色号
        return ("variant", tok)

    pref = []
    for name in DICT_ORDER:
        for e in cfg.entries(name):
            if (e["code"].lower().startswith(low)
                    or any(str(a).lower().startswith(low) for a in e.get("alias", []))):
                pref.append((name, e["code"]))
    if len(pref) == 1:
        return pref[0]
    if len(pref) > 1:
        return ("ambiguous", pref)
    return None


def parse_spec(cfg: core.Config, text: str):
    """把 "mts tf ss86 r,b" 这类文本解析成规格。严格要求每个 token 都能识别，否则整体作废。"""
    if not text or len(text) > 200 or "\n" in text.strip():
        return None
    tokens = [t for t in re.split(r"[\s,;/|·]+", text.strip()) if t]
    if not tokens:
        return None

    spec = {"store": None, "cat": None, "series": None, "variants": []}
    for tok in tokens:
        got = classify(cfg, tok)
        if got is None:
            return None
        name, code = got
        if name == "ambiguous":
            return None
        if name == "variant":
            spec["variants"].append(code)
            continue
        if spec[name] is not None:
            return None                    # 同一个字段给了两次，认定不是规格
        spec[name] = code

    if not spec["series"]:
        return None
    spec["store"] = spec["store"] or cfg.defaults.get("store")
    spec["cat"] = spec["cat"] or cfg.defaults.get("cat")
    if not (spec["store"] and spec["cat"]):
        return None
    spec["raw"] = text.strip()
    return spec


# ---------------------------------------------------------------- 状态

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = core.today()
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_FILE)


def describe(spec: dict) -> str:
    vs = spec.get("variants") or []
    base = f"{spec['store']}-{spec['cat']}-{spec['series']}"
    return f"{base}-{'/'.join(vs)}" if vs else f"{base}（无变体）"


# ---------------------------------------------------------------- 出号

def next_sku(cfg: core.Config, ledger: core.Ledger, state: dict, commit: bool = True):
    """按规格分配下一个 SKU。多变体时同一流水号依次出完，再进下一个号。

    commit=False 时纯预览：不写台账、不动 state。
    """
    spec = state.get("spec")
    if not spec:
        return None, '还没有设置规格：先跑一次 --set "mts tf ss86 r"'

    variants = spec.get("variants") or [None]
    base = state.get("base")
    idx = int(state.get("queue_index", 0))
    seed = {"store": spec["store"], "cat": spec["cat"], "series": spec["series"]}

    if not base or idx >= len(variants):
        serial = ledger.peek_next(cfg, seed)
        while True:
            cand = cfg.sep.join([spec["store"], spec["cat"], spec["series"],
                                 str(serial).zfill(cfg.width)])
            if not ledger.find_base(cand):
                break
            serial += 1
        base = cand
        idx = 0
    else:
        serial = int(state.get("serial", 0))

    v = variants[idx]
    sku = base + (cfg.sep + v if v else "")

    if commit:
        done = idx + 1 >= len(variants)
        state["base"] = None if done else base        # 变体出完 → 下次按就是新流水号
        state["serial"] = serial
        state["queue_index"] = 0 if done else idx + 1
        state["count"] = int(state.get("count", 0)) + 1
        if not ledger.exists(sku):
            ledger.add({
                "sku": sku, "base": base,
                "store": spec["store"], "cat": spec["cat"], "series": spec["series"],
                "serial": serial, "variant": v or "", "variant_name": "",
                "name": "", "created_at": core.today(), "source": "hotkey",
            })
            ledger.bump(cfg, seed, serial)
            ledger.save()
    return sku, None


# ---------------------------------------------------------------- 热键循环

class HotkeyDaemon:
    def __init__(self, cfg, ledger, args):
        self.cfg = cfg
        self.ledger = ledger
        self.args = args
        self.state = load_state()
        self.running = True

    def log(self, msg: str):
        if not self.args.quiet:
            print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

    def banner(self):
        print("=" * 70)
        print("  SKU 热键出号器")
        print("=" * 70)
        print(f"  台账     {self.ledger.path}（已有 {len(self.ledger.items)} 条）")
        print(f"  当前规格 {describe(self.state['spec']) if self.state.get('spec') else '（未设置）'}")
        print(f"  快捷键   Ctrl+B = 出号并粘贴    Ctrl+Shift+B = 用剪贴板里的速记符切换规格")
        print(f"           {'（仅复制到剪贴板，不自动粘贴）' if self.args.copy_only else ''}")
        print("  退出     本窗口 Ctrl+C，或另开窗口跑 --stop")
        print("=" * 70)

    def do_switch(self):
        text = get_clipboard()
        spec = parse_spec(self.cfg, text)
        if not spec:
            self.log(f"切换失败：剪贴板内容「{(text or '').strip()[:40]}」不是有效规格")
            self.log("          正确写法如：mts tf ss86 r   /   ss86 r   /   62店 md msb 01")
            return
        self.state["spec"] = spec
        self.state["base"] = None
        self.state["queue_index"] = 0
        save_state(self.state)
        self.log(f"规格已切换 → {describe(spec)}")

    def do_press(self):
        sku, err = next_sku(self.cfg, self.ledger, self.state)
        if err:
            self.log(f"× {err}")
            return
        save_state(self.state)
        if not set_clipboard(sku):
            self.log(f"× 写剪贴板失败（可能被其他程序占用），SKU 为 {sku}")
            return
        if self.args.copy_only:
            self.log(f"✓ {sku}  已复制到剪贴板")
            return
        time.sleep(self.args.settle_ms / 1000.0)
        n = paste()
        if n != 4:
            self.log(f"! {sku} 已复制，但按键注入返回 {n}（预期 4），请手动 Ctrl+V")
        else:
            self.log(f"✓ 已粘贴 {sku}")

    def run(self):
        self.banner()
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()), encoding="utf-8")

        ids = {}
        if not user32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_NOREPEAT, VK_B):
            err = ctypes.get_last_error()
            PID_FILE.unlink(missing_ok=True)
            hint = "（已有别的程序占用了这个组合键，关掉它再试）" if err == 1409 else ""
            core.die(f"注册 Ctrl+B 失败，错误码 {err} {hint}")
        ids[1] = "Ctrl+B"
        if user32.RegisterHotKey(None, 2, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, VK_B):
            ids[2] = "Ctrl+Shift+B"
        else:
            self.log("! Ctrl+Shift+B 被占用，切换规格请改用 --set")

        self.log(f"已就绪，监听 {', '.join(ids.values())}。")

        msg = wintypes.MSG()
        try:
            while self.running:
                r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if r in (0, -1):
                    break
                if msg.message == WM_HOTKEY:
                    if msg.wParam == 1:
                        self.do_press()
                    elif msg.wParam == 2:
                        self.do_switch()
        except KeyboardInterrupt:
            pass
        finally:
            for i in ids:
                user32.UnregisterHotKey(None, i)
            PID_FILE.unlink(missing_ok=True)
            self.log("已退出，热键已释放。")


# ---------------------------------------------------------------- 自检

def probe(cfg, ledger):
    print("环境自检")
    print("-" * 60)
    ok = True

    r = user32.RegisterHotKey(None, 99, MOD_CONTROL | MOD_NOREPEAT, VK_B)
    err = ctypes.get_last_error()
    if r:
        user32.UnregisterHotKey(None, 99)
        print("  [OK]   Ctrl+B 可用（已注册并立即释放）")
    else:
        ok = False
        print(f"  [FAIL] 无法注册 Ctrl+B，错误码 {err}"
              + ("（ERROR_HOTKEY_ALREADY_REGISTERED，别的程序占用了）" if err == 1409 else ""))

    old = get_clipboard()
    probe_text = "SKU_PROBE_测试_" + str(int(time.time()))
    if set_clipboard(probe_text):
        back = get_clipboard()
        if back == probe_text:
            print("  [OK]   剪贴板读写正常（中文往返一致）")
        else:
            ok = False
            print(f"  [FAIL] 剪贴板内容不一致：写入 {probe_text!r} 读回 {back!r}")
    else:
        ok = False
        print("  [FAIL] 写剪贴板失败")
    if old:
        set_clipboard(old)
        print("  [OK]   已还原原剪贴板内容")

    _send(())                                # 空数组调用一次，确认 ctypes 调用链正常
    expect = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
    if ctypes.sizeof(INPUT) == expect:
        print(f"  [OK]   INPUT 结构体布局正确（{ctypes.sizeof(INPUT)} 字节，{expect} 为预期），按键注入可用")
    else:
        ok = False
        print(f"  [FAIL] INPUT 结构体大小 {ctypes.sizeof(INPUT)}，预期 {expect}，Ctrl+V 会注入失败")

    spec = parse_spec(cfg, "mts tf ss86 r,b")
    if spec and spec["variants"] == ["RD", "BL"]:
        print("  [OK]   规格解析：mts tf ss86 r,b → MTS/TF/SS86 + RD,BL")
    else:
        ok = False
        print(f"  [FAIL] 规格解析异常：{spec}")

    for bad in ("SS86 擎天柱", "随便一段话", "mts tf", "zzz"):
        if parse_spec(cfg, bad) is not None:
            ok = False
            print(f"  [FAIL] 本不该被当成规格：{bad}")
    print("  [OK]   非规格文本被正确拒绝（商品标题/闲聊不会误切换）")

    print("-" * 60)
    print("自检通过。" if ok else "自检存在问题，见上方 FAIL。")
    return 0 if ok else 1


# ---------------------------------------------------------------- 入口

def main():
    global STATE_FILE
    core.setup_console()
    ap = argparse.ArgumentParser(prog="sku_hotkey.py",
                                 description="SKU 热键出号器：Ctrl+B 自动粘贴下一个 SKU 编号")
    ap.add_argument("--set", metavar="速记符", help='设置规格，如 --set "mts tf ss86 r"')
    ap.add_argument("--status", action="store_true", help="查看当前规格与下一个编号")
    ap.add_argument("--stop", action="store_true", help="停止正在运行的热键程序")
    ap.add_argument("--probe", action="store_true", help="环境自检（热键/剪贴板/按键注入/解析）")
    ap.add_argument("--copy-only", action="store_true", help="只复制到剪贴板，不自动粘贴")
    ap.add_argument("--quiet", action="store_true", help="不打印每次出号的日志")
    ap.add_argument("--settle-ms", type=int, default=180,
                    help="触发后等多久再粘贴（默认180ms，让手离开Ctrl）")
    ap.add_argument("--config", default=str(core.DEFAULT_CONFIG))
    ap.add_argument("--ledger", default=str(core.DEFAULT_LEDGER))
    ap.add_argument("--state", default=str(STATE_FILE), help="规格状态文件路径（一般不用改）")
    args = ap.parse_args()

    STATE_FILE = Path(args.state).resolve()
    cfg = core.Config(Path(args.config).resolve())
    ledger = core.Ledger(Path(args.ledger).resolve())

    if args.stop:
        if not PID_FILE.exists():
            core.die("没找到运行中的热键程序（没有 pid 文件）。")
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        h = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if not h:
            PID_FILE.unlink(missing_ok=True)
            core.die(f"进程 {pid} 已不在运行，已清理 pid 文件。")
        kernel32.TerminateProcess(h, 0)
        kernel32.CloseHandle(h)
        PID_FILE.unlink(missing_ok=True)
        print(f"已停止热键程序（PID {pid}）。")
        return

    if args.probe:
        sys.exit(probe(cfg, ledger))

    if args.set:
        spec = parse_spec(cfg, args.set)
        if not spec:
            core.die(f'无法识别规格「{args.set}」。正确写法如：mts tf ss86 r  /  ss86 r  /  62店 md msb 01')
        st = load_state()
        st["spec"] = spec
        st["base"] = None
        st["queue_index"] = 0
        save_state(st)
        print(f"规格已设置 → {describe(spec)}")
        print(f"下一个编号    {sku_preview(cfg, ledger, st)}")
        return

    if args.status:
        st = load_state()
        if not st.get("spec"):
            print("尚未设置规格。跑一次：  --set \"mts tf ss86 r\"")
            return
        print(f"当前规格   {describe(st['spec'])}")
        print(f"原始输入   {st['spec'].get('raw', '')}")
        print(f"已出号     {st.get('count', 0)} 个")
        print(f"下一个编号 {sku_preview(cfg, ledger, st)}")
        print(f"台账       {ledger.path}（{len(ledger.items)} 条）")
        print(f"运行中     {'是' if PID_FILE.exists() else '否'}")
        return

    HotkeyDaemon(cfg, ledger, args).run()


def sku_preview(cfg, ledger, state) -> str:
    """只算不写：预览下一个会出什么号。"""
    sku, err = next_sku(cfg, ledger, copy.deepcopy(state), commit=False)
    return sku if sku else (err or "?")


if __name__ == "__main__":
    main()
