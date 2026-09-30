#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编号热键出号器 —— 按 Ctrl+B 自动把下一个编号粘贴到光标处。

默认：日期流水号（装上就能用，不需要任何设置）
    ├─ 按一下 Ctrl+B → 20260930-00001 → 20260930-00002 → … → 自动粘贴
    ├─ 前缀默认是当天日期，隔天自动换成新日期、序号重新从 1 开始
    ├─ 序号记在 data/hotkey_state.json，关掉重开接着往下走，不会重号
    └─ 不写台账，只管出号

改编号长相（前缀 / 连接词 / 位数）—— 设一次就一直记住
    python sku_hotkey.py --prefix "{date}"        # 20260930-00001（默认）
    python sku_hotkey.py --prefix "MTS"           # MTS-00001
    python sku_hotkey.py --prefix "MTS-{date}"    # MTS-20260930-00001
    python sku_hotkey.py --prefix ""              # 00001（不要前缀）
    python sku_hotkey.py --sep "_" --width 3      # 换连接词与补零位数
    python sku_hotkey.py --from 1200              # 把下一个编号设为 1200

可选：SKU 编码模式（要带店铺/品类/系列/颜色时）
    ├─ python sku_hotkey.py --set "mts tf ss86 r" 切过去，出 MTS-TF-SS86-0001-RD
    ├─ 剪贴板里放着速记符时，按 Ctrl+Shift+B 也能切
    └─ 这个模式下才写台账，和命令行模式共用流水号，不会撞号

用法
    启动热键：  python sku_hotkey.py       （或双击 start_hotkey.bat）
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
from datetime import datetime, timedelta
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
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

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
# 必须声明签名：否则 64 位下 OpenProcess 返回的句柄会被默认 restype 截成 32 位
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
kernel32.TerminateProcess.restype = wintypes.BOOL


# ---------------------------------------------------------------- 进程状态

def read_pid():
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def pid_alive(pid: int) -> bool:
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not h:
        return False
    kernel32.CloseHandle(h)
    return True


def daemon_running() -> bool:
    """pid 文件存在 ≠ 进程还活着：被强杀后残留的 pid 会让状态误报「运行中」。"""
    pid = read_pid()
    return bool(pid and pid_alive(pid))


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

def migrate_state(st: dict) -> dict:
    """老版本 state（纯数字流水号 0001/0002…）迁移到「日期-序号」结构。

    编号长相都变了，旧的计数没有参考价值，直接作废，避免 --status 报出
    「已出 10 个」却一个都没出过的怪数。幂等：出过一次号后 seq 存在，就不再动。
    """
    if "seq" not in st and "next" in st:
        st.pop("next", None)
        st["count"] = 0
    return st


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return migrate_state(json.loads(STATE_FILE.read_text(encoding="utf-8")))
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
        return None, '当前是 SKU 编码模式但还没设规格：先跑一次 --set "mts tf ss86 r"'

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


# ---------------------------------------------------------------- 流水号模式（默认）

DEFAULT_PREFIX = "{date}"        # 默认前缀：当天日期 YYYYMMDD
DEFAULT_SEP = "-"                # 前缀与序号之间的连接词
DEFAULT_WIDTH = 5                # 序号补零位数


def render_prefix(state: dict, now=None) -> str:
    """把前缀模板渲染成实际文本。

    占位符：{date}=YYYYMMDD、{yy}、{mm}、{dd}。
    前缀写成空串表示「不要前缀」，此时只出流水号。
    """
    tmpl = state.get("prefix")
    if tmpl is None:
        tmpl = DEFAULT_PREFIX
    if not tmpl:
        return ""
    d = now or datetime.now()
    return (str(tmpl)
            .replace("{date}", d.strftime("%Y%m%d"))
            .replace("{yy}", d.strftime("%y"))
            .replace("{mm}", d.strftime("%m"))
            .replace("{dd}", d.strftime("%d")))


def compose(prefix: str, sep: str, n: int, width: int) -> str:
    """拼出最终编号：前缀 + 连接词 + 序号。前缀为空时只留序号。"""
    body = str(n).zfill(width) if width > 0 else str(n)
    return (prefix + sep + body) if prefix else body


