# -*- coding: utf-8 -*-
"""
verify_ledger.py — 62店采购台账「写入后统一验证」（2026-09-04 防呆加固）

用法:
  python verify_ledger.py <台账.xlsx> [--sheet 自发货采购登记表] [--expect row,col,srcfile]...

  --expect 可多次传入，含义：Excel 行号,Excel列号,源图路径
          校验该行该列展示的图片与源图 md5 完全一致（拦截"张冠李戴/插反"）。
          自动兼容两种存储：浮动锚点(drawing1.xml) 与 WPS 嵌入图(DISPIMG/cellimages)。
          例: --expect 37,18,"C:/.../支付宝账单-524.00.png"
  --sheet  默认 自发货采购登记表

校验项:
  1. 序号列(col1)从 1 起严格连续递增、无中间空行
  2. 浮动锚点(drawing1.xml): 列必须在 P/Q/R (Excel 16/17/18, 0-based 15/16/17),
     无 14/16 错位; 每个 r:embed 的 rId 都能经 rels 解析且 media 文件真实存在
  3. --expect 指定的 (行,列): 该处图片 media md5 必须 == 源图 md5
     (浮动锚点或 DISPIMG 嵌入图两种存储都支持)
  4. WPS 嵌入图(cellimages.xml): 每个 rel 的 Target media 存在; 每个 DISPIMG
     公式引用的图片名都能映射到 rId 且 rel/media 齐全
  5. 浮动图媒体名与 cellimages 媒体名无重名冲突(防 openpyxl 覆盖 bug 复发)
  6. 含 DISPIMG 公式的单元格只能位于 P/Q/R 列 (Excel 16/17/18)

退出码: 0=全部通过; 1=存在 FAIL(此时台账不应交付/应回滚)
"""
import sys, os, re, hashlib, zipfile, argparse
sys.stdout.reconfigure(encoding='utf-8')

# ---- 列定义 ----
COL_SEQ = 1          # 序号
COL_P, COL_Q, COL_R = 16, 17, 18   # 产品图片 / 垫付截图 / 财务付款截图 (Excel 列号)
ALLOWED_IMG_COLS = {COL_P, COL_Q, COL_R}
DISPIMG_PREFIX = '=_xlfn.DISPIMG'

def md5b(b):
    return hashlib.md5(b).hexdigest()

def parse_rels(xml):
    """兼容 Id 在前 / Target 在前两种属性顺序"""
    m = {}
    for rel in re.findall(r'<Relationship\b[^>]*/?>', xml):
        i = re.search(r'Id="([^"]+)"', rel)
        t = re.search(r'Target="([^"]+)"', rel)
        if i and t:
            m[i.group(1)] = t.group(1)
    return m

def norm_media(t):
    b = t.replace('../', '').lstrip('/')
    return b if b.startswith('xl/') else 'xl/' + b

