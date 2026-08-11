# -*- coding: utf-8 -*-
"""
verify_unchanged.py — 验证主文件与写入前备份一致（除新增行外）

用法:
  python verify_unchanged.py --backup "备份.xlsx" --file "主文件.xlsx" --row 19

对比范围:
  - 除新增行（--row）外，所有已存在行的单元格值、公式
  - 表头（row 1-2）
  - 单元格格式（字体/边框/填充/对齐）
  - 列宽、行高（sheet 默认行高）
  - 冻结窗格、自动筛选、合并单元格
  - 数据验证（下拉框）

输出: 有差异则打印差异明细并以退出码 1 结束；无差异打印 OK。
"""
import argparse, sys
import openpyxl


def cell_sig(cell, include_format=True):
    """生成单元格签名（值+公式+格式）"""
    parts = [repr(cell.value)]
    if include_format:
        f = cell.font
        fill = cell.fill
        parts.append(f"{f.name}|{f.size}|{f.bold}|{f.color.rgb if f.color else None}")
        if fill and fill.fgColor:
            parts.append(f"fill:{fill.fgColor.rgb}")
        b = cell.border
        parts.append(f"border:{b.left.style}|{b.right.style}|{b.top.style}|{b.bottom.style}")
        a = cell.alignment
        parts.append(f"align:{a.horizontal}|{a.vertical}|{a.wrap_text}")
        nf = cell.number_format
        parts.append(f"numfmt:{nf}")
    return "|".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backup", required=True, help="写入前的备份文件")
    ap.add_argument("--file", required=True, help="写入后的主文件")
    ap.add_argument("--sheet", default="运营利润统计表")
    ap.add_argument("--row", type=int, required=True, help="本次新增的行号")
    ap.add_argument("--no-format", action="store_true", help="只对比值，不对比格式")
    args = ap.parse_args()

    wb_bak = openpyxl.load_workbook(args.backup)
    wb_new = openpyxl.load_workbook(args.file)

    if args.sheet not in wb_bak.sheetnames:
        sys.exit(f"备份文件无 sheet: {args.sheet}")
    if args.sheet not in wb_new.sheetnames:
        sys.exit(f"主文件无 sheet: {args.sheet}")

    ws_bak = wb_bak[args.sheet]
    ws_new = wb_new[args.sheet]

    include_format = not args.no_format
    diffs = []

    # 1. 对比表头 + 新增行之前的所有行（row 1 .. row-1）
    max_cmp = min(ws_bak.max_row, ws_new.max_row, args.row - 1)
    for r in range(1, max_cmp + 1):
        for c in range(1, max(ws_bak.max_column, ws_new.max_column) + 1):
            s_bak = cell_sig(ws_bak.cell(r, c), include_format)
            s_new = cell_sig(ws_new.cell(r, c), include_format)
            if s_bak != s_new:
                diffs.append(f"  R{r}C{c}: 备份={s_bak}  新={s_new}")

    # 2. 对比结构属性
    def sheet_props(ws):
        return (
            ws.freeze_panes,
            ws.auto_filter.ref,
            str(sorted(str(m) for m in ws.merged_cells.ranges)),
            ws.sheet_format.defaultRowHeight,
        )

    if sheet_props(ws_bak) != sheet_props(ws_new):
        diffs.append(f"  结构属性: 备份={sheet_props(ws_bak)} 新={sheet_props(ws_new)}")

    # 3. 列宽
    for col in set(list(ws_bak.column_dimensions.keys()) + list(ws_new.column_dimensions.keys())):
        w_bak = ws_bak.column_dimensions[col].width
        w_new = ws_new.column_dimensions[col].width
        if w_bak != w_new:
            diffs.append(f"  列宽 {col}: 备份={w_bak} 新={w_new}")

    # 4. 数据验证（下拉框）
    dv_bak = sorted(str(dv.sqref) for dv in ws_bak.data_validations.dataValidation)
    dv_new = sorted(str(dv.sqref) for dv in ws_new.data_validations.dataValidation)
    if dv_bak != dv_new:
        diffs.append(f"  数据验证: 备份={dv_bak} 新={dv_new}")

    if diffs:
        print(f"❌ 发现 {len(diffs)} 处差异（可能影响已有内容）:")
        for d in diffs[:50]:
            print(d)
        sys.exit(1)
    else:
        print(f"✅ OK: 除新增行 R{args.row} 外，其余内容与备份完全一致")


if __name__ == "__main__":
    main()
