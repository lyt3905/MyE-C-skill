#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端验证用：向运行中的出号器注入一次真实的 Ctrl+B，**不碰剪贴板**。

为什么要单独有这个脚本：
    验证「热键 → 出号 → 剪贴板」整条链路时，最容易犯的错是让验证脚本自己去写剪贴板
    （写哨兵、再读回来）。跨进程反复交替读写 GlobalAlloc 的私有 HGLOBAL 时，内容会互相遮挡，
    读回来是旧值，看起来像产品 bug，其实是验证脚本的副作用。

正确姿势（本脚本 + 独立读取工具）：
    1. 先启动出号器（加 --copy-only，避免把测试编号粘到前台窗口）：
          编号出号器.exe --copy-only --quiet
    2. 跑本脚本注入按键：
          python scripts/press_only.py            # 注入一次
          python scripts/press_only.py 3          # 连续注入三次（每次间隔 1s）
    3. 用**独立工具**读剪贴板核对（PowerShell）：
          Get-Clipboard
       也可以看 data/hotkey.log 里每次出号的记录。

实测基准：注入后约 0.25s 编号就已写入剪贴板，出号递增且内容稳定。
"""
from __future__ import annotations

import ctypes
import sys
import time

user32 = ctypes.WinDLL("user32", use_last_error=True)

VK_CONTROL = 0x11
VK_B = 0x42
KEYEVENTF_KEYUP = 0x0002


def press_ctrl_b() -> None:
    """注入 Ctrl+B（按下-保持-抬起的顺序与真人按键一致，否则热键可能漏触发）。"""
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    time.sleep(0.03)
    user32.keybd_event(VK_B, 0, 0, 0)
    time.sleep(0.03)
    user32.keybd_event(VK_B, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.03)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def main() -> int:
    times = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    for i in range(times):
        press_ctrl_b()
        if i + 1 < times:
            time.sleep(1.0)
    time.sleep(0.5)                     # 给出号器留出处理时间
    print(f"已注入 Ctrl+B × {times}（未触碰剪贴板）。"
          "请用 Get-Clipboard 或 data/hotkey.log 核对结果。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
