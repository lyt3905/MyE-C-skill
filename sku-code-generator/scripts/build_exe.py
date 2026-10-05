#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把热键出号器打包成单个 exe（双击即用，缩在右下角托盘）。

用带 PyInstaller 的隔离 venv 跑：
    "C:/Users/shana/.workbuddy/binaries/python/envs/default/Scripts/python.exe" scripts/build_exe.py

产物：dist/编号出号器.exe（单文件，无控制台窗口）
    · 数据（序号、pid、日志）落在 exe 同目录的 data/ —— 换机器时把整个文件夹拷走即可
    · 字典内置一份兜底副本；要改字典就用 --config 指定外部文件
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_PY = Path("C:/Users/shana/.workbuddy/binaries/python/envs/default/Scripts/python.exe")
APP_NAME = "编号出号器"
ENTRY = ROOT / "scripts" / "sku_hotkey.py"
ICON = ROOT / "assets" / "sku_hotkey.ico"
DIST = ROOT / "dist"


def main() -> int:
    python = str(VENV_PY if VENV_PY.exists() else sys.executable)

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print(f"[错误] {python} 里没有 PyInstaller。先装：\n"
              f'  "{python}" -m pip install pyinstaller')
        return 1

    if not ICON.exists():
        print("[错误] 找不到图标 %s，先跑一次 scripts/make_icon.py" % ICON)
        return 1

    args = [
        python, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile",                       # 单文件
        "--windowed",                      # 不要控制台黑框（托盘程序）
        "--name", APP_NAME,
        "--icon", str(ICON),
        # 字典兜底副本：exe 同目录没放 config/ 时用它
        "--add-data", f"{ROOT / 'config' / 'sku_config.json'}{os.pathsep}config",
        # 托盘图标兜底（正常情况下直接抽 exe 自身的图标资源）
        "--add-data", f"{ICON}{os.pathsep}assets",
        "--distpath", str(DIST),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
    ]
    # 托盘 exe 用不到批量表格（那是命令行 sku_gen.py 的活），把重家伙排掉省体积
    for mod in ("openpyxl", "et_xmlfile", "tkinter", "unittest", "pydoc", "doctest",
                "sqlite3", "xml", "http", "email", "PIL", "numpy", "setuptools", "pip"):
        args += ["--exclude-module", mod]
    args.append(str(ENTRY))

    # 产物被占用是打包失败最常见的原因，而 PyInstaller 只会甩一句"退出码 1"，
    # 根本看不出为什么。提前探一次，报错说得明白些。
    exe = DIST / f"{APP_NAME}.exe"
    if exe.exists():
        try:
            with exe.open("rb+"):
                pass
        except OSError:
            print(f"[错误] {exe}\n"
                  f"       正被运行中的程序占用，无法覆盖。先停掉它：\n"
                  f'         "{exe}" --stop\n'
                  f"       或在托盘图标上右键 → 退出。")
            return 1

    print("开始打包…")
    print("  " + " ".join(args[2:]))
    r = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(f"[错误] PyInstaller 退出码 {r.returncode}，输出尾部：")
        for line in (r.stdout or "").strip().splitlines()[-25:]:
            print("  " + line)
        for line in (r.stderr or "").strip().splitlines()[-15:]:
            print("  ! " + line)
        return r.returncode
    if r.stdout:
        print("  " + r.stdout.strip().splitlines()[-1])

    if not exe.exists():
        print(f"[错误] 没找到产物 {exe}")
        return 1

    # 把用到的东西也放一份到 dist，方便连文件夹一起拷到别的机器
    readme = DIST / "使用说明.txt"
    readme.write_text(
        f"""编号出号器（{APP_NAME}.exe）

1. 双击 {APP_NAME}.exe —— 程序缩到右下角托盘，不占屏幕
2. 在任何输入框里按 Ctrl+B → 编号直接粘到光标处，按一次加一
3. 托盘图标：双击 = 出号并粘贴；右键 = 菜单（查看下一个 / 打开数据目录 / 退出）
4. 关掉重开、重启电脑都会接着上次的序号往下走，不会重号

改编号长相（前缀 / 连接词 / 位数），在命令行里跑一次就永久记住：
    {APP_NAME}.exe --prefix "MTS-{{date}}"      → MTS-20261005-00001
    {APP_NAME}.exe --prefix "MTS"               → MTS-00001
    {APP_NAME}.exe --prefix ""                  → 00001（不要前缀）
    {APP_NAME}.exe --sep "_" --width 3          → 20261005_001
    {APP_NAME}.exe --from 1200                  → 下一个从 1200 开始
    {APP_NAME}.exe --status                     → 看当前设置和下一个编号
    {APP_NAME}.exe --stop                       → 停止托盘程序

数据都在本目录的 data\\ 下，换机器时整个文件夹拷走即可。
""", encoding="utf-8")

    size_mb = exe.stat().st_size / 1024 / 1024
    print(f"\n打包完成：{exe}")
    print(f"  体积 {size_mb:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
