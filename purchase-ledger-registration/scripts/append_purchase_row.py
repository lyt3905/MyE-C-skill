# -*- coding: utf-8 -*-
"""
append_purchase_row.py — 向 62店采购台账的「自发货采购登记表」追加一条采购记录
用法:
  python append_purchase_row.py --file "C:\...\62店8月-采购登记表.xlsx" \
      --row 4 \
      --data '[1,"2026-08-01T10:49:36",null,"备货进货","变形金刚","商品名","闲鱼",1,170,170,"刘宇彤","亲情卡",170,"2026-08-01T10:49:36","2026-08-04T10:49:36",null,null,null,"2026-08-04T10:49:36","刘宇彤"]' \
      [--img-prod "产品图.jpg"] [--img-self-pay "垫付截图.jpg"] [--img-pay "财务图.jpg"] [--row-height 334]

要点:
  - 20 列顺序: 序号,采购日期,企业微信审批编号,采购类别,系列,名字(商品规格),单位,采购数量,单价(元),
    合计金额(元),进货人,付款方式,付款金额,付款日期,预计到货日期,产品图片,自行垫付支付截图,
    财务付款截图,实际入库日期,收货人
  - 日期字符串用 ISO 格式 "2026-08-01T10:49:36" 会被转成 datetime
  - 图片列不写值,由 --img-prod/--img-self-pay/--img-pay 插入浮动图(oneCellAnchor, 200x445px):
      --img-prod      → P 列(产品图片)
      --img-self-pay  → Q 列(自行垫付支付截图,如微信支付账单)
      --img-pay       → R 列(财务付款截图)
  - 自动保留 WPS 的 cellimages.xml(用户手动嵌入的图) —— openpyxl 保存会丢,脚本会在保存后加回
  - 若文件被预览面板/WPS 锁定,保存会 PermissionError,需先请用户关闭
"""
import argparse, json, os, sys, shutil, zipfile, re, tempfile
from datetime import datetime

def parse_date(v):
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", ""))
        except ValueError:
            return v
    return v

def backup_wps_parts(zip_path):
    """提取 WPS 特有部件,openpyxl 保存后会丢失,需要加回"""
    parts = {}
    try:
        z = zipfile.ZipFile(zip_path)
        names = z.namelist()
        for n in names:
            if n in ("xl/cellimages.xml", "xl/_rels/cellimages.xml.rels",
                     "xl/customStorage/customStorage.xml",
                     "xl/customStorage/_rels/customStorage.xml.rels",
                     "xl/drawings/_rels/drawing1.xml.rels",
                     "[Content_Types].xml", "xl/_rels/workbook.xml.rels",
                     "xl/sharedStrings.xml", "xl/_rels/sharedStrings.xml.rels"):
                parts[n] = z.read(n)
        # 图片 media 也要保留(openpyxl 会保留自己插入的,但原嵌入图 media 可能被当孤儿删除)
        for n in names:
            if n.startswith("xl/media/") and n not in parts:
                parts[n] = z.read(n)
        z.close()
    except Exception as e:
        print("警告: 提取 WPS 部件失败:", e)
    return parts