def describe_plain(state: dict, now=None) -> str:
    """一句话描述当前编号长相（给 banner / --status 用）。"""
    prefix = render_prefix(state, now)
    width = int(state.get("width", DEFAULT_WIDTH))
    sep = str(state.get("sep", DEFAULT_SEP))
    w = f"{width} 位补零" if width > 0 else "不补零"
    if not prefix:
        return f"无前缀 · {w}"
    return f"前缀「{prefix}」+ 连接词「{sep}」+ {w}"


def next_plain(cfg: core.Config, state: dict, now=None) -> str:
    """日期流水号：20260930-00001 → 20260930-00002 → 20260930-00003。

    计数器按「渲染后的前缀」分组存放，所以：
      · 前缀带日期 → 隔天 key 变了，序号自动从 1 重新开始；
      · 前缀固定（如 MTS）→ 只有一个 key，序号一直连续递增。
    """
    prefix = render_prefix(state, now)
    width = int(state.get("width", DEFAULT_WIDTH))
    sep = str(state.get("sep", DEFAULT_SEP))

    seq = state.setdefault("seq", {})
    n = int(seq.get(prefix, 0) or 0) + 1
    seq[prefix] = n
    state["count"] = int(state.get("count", 0)) + 1
    return compose(prefix, sep, n, width)


def mode_of(state: dict) -> str:
    """默认就是纯流水号模式 —— 装上按 Ctrl+B 就能用，不需要任何设置。"""
    return "sku" if state.get("mode") == "sku" else "plain"


