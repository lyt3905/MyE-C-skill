# -*- coding: utf-8 -*-
r"""
append_profit_row.py — 向 62店台账「运营利润统计表」追加订单记录（自动适配 12 列 / 13 列）

用法（推荐：按字段名传）:
  python append_profit_row.py --file "D:/E-c/台账/利润表/新利润表/62店10月利润表.xlsx" \
      --data '{"下单日期":"2026-10-08","订单编号":"3077286416392746","名字（商品规格）":"【1】 DK07 猩猩队长",
               "进货价格":128.51,"平台预计可得（CNY）":340.76,"运费":28.84,"进货渠道":"线上进货",
               "平台其他扣费":null,"进货人":null,"备注":"yu1 128.51"}'

用法（旧式：12 元素数组，仍兼容）:
  python append_profit_row.py --file "..." --data '[1,"2026-08-10","1234567890","商品名",100,"200.00","20.00","",null,null,"刘宇彤",""]'
  12 元素顺序: 序号,下单日期,订单编号,名字(商品规格),进货价格,平台预计可得(CNY),运费,平台其他扣费,利润,利润率,进货人,备注
  （序号/利润/利润率 三列脚本自己处理，传 null 即可）

要点:
  - **按 row 2 表头文字定位列**，不写死列号：
      9 月及以前 = 12 列（无「进货渠道」，利润/利润率在 I/J）
      10 月起     = 13 列（H 是「进货渠道」，利润/利润率在 J/K，平台其他扣费在 I）
    写死 12 列会把 10 月表的「进货渠道」当「平台其他扣费」、公式写进备注列——已在 2026-11 踩过。
  - 数据从 row 3 开始（row 1 标题、row 2 列名）
  - 利润/利润率：单元格已有公式则保留原样；空着才按本表列位补写
  - 写前自动备份到 --backup-dir，写后自动与备份逐格比对（新增行之前全部行 + 结构属性），有差异退出码 1
  - 新行样式默认继承上一行同列（字体/边框/填充/对齐/数字格式），行高也继承；--no-style 可关闭
  - 保留 WPS 嵌入部件（cellimages / customStorage / sharedStrings / media）
"""
import argparse, json, os, re, shutil, sys, zipfile
from datetime import datetime, date

# 表头文字 → 内部字段名（去空格/换行后匹配，允许前缀匹配以兼容「平台预计可得\n（CNY）」）
HEADER_MAP = {
    "序号": "seq",
    "下单日期": "date",
    "订单编号": "order",
    "名字（商品规格）": "name",
    "名字(商品规格)": "name",
    "商品规格": "name",
    "进货价格": "cost",
    "平台预计可得": "income",
    "运费": "freight",
    "进货渠道": "channel",
    "平台其他扣费": "fee",
    "利润": "profit",
    "利润率": "rate",
    "进货人": "buyer",
    "备注": "remark",
}

# 旧式 12 元素数组的位置映射（不含序号/利润/利润率）
LEGACY12 = ["seq", "date", "order", "name", "cost", "income", "freight", "fee", None, None, "buyer", "remark"]

FORMULA_COLS = {"profit", "rate"}


def field_of(name):
    """把用户给的字段名（可能是「平台预计可得（CNY）」这种带后缀的）归一成内部字段名"""
    n = norm(name)
    if not n:
        return None
    for key, field in HEADER_MAP.items():
        if n == norm(key):
            return field
    for key, field in HEADER_MAP.items():
        if n.startswith(norm(key)):
            return field
    return None


def norm(h):
    if h is None:
        return ""
    return re.sub(r"[\s\n\r]+", "", str(h))


def map_headers(ws):
    """读 row 2 表头，返回 {field: col_idx}

    两轮匹配：先全等（避免「利润」抢走「利润率」），再前缀（兼容「平台预计可得\\n（CNY）」）。
    """
    heads = {c: norm(ws.cell(row=2, column=c).value) for c in range(1, ws.max_column + 1)}
    cols = {}
    for c, h in heads.items():
        if not h:
            continue
        for key, field in HEADER_MAP.items():
            if h == norm(key):
                cols.setdefault(field, c)
                break
    for c, h in heads.items():
        if not h or c in cols.values():
            continue
        for key, field in HEADER_MAP.items():
            if h.startswith(norm(key)):
                cols.setdefault(field, c)
                break
    missing = [f for f in ("date", "order", "name", "cost", "income") if f not in cols]
    if missing:
        sys.exit(f"表头识别失败，缺少列: {missing}；row2 = {[ws.cell(2, c).value for c in range(1, ws.max_column + 1)]}")
    return cols


