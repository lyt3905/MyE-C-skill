# -*- coding: utf-8 -*-
r"""
append_profit_row.py — 向 62店台账「运营利润统计表」追加一条订单记录
用法:
  python append_profit_row.py --file "C:/.../62店8月-采购登记表.xlsx" \
      --data '[1,"2026-08-10","1234567890","商品名",100,"200.00","20.00","",null,null,"刘宇彤",""]'

要点:
  - 12 列顺序: 序号,下单日期,订单编号,名字(商品规格),进货价格,平台预计可得(CNY),运费,
    平台其他扣费,利润,利润率,进货人,备注
  - 日期用字符串 "2026-08-10" 格式传入
  - 序号传 null 则自动计算(最后一行+1)
  - 利润(I列)和利润率(J列)传 null，脚本自动写入公式:
      I = ROUND(F-G-E-H, 2)
      J = ROUND(I/(G+E), 2)
  - 数据从 row 3 开始(row 1 标题, row 2 列名)
  - 保留 WPS 嵌入部件(cellimages/customStorage/sharedStrings)
"""
import argparse, json, os, sys, shutil, zipfile, re
from datetime import datetime


def parse_date(v):
    """将字符串日期转为 datetime，非字符串直接返回"""
    if isinstance(v, str) and v.strip():
        try:
            return datetime.fromisoformat(v.replace("Z", ""))
        except ValueError:
            return v
    return v


def backup_wps_parts(zip_path):
    """提取 WPS 特有部件，openpyxl 保存后会丢失，需要加回"""
    parts = {}
    try:
        z = zipfile.ZipFile(zip_path)
        for n in z.namelist():
            if n in (
                "xl/cellimages.xml", "xl/_rels/cellimages.xml.rels",
                "xl/customStorage/customStorage.xml",
                "xl/customStorage/_rels/customStorage.xml.rels",
                "xl/drawings/_rels/drawing1.xml.rels",
                "[Content_Types].xml", "xl/_rels/workbook.xml.rels",
                "xl/sharedStrings.xml", "xl/_rels/sharedStrings.xml.rels",
            ):
                parts[n] = z.read(n)
        for n in z.namelist():
            if n.startswith("xl/media/") and n not in parts:
                parts[n] = z.read(n)
        z.close()
    except Exception as e:
        print("警告: 提取 WPS 部件失败:", e)
    return parts