def get_dispimg_id(v):
    """单元格值为 DISPIMG 公式时返回图片 ID，否则 None"""
    if isinstance(v, str) and v.strip().startswith(DISPIMG_PREFIX):
        m = re.search(r'"((?:ID_)?[0-9A-Fa-f]+)"', v)
        return m.group(1) if m else v.strip()
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('file')
    ap.add_argument('--sheet', default='自发货采购登记表')
    ap.add_argument('--expect', action='append', default=[])
    args = ap.parse_args()

    fp = args.file
    if not os.path.exists(fp):
        print(f'FAIL 文件不存在: {fp}'); sys.exit(1)

    results = []
    def check(ok, msg):
        results.append((ok, msg))
        print(('OK  ' if ok else 'FAIL') + ' ' + msg)

    # ---------- zip 层 ----------
    z = zipfile.ZipFile(fp)
    names = set(z.namelist())
    draw_names = sorted(n for n in names if re.match(r'xl/drawings/drawing\d+\.xml$', n))
    media_names = [n for n in names if n.startswith('xl/media/') and not n.endswith('/')]
    cellimage_present = 'xl/cellimages.xml' in names
    drawing_present = bool(draw_names)

    # --- 浮动锚点 ---
    n_anchors = 0
    bad_col = []
    missing_rel_media = []
    anchor_map = {}   # (excel_row, excel_col) -> media_path
    float_media = set()
    for dn in draw_names:
        d = z.read(dn).decode('utf-8')
        # zip 内路径是正斜杠，Windows 下 os.path.join 会产生反斜杠导致匹配失败
        parts = dn.rsplit('/', 1)
        rels_f = parts[0] + '/_rels/' + parts[1] + '.rels' if len(parts) == 2 else '_rels/' + dn + '.rels'
        drels = parse_rels(z.read(rels_f).decode('utf-8')) if rels_f in names else {}
        for t in drels.values():
            float_media.add(norm_media(t))
        for a in re.findall(r'<(?:\w+:)?oneCellAnchor>.*?</(?:\w+:)?oneCellAnchor>', d, re.S):
            m_col = re.search(r'<(?:xdr:)?col>(\d+)</(?:xdr:)?col>', a)
            m_row = re.search(r'<(?:xdr:)?row>(\d+)</(?:xdr:)?row>', a)
            m_emb = re.search(r'r:embed="(rId\d+)"', a)
            if not (m_col and m_row and m_emb):
                continue
            col0, row0, rid = int(m_col.group(1)), int(m_row.group(1)), m_emb.group(1)
            n_anchors += 1
            if col0 + 1 not in ALLOWED_IMG_COLS:
                bad_col.append((row0 + 1, col0 + 1))
            if rid in drels:
                media = norm_media(drels[rid])
                if media not in names:
                    missing_rel_media.append((row0 + 1, rid, media))
                anchor_map[(row0 + 1, col0 + 1)] = media
            else:
                missing_rel_media.append((row0 + 1, rid, None))
    check(not bad_col, f'浮动锚点列均在 P/Q/R({sorted(ALLOWED_IMG_COLS)}), 共 {n_anchors} 个'
          + (f'; 错位列: {bad_col}' if bad_col else ''))
    check(not missing_rel_media, f'锚点 rId→media 全部存在'
          + (f'; 缺失: {missing_rel_media}' if missing_rel_media else ''))

    # --- cellimages 嵌入图 ---
    cirels = {}
    cell_name2rid = {}   # 图片名(ID_xxx) -> rId
    n_ci = 0
    if cellimage_present:
        cirl_f = 'xl/_rels/cellimages.xml.rels'
        cirels = parse_rels(z.read(cirl_f).decode('utf-8')) if cirl_f in names else {}
        ci = z.read('xl/cellimages.xml').decode('utf-8')
        n_ci = len(re.findall(r'<(?:\w+:)?cellImage[ >]', ci))
        for seg in re.split(r'<(?:\w+:)?cellImage[ >]', ci)[1:]:
            m_name = re.search(r'name="([^"]+)"', seg)
            m_emb = re.search(r'r:embed="(rId\d+)"', seg)
            if m_name and m_emb:
                cell_name2rid[m_name.group(1)] = m_emb.group(1)
        miss = [(rid, norm_media(t)) for rid, t in cirels.items() if norm_media(t) not in names]
        check(not miss, f'cellimages 嵌入图 rels→media 完整 ({n_ci} 个 cellImage, {len(cirels)} rels, '
              f'{len(cell_name2rid)} 可解析名称)' + (f'; 缺失: {miss}' if miss else ''))
        cell_media = {norm_media(t) for t in cirels.values()}
    else:
        cell_media = set()
        if not drawing_present:
            check(False, '既无 cellimages 也无 drawing，文件可能丢失全部图片')
        else:
            check(True, '纯浮动图模式(无 cellimages)，跳过嵌入图检查')

    # --- media 重名冲突 ---
    clash = sorted(float_media & cell_media)
    check(not clash, '浮动图与嵌入图 media 无重名冲突'
          + (f'; 冲突: {clash}' if clash else ''))

    # ---------- 数据层 (序号 / DISPIMG 列位 / expect 溯源) ----------
    from openpyxl import load_workbook
    wb = load_workbook(fp, read_only=True, data_only=False)
    ws = wb[args.sheet]

    seqs = []
    dispimg_bad_col = []
    dispimg_cell = {}    # (row, col) -> dispimg 图片名
    for r in range(2, ws.max_row + 1):
        v_seq = ws.cell(r, COL_SEQ).value
        if isinstance(v_seq, (int, float)) and not isinstance(v_seq, bool):
            seqs.append((r, int(v_seq)))
        elif v_seq not in (None, ''):
            seqs.append((r, v_seq))
        for c in range(1, 21):
            v = ws.cell(r, c).value
            did = get_dispimg_id(v) if c in (15, 16, 17, 18, 19) else None
            if did:
                if c not in ALLOWED_IMG_COLS:
                    dispimg_bad_col.append((r, c))
                dispimg_cell[(r, c)] = did

    if seqs:
        nums = [s[1] for s in seqs]
        if nums == list(range(1, len(nums) + 1)) and all(isinstance(x, int) for x in nums):
            check(True, f'序号 1..{nums[-1]} 严格连续 ({len(nums)} 行, 末行 row{seqs[-1][0]})')
        else:
            check(False, f'序号不连续或非纯数字: {nums[:20]}... (末行 row{seqs[-1][0]})')
    else:
        check(True, '无数据行(仅表头)')

    # --- 数量×单价=合计 (H×I=J) ---
    bad_hij = []
    for r in range(2, ws.max_row + 1):
        name = ws.cell(r, 6).value
        if name in (None, ''):
            continue
        h = ws.cell(r, 8).value
        i = ws.cell(r, 9).value
        j = ws.cell(r, 10).value
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (h, i, j)):
            bad_hij.append((r, h, i, j, '非数字'))
            continue
        if abs(h * i - j) > 0.02:  # 0.02 容差吸收单价两位小数的四舍五入尾差（如 3×66.7 vs 200.11）
            bad_hij.append((r, h, i, j, f'H×I={round(h*i,2)}'))
    check(not bad_hij, '数量×单价=合计 (H×I=J)'
          + ('; 不等: ' + str(bad_hij[:5]) if bad_hij else ''))

    check(not dispimg_bad_col, f'DISPIMG 嵌入图单元格均在 P/Q/R 列'
          + (f'; 错位: {dispimg_bad_col}' if dispimg_bad_col else ''))

    # --- expect 溯源 (浮动锚点优先, 否则 DISPIMG) ---
    for e in args.expect:
        parts = [p.strip() for p in e.split(',', 2)]
        if len(parts) != 3:
            check(False, f'--expect 格式应为 row,col,srcfile: {e}')
            continue
        row_e, col_e = int(parts[0]), int(parts[1])
        src = parts[2].strip('"')
        lbl = f'row{row_e} col{col_e}(' + ('PQR'[col_e - 16] if col_e in (16, 17, 18) else '?') + ')'
        media = anchor_map.get((row_e, col_e))
        if not media:
            did = dispimg_cell.get((row_e, col_e))
            if did:
                rid = cell_name2rid.get(did)
                tgt = cirels.get(rid) if rid else None
                media = norm_media(tgt) if tgt else None
        if not media:
            check(False, f'--expect {lbl}: 该处无浮动锚点也无 DISPIMG 嵌入图')
            continue
        if not os.path.exists(src):
            check(False, f'--expect {lbl}: 源图不存在: {src}')
            continue
        src_md5 = md5b(open(src, 'rb').read())
        got_md5 = md5b(z.read(media))
        if src_md5 == got_md5:
            check(True, f'--expect {lbl} {media} md5 与源图一致')
        else:
            check(False, f'--expect {lbl} md5 不一致! media={media}')
    z.close()
    wb.close()

    failed = sum(1 for ok, _ in results if not ok)
    print('-' * 50)
    print(f'共 {len(results)} 项: {len(results)-failed} OK / {failed} FAIL')
    sys.exit(1 if failed else 0)

if __name__ == '__main__':
    main()
