#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 assets/sku_hotkey.ico（程序图标 + 托盘图标）。

图标只在「重新设计外观」时才需要重跑一次，生成结果 .ico 已提交进仓库，
所以打包 exe 并不依赖 Pillow —— 只有这个脚本需要。

设计：深蓝渐变圆角方块 + 白色 # 号（编号/标签的通用符号），
导出 16/24/32/48/64/128/256 七种尺寸，小到托盘 16px、大到文件管理器 256px 都清晰。

用法（用带 Pillow 的隔离 venv）：
    "C:/Users/shana/.workbuddy/binaries/python/envs/default/Scripts/python.exe" scripts/make_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "sku_hotkey.ico"
SIZE = 256

TOP = (32, 74, 158)        # 渐变上端：深蓝
BOTTOM = (18, 42, 94)      # 渐变下端：更深的蓝
ACCENT = (255, 255, 255)


def gradient(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), TOP)
    d = ImageDraw.Draw(img)
    for y in range(size):
        t = y / max(size - 1, 1)
        d.line([(0, y), (size, y)],
               fill=tuple(round(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)))
    return img


def rounded_mask(size: int, radius_ratio: float = 0.22) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * radius_ratio), fill=255)
    return mask


def draw_hash(img: Image.Image) -> None:
    """画 # 号。优先用系统粗体字体；取不到就用手绘线条（保证脚本到处能跑）。"""
    size = img.width
    d = ImageDraw.Draw(img)
    text = "#"
    font = None
    for name in ("arialbd.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(name, int(size * 0.68))
            break
        except Exception:
            continue

    if font:
        box = d.textbbox((0, 0), text, font=font)
        w, h = box[2] - box[0], box[3] - box[1]
        d.text(((size - w) / 2 - box[0], (size - h) / 2 - box[1]),
               text, font=font, fill=ACCENT)
        return

    lw = max(2, int(size * 0.085))          # 手绘：两竖两横
    x1, x2 = int(size * 0.36), int(size * 0.64)
    y1, y2 = int(size * 0.24), int(size * 0.76)
    d.line([(x1, y1), (x2, y2)], fill=ACCENT, width=lw)
    d.line([(x1 + int(size * 0.07), y1), (x2 + int(size * 0.07), y2)], fill=ACCENT, width=lw)
    d.line([(int(size * 0.22), int(size * 0.42)), (int(size * 0.78), int(size * 0.42))],
           fill=ACCENT, width=lw)
    d.line([(int(size * 0.22), int(size * 0.60)), (int(size * 0.78), int(size * 0.60))],
           fill=ACCENT, width=lw)


def main() -> int:
    base = gradient(SIZE)
    draw_hash(base)
    base.putalpha(rounded_mask(SIZE))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    base.save(OUT, format="ICO", sizes=sizes)

    # 顺手存一份 png，方便在文档/预览里看效果
    base.resize((128, 128), Image.LANCZOS).save(OUT.with_suffix(".png"))

    print(f"已生成 {OUT}（{OUT.stat().st_size} 字节，尺寸 {', '.join(str(s[0]) for s in sizes)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