def col_letter(idx):
    s = ""
    while idx:
        idx, r = divmod(idx - 1, 26)
        s = chr(65 + r) + s
    return s


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

    for n in (
        "xl/cellimages.xml", "xl/_rels/cellimages.xml.rels",
        "xl/customStorage/customStorage.xml",
        "xl/customStorage/_rels/customStorage.xml.rels",
        "xl/sharedStrings.xml", "xl/_rels/sharedStrings.xml.rels",
    ):
        if n in parts:
            items[n] = parts[n]

    for n, d in parts.items():
        if n.startswith("xl/media/") and n not in items:
            items[n] = d

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


def parse_date(v):
    if isinstance(v, str) and v.strip():
        s = v.strip().replace("Z", "")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return v
    if isinstance(v, date) and not isinstance(v, datetime):
        return datetime(v.year, v.month, v.day)
    return v


def find_next_row(ws, cols):
    """找数据区末尾的下一行。

    ⚠️ 不能用 ws.max_row：这些台账的 J/K（利润/利润率）公式已预填到 ~490 行，
    所以「最后一个非空行」「整行全空」都靠不住。

    也不能靠「B 列是文字」判汇总行，因为 8 月表里有 **小节标题行**：
        row 286  B='预售'  C 空  →  但下面 row 287–293 还有 7 行真实数据
    按文字判会把「预售」误判成汇总行、拒绝写入。

    可靠做法：以「最后一个订单编号非空的行」为锚点。
      last = 最后一个 order 非空的行
      cand = last + 1
      若 cand 的非公式列全空 → 就是它
      若 cand 有内容（说明紧贴着汇总行/标题行，中间没空行）→ 报错，让用户先插一空行
    已验证：8月表 last=293 → 294；10月表 last=144 → 145；9月表 last=192 → 193。
    """
    order_col = cols.get("order")
    if not order_col:
        sys.exit("表头里找不到「订单编号」列，无法定位数据区末尾")
    # 可写列（排除公式列 seq/profit/rate——A 列 `=ROW()-2` 永远"非空"，J/K 预填到 490 行）
    check_cols = [c for f, c in cols.items() if f not in FORMULA_COLS and f != "seq"]

    last = 2
    for r in range(3, ws.max_row + 1):
        if ws.cell(row=r, column=order_col).value not in (None, ""):
            last = r
    cand = last + 1
    if cand <= 2:
        return 3
    occupied = [c for c in check_cols if ws.cell(row=cand, column=c).value not in (None, "")]
    if occupied:
        letters = ", ".join(col_letter(c) for c in occupied)
        sys.exit(
            f"⚠️ 数据区末尾（第 {last} 行，最后一个订单编号）下面第 {cand} 行已经有内容（{letters} 列非空），"
            f"多半是汇总行或小节标题，中间没有空行。\n"
            f"   请先在 WPS/Excel 里第 {cand} 行上方插入一空行，再重跑本脚本；"
            f"或用 --row 明确指定行号。"
        )
    return cand


def cell_sig(cell, include_format=True):
    parts = [repr(cell.value) if cell.value not in (None, "") else "EMPTY"]
    if include_format:
        f = cell.font
        parts.append(f"{f.name}|{f.size}|{f.bold}|{str(f.color.rgb) if f.color else None}")
        fill = cell.fill
        if fill and fill.fgColor:
            parts.append(f"fill:{str(fill.fgColor.rgb)}")
        b = cell.border
        parts.append(f"border:{b.left.style}|{b.right.style}|{b.top.style}|{b.bottom.style}")
        a = cell.alignment
        parts.append(f"align:{a.horizontal}|{a.vertical}|{a.wrap_text}")
        parts.append(f"numfmt:{cell.number_format}")
    return "|".join(parts)