def next_code(cfg: core.Config, ledger: core.Ledger, state: dict, commit: bool = True):
    """统一出口：按当前模式取下一个编号。"""
    if mode_of(state) == "plain":
        return next_plain(cfg, state), None
    return next_sku(cfg, ledger, state, commit=commit)


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
        print("  编号热键出号器")
        print("=" * 70)
        if mode_of(self.state) == "plain":
            print(f"  模式     流水号 · {describe_plain(self.state)}")
            print(f"  下一个   {sku_preview(self.cfg, self.ledger, self.state)}")
        else:
            print("  模式     SKU 编码")
            print(f"  当前规格 {describe(self.state['spec'])}")
            print(f"  台账     {self.ledger.path}（已有 {len(self.ledger.items)} 条）")
        print("  快捷键   Ctrl+B = 出号并粘贴    Ctrl+Shift+B = 用剪贴板里的速记符切到 SKU 模式")
        print(f"           {'（仅复制到剪贴板，不自动粘贴）' if self.args.copy_only else ''}")
        print("  退出     本窗口 Ctrl+C，或另开窗口跑 --stop")
        print("=" * 70)

    def refresh(self):
        """每次按键前重读磁盘状态。

        守护进程是常驻的。若只在启动时读一次：
          1) 外部 `--set` 改的规格不会生效（按出来还是旧规格的号）；
          2) 接着 `save_state(self.state)` 还会把内存里的旧规格写回文件，把设置覆盖掉；
          3) 命令行模式（sku_gen.py）写了新号，这边也不知道，会重复分配同一个流水号。
        """
        self.state = load_state()
        self.ledger.reload()

    def do_switch(self):
        self.refresh()
        text = get_clipboard()
        spec = parse_spec(self.cfg, text)
        if not spec:
            self.log(f"切换失败：剪贴板内容「{(text or '').strip()[:40]}」不是有效规格")
            self.log("          正确写法如：mts tf ss86 r   /   ss86 r   /   62店 md msb 01")
            return
        self.state["spec"] = spec
        self.state["mode"] = "sku"
        self.state["base"] = None
        self.state["queue_index"] = 0
        save_state(self.state)
        self.log(f"规格已切换 → {describe(spec)}（SKU 模式）")

    def do_press(self):
        self.refresh()
        sku, err = next_code(self.cfg, self.ledger, self.state)
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

    day1 = datetime(2026, 9, 30, 10, 0, 0)

    st_plain = {}
    got_plain = [next_plain(cfg, st_plain, now=day1) for _ in range(3)]
    if got_plain == ["20260930-00001", "20260930-00002", "20260930-00003"]:
        print("  [OK]   日期流水号自增：20260930-00001 → 00002 → 00003")
    else:
        ok = False
        print(f"  [FAIL] 日期流水号自增异常：{got_plain}")

    st_day2 = {"seq": {"20260930": 3}}
    got_day2 = [next_plain(cfg, st_day2, now=day1 + timedelta(days=1)) for _ in range(2)]
    if got_day2 == ["20261001-00001", "20261001-00002"]:
        print("  [OK]   跨天自动换日期、序号重新从 1 开始（20260930…→20261001-00001）")
    else:
        ok = False
        print(f"  [FAIL] 跨天行为异常：{got_day2}")

    st_custom = {"prefix": "MTS", "sep": "_", "width": 4}
    got_custom = [next_plain(cfg, st_custom, now=day1) for _ in range(2)]
    if got_custom == ["MTS_0001", "MTS_0002"]:
        print("  [OK]   自定义前缀/连接词/位数：MTS_0001 → MTS_0002")
    else:
        ok = False
        print(f"  [FAIL] 自定义前缀异常：{got_custom}")

    st_noprefix = {"prefix": "", "width": 3}
    got_np = [next_plain(cfg, st_noprefix, now=day1) for _ in range(2)]
    if got_np == ["001", "002"]:
        print("  [OK]   不要前缀时只出流水号：001 → 002")
    else:
        ok = False
        print(f"  [FAIL] 无前缀模式异常：{got_np}")

    st_tpl = {"prefix": "MTS-{yy}{mm}{dd}"}
    got_tpl = next_plain(cfg, st_tpl, now=day1)
    if got_tpl == "MTS-260930-00001":
        print("  [OK]   前缀占位符渲染：MTS-{yy}{mm}{dd} → MTS-260930-00001")
    else:
        ok = False
        print(f"  [FAIL] 占位符渲染异常：{got_tpl}")

    if mode_of({}) == "plain" and mode_of({"mode": "sku", "spec": {"store": "MTS"}}) == "sku":
        print("  [OK]   模式判定：默认纯流水号，--set 后为 SKU 模式")
    else:
        ok = False
        print("  [FAIL] 模式判定异常")

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
                                 description="按 Ctrl+B 自动粘贴下一个编号（默认纯流水号，装上即用）")
    ap.add_argument("--plain", action="store_true",
                    help="切到流水号模式（默认就是这个，不记台账）")
    ap.add_argument("--prefix", metavar="模板",
                    help='前缀模板："{date}"=当天日期（默认）、"MTS"、"MTS-{date}"；传 "" 表示不要前缀')
    ap.add_argument("--sep", metavar="连接词", help='前缀与序号之间的连接词（默认 "-"）')
    ap.add_argument("--width", type=int, metavar="位数",
                    help="序号补零位数（默认 5；0 = 不补零）")
    ap.add_argument("--from", dest="from_", type=int, metavar="N",
                    help="把下一个编号设为 N（只影响当前前缀）")
    ap.add_argument("--set", metavar="速记符",
                    help='切到 SKU 编码模式并设规格，如 --set "mts tf ss86 r"')
    ap.add_argument("--status", action="store_true", help="查看当前模式与下一个编号")
    ap.add_argument("--stop", action="store_true", help="停止正在运行的热键程序")
    ap.add_argument("--probe", action="store_true", help="环境自检（热键/剪贴板/按键注入/解析）")
    ap.add_argument("--copy-only", action="store_true", help="只复制到剪贴板，不自动粘贴")
    ap.add_argument("--quiet", action="store_true", help="不打印每次出号的日志")
    ap.add_argument("--settle-ms", type=int, default=180,
                    help="触发后等多久再粘贴（默认180ms，让手离开Ctrl）")
    ap.add_argument("--config", default=str(core.DEFAULT_CONFIG))
    ap.add_argument("--ledger", default=str(core.DEFAULT_LEDGER))
    ap.add_argument("--state", default=str(STATE_FILE), help="状态文件路径（一般不用改）")
    args = ap.parse_args()

    STATE_FILE = Path(args.state).resolve()
    cfg = core.Config(Path(args.config).resolve())
    ledger = core.Ledger(Path(args.ledger).resolve())

    if args.stop:
        pid = read_pid()
        if not pid:
            core.die("没找到运行中的热键程序（没有 pid 文件）。")
        h = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if not h:
            PID_FILE.unlink(missing_ok=True)
            core.die(f"进程 {pid} 已不在运行，已清理残留的 pid 文件。")
        kernel32.TerminateProcess(h, 0)
        kernel32.CloseHandle(h)
        PID_FILE.unlink(missing_ok=True)
        print(f"已停止热键程序（PID {pid}）。")
        return

    if args.probe:
        sys.exit(probe(cfg, ledger))

    if (args.plain or args.prefix is not None or args.from_ is not None
            or args.sep is not None or args.width is not None):
        st = load_state()
        # --plain / --prefix / --from 都会切到流水号模式；单独改 --sep / --width 不动模式
        if args.plain or args.prefix is not None or args.from_ is not None:
            st["mode"] = "plain"
        if args.prefix is not None:
            st["prefix"] = args.prefix            # 允许空串 = 不要前缀
        else:
            st.setdefault("prefix", DEFAULT_PREFIX)
        if args.sep is not None:
            st["sep"] = args.sep
        if args.width is not None:
            if args.width < 0:
                core.die("--width 不能是负数（0 表示不补零）。")
            st["width"] = args.width
        if args.from_ is not None:
            if args.from_ < 1:
                core.die("--from 需要是不小于 1 的整数。")
            st.setdefault("seq", {})[render_prefix(st)] = args.from_ - 1
        save_state(st)
        print(f"已设为流水号模式 · {describe_plain(st)}")
        print(f"下一个编号 {sku_preview(cfg, ledger, st)}")
        return

    if args.set:
        spec = parse_spec(cfg, args.set)
        if not spec:
            core.die(f'无法识别规格「{args.set}」。正确写法如：mts tf ss86 r  /  ss86 r  /  62店 md msb 01')
        st = load_state()
        st["spec"] = spec
        st["mode"] = "sku"
        st["base"] = None
        st["queue_index"] = 0
        save_state(st)
        print(f"已切到 SKU 编码模式 → {describe(spec)}")
        print(f"下一个编号            {sku_preview(cfg, ledger, st)}")
        return

    if args.status:
        st = load_state()
        if mode_of(st) == "plain":
            prefix = render_prefix(st)
            seq = st.get("seq", {})
            print(f"模式       流水号（{describe_plain(st)}，不记台账）")
            print(f"已出号     {st.get('count', 0)} 个")
            if prefix:
                used = seq.get(prefix, 0)
                print(f"当前前缀   {prefix}" + (f"（已出到第 {used} 个）" if used else "（还没出过号）"))
            print(f"下一个编号 {sku_preview(cfg, ledger, st)}")
            others = sorted(k for k in seq if k != prefix)
            if others:
                print("历史前缀   " + "、".join(f"{k}→{seq[k]}" for k in others[-6:]))
        else:
            print("模式       SKU 编码")
            print(f"当前规格   {describe(st['spec'])}")
            print(f"原始输入   {st['spec'].get('raw', '')}")
            print(f"已出号     {st.get('count', 0)} 个")
            print(f"下一个编号 {sku_preview(cfg, ledger, st)}")
            print(f"台账       {ledger.path}（{len(ledger.items)} 条）")
        if daemon_running():
            run_str = "是"
        elif read_pid():
            run_str = "否（pid 文件是残留的，已清理）"
            PID_FILE.unlink(missing_ok=True)
        else:
            run_str = "否"
        print(f"运行中     {run_str}")
        return

    HotkeyDaemon(cfg, ledger, args).run()


def sku_preview(cfg, ledger, state) -> str:
    """只算不写：预览下一个会出什么号。"""
    sku, err = next_code(cfg, ledger, copy.deepcopy(state), commit=False)
    return sku if sku else (err or "?")


if __name__ == "__main__":
    main()
