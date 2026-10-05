#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows 系统托盘图标（纯 ctypes 实现，不依赖 pystray / Pillow）。

为什么要自己写
    pystray 需要 Pillow，PyInstaller 打包后会多出十几 MB；而托盘本质只是
    shell32 的一个 Shell_NotifyIconW 调用 + 一个接收鼠标消息的隐藏窗口。
    自己写 ≈ 200 行，零第三方依赖，打包出来的 exe 干净。

用法
    tray = TrayIcon(tooltip="编号出号器", icon_path=..., on_command=cb,
                    menu=[(1, "出下一个编号"), (None, None), (9, "退出")])
    tray.create()                      # 建隐藏窗口 + 注册图标
    tray.set_tip("下一个 20261005-00003")

    # 在主消息循环里把非热键消息派发掉，托盘的鼠标消息才会到达
    while running:
        if user32.GetMessageW(byref(msg), None, 0, 0) in (0, -1):
            break
        if msg.message == WM_HOTKEY:
            ...
        elif msg.hwnd:
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))

    tray.destroy()                     # 退出前必须摘掉图标，否则托盘残留"幽灵图标"

踩过的坑（写在这里免得下次再踩）
    · NOTIFYICONDATAW 的 cbSize 必须填真实结构体大小，Windows 靠它判断版本；
      填错会静默失败（Shell_NotifyIconW 返回 0）。
    · 弹菜单前必须 SetForegroundWindow(hwnd) + PostMessage(WM_NULL)，否则点击
      菜单外部区域时菜单不会消失（Windows 的经典怪癖）。
    · WndProc 回调对象必须保持引用，否则被 GC 回收后收到消息直接崩溃。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

# ---------------------------------------------------------------- 常量

WM_APP = 0x8000
WM_TRAYICON = WM_APP + 1          # 自定义：托盘鼠标消息都发到这个号
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
WM_NULL = 0x0000

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIM_SETVERSION = 4

NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
NIF_SHOWTIP = 0x00000080

NIIF_NONE = 0x00000000
NIIF_INFO = 0x00000001
NIIF_WARNING = 0x00000002
NIIF_ERROR = 0x00000003
NIIF_NOSOUND = 0x00000010

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040
IDI_APPLICATION = 32512

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_GRAYED = 0x00000001
MF_DEFAULT = 0x00001000
TPM_RETURNCMD = 0x0100
TPM_RIGHTBUTTON = 0x0002
TPM_NONOTIFY = 0x0080

TOOLTIP_MAX = 128                 # NOTIFYICONDATAW.szTip 固定长度


class NOTIFYICONDATAW(ctypes.Structure):
    """必须和 Windows 的定义逐字段对齐；cbSize 填 sizeof 本身。"""

    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


_kernel32_handle = kernel32.GetModuleHandleW(None)
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                   wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                   wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.DefWindowProcW.restype = ctypes.c_void_p
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.RegisterClassExW.restype = wintypes.ATOM
user32.LoadImageW.restype = wintypes.HANDLE
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.LoadIconW.restype = wintypes.HICON
user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.DestroyIcon.argtypes = [wintypes.HICON]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.restype = wintypes.BOOL
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR]
user32.TrackPopupMenu.restype = wintypes.BOOL      # 带 TPM_RETURNCMD 时返回 BOOL(命令号)
user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.LPVOID]
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.PostQuitMessage.argtypes = [ctypes.c_int]


def _signed_lowword(v: int) -> int:
    """lParam 里的坐标是 16 位有符号数，多屏负坐标要还原。"""
    n = v & 0xFFFF
    return n - 0x10000 if n & 0x8000 else n


def _signed_highword(v: int) -> int:
    n = (v >> 16) & 0xFFFF
    return n - 0x10000 if n & 0x8000 else n


