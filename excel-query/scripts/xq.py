#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xq.py —— Excel / CSV 通用查询器（供 excel-query skill 调用）

设计目标：让任何一个新对话都能在**不重新上传文件**、**不猜列名**的前提下查表。

常用命令
  python scripts/xq.py sources                       # 有哪些表可用
  python scripts/xq.py sheets  --source 别名          # 有哪些 sheet / 表头长什么样
  python scripts/xq.py head    --source 别名 [--sheet X] [--rows 10] [--header 1]
  python scripts/xq.py find "关键词" --source 别名 [--column 列名] [--limit 50]
  python scripts/xq.py filter  --source 别名 --where "列~值" --where "金额>100"
  python scripts/xq.py group   --source 别名 --by 列1,列2 --agg "金额:sum"
  python scripts/xq.py row     --source 别名 --n 37          # 按 Excel 行号看整行
  python scripts/xq.py tables  --source 别名                 # 建 SQLite 缓存并列出可查表
  python scripts/xq.py sql "select ..." --source 别名        # 任意 SQL
  python scripts/xq.py add  --alias 别名 --path D:\\x.xlsx [--copy]
  python scripts/xq.py drop --alias 别名

约定
  * --source 既可以是登记的别名，也可以是文件路径（绝对 / 相对本 skill 目录）。
  * 结果里的 `#行` 就是 Excel 里的真实行号，用户说「第 37 行」时直接对应得上。
  * 所有命令都支持 --json，给程序读。
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

try:  # 保证中文在 Windows 控制台 / 管道里不乱码
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"
CONFIG_DIR = SKILL_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "sources.json"
CACHE_DIR = DATA_DIR / "_cache"
EXCEL_EXT = {".xlsx", ".xlsm", ".xls", ".xlsb", ".ods", ".csv", ".tsv", ".txt"}


# --------------------------------------------------------------------------
# 源（表格）解析
# --------------------------------------------------------------------------

def _load_registry() -> dict:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return dict(data.get("sources") or {})
        except Exception:
            return {}
    return {}