def restore_wps_parts(zip_path, parts):
    """把 WPS 部件写回保存后的文件，并修复注册"""
    items = {}
    z = zipfile.ZipFile(zip_path)
    for n in z.namelist():
        items[n] = z.read(n)
    z.close()

    # 1. 写回 cellimages / customStorage / sharedStrings
    for n in (
        "xl/cellimages.xml", "xl/_rels/cellimages.xml.rels",
        "xl/customStorage/customStorage.xml",
        "xl/customStorage/_rels/customStorage.xml.rels",
        "xl/sharedStrings.xml", "xl/_rels/sharedStrings.xml.rels",
    ):
        if n in parts:
            items[n] = parts[n]

    # 2. media: 合并
    for n, d in parts.items():
        if n.startswith("xl/media/") and n not in items:
            items[n] = d

    # 3. [Content_Types].xml: 补注册
    if "[Content_Types].xml" in parts:
        ct = parts["[Content_Types].xml"].decode("utf-8")
        if "cellimages" not in ct:
            ct = ct.replace(
                "</Types>",
                '<Override PartName="/xl/cellimages.xml" ContentType="application/vnd.wps-officedocument.cellimage+xml"/></Types>',
            )
        if "customStorage" not in ct:
            ct = ct.replace(
                "</Types>",
                '<Override PartName="/xl/customStorage/customStorage.xml" ContentType="application/vnd.wps-officedocument.customStorage+xml"/></Types>',
            )
        items["[Content_Types].xml"] = ct.encode("utf-8")

    # 4. workbook.xml.rels: 补 relationship
    if "xl/_rels/workbook.xml.rels" in parts:
        wr = parts["xl/_rels/workbook.xml.rels"].decode("utf-8")
        if "cellImage" not in wr and "cellimages" in parts:
            rid = "rId%d" % (len(re.findall(r'Id="rId\d+"', wr)) + 1)
            wr = wr.replace(
                "</Relationships>",
                f'<Relationship Id="{rid}" Type="http://www.wps.cn/officeDocument/2020/cellImage" Target="cellimages.xml"/></Relationships>',
            )
        if "customStorage" not in wr and "xl/customStorage/customStorage.xml" in parts:
            rid = "rId%d" % (len(re.findall(r'Id="rId\d+"', wr)) + 1)
            wr = wr.replace(
                "</Relationships>",
                f'<Relationship Id="{rid}" Type="http://www.wps.cn/officeDocument/2023/relationships/customStorage" Target="customStorage/customStorage.xml"/></Relationships>',
            )
        items["xl/_rels/workbook.xml.rels"] = wr.encode("utf-8")

    # 重写 zip
    tmp = zip_path + ".tmp"
    zout = zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED)
    for n, d in items.items():
        zout.writestr(n, d)
    zout.close()
    shutil.copy2(tmp, zip_path)
    try:
        os.remove(tmp)
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--row", type=int, default=None, help="行号(默认自动找下一空行)")
    ap.add_argument("--data", required=True, help="JSON 数组，12 个值")
    args = ap.parse_args()

    FILE = args.file
    if not os.path.exists(FILE):
        sys.exit(f"文件不存在: {FILE}")

    # 提取 WPS 部件(在 openpyxl 打开前)
    wps_parts = backup_wps_parts(FILE)

    import openpyxl
    from openpyxl.styles import Font, Alignment, Border, Side

    wb = openpyxl.load_workbook(FILE)
    ws = wb["运营利润统计表"]

    # 确定行号
    row = args.row
    if row is None:
        # 从 max_row 往回找最后一个非空行（跳过 row 1 标题 / row 2 列名）
        row = ws.max_row
        while row > 2 and all(
            ws.cell(row=row, column=c).value is None for c in range(1, 13)
        ):
            row -= 1
        row += 1
        if row < 3:
            row = 3

    data = json.loads(args.data)
    assert len(data) == 12, f"需要 12 个值，实际 {len(data)}"

    body_font = Font(name="微软雅黑", size=10)
    thin = Side(style="thin", color="B0B0B0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # 写入数据（跳过 I/J 公式列）
    COL_SEQ = 1   # A: 序号
    COL_DATE = 2  # B: 下单日期
    COL_ORDER = 3 # C: 订单编号
    COL_NAME = 4  # D: 商品规格
    COL_COST = 5  # E: 进货价格
    COL_INCOME = 6 # F: 平台预计可得
    COL_FREIGHT = 7 # G: 运费
    COL_FEE = 8   # H: 平台其他扣费
    COL_PROFIT = 9 # I: 利润（公式）
    COL_RATE = 10  # J: 利润率（公式）
    COL_BUYER = 11 # K: 进货人
    COL_REMARK = 12 # L: 备注

    # 写序号：如果传的是 null 则自动算
    seq = data[0]
    if seq is None or seq == "":
        seq = row - 2  # row 3 → 序号 1
    c = ws.cell(row=row, column=COL_SEQ, value=seq)
    c.font = body_font
    c.border = border
    c.alignment = center

    # 写数据列（跳过 I/J 公式列）
    data_cols = {
        COL_DATE: 1,
        COL_ORDER: 2,
        COL_NAME: 3,
        COL_COST: 4,
        COL_INCOME: 5,
        COL_FREIGHT: 6,
        COL_FEE: 7,
        COL_BUYER: 10,
        COL_REMARK: 11,
    }

    for col_idx, data_idx in data_cols.items():
        v = data[data_idx]
        v = parse_date(v)
        if v is None or v == "":
            v = None
        c = ws.cell(row=row, column=col_idx, value=v)
        c.font = body_font
        c.border = border
        c.alignment = center
        if isinstance(v, datetime):
            c.number_format = "yyyy-mm-dd"

    # 写公式：I列 利润 = ROUND(F-G-E-H, 2)
    profit_formula = f"=ROUND(F{row}-G{row}-E{row}-H{row},2)"
    c = ws.cell(row=row, column=COL_PROFIT, value=profit_formula)
    c.font = body_font
    c.border = border
    c.alignment = center

    # 写公式：J列 利润率 = ROUND(I/(G+E), 2)
    rate_formula = f"=ROUND(I{row}/(G{row}+E{row}),2)"
    c = ws.cell(row=row, column=COL_RATE, value=rate_formula)
    c.font = body_font
    c.border = border
    c.alignment = center

    wb.save(FILE)
    print(f"已写入第 {row} 行")

    # 加回 WPS 部件
    if wps_parts:
        restore_wps_parts(FILE, wps_parts)
        print("WPS 嵌入部件已保留")


if __name__ == "__main__":
    main()