class TrayIcon:
    """一个托盘图标 + 右键菜单 + 隐藏消息窗口。"""

    _class_seq = 0

    def __init__(self, tooltip: str = "编号出号器", icon_path=None,
                 on_command=None, on_double_click=None, menu=None,
                 class_name: str | None = None, close_command=None):
        self.tooltip = tooltip
        self.icon_path = Path(icon_path) if icon_path else None
        self.on_command = on_command            # 回调：菜单命令号
        self.on_double_click = on_double_click  # 回调：双击图标
        self.menu = list(menu or [])            # [(命令号, 文本)]，文本为 None 表示分隔线
        self.close_command = close_command      # 收到 WM_CLOSE 时触发的命令号（供 --stop 优雅退出）
        # 固定类名让外部进程能用 FindWindowW 找到这个窗口（强杀会留幽灵图标，优雅退出才是正解）
        self.class_name = class_name

        self.hwnd = None
        self.hicon = None
        self._wndproc = None                    # 必须持有引用，否则被 GC → 崩溃
        self._class_name = None
        self._added = False
        self.commands = {}                      # 命令号 → 文本

    # ------------------------------------------------------------ 图标

    def _load_icon(self):
        """图标优先级：exe 自身资源（打包场景，一定和 exe 图标一致）→ ico 文件 → 系统默认。"""
        if getattr(sys, "frozen", False):
            large = wintypes.HICON()
            small = wintypes.HICON()
            n = shell32.ExtractIconExW(sys.executable, 0, ctypes.byref(large),
                                       ctypes.byref(small), 1)
            if n > 0 and large.value:
                if small.value:
                    user32.DestroyIcon(small)
                return large
        if self.icon_path and self.icon_path.exists():
            h = user32.LoadImageW(None, str(self.icon_path), IMAGE_ICON, 0, 0,
                                  LR_LOADFROMFILE | LR_DEFAULTSIZE)
            if h:
                return h
        return user32.LoadIconW(None, wintypes.LPCWSTR(IDI_APPLICATION))

    # ------------------------------------------------------------ 窗口

    def _register_class(self):
        if self.class_name:
            self._class_name = self.class_name
        else:
            TrayIcon._class_seq += 1
            self._class_name = f"SKUTrayWnd_{id(self):x}_{TrayIcon._class_seq}"

        @WNDPROC
        def _proc(hwnd, msg, wparam, lparam):
            try:
                return self._on_message(hwnd, msg, wparam, lparam)
            except Exception:
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc = _proc                # 持有引用，防止 GC

        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = 0
        wc.lpfnWndProc = _proc
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = _kernel32_handle
        wc.hIcon = None
        wc.hCursor = None
        wc.hbrBackground = None
        wc.lpszMenuName = None
        wc.lpszClassName = self._class_name
        wc.hIconSm = None
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            raise OSError("RegisterClassExW 失败，错误码 %d" % ctypes.get_last_error())

    def _on_message(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAYICON:
            if lparam in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._popup_menu()
            elif lparam == WM_LBUTTONDBLCLK:
                if self.on_double_click:
                    self.on_double_click()
            elif lparam == WM_LBUTTONUP:
                if self.on_command and getattr(self, "click_command", None):
                    self.on_command(self.click_command)
            return 0
        if msg == WM_CLOSE:
            # 外部（--stop）请求退出：交给上层走正常清理流程，别直接 DestroyWindow
            if self.on_command and self.close_command:
                self.on_command(self.close_command)
                return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def create(self):
        """建隐藏窗口并把图标挂上托盘。窗口从不 ShowWindow，所以界面里看不到。"""
        self._register_class()
        self.hwnd = user32.CreateWindowExW(
            0, self._class_name, "SKU Tray", 0, 0, 0, 0, 0,
            None, None, _kernel32_handle, None)
        if not self.hwnd:
            raise OSError("CreateWindowExW 失败，错误码 %d" % ctypes.get_last_error())

        self.hicon = self._load_icon()
        data = self._nid()
        data.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP | NIF_SHOWTIP
        data.uCallbackMessage = WM_TRAYICON
        data.hIcon = self.hicon
        data.szTip = self.tooltip[:TOOLTIP_MAX - 1]
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data)):
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
            raise OSError("Shell_NotifyIconW(NIM_ADD) 失败，托盘图标没能挂上")
        self._added = True
        return self

    def _nid(self) -> NOTIFYICONDATAW:
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self.hwnd
        data.uID = 1
        return data

    # ------------------------------------------------------------ 菜单

    def _popup_menu(self):
        if not self.menu:
            return
        menu = user32.CreatePopupMenu()
        if not menu:
            return
        self.commands.clear()
        for cmd, label in self.menu:
            if label is None:
                user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            else:
                user32.AppendMenuW(menu, MF_STRING, cmd, label)
                self.commands[cmd] = label

        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        # 这两行是必须的：不这么做，点菜单外面菜单不会消失
        user32.SetForegroundWindow(self.hwnd)
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)

        cmd = user32.TrackPopupMenu(
            menu, TPM_RETURNCMD | TPM_RIGHTBUTTON, pt.x, pt.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)

        if cmd and self.on_command:
            self.on_command(cmd)

    # ------------------------------------------------------------ 提示

    def set_tip(self, text: str):
        """更新悬停提示。出号后调一下，鼠标一悬停就能看到下一个编号。"""
        self.tooltip = text
        if not self._added:
            return
        data = self._nid()
        data.uFlags = NIF_TIP | NIF_SHOWTIP
        data.szTip = text[:TOOLTIP_MAX - 1]
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(data))

    def notify(self, title: str, text: str, level: int = NIIF_INFO):
        """气泡通知（默认静音，不打断）。"""
        if not self._added:
            return
        data = self._nid()
        data.uFlags = NIF_INFO
        data.szInfoTitle = title[:63]
        data.szInfo = text[:255]
        data.dwInfoFlags = level | NIIF_NOSOUND
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(data))

    # ------------------------------------------------------------ 清理

    def destroy(self):
        if self._added:
            data = self._nid()
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))
            self._added = False
        if self.hicon:
            user32.DestroyIcon(self.hicon)
            self.hicon = None
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
        self._wndproc = None