def _save_registry(reg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps({"sources": reg}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _reg_defaults(alias: str) -> dict:
    """登记时记下的默认 sheet / 表头行 / 说明。"""
    item = _load_registry().get(alias)
    if not isinstance(item, dict):
        return {}
    return {k: item[k] for k in ("sheet", "header", "block", "note") if item.get(k) not in (None, "")}


def _abs(p: str | Path) -> Path:
    p = Path(p)
    return p if p.is_absolute() else (SKILL_DIR / p)


def all_sources() -> "dict[str, Path]":
    """登记的别名 + data/ 目录下自动发现的文件（文件名即别名）。"""
    out: "dict[str, Path]" = {}
    reg = _load_registry()
    registered: "set[str]" = set()
    for alias, item in reg.items():
        path = _abs(item.get("path", "") if isinstance(item, dict) else str(item))
        registered.add(str(path.resolve()).lower())
        out[str(alias)] = path  # 不存在也保留，sources 里标 ✗
    if DATA_DIR.exists():
        for f in sorted(DATA_DIR.iterdir()):
            if f.is_file() and f.suffix.lower() in EXCEL_EXT:
                if str(f.resolve()).lower() in registered:
                    continue  # 已经用别名登记过，不再重复出现
                alias = f.stem
                if alias not in out:
                    out[alias] = f
    return out


def die(msg: str) -> None:
    print(f"[xq] {msg}", file=sys.stderr)
    raise SystemExit(2)


def resolve_source(name: str | None) -> "tuple[str, Path]":
    srcs = all_sources()
    if name:
        p = Path(name)
        if p.exists():
            return p.stem, p
        cand = _abs(name)
        if cand.exists():
            return cand.stem, cand
        if name in srcs:
            path = srcs[name]
            if not path.exists():
                die(f"别名「{name}」登记的文件不存在了：{path}\n用 `sources` 看看，或用 `add` 重新登记。")
            return name, path
        hits = [a for a in srcs if a.lower() == name.lower()]
        if not hits:
            hits = [a for a in srcs if name.lower() in a.lower()]
        if len(hits) == 1:
            return hits[0], srcs[hits[0]]
        if len(hits) > 1:
            die(f"「{name}」匹配到多个表：{', '.join(hits)}，请写全名。")
        avail = "\n".join(f"  - {a}  ({p})" for a, p in srcs.items()) or "  （空）"
        die(f"找不到表「{name}」。可用的有：\n{avail}\n"
            f"也可以直接给路径：--source \"D:\\某目录\\某文件.xlsx\"")
    if len(srcs) == 1:
        a, p = next(iter(srcs.items()))
        return a, p
    if not srcs:
        die("还没有任何可查的表。\n"
            f"  1) 把 xlsx 放进 {DATA_DIR}（文件名就是别名），或\n"
            f"  2) python scripts/xq.py add --alias 别名 --path \"D:\\路径\\文件.xlsx\"")
    avail = "\n".join(f"  - {a}  ({p})" for a, p in srcs.items())
    die(f"有多个表，请用 --source 指定：\n{avail}")


# --------------------------------------------------------------------------
# 读表
# --------------------------------------------------------------------------

def _match_sheet(sheets: "list[str]", want: str | None) -> str:
    if not want:
        return sheets[0]
    if want in sheets:
        return want
    low = want.lower()
    hits = [s for s in sheets if s.lower() == low] or [s for s in sheets if low in s.lower()]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        die(f"--sheet「{want}」匹配到多个：{', '.join(hits)}")
    die(f"没有这个 sheet：「{want}」。可用的有：{', '.join(sheets)}")


def _read_raw(path: Path, sheet: str | None = None) -> "tuple[pd.DataFrame, list[str], str]":
    """整表读成无表头的二维表，返回 (raw, sheet 列表, 实际用的 sheet)。"""
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv", ".txt"}:
        sep = "\t" if suffix in {".tsv", ".txt"} else ","
        raw = pd.read_csv(path, header=None, dtype=object, sep=sep, engine="python")
        return raw, ["(csv)"], "(csv)"
    if suffix == ".xls":
        try:
            xl = pd.ExcelFile(path)
        except Exception as e:  # xlrd 缺失等
            die(f"读不了 .xls（需要 xlrd）：{e}\n建议用 Excel 另存为 .xlsx 再放进来。")
    xl = pd.ExcelFile(path)
    sheets = list(xl.sheet_names)
    use = _match_sheet(sheets, sheet)
    raw = xl.parse(use, header=None, dtype=object)
    return raw, sheets, use


def _clean_name(v, idx: int) -> str:
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return f"列{idx + 1}"
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return f"列{idx + 1}"
    return re.sub(r"\s+", " ", s)


def to_frame(raw: pd.DataFrame, header_row: int = 1) -> pd.DataFrame:
    """把无表头二维表按 header_row(1 起) 转成带列名的 DataFrame，并加 `#行`(Excel 行号)。"""
    if raw.empty:
        return pd.DataFrame(columns=["#行"])
    h = max(0, header_row - 1)
    if h >= len(raw):
        die(f"--header {header_row} 超出表格范围（共 {len(raw)} 行）。")
    names: "list[str]" = []
    seen: "dict[str,int]" = {}
    for i, v in enumerate(raw.iloc[h].tolist()):
        base = _clean_name(v, i)
        if base in seen:
            seen[base] += 1
            base = f"{base}.{seen[base]}"
        else:
            seen[base] = 1
        names.append(base)

    df = raw.iloc[h + 1:].reset_index(drop=True).copy()
    df.columns = names
    df.insert(0, "#行", [h + 2 + i for i in range(len(df))])
    df = df.dropna(how="all", subset=[c for c in df.columns if c != "#行"])
    # 去掉右侧整列全空的尾巴（Excel 常见的脏格式列）
    keep = len(df.columns)
    for i in range(len(df.columns) - 1, 0, -1):
        col = df.columns[i]
        if col == "#行":
            continue
        if df[col].notna().any():
            break
        keep = i
    df = df.iloc[:, :keep]
    return df.reset_index(drop=True)


def load_frame(source: str | None, sheet: str | None, header: "int | None",
               block: int | None = None) -> "tuple[str, Path, str, pd.DataFrame]":
    alias, path = resolve_source(source)
    d = _reg_defaults(alias)
    if not sheet:
        sheet = d.get("sheet")
    if block is None:
        block = d.get("block")
    if block:
        alias, path, use, df = _load_block_frame(alias, path, sheet, int(block))
        return alias, path, use, df
    if not header:
        header = d.get("header") or 1
    raw, _sheets, use = _read_raw(path, sheet)
    return alias, path, use, to_frame(raw, int(header))


# --------------------------------------------------------------------------
# 多段堆叠表：一个 sheet 里竖着排了好几张表，每张表有自己的表头/列
# --------------------------------------------------------------------------

def _cell_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and float(v).is_integer():
        return str(int(v))
    return re.sub(r"\s+", " ", str(v)).strip()


def _raw_grid(path: Path, sheet: str | None) -> "tuple[list[list], str]":
    import openpyxl
    wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
    try:
        name = _match_sheet(list(wb.sheetnames), sheet)
        ws = wb[name]
        return [list(r) for r in ws.iter_rows(values_only=True)], name
    finally:
        wb.close()


def _is_hdr(row) -> bool:
    return bool(row) and _cell_text(row[0]).startswith("运达国家")


def _is_data(row) -> bool:
    if not row or _is_hdr(row):
        return False
    a = _cell_text(row[0])
    if not a or len(a) > 30 or a[0].isdigit():
        return False
    c = _cell_text(row[2]) if len(row) > 2 else ""
    if c and not (c.isalpha() and c.isupper() and len(c) <= 3):
        return False
    return True


def _ffill(row) -> "list[str]":
    out, last = [], ""
    for v in row:
        t = _cell_text(v)
        if t:
            last = t
        out.append(last)
    return out


_GROUP_SHORT = [
    ("小包普货&小包非普货计费", "普货&非普货"),
    ("小包非普货计费（其他仓）", "非普货(其他仓)"),
    ("小包非普货计费", "非普货"),
    ("小包普货计费", "普货"),
    ("大包计费", "大包"),
]


def _norm_part(p: str) -> str:
    """把单位行/计费组那几行啰嗦的表头压短，让列名在 20 字内能看清区别。"""
    if p.startswith("配送服务费"):
        return "配送费"
    if p.startswith("挂号服务费"):
        return "挂号费"
    if p.startswith("0.5KG首重"):
        return "首重0.5KG"
    if p.startswith("续重"):
        return "续重/500g"
    p = p.replace("(含)", "")
    for long, short in _GROUP_SHORT:
        if p.startswith(long):
            return short + p[len(long):]
    return p


def _block_cols(grid, lay, width=None) -> "list[str]":
    frows = [_ffill(grid[i]) for i in lay]
    if width is None:
        width = max((len(r) for r in frows), default=0)
    names = []
    for j in range(width):
        parts: "list[str]" = []
        for r in frows:
            t = r[j] if j < len(r) else ""
            if t:
                t = _norm_part(t)
            if t and (not parts or parts[-1] != t):
                parts.append(t)
        names.append("/".join(parts) or f"列{j + 1}")
    return names


def find_blocks(grid) -> "list[dict]":
    heads = [i for i, r in enumerate(grid) if _is_hdr(r)]
    out = []
    for idx, h in enumerate(heads):
        end = heads[idx + 1] if idx + 1 < len(heads) else len(grid)
        lay = [h]
        k = h + 1
        while k < end and len(lay) < 4 and not _is_data(grid[k]):
            if sum(1 for v in grid[k] if _cell_text(v)) >= 2:
                lay.append(k)
            k += 1
        rows = [r for r in range(lay[-1] + 1, end) if _is_data(grid[r])]
        if not rows:
            continue
        # openpyxl 会把每行补齐到整表最宽；合并单元格的标签又会被 _ffill 向右无限复制。
        # 用「表头行 + 数据行里最后一个非空单元格」定真实列宽，避免造出一堆假列。
        width = 0
        for r in rows + lay:
            line = grid[r]
            for j in range(len(line) - 1, -1, -1):
                if _cell_text(line[j]):
                    width = max(width, j + 1)
                    break
        out.append({
            "header_row": h + 1,
            "layout": [x + 1 for x in lay],
            "rows": (rows[0] + 1, rows[-1] + 1),
            "count": len(rows),
            "cols": _block_cols(grid, lay, width),
            "width": width,
            "first": _cell_text(grid[rows[0]][0]),
            "last": _cell_text(grid[rows[-1]][0]),
        })
    return out


def _load_block_frame(alias, path, sheet, block: int) -> "tuple[str, Path, str, pd.DataFrame]":
    grid, use = _raw_grid(path, sheet)
    blocks = find_blocks(grid)
    if not blocks:
        die(f"「{use}」里没找到「运达国家/地区」表头段。改用 --header 指定表头行。")
    if not 1 <= block <= len(blocks):
        lines = "\n".join(f"  段{i + 1}: #行 {b['rows'][0]}–{b['rows'][1]}（{b['count']} 行）"
                          for i, b in enumerate(blocks))
        die(f"--block 超出范围：这个 sheet 共 {len(blocks)} 段\n{lines}")
    b = blocks[block - 1]
    r0, r1 = b["rows"]
    cols: "list[str]" = []
    seen: "dict[str, int]" = {}
    for n in b["cols"]:
        if n in seen:
            seen[n] += 1
            cols.append(f"{n}#{seen[n]}")
        else:
            seen[n] = 1
            cols.append(n)
    width = len(cols)
    data = []
    for r in range(r0 - 1, r1):
        row = list(grid[r])
        if len(row) < width:
            row += [None] * (width - len(row))
        data.append(row[:width])
    df = pd.DataFrame(data, columns=cols)
    df.insert(0, "#行", list(range(r0, r1 + 1)))
    df = df.dropna(how="all", subset=[c for c in df.columns if c != "#行"])
    # 去掉右侧整列全空的尾巴（openpyxl 会按整表最宽行补齐）
    for c in [c for c in reversed(list(df.columns)) if c != "#行"]:
        if df[c].notna().any():
            break
        df = df.drop(columns=[c])
    return alias, path, use, df.reset_index(drop=True)


def _scope(args) -> "tuple[str, Path, str | None, int]":
    """别名/路径 + 生效的 sheet 与表头行（含登记时的默认值）。"""
    alias, path = resolve_source(getattr(args, "source", None))
    d = _reg_defaults(alias)
    sheet = getattr(args, "sheet", None) or d.get("sheet") or None
    header = int(getattr(args, "header", None) or d.get("header") or 1)
    return alias, path, sheet, header


def cmd_blocks(args) -> None:
    alias, path = resolve_source(args.source)
    d = _reg_defaults(alias)
    sheet = args.sheet or d.get("sheet")
    grid, use = _raw_grid(path, sheet)
    blocks = find_blocks(grid)
    if not blocks:
        print(f"{alias} / {use}：没有「运达国家/地区」这种分段表头。用 head/sheets 看结构。")
        return
    print(f"{alias} / {use}：共 {len(blocks)} 段（一个 sheet 里竖排了多张表，各自表头不同）")
    for i, b in enumerate(blocks, 1):
        mark = "  ← 登记默认" if d.get("block") == i else ""
        print(f"\n段{i}  #行 {b['rows'][0]}–{b['rows'][1]}  表头在第 {b['header_row']} 行"
              f"（+{'/'.join(str(x) for x in b['layout'][1:])} 是分段/单位行）  {b['count']} 行"
              f"  国家：{b['first']} … {b['last']}{mark}")
        cols = b["cols"]
        shown = cols[:8]
        print("   列：" + " | ".join(shown) + (f" …（共 {len(cols)} 列）" if len(cols) > len(shown) else ""))
    if d.get("block"):
        print(f"\n这个别名默认按段{d['block']} 查；要换段加 --block N，或重新 add 覆盖默认值。")
    else:
        print("\n查某一段：xq.py filter --source " + alias + " --block 1 --where \"Code=US\"")


_BRACKET = re.compile(r"(\d+)\s*[~\-]\s*(\d+)\s*[gG]")


def _ptype_of(group: str) -> str:
    if group.startswith("大包"):
        return "大包"
    if group.startswith("普货&"):
        return "普货&非普货"
    if group.startswith("非普货"):
        return "非普货"
    if group.startswith("普货"):
        return "普货"
    return group


def _price_map(cols) -> "dict[tuple[str, int, int], dict[str, int]]":
    """{(计费组, 重量下限, 重量上限): {计费项: 列序号}}"""
    out: "dict[tuple[str, int, int], dict[str, int]]" = {}
    for j, c in enumerate(cols):
        parts = c.split("/")
        if len(parts) < 3:
            continue
        ptype = _ptype_of(parts[0])
        m = _BRACKET.search(parts[1])
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
        elif ptype == "大包":
            lo, hi = 0, 30000  # 「大包（计泡）/限重30kg」没有重量分段时，按一个区间算
        else:
            continue
        item = "/".join(parts[2:])  # 「续重/500g」自己带斜杠，不能被 split 拆散
        out.setdefault((ptype, lo, hi), {})[item] = j
    return out


def cmd_quote(args) -> None:
    """按「国家 + 重量 + 货物类型」在分段报价表里算运费。"""
    alias, path = resolve_source(args.source)
    d = _reg_defaults(alias)
    sheet = args.sheet or d.get("sheet")
    want = (args.to or "").strip()
    if not want:
        die("--to 必填：国家名（中文、英文、两位 Code 都能认）")
    weight = float(args.weight)
    if weight <= 0:
        die("--weight 要大于 0（单位：克）")
    ptype = (args.type or "普货").strip()
    grid, use = _raw_grid(path, sheet)
    blocks = find_blocks(grid)
    if not blocks:
        die(f"「{use}」里没有「运达国家/地区」这种分段表头；quote 只适用于分段报价表。")

    key = want.casefold()
    cand: "list[tuple]" = []
    for bi, b in enumerate(blocks, 1):
        if getattr(args, "block", None) and bi != args.block:
            continue
        pmap = _price_map(b["cols"])
        groups = {"普货&非普货", ptype} if ptype in ("普货", "非普货") else {ptype}
        r0, r1 = b["rows"]
        for r in range(r0 - 1, r1):
            data = list(grid[r])
            cells = [_cell_text(data[j]) if j < len(data) else "" for j in range(3)]
            low = [c.casefold() for c in cells if c]
            if key in low or (len(key) >= 2 and any(key in c for c in low)):
                cand.append((bi, r + 1, cells, data, pmap, groups))
    # 名字正好的（美国 / United States / US）优先；都没有才退回「包含」匹配
    exact = [c for c in cand if key in [x.casefold() for x in c[2] if x]]
    chosen = exact or cand
    if cand and not exact:
        print(f"（没有哪个国家的名字正好是「{want}」，下面把包含它的都列出来：）")

    got: "list[dict]" = []
    miss: "list[tuple]" = []
    warn: "list[str]" = []
    for bi, ln, cells, data, pmap, groups in chosen:
        hit = None
        for (g, lo, hi), items in sorted(pmap.items()):
            if g in groups and lo <= weight <= hi:
                hit = (g, lo, hi, items)
                break
        if not hit:
            miss.append((bi, ln, cells[0],
                         sorted((g, lo, hi) for (g, lo, hi) in pmap if g in groups)))
            continue

        def val(name, items=items, data=data):
            idx = items.get(name)
            if idx is None or idx >= len(data):
                return None
            n = _num(data[idx])
            return None if n is None else float(n)

        g, lo, hi, items = hit
        first = val("首重0.5KG") if g == "大包" else None
        if g == "大包" and first is not None:
            extra = val("续重/500g")
            steps = max(0, math.ceil((weight - 500) / 500.0))
            total = first + steps * (extra or 0.0)
            if extra is None and weight > 500:
                warn.append(f"段{bi} #行{ln} {cells[0]}：这张表没有续重价，估算合计只含首重，实际以报价为准。")
            got.append({"段": bi, "#行": ln, "国家": cells[0], "Code": cells[2],
                        "计费档": f"{g} {lo}-{hi}g", "首重0.5kg(元)": first,
                        "续重/500g(元)": extra, "估算合计(元)": round(total, 2)})
        else:
            ship, reg = val("配送费"), val("挂号费")
            total = (ship or 0.0) * weight / 1000.0 + (reg or 0.0)
            got.append({"段": bi, "#行": ln, "国家": cells[0], "Code": cells[2],
                        "计费档": f"{g} {lo}-{hi}g", "配送费(元/kg)": ship,
                        "挂号费(元/件)": reg, "合计(元)": round(total, 2)})

    title = f"{alias} / {use}：{want} {weight:g}g {ptype}"
    if got:
        df = pd.DataFrame(got)
        if args.json:
            dump_json(df)
            return
        print(render(df, len(df), args.max_width, max_cols=args.max_cols,
                     title=title + f" → {len(df)} 条"))
        print("\n算法：合计 = 重量(kg) × 配送费 + 挂号费（1g 计重，不足 1g 按实际重量算）；")
        print("      大包 = 首重 0.5kg 价 + 超出部分每 500g 续重价。表里的单价原样列出，可自行复核。")
        for w in warn:
            print("注意：" + w)
    if miss:
        print(f"\n另有 {len(miss)} 处匹配到「{want}」，但 {weight:g}g 不在该段的档位里：")
        for bi, ln, name, spans in miss:
            txt = "、".join(f"{g} {lo}-{hi}g" for g, lo, hi in spans) or "（该段没解析出重量档，用 --block 看原文）"
            print(f"  段{bi} #行{ln} {name}：可选 {txt}")
    if not got and not miss:
        die(f"「{use}」里没找到国家「{want}」。先跑 blocks 看每段覆盖哪些国家；"
            f"或 --json 逐段核对国家写法。")


# --------------------------------------------------------------------------
# 列名 / 条件
# --------------------------------------------------------------------------

def resolve_col(df: pd.DataFrame, name: str) -> str:
    cols = [c for c in df.columns]
    if name in cols:
        return name
    low = name.strip().lower()
    hits = [c for c in cols if c.lower() == low]
    if not hits:
        hits = [c for c in cols if low in c.lower()]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        die(f"列名「{name}」匹配到多个：{', '.join(hits)}，请写全。")
    die(f"没有这一列：「{name}」。现有列：{', '.join(str(c) for c in cols)}\n"
        f"（结构不确定就先跑 sheets / head）")


def _num(x):
    if x is None:
        return None
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return None if pd.isna(x) else float(x)
    if isinstance(x, (datetime, date)):
        return None
    s = str(x).strip().replace(",", "").replace("¥", "").replace("￥", "").replace("$", "").replace("%", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _strs(series: pd.Series) -> pd.Series:
    return series.map(lambda x: "" if (x is None or (not isinstance(x, str) and pd.isna(x))) else str(x).strip())


def parse_where(expr: str) -> "tuple[str, str, str]":
    m = re.match(r"^\s*(.*?)\s*(!=|!~|>=|<=|=|~|>|<)\s*(.*)$", expr, re.S)
    if not m or not m.group(1):
        die(f"--where 要写成「列 运算符 值」，例如 \"金额>100\" 或 \"店铺~Morph\"。收到：{expr!r}")
    return m.group(1).strip(), m.group(2), m.group(3).strip()


def apply_where(df: pd.DataFrame, expr: str, use_regex: bool = False) -> pd.Series:
    col_raw, op, val = parse_where(expr)
    s = df[resolve_col(df, col_raw)]
    s_str = _strs(s)
    if op == "=":
        if val == "":
            return s_str == ""
        mask = s_str == val
        nv = _num(val)
        if nv is not None:
            mask = mask | (s.map(_num) == nv)
        return mask.fillna(False)
    if op == "!=":
        return ~apply_where(df, f"{col_raw}={val}", use_regex)
    if op in ("~", "!~"):
        if use_regex:
            m = s_str.str.contains(val, case=False, na=False, regex=True)
        else:
            m = s_str.str.contains(val, case=False, na=False, regex=False)
        return m if op == "~" else ~m
    nv = _num(val)
    if nv is None:
        die(f"「{op}」需要数字，收到 {val!r}")
    s_num = s.map(_num)
    nonnull = s.notna().sum()
    if nonnull and s_num.notna().sum() >= nonnull * 0.8:
        left = s_num
    else:  # 日期/文本按字符串比
        left = s_str
        nv_s = val
        ops = {">": left > nv_s, "<": left < nv_s, ">=": left >= nv_s, "<=": left <= nv_s}
        return ops[op].fillna(False)
    ops = {">": left > nv, "<": left < nv, ">=": left >= nv, "<=": left <= nv}
    return ops[op].fillna(False)


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------

def cell_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        if pd.isna(v):
            return ""
        if v.is_integer() and abs(v) < 1e15:
            return str(int(v))
        return f"{v:g}"
    if isinstance(v, (pd.Timestamp, datetime)):
        if getattr(v, "hour", 0) == 0 and getattr(v, "minute", 0) == 0 and getattr(v, "second", 0) == 0:
            return v.strftime("%Y-%m-%d")
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if v is pd.NaT:
        return ""
    s = str(v)
    if s.lower() == "nan" or s == "NaT":
        return ""
    return s.replace("\r\n", " ").replace("\n", " ").replace("\t", " ")


def _dw(s: str) -> int:
    w = 0
    for ch in s:
        if unicodedata.combining(ch):
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def _fit(s: str, width: int) -> str:
    if _dw(s) <= width:
        return s
    out, w = "", 0
    for ch in s:
        cw = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if w + cw > width - 1:
            break
        out += ch
        w += cw
    return out + "…"


def _pad(s: str, width: int, right: bool = False) -> str:
    gap = width - _dw(s)
    return (" " * gap + s) if right else (s + " " * gap)


def render(df: pd.DataFrame, max_rows: int = 40, max_width: int = 40, title: str = "",
           max_cols: int = 12) -> str:
    if df.empty:
        return (title + "\n" if title else "") + "（0 行匹配）"
    hidden = 0
    if len(df.columns) > max_cols:
        hidden = len(df.columns) - max_cols
        df = df.iloc[:, :max_cols]
    rows = df.head(max_rows)
    cols = [str(c) for c in rows.columns]
    cells = [[cell_str(v) for v in rec] for rec in rows.itertuples(index=False)]
    widths = []
    for i, c in enumerate(cols):
        w = max([_dw(c)] + [_dw(r[i]) for r in cells])
        widths.append(min(max(w, 2), max_width))
    numeric = []
    for i, c in enumerate(rows.columns):
        series = rows.iloc[:, i]
        nonnull = [v for v in series.tolist() if cell_str(v) != ""]
        numeric.append(bool(nonnull) and all(_num(v) is not None for v in nonnull) and c != "#行")

    lines = []
    if title:
        lines.append(title)
    lines.append("  ".join(_pad(_fit(c, widths[i]), widths[i]) for i, c in enumerate(cols)).rstrip())
    lines.append("  ".join("-" * widths[i] for i in range(len(cols))))
    for r in cells:
        lines.append("  ".join(_pad(_fit(r[i], widths[i]), widths[i], right=numeric[i]) for i in range(len(cols))).rstrip())
    if len(df) > len(rows):
        lines.append(f"…… 共 {len(df)} 行，只显示前 {len(rows)} 行（用 --limit 调整，或 --json 取全量）")
    if hidden:
        lines.append(f"…… 另有 {hidden} 列未显示（--max-cols 调整；看某列请用 --column / --json）")
    return "\n".join(lines)


def dump_json(df: pd.DataFrame) -> None:
    recs = []
    for rec in df.to_dict(orient="records"):
        clean = {}
        for k, v in rec.items():
            if v is None or (not isinstance(v, str) and pd.isna(v)):
                clean[str(k)] = None
            elif isinstance(v, (pd.Timestamp, datetime)):
                clean[str(k)] = v.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(v, float) and v.is_integer():
                clean[str(k)] = int(v)
            else:
                clean[str(k)] = v if isinstance(v, (int, float, str, bool)) else str(v)
        recs.append(clean)
    print(json.dumps(recs, ensure_ascii=False, indent=1))


# --------------------------------------------------------------------------
# SQLite 缓存
# --------------------------------------------------------------------------

def _safe_table(name: str) -> str:
    t = re.sub(r"[^\w\u4e00-\u9fff]+", "_", str(name)).strip("_")
    return t or "sheet"


def build_sqlite(alias: str, path: Path, header: int = 1, force: bool = False):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = re.sub(r"[^\w\u4e00-\u9fff]+", "_", alias) or "src"
    db = CACHE_DIR / f"{key}.sqlite"
    meta_file = CACHE_DIR / f"{key}.meta.json"
    st = path.stat()
    stamp = {"path": str(path), "mtime": st.st_mtime, "size": st.st_size, "header": header}
    if not force and db.exists() and meta_file.exists():
        try:
            if json.loads(meta_file.read_text(encoding="utf-8")) == stamp:
                return db, json.loads((CACHE_DIR / f"{key}.manifest.json").read_text(encoding="utf-8"))
        except Exception:
            pass

    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv", ".txt"}:
        sheets: "dict[str, pd.DataFrame]" = {"(csv)": _read_raw(path)[0]}
    else:
        xl = pd.ExcelFile(path)
        sheets = {s: xl.parse(s, header=None, dtype=object) for s in xl.sheet_names}

    import sqlite3
    if db.exists():
        db.unlink()
    manifest = []
    conn = sqlite3.connect(str(db))
    try:
        used = set()
        for sname, raw in sheets.items():
            df = to_frame(raw, header)
            if df.empty:
                continue
            body = df.drop(columns=["#行"])
            t = _safe_table(sname)
            base, n = t, 1
            while t in used:
                n += 1
                t = f"{base}_{n}"
            used.add(t)
            out = pd.DataFrame({"_row": df["#行"].astype(int)})
            for c in body.columns:
                series = body[c]
                coerced = pd.to_numeric(series, errors="coerce")
                nonnull = series.notna().sum()
                if nonnull and coerced.notna().sum() >= nonnull * 0.9:
                    out[str(c)] = coerced
                else:
                    out[str(c)] = series.map(lambda x: None if (x is None or (not isinstance(x, str) and pd.isna(x))) else str(x).strip())
            out.to_sql(t, conn, if_exists="replace", index=False)
            manifest.append({"sheet": sname, "table": t, "rows": len(out), "columns": [str(c) for c in out.columns]})
        conn.commit()
    finally:
        conn.close()
    meta_file.write_text(json.dumps(stamp, ensure_ascii=False), encoding="utf-8")
    (CACHE_DIR / f"{key}.manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return db, manifest


def cmd_tables(args) -> None:
    alias, path, _sheet, header = _scope(args)
    db, manifest = build_sqlite(alias, path, header, force=True)
    print(f"[SQLite 缓存] {db}")
    for m in manifest:
        print(f"\n表 {m['table']}   ← sheet「{m['sheet']}」  {m['rows']} 行")
        print(f"  列: {', '.join(m['columns'])}")
    print('\n查询：xq.py sql "select * from 表名 limit 5" --source ' + alias)


def cmd_sql(args) -> None:
    alias, path, _sheet, header = _scope(args)
    db, manifest = build_sqlite(alias, path, header)
    query = args.query
    if getattr(args, "file", None):
        query = Path(args.file).read_text(encoding="utf-8")
    if not query:
        die('缺少 SQL。用法：xq.py sql "select ..." --source 别名（PowerShell 引号打架时改存成 .sql 用 --file）')
    query = query.strip().rstrip(";")
    import sqlite3
    conn = sqlite3.connect(str(db))
    try:
        df = pd.read_sql_query(query, conn)
    except Exception as e:
        tables = ", ".join(m["table"] for m in manifest)
        die(f"SQL 出错：{e}\n可用的表：{tables}\n"
            f"列名含中文/空格时用双引号括起来，例如 select \"店铺\", sum(\"金额\") from 表名 group by 1")
    finally:
        conn.close()
    if args.json:
        dump_json(df)
    else:
        print(render(df, args.limit, args.max_width, max_cols=args.max_cols))


# --------------------------------------------------------------------------
# 普通命令
# --------------------------------------------------------------------------

def cmd_sources(args) -> None:
    srcs = all_sources()
    if args.json:
        print(json.dumps({a: str(p) for a, p in srcs.items()}, ensure_ascii=False, indent=1))
        return
    if not srcs:
        print("（还没有可查的表）")
        print(f"  把 xlsx 直接放进：{DATA_DIR}")
        print("  或登记：python scripts/xq.py add --alias 别名 --path \"D:\\…\\文件.xlsx\"")
        return
    print(f"共 {len(srcs)} 个可查表：")
    for a, p in srcs.items():
        ok = "✓" if p.exists() else "✗ 文件已不存在"
        d = _reg_defaults(a)
        extra = ""
        if d.get("sheet") or d.get("header"):
            extra = f"   [默认 sheet={d.get('sheet') or '第一个'} 表头行={d.get('header') or 1}]"
        print(f"  - {a:<24} {ok}  {p}{extra}")
    print(f"\n数据目录：{DATA_DIR}")


def cmd_sheets(args) -> None:
    alias, path = resolve_source(args.source)
    raw_sheets: "list[tuple[str, pd.DataFrame]]" = []
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv", ".txt"}:
        raw_sheets.append(("(csv)", _read_raw(path)[0]))
    else:
        xl = pd.ExcelFile(path)
        for s in xl.sheet_names:
            raw_sheets.append((s, xl.parse(s, header=None, dtype=object)))
    print(f"表：{alias}   {path}")
    for sname, raw in raw_sheets:
        nonempty = raw.dropna(how="all").shape[0]
        print(f"\n=== sheet「{sname}」  约 {nonempty} 行 × {raw.shape[1]} 列")
        for i in range(min(3, len(raw))):
            vals = [cell_str(v) for v in raw.iloc[i].tolist()]
            vals = [v for v in vals if v]
            if vals:
                print(f"  第{i + 1}行: " + " | ".join(v[:22] for v in vals[:12]))
    print("\n下一步：head --source " + alias + " [--sheet 名字] [--header 行号]")
    print("提示：#行 列是 Excel 真实行号；表头不在第 1 行时用 --header N 指定。")


def cmd_head(args) -> None:
    alias, path, use, df = load_frame(args.source, args.sheet, args.header, getattr(args, "block", None))
    if args.json:
        dump_json(df.head(args.limit))
        return
    print(render(df.head(args.limit), args.limit, args.max_width, max_cols=args.max_cols,
                 title=f"{alias} / {use}：{len(df)} 行 × {len(df.columns) - 1} 列"))


def cmd_find(args) -> None:
    alias, path, use, df = load_frame(args.source, args.sheet, args.header, getattr(args, "block", None))
    if args.column:
        col = resolve_col(df, args.column)
        series = _strs(df[col])
    else:
        body = df.drop(columns=["#行"])
        if body.shape[1] == 0 or body.shape[0] == 0:
            die("这个 sheet 在给定 --header 下没有可读数据；先跑 sheets 看结构，或换个 --header")
        series = body.apply(lambda c: _strs(c)).agg(" | ".join, axis=1)
        series = pd.Series(series.tolist(), dtype=object)
        col = "(全部列)"
    try:
        mask = pd.Series(_strs(series)).str.contains(args.query, case=not args.case_sensitive, na=False, regex=args.regex)
    except re.error as e:
        die(f"--regex 正则写错了：{e}")
    hit = df[mask]
    if args.json:
        dump_json(hit.head(args.limit))
        return
    where = f"列「{col}」" if args.column else "全部列"
    print(render(hit.head(args.limit), args.limit, args.max_width, max_cols=args.max_cols,
                 title=f"{alias} / {use}：{where} 含「{args.query}」→ {len(hit)} 行"))


def cmd_filter(args) -> None:
    alias, path, use, df = load_frame(args.source, args.sheet, args.header, getattr(args, "block", None))
    mask = pd.Series(True, index=df.index)
    for w in args.where:
        mask = mask & apply_where(df, w, args.regex)
    hit = df[mask]
    if args.sort:
        sc = resolve_col(df, args.sort)
        hit = hit.sort_values(sc, ascending=not args.desc, key=lambda s: s.map(_num) if s.map(_num).notna().sum() else s)
    if args.json:
        dump_json(hit.head(args.limit))
        return
    cond = " AND ".join(args.where)
    print(render(hit.head(args.limit), args.limit, args.max_width, max_cols=args.max_cols,
                 title=f"{alias} / {use}：{cond} → {len(hit)} 行"))


def cmd_group(args) -> None:
    alias, path, use, df = load_frame(args.source, args.sheet, args.header, getattr(args, "block", None))
    mask = pd.Series(True, index=df.index)
    for w in (args.where or []):
        mask = mask & apply_where(df, w, args.regex)
    work = df[mask]
    keys = [resolve_col(work, k.strip()) for k in args.by.split(",") if k.strip()]
    aggs: "dict[str,list[tuple[str,str]]]" = {}
    for spec in (args.agg or []):
        for part in spec.split(","):
            if not part.strip():
                continue
            if ":" not in part:
                die(f"--agg 要写成 列:函数，例如 \"金额:sum\"。收到 {part!r}")
            c, f = part.split(":", 1)
            c, f = resolve_col(work, c.strip()), f.strip().lower()
            if f not in {"sum", "mean", "min", "max", "count", "nunique"}:
                die("支持的聚合函数：sum / mean / min / max / count / nunique")
            aggs.setdefault(f, []).append(c)
    if not aggs:
        aggs = {"count": [keys[0]]}
    tmp = work.copy()
    for f, cols in aggs.items():
        for c in cols:
            if f in {"sum", "mean", "min", "max"}:
                tmp[f"{c}"] = tmp[c].map(_num)
    named = {}
    for f, cols in aggs.items():
        for c in cols:
            src = f"{c}" if f in {"sum", "mean", "min", "max"} else c
            named[f"{c}_{f}"] = (src, f)
    g = tmp.groupby(keys, dropna=False).agg(**named).reset_index()
    if args.agg:
        cols = [c for c in g.columns if c not in keys]
        if cols:
            g = g.sort_values(cols[0], ascending=False)
    if args.json:
        dump_json(g.head(args.limit))
        return
    print(render(g.head(args.limit), args.limit, args.max_width, max_cols=args.max_cols,
                 title=f"{alias} / {use}：按 {'+'.join(keys)} 汇总（{len(work)} 行参与）"))


def cmd_row(args) -> None:
    alias, path, use, df = load_frame(args.source, args.sheet, args.header, getattr(args, "block", None))
    hit = df[df["#行"] == args.n]
    if hit.empty:
        die(f"{alias} / {use} 没有第 {args.n} 行（数据范围 #{df['#行'].min()}–#{df['#行'].max()}）。")
    rec = hit.iloc[0]
    if args.json:
        dump_json(hit)
        return
    print(f"{alias} / {use}  第 {args.n} 行")
    for c in df.columns:
        v = cell_str(rec[c])
        if v:
            print(f"  {c}: {v}")


def cmd_add(args) -> None:
    p = Path(args.path).expanduser()
    if not p.exists():
        die(f"文件不存在：{p}")
    if args.copy:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        target = DATA_DIR / p.name
        shutil.copy2(p, target)
        p = target
    else:
        try:
            p_rel = p.resolve().relative_to(SKILL_DIR.resolve())
            p = p_rel
        except ValueError:
            pass  # 用绝对路径
    reg = _load_registry()
    entry = {"path": str(p), "note": args.note or ""}
    if getattr(args, "sheet", None):
        entry["sheet"] = args.sheet
    if getattr(args, "header", None):
        entry["header"] = int(args.header)
    if getattr(args, "block", None):
        entry["block"] = int(args.block)
    reg[args.alias] = entry
    _save_registry(reg)
    print(f"已登记：{args.alias} -> {p}")
    if entry.get("sheet") or entry.get("header") or entry.get("block"):
        bits = [f"默认 sheet={entry.get('sheet') or '（第一个）'}"]
        bits.append(f"段={entry.get('block')}" if entry.get("block") else f"表头行={entry.get('header') or 1}")
        print("  " + "  ".join(bits))
    print("之后任何对话都能直接用：xq.py sheets --source " + args.alias)


def cmd_drop(args) -> None:
    reg = _load_registry()
    if args.alias not in reg:
        die(f"没有登记这个别名：{args.alias}")
    reg.pop(args.alias)
    _save_registry(reg)
    print(f"已删除登记：{args.alias}")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(prog="xq.py", description="Excel / CSV 通用查询器")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, need_src=True):
        if need_src:
            p.add_argument("--source", "-s", help="别名或文件路径（只有一个表时可省略）")
        p.add_argument("--sheet", help="sheet 名（可省略，默认第一个）")
        p.add_argument("--header", type=int, default=None,
                       help="表头在第几行（1 起；不填则用登记时的默认行，再不行按 1）")
        p.add_argument("--block", type=int,
                       help="多段堆叠表（一个 sheet 竖排多张表）：查第 N 段，先跑 blocks 看有几段")
        p.add_argument("--limit", type=int, default=40, help="最多显示多少行（默认 40）")
        p.add_argument("--max-width", type=int, default=40, help="单元格最大宽度（默认 40）")
        p.add_argument("--max-cols", type=int, default=12, help="最多显示多少列（默认 12）")
        p.add_argument("--json", action="store_true", help="输出 JSON")
        p.add_argument("--regex", action="store_true", help="~ / find 用正则")

    p = sub.add_parser("sources", help="列出所有可查的表")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_sources)

    p = sub.add_parser("sheets", help="列出 sheet 和开头几行（摸结构用）")
    common(p)
    p.set_defaults(func=cmd_sheets)

    p = sub.add_parser("blocks", help="一个 sheet 里竖排了多张表时，列出每段的表头/行范围")
    common(p)
    p.set_defaults(func=cmd_blocks)

    p = sub.add_parser("quote", help="分段报价表：按「国家 + 重量 + 货类」直接算运费")
    common(p)
    p.add_argument("--to", required=True, help="国家：中文 / 英文 / 两位 Code（US）都行")
    p.add_argument("--weight", required=True, type=float, help="包裹重量，单位克")
    p.add_argument("--type", default="普货", help="货物类型：普货（默认）/ 非普货 / 大包")
    p.set_defaults(func=cmd_quote)

    p = sub.add_parser("head", help="看前几行")
    common(p)
    p.add_argument("--rows", type=int, default=10, help="行数（同 --limit）")
    p.set_defaults(func=cmd_head)

    p = sub.add_parser("find", help="全文关键词搜索")
    common(p)
    p.add_argument("query", help="关键词")
    p.add_argument("--column", "-c", help="只搜这一列")
    p.add_argument("--case-sensitive", action="store_true")
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("filter", help="按条件筛选（可多个 --where，AND）")
    common(p)
    p.add_argument("--where", "-w", action="append", required=True,
                   help='条件，如 "金额>100"、"店铺~Morph"、"状态=已发货"、"备注="')
    p.add_argument("--sort", help="排序列")
    p.add_argument("--desc", action="store_true")
    p.set_defaults(func=cmd_filter)

    p = sub.add_parser("group", help="分组汇总")
    common(p)
    p.add_argument("--by", required=True, help="分组列，逗号分隔")
    p.add_argument("--agg", action="append", help='聚合，如 "金额:sum"、"订单号:nunique"')
    p.add_argument("--where", "-w", action="append")
    p.set_defaults(func=cmd_group)

    p = sub.add_parser("row", help="按 Excel 行号看整行")
    common(p)
    p.add_argument("--n", type=int, required=True, help="Excel 行号（#行）")
    p.set_defaults(func=cmd_row)

    p = sub.add_parser("tables", help="建 SQLite 缓存并列出可查表/列")
    common(p)
    p.set_defaults(func=cmd_tables)

    p = sub.add_parser("sql", help="跑任意 SQL")
    common(p)
    p.add_argument("query", nargs="?", help="SQL 语句")
    p.add_argument("--file", help="从 .sql 文件读 SQL（引号不好转义时用）")
    p.set_defaults(func=cmd_sql)

    p = sub.add_parser("add", help="登记一个表")
    p.add_argument("--alias", required=True)
    p.add_argument("--path", required=True)
    p.add_argument("--copy", action="store_true", help="复制进 data/ 目录（推荐，单机长期使用）")
    p.add_argument("--sheet", help="记住默认 sheet（查这张表时不用再写 --sheet）")
    p.add_argument("--header", type=int, help="记住默认表头行（不用再写 --header）")
    p.add_argument("--block", type=int, help="记住默认段号（多段堆叠表用）")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("drop", help="删除登记")
    p.add_argument("--alias", required=True)
    p.set_defaults(func=cmd_drop)

    args = ap.parse_args()
    if getattr(args, "rows", None):
        args.limit = args.rows
    args.func(args)


if __name__ == "__main__":
    main()
