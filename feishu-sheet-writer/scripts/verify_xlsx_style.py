#!/usr/bin/env python3
"""verify_xlsx_style.py —— 飞书表格导出后做「第三层校验」：样式 / 条件格式 / 数据验证 / 图片。

对飞书**只能写值、不能读样式**的补偿手段：
把线上表导出成 xlsx（node feishu.js export <ssToken> --out cur.xlsx），再用本脚本看
字体（尤其删除线）、条件格式、下拉验证、内嵌图片数量与实际值。

用法:
    python verify_xlsx_style.py cur.xlsx [工作表名] [--rows 3-12] [--cols ABCDEFGHI]

示例:
    python verify_xlsx_style.py cur.xlsx 待办事项清单 --rows 3-8
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

from openpyxl import load_workbook


def font_flags(font) -> str:
    flags = ("B" if font.bold else "") + ("I" if font.italic else "") + ("S" if font.strike else "")
    return f" [{flags}]" if flags else ""


def parse_span(text: str) -> tuple[int, int]:
    a, _, b = text.partition("-")
    return int(a), int(b or a)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx")
    ap.add_argument("sheet", nargs="?", default=None, help="工作表名，缺省取第一个")
    ap.add_argument("--rows", default="3-12", help="要检查的行区间，如 3-12")
    ap.add_argument("--cols", default="ABCDEFGHI", help="要检查的列，如 ABCDEFGHI")
    args = ap.parse_args()

    path = Path(args.xlsx)
    if not path.exists():
        print(f"找不到文件: {path}", file=sys.stderr)
        return 2

    wb = load_workbook(path)
    ws = wb[args.sheet] if args.sheet else wb.worksheets[0]
    r0, r1 = parse_span(args.rows)

    print(f"file    : {path}  ({path.stat().st_size:,} bytes)")
    print(f"sheet   : {ws.title}  | dims {ws.dimensions} | freeze {ws.freeze_panes}")
    print(f"sheets  : {wb.sheetnames}")

    # 1) 字体（删除线是历史事故点）
    print("\n[字体] 行 x 列 —— 关注 S(删除线)")
    for r in range(r0, r1 + 1):
        parts = []
        for col in args.cols:
            c = ws[f"{col}{r}"]
            parts.append(f"{col}{r}:{c.font.name} {c.font.sz}{font_flags(c.font)}")
        print("  " + " | ".join(parts))
    struck = [
        f"{col}{r}"
        for r in range(r0, r1 + 1)
        for col in args.cols
        if ws[f"{col}{r}"].font.strike
    ]
    print(f"  => 带删除线的单元格: {struck or '无'}")

    # 2) 条件格式
    print("\n[条件格式]")
    cfs = list(ws.conditional_formatting)
    if not cfs:
        print("  无")
    for rng in cfs:
        for rule in rng.rules:
            print(f"  {rng.sqref}: type={rule.type} formula={getattr(rule, 'formula', None)}")

    # 3) 数据验证
    print("\n[数据验证]")
    dvs = list(ws.data_validations.dataValidation)
    if not dvs:
        print("  无")
    for d in dvs:
        print(f"  {d.type} {d.formula1} -> {d.sqref}")

    # 4) 图片
    print("\n[内嵌图片]")
    for name in wb.sheetnames:
        imgs = getattr(wb[name], "_images", [])
        if imgs:
            print(f"  {name}: {len(imgs)} 张")
            for im in imgs:
                frm = getattr(im.anchor, "_from", None)
                pos = f"c{frm.col}r{frm.row}" if frm else "?"
                print(f"    - {pos} {round(im.width)}x{round(im.height)}")
    with zipfile.ZipFile(path) as z:
        media = [n for n in z.namelist() if n.startswith("xl/media/")]
        print(f"  xl/media 文件数: {len(media)} -> {[Path(m).name for m in media]}")

    # 5) 值（看公式有没有算出来 / 有没有被拍成静态）
    print("\n[单元格值]")
    for r in range(r0, min(r1, r0 + 6) + 1):
        row = [ws.cell(row=r, column=i).value for i in range(1, len(args.cols) + 1)]
        print(f"  R{r}: {row}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