def verify(backup, main, sheet, row):
    """新增行之前的所有行 + 结构属性逐格比对"""
    import openpyxl
    wb_bak = openpyxl.load_workbook(backup)
    wb_new = openpyxl.load_workbook(main)
    ws_b, ws_n = wb_bak[sheet], wb_new[sheet]
    diffs = []
    max_cmp = min(ws_b.max_row, ws_n.max_row, row - 1)
    ncol = max(ws_b.max_column, ws_n.max_column)
    for r in range(1, max_cmp + 1):
        for c in range(1, ncol + 1):
            s1 = cell_sig(ws_b.cell(r, c))
            s2 = cell_sig(ws_n.cell(r, c))
            if s1 != s2:
                diffs.append(f"  R{r}C{c}: 备份={s1}  新={s2}")
    props = lambda ws: (ws.freeze_panes, ws.auto_filter.ref,
                        str(sorted(str(m) for m in ws.merged_cells.ranges)),
                        ws.sheet_format.defaultRowHeight)
    if props(ws_b) != props(ws_n):
        diffs.append(f"  结构属性: 备份={props(ws_b)} 新={props(ws_n)}")
    for col in set(list(ws_b.column_dimensions.keys()) + list(ws_n.column_dimensions.keys())):
        if ws_b.column_dimensions[col].width != ws_n.column_dimensions[col].width:
            diffs.append(f"  列宽 {col}: 备份={ws_b.column_dimensions[col].width} 新={ws_n.column_dimensions[col].width}")
    dv_b = sorted(str(dv.sqref) for dv in ws_b.data_validations.dataValidation)
    dv_n = sorted(str(dv.sqref) for dv in ws_n.data_validations.dataValidation)
    if dv_b != dv_n:
        diffs.append(f"  数据验证: 备份={dv_b} 新={dv_n}")
    if diffs:
        print(f"❌ 校验失败，发现 {len(diffs)} 处差异（已有内容被改动）:")
        for d in diffs[:50]:
            print(d)
        return False
    print(f"✅ 校验通过: 除新增 R{row} 外，其余内容与备份完全一致")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--sheet", default="运营利润统计表")
    ap.add_argument("--row", type=int, default=None, help="行号（默认自动找下一空行）")
    ap.add_argument("--data", default=None, help="JSON 对象（按字段名）或数组")
    ap.add_argument("--data-file", default=None, help="从 UTF-8 JSON 文件读 --data（PowerShell 下双引号会被吞，推荐用这个）")
    ap.add_argument("--backup-dir", default=r"C:\Users\shana\Desktop\62店台账备份\利润表备份")
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--no-style", action="store_true", help="不继承上一行样式")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()

    FILE = args.file
    if not os.path.exists(FILE):
        sys.exit(f"文件不存在: {FILE}")
    if os.path.exists(os.path.join(os.path.dirname(FILE), "~$" + os.path.basename(FILE))):
        sys.exit("⚠️ 检测到 WPS/Excel 锁文件（~$…），请先关闭该表格再写入，否则会写坏或写入被覆盖")

    # 1) 备份
    backup = None
    if not args.no_backup:
        os.makedirs(args.backup_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = os.path.splitext(os.path.basename(FILE))[0]
        backup = os.path.join(args.backup_dir, f"{stem}_{ts}_before_append.xlsx")
        shutil.copy2(FILE, backup)
        print("备份:", backup)

    wps_parts = backup_wps_parts(FILE)

    import openpyxl
    from copy import copy
    from openpyxl.styles import Font, Alignment, Border, Side

    wb = openpyxl.load_workbook(FILE)
    ws = wb[args.sheet]
    cols = map_headers(ws)
    print("列定位:", {k: f"{col_letter(v)}({v})" for k, v in sorted(cols.items(), key=lambda x: x[1])})

    # 4) 行号
    row = args.row
    if row is None:
        row = find_next_row(ws, cols)

    # 3) 解析 --data
    if args.data_file:
        # utf-8-sig：PowerShell 的 Out-File -Encoding utf8 会写 BOM，普通 utf-8 读会报
        # json.decoder.JSONDecodeError: Unexpected UTF-8 BOM (decode using utf-8-sig)
        with open(args.data_file, encoding="utf-8-sig") as f:
            raw = json.load(f)
    elif args.data:
        try:
            raw = json.loads(args.data)
        except json.JSONDecodeError:
            # 兼容 PowerShell 把双引号吞掉后传进来的 {a:b} 形态
            fixed = re.sub(r"([{,]\s*)([^\s\"'{},:\[\]]+)(\s*:)", r'\1"\2"\3', args.data)
            raw = json.loads(fixed)
    else:
        sys.exit("必须提供 --data 或 --data-file")
    if isinstance(raw, dict):
        vals = {}
        unknown = []
        for k, v in raw.items():
            f = field_of(k)
            if f is None:
                unknown.append(k)
            else:
                vals[f] = v
        if unknown:
            sys.exit(f"⚠️ 无法识别的字段名: {unknown}\n"
                     f"   本表实际表头: {[ws.cell(2, c).value for c in range(1, ws.max_column + 1)]}\n"
                     f"   可用字段: {sorted(HEADER_MAP)}")
        # 本表没有的列（例如 9 月表没有「进货渠道」）只提示，不中断
        extra = [f for f in vals if f not in cols and f not in FORMULA_COLS]
        if extra:
            print(f"⚠️ 本表没有这些列，已跳过: {extra}")
    else:
        writable = [f for f, _ in sorted(cols.items(), key=lambda x: x[1]) if f != "seq" and f not in FORMULA_COLS]
        if len(raw) == 12:
            vals = {LEGACY12[i]: raw[i] for i in range(12) if LEGACY12[i]}
            vals.pop("seq", None)
        elif len(raw) == len(writable):
            vals = dict(zip(writable, raw))
        else:
            sys.exit(f"--data 数组长度 {len(raw)} 无法匹配：本表可写列 {len(writable)} 个 {writable}，或传 12 元素旧格式")

    # 4) 写入
    default_font = Font(name="微软雅黑", size=10)
    thin = Side(style="thin", color="B0B0B0")
    default_border = Border(left=thin, right=thin, top=thin, bottom=thin)
    default_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for field, col in cols.items():
        if field == "seq" or field in FORMULA_COLS:
            continue
        if field not in vals:
            continue
        v = vals[field]
        v = parse_date(v) if field == "date" else v
        if isinstance(v, str) and v.strip() == "":
            v = None
        cell = ws.cell(row=row, column=col, value=v)
        if not args.no_style:
            prev = ws.cell(row=row - 1, column=col) if row > 3 else None
            if prev is not None and (prev.has_style):
                cell._style = copy(prev._style)
            else:
                cell.font, cell.border, cell.alignment = default_font, default_border, default_align
        if isinstance(v, datetime) and not (not args.no_style and row > 3 and ws.cell(row=row - 1, column=col).number_format not in ("General",)):
            cell.number_format = "yyyy-mm-dd"

    # 序号
    if "seq" in cols:
        sc = ws.cell(row=row, column=cols["seq"])
        if sc.value in (None, ""):
            sc.value = "=ROW()-2"
            if not args.no_style and row > 3 and ws.cell(row=row - 1, column=cols["seq"]).has_style:
                sc._style = copy(ws.cell(row=row - 1, column=cols["seq"])._style)

    # 利润 / 利润率（已有公式就保留）
    L = {f: col_letter(c) for f, c in cols.items()}
    if "profit" in cols:
        pc = ws.cell(row=row, column=cols["profit"])
        if pc.value in (None, ""):
            if "fee" in cols:
                pc.value = f"=IF(COUNTA(B{row}:I{row})=0,\"\",ROUND(F{row}-G{row}-E{row}-{L['fee']}{row},2))" if "channel" in cols \
                    else f"=IF(COUNTA(B{row}:H{row})=0,\"\",ROUND(F{row}-G{row}-E{row}-{L['fee']}{row},2))"
            else:
                pc.value = f"=ROUND(F{row}-G{row}-E{row},2)"
            if not args.no_style and row > 3 and ws.cell(row=row - 1, column=cols["profit"]).has_style:
                pc._style = copy(ws.cell(row=row - 1, column=cols["profit"])._style)
    if "rate" in cols:
        rc = ws.cell(row=row, column=cols["rate"])
        if rc.value in (None, ""):
            rc.value = f"=IFERROR(ROUND({L['profit']}{row}/(G{row}+E{row}),2),\"\")"
            if not args.no_style and row > 3 and ws.cell(row=row - 1, column=cols["rate"]).has_style:
                rc._style = copy(ws.cell(row=row - 1, column=cols["rate"])._style)

    # 行高继承
    if not args.no_style and row > 3:
        prev_h = ws.row_dimensions[row - 1].height
        if prev_h:
            ws.row_dimensions[row].height = prev_h

    wb.save(FILE)
    print(f"已写入第 {row} 行")

    if wps_parts:
        restore_wps_parts(FILE, wps_parts)
        print("WPS 嵌入部件已保留")

    # 5) 回读
    wb2 = openpyxl.load_workbook(FILE)
    ws2 = wb2[args.sheet]
    back = {f: ws2.cell(row=row, column=c).value for f, c in cols.items()}
    print("回读:", back)

    # 6) 校验
    if backup and not args.no_verify:
        if not verify(backup, FILE, args.sheet, row):
            sys.exit(1)


if __name__ == "__main__":
    main()