def restore_wps_parts(zip_path, parts):
    """把 WPS 部件写回保存后的文件,并修复注册"""
    items = {}
    z = zipfile.ZipFile(zip_path)
    for n in z.namelist():
        items[n] = z.read(n)
    z.close()

    # 1. 写回 cellimages / customStorage / sharedStrings / media
    for n in ("xl/cellimages.xml", "xl/_rels/cellimages.xml.rels",
              "xl/customStorage/customStorage.xml",
              "xl/customStorage/_rels/customStorage.xml.rels",
              "xl/sharedStrings.xml", "xl/_rels/sharedStrings.xml.rels"):
        if n in parts:
            items[n] = parts[n]

    # 2. media: 合并(保留原嵌入图 + openpyxl 新插入的图)
    for n, d in parts.items():
        if n.startswith("xl/media/") and n not in items:
            items[n] = d

    # 3. [Content_Types].xml: 补 cellimages / customStorage Override
    if "[Content_Types].xml" in parts:
        ct = parts["[Content_Types].xml"].decode("utf-8")
        if "cellimages" not in ct:
            ct = ct.replace("</Types>",
                '<Override PartName="/xl/cellimages.xml" ContentType="application/vnd.wps-officedocument.cellimage+xml"/></Types>')
        if "customStorage" not in ct:
            ct = ct.replace("</Types>",
                '<Override PartName="/xl/customStorage/customStorage.xml" ContentType="application/vnd.wps-officedocument.customStorage+xml"/></Types>')
        items["[Content_Types].xml"] = ct.encode("utf-8")

    # 4. workbook.xml.rels: 补 cellImage / customStorage relationship
    if "xl/_rels/workbook.xml.rels" in parts:
        wr = parts["xl/_rels/workbook.xml.rels"].decode("utf-8")
        if "cellImage" not in wr and "cellimages" in parts:
            rid = "rId%d" % (len(re.findall(r'Id="rId\d+"', wr)) + 1)
            wr = wr.replace("</Relationships>",
                f'<Relationship Id="{rid}" Type="http://www.wps.cn/officeDocument/2020/cellImage" Target="cellimages.xml"/></Relationships>')
        if "customStorage" not in wr and "xl/customStorage/customStorage.xml" in parts:
            rid = "rId%d" % (len(re.findall(r'Id="rId\d+"', wr)) + 1)
            wr = wr.replace("</Relationships>",
                f'<Relationship Id="{rid}" Type="http://www.wps.cn/officeDocument/2023/relationships/customStorage" Target="customStorage/customStorage.xml"/></Relationships>')
        items["xl/_rels/workbook.xml.rels"] = wr.encode("utf-8")

    # 重写 zip
    tmp = zip_path + ".tmp"
    zout = zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED)
    for n, d in items.items():
        zout.writestr(n, d)
    zout.close()
    # 用 copy2 覆盖(沙箱/文件占用下 os.replace 可能失败, copy2 更稳)
    shutil.copy2(tmp, zip_path)
    try:
        os.remove(tmp)
    except OSError:
        pass

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--row", type=int, default=None, help="行号(默认自动找下一空行)")
    ap.add_argument("--data", required=True, help="JSON 数组,20 个值")
    ap.add_argument("--img-prod", default=None, help="产品图片(插入 P 列)")
    ap.add_argument("--img-pay", default=None, help="财务付款截图(插入 R 列)")
    ap.add_argument("--img-self-pay", default=None, help="自行垫付支付截图(插入 Q 列)")
    ap.add_argument("--row-height", type=float, default=334)
    args = ap.parse_args()

    FILE = args.file
    if not os.path.exists(FILE):
        sys.exit(f"文件不存在: {FILE}")

    # 提取 WPS 部件(在 openpyxl 打开前)
    wps_parts = backup_wps_parts(FILE)

    import openpyxl
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Font, Alignment, Border, Side

    wb = openpyxl.load_workbook(FILE)
    ws = wb["自发货采购登记表"]

    row = args.row
    if row is None:
        row = ws.max_row + 1
        while row > 1 and all(ws.cell(row=row, column=c).value is None
                              for c in range(1, 21)):
            row -= 1
        row += 1

    data = json.loads(args.data)
    assert len(data) == 20, f"需要20个值,实际{len(data)}"

    body_font = Font(name="微软雅黑", size=10)
    thin = Side(style="thin", color="B0B0B0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for i, v in enumerate(data, 1):
        v = parse_date(v)
        c = ws.cell(row=row, column=i, value=v)
        c.font = body_font
        c.border = border
        c.alignment = center
        if isinstance(v, datetime):
            c.number_format = "yyyy-mm-dd hh:mm"

    # 若指定了 --row，先清除该行已有浮动图，避免重复叠加
    if args.row is not None:
        target_row_0based = row - 1
        ws._images = [img for img in ws._images
                      if not (hasattr(img, "anchor")
                              and hasattr(img.anchor, "_from")
                              and getattr(img.anchor._from, "row", None) == target_row_0based)]

    # 插入浮动图
    if args.img_prod:
        img = XLImage(args.img_prod)
        img.width, img.height = 200, 445
        ws.add_image(img, f"P{row}")
    if args.img_self_pay:
        img = XLImage(args.img_self_pay)
        img.width, img.height = 200, 445
        ws.add_image(img, f"Q{row}")
    if args.img_pay:
        img = XLImage(args.img_pay)
        img.width, img.height = 200, 445
        ws.add_image(img, f"R{row}")

    ws.row_dimensions[row].height = args.row_height

    wb.save(FILE)
    print(f"已写入第 {row} 行")

    # 加回 WPS 部件
    if wps_parts:
        restore_wps_parts(FILE, wps_parts)
        print("WPS 嵌入部件(cellimages)已保留")

if __name__ == "__main__":
    main()
