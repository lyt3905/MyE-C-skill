#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SKU 编码自动生成器 —— 跨境玩具（Morph Toys Store / Childhood Memories / PureSun）

编码格式（由 config/sku_config.json 的 segment_order 决定）：
    店铺-品类-系列-流水号[-变体]
    例：MTS-TF-SS86-0001-RD

核心特性
    1. 速记符自动补全：输入 s86 自动补成 SS86，输入 r 补成 RD（大小写不敏感、支持前缀）
    2. 本地台账防重：流水号按「店铺+系列」独立递增，SKU 绝不撞号
    3. 单条交互 / 批量表格（CSV、XLSX）双模式
    4. 字典全在 JSON 里，加新系列不用改代码

用法速览
    python sku_gen.py                              # 交互模式（推荐日常用）
    python sku_gen.py -s mts -c tf -e s86 -v r,b -n "SS86 擎天柱"
    python sku_gen.py -E s86 -V r --dry-run        # 只预览，不写台账
    python sku_gen.py -i 商品表.xlsx -o SKU结果.xlsx  # 批量
    python sku_gen.py --list                       # 看台账
    python sku_gen.py --find SS86                  # 搜台账
    python sku_gen.py --export 台账导出.csv         # 导出
    python sku_gen.py --stats                      # 统计

依赖：批量读写 XLSX 需要 openpyxl；只用 CSV 或交互模式则零依赖（纯标准库）。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------- 路径与常量

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
DEFAULT_CONFIG = ROOT_DIR / "config" / "sku_config.json"
DEFAULT_LEDGER = ROOT_DIR / "data" / "sku_ledger.json"
VENV_PY = "C:/Users/shana/.workbuddy/binaries/python/envs/default/Scripts/python.exe"

# 批量表格的列名识别（中英文皆可）
HEADER_ALIASES = {
    "name": ["名称", "商品名", "商品名称", "标题", "name", "product", "product_name", "title"],
    "store": ["店铺", "店面", "store", "shop"],
    "cat": ["品类", "类目", "类型", "cat", "category", "type"],
    "series": ["系列", "产品线", "series", "line"],
    "variant": ["变体", "颜色", "规格", "变体颜色", "variant", "color", "colour", "spec"],
    "quick": ["速记", "速记符", "简写", "quick", "short", "abbr"],
}
OUT_HEADERS = ["序号", "SKU", "基础编码", "名称", "店铺", "品类", "系列", "流水号", "变体", "状态", "备注"]


# ---------------------------------------------------------------- 小工具

def out(msg: str = "") -> None:
    print(msg, flush=True)


def die(msg: str, code: int = 1):
    out("\n[错误] " + msg)
    sys.exit(code)


def cjk_width(text: str) -> int:
    """按终端等宽字体估算显示宽度（中文/全角算 2）"""
    w = 0
    for ch in str(text):
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def pad(text: str, width: int) -> str:
    text = str(text)
    return text + " " * max(0, width - cjk_width(text))


def render_table(headers, rows) -> str:
    cols = list(zip(*([headers] + [list(r) for r in rows]))) if rows else [(h,) for h in headers]
    widths = [max(cjk_width(c) for c in col) for col in cols]
    line = "  ".join(pad(h, w) for h, w in zip(headers, widths))
    sep = "  ".join("-" * w for w in widths)
    body = ["  ".join(pad(c, w) for c, w in zip(r, widths)) for r in rows]
    return "\n".join([line, sep] + body)


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def vlabel(rec: dict) -> str:
    """变体显示：RD 红色"""
    code, name = rec.get("variant", ""), rec.get("variant_name", "")
    if code and name and name != code:
        return f"{code} {name}"
    return code or name or "-"


# ---------------------------------------------------------------- 字典解析

class ResolveError(Exception):
    pass


class AmbiguousError(ResolveError):
    def __init__(self, raw, candidates):
        self.raw = raw
        self.candidates = candidates
        pretty = "、".join(f"{c}{f'（{n}）' if n and n != c else ''}" for c, n in candidates)
        super().__init__(f"「{raw}」匹配到多个：{pretty}")


class UnknownError(ResolveError):
    def __init__(self, raw, known):
        self.raw = raw
        self.known = known
        super().__init__(f"「{raw}」不在字典中")


def resolve_value(entries, raw, label, allow_passthrough=False):
    """把速记符解析成字典条目。返回 (code, name)。

    匹配优先级：编码全等 → 速记符全等 → 编码前缀 → 速记符前缀 → 名称包含。
    歧义时报错并列出候选，绝不做模糊猜测。
    """
    q = str(raw).strip()
    if not q:
        return None, None

    low = q.lower()

    # 变体支持纯数字色号（01/02/03…）直接透传
    if allow_passthrough and q.isdigit():
        return q, q

    def hit(entry):
        return (entry["code"], entry.get("name", entry["code"]))

    for e in entries:                                    # 1) 编码全等
        if e["code"].lower() == low:
            return hit(e)
    for e in entries:                                    # 2) 速记符全等
        if low in [str(a).lower() for a in e.get("alias", [])]:
            return hit(e)

    # 3) 前缀匹配：编码前缀 + 速记符前缀 + 名称包含，合并后必须唯一，否则报歧义
    cands = []
    for e in entries:
        aliases = [str(a).lower() for a in e.get("alias", [])]
        if (e["code"].lower().startswith(low)
                or any(a.startswith(low) for a in aliases)
                or (len(low) >= 2 and low in str(e.get("name", "")).lower())):
            if e["code"] not in [c[0] for c in cands]:
                cands.append(hit(e))
    if len(cands) == 1:
        return cands[0]
    if len(cands) > 1:
        raise AmbiguousError(q, cands)
    raise UnknownError(q, [f"{e['code']}({e.get('name','')})" for e in entries])


def quick_hint(entries, limit=8) -> str:
    """给交互提示用的速记符速查串"""
    parts = []
    for e in entries:
        al = e.get("alias", [])
        short = al[0] if al else e["code"].lower()
        parts.append(f"{short}→{e['code']}")
    return "  ".join(parts[:limit]) + ("  …" if len(parts) > limit else "")


# ---------------------------------------------------------------- 配置

class Config:
    def __init__(self, path: Path):
        if not path.exists():
            die(f"配置文件不存在：{path}")
        with path.open("r", encoding="utf-8") as f:
            self.raw = json.load(f)
        self.path = path
        self.dicts = self.raw.get("dicts", {})
        self.sep = self.raw.get("separator", "-")
        self.width = int(self.raw.get("serial_width", 4))
        self.scope = self.raw.get("serial_scope", ["store", "series"])
        self.segment_order = self.raw.get("segment_order", ["store", "cat", "series", "serial", "variant"])
        self.reuse_on_same_name = bool(self.raw.get("reuse_on_same_name", True))
        self.allow_custom_series = bool(self.raw.get("allow_custom_series", False))
        self.defaults = self.raw.get("defaults", {}) or {}
        self.labels = self.raw.get("labels", {})
        # 清理 _ 开头的说明字段
        self.dicts = {k: v for k, v in self.dicts.items() if not k.startswith("_")}

    def label(self, key):
        return self.labels.get(key, key)

    def entries(self, key):
        return self.dicts.get(key, [])


# ---------------------------------------------------------------- 台账

class Ledger:
    """SKU 台账：流水号计数器 + 已生成 SKU 明细。JSON 存储，原子写入 + 自动备份。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = {"version": 1, "created_at": today(), "updated_at": today(),
                     "counters": {}, "items": []}
        self._dirty = False
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self.data.update(loaded)
                self.data.setdefault("counters", {})
                self.data.setdefault("items", [])
            except Exception as e:
                die(f"台账文件损坏：{self.path}\n  {e}\n  请先修复或改名后再运行（不会被自动覆盖）")

    # ---- 计数器

    def scope_key(self, cfg: Config, rec: dict) -> str:
        return "|".join(str(rec.get(k, "")) for k in cfg.scope)

    def peek_next(self, cfg: Config, rec: dict) -> int:
        return int(self.data["counters"].get(self.scope_key(cfg, rec), 0)) + 1

    def bump(self, cfg: Config, rec: dict, serial: int) -> None:
        """推进计数器。只增不减 —— 复用旧流水号时绝不能把计数器回写成更小的值，否则后续必然撞号。"""
        key = self.scope_key(cfg, rec)
        self.data["counters"][key] = max(int(self.data["counters"].get(key, 0)), int(serial))
        self._dirty = True

    # ---- 明细

    @property
    def items(self):
        return self.data["items"]

    def exists(self, sku: str):
        for r in self.items:
            if r.get("sku") == sku:
                return r
        return None

    def find_base(self, base: str):
        for r in self.items:
            if r.get("base") == base:
                return r
        return None

    def find_by_name(self, store, cat, series, name):
        if not name:
            return None
        for r in self.items:
            if (r.get("store"), r.get("cat"), r.get("series"), r.get("name")) == (store, cat, series, name):
                return r
        return None

    def add(self, rec: dict) -> None:
        self.data["items"].append(rec)
        self._dirty = True

    # ---- 落盘

    def save(self, backup: bool = True) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        bak = None
        if backup and self.path.exists():
            bak = self.path.with_suffix(self.path.suffix + ".bak")
            shutil.copy2(self.path, bak)
        self.data["updated_at"] = today()
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
        self._dirty = False
        return str(bak) if bak else ""


# ---------------------------------------------------------------- 编码构建

def build_codes(cfg: Config, ledger: Ledger, store, cat, series, name, variants, dry_run=False):
    """解析字典 → 分配流水号 → 输出记录列表。

    返回 (records, notes)；records 每项为 dict。
    """
    notes = []
    s = resolve_value(cfg.entries("store"), store, "store")
    c = resolve_value(cfg.entries("cat"), cat, "cat")
    e = resolve_value(cfg.entries("series"), series, "series")

    if not s[0] or not c[0] or not e[0]:
        raise ResolveError("店铺/品类/系列 三项都不能为空")

    rec_seed = {"store": s[0], "cat": c[0], "series": e[0]}

    # 1) 同款复用：同店铺+品类+系列+名称 → 复用已有流水号，避免重跑撞号
    base_rec = None
    if cfg.reuse_on_same_name and name:
        prev = ledger.find_by_name(s[0], c[0], e[0], name)
        if prev:
            base_rec = prev
            notes.append(f"名称「{name}」已存在 → 复用流水号 {prev['serial']}（{prev['base']}）")

    # 2) 否则分配新流水号
    if base_rec:
        serial = int(base_rec["serial"])
    else:
        serial = ledger.peek_next(cfg, rec_seed)

    serial_str = str(serial).zfill(cfg.width)
    base = cfg.sep.join([s[0], c[0], e[0], serial_str])

    # 3) 变体展开
    vlist = []
    for v in variants or []:
        if v is None or str(v).strip() == "":
            continue
        code, vname = resolve_value(cfg.entries("variant"), v, "variant", allow_passthrough=True)
        vlist.append((code, vname))
    if not vlist:
        vlist = [(None, "")]

    records = []
    for vcode, vname in vlist:
        parts = [s[0], c[0], e[0], serial_str] + ([vcode] if vcode else [])
        sku = cfg.sep.join(parts)
        rec = {
            "sku": sku,
            "base": base,
            "store": s[0], "store_name": s[1],
            "cat": c[0], "cat_name": c[1],
            "series": e[0], "series_name": e[1],
            "serial": serial,
            "variant": vcode or "", "variant_name": vname or "",
            "name": name or "",
            "created_at": today(),
            "source": "",
        }
        exist = ledger.exists(sku)
        if exist:
            rec["status"] = "已存在"
            rec["remark"] = f"首次生成于 {exist.get('created_at', '未知')}"
        elif base_rec:
            rec["status"] = "复用"
            rec["remark"] = f"流水号复用自同名商品 {base}"
        else:
            rec["status"] = "新增"
            rec["remark"] = ""
        records.append(rec)

    return records, notes, bool(base_rec)


def commit(cfg: Config, ledger: Ledger, records, source: str, dry_run: bool):
    """把非「已存在」的记录写进台账；同一批多变体只推进一次计数器。"""
    added = 0
    bumped = set()
    for rec in records:
        if rec["status"] == "已存在":
            continue
        rec["source"] = source
        ledger.add(rec)
        added += 1
        k = ledger.scope_key(cfg, rec)
        if k not in bumped:
            ledger.bump(cfg, rec, rec["serial"])
            bumped.add(k)
    if dry_run:
        return added, False
    bak = ledger.save()
    return added, bak


# ---------------------------------------------------------------- 交互模式

def ask(cfg: Config, key: str, optional=False, multi=False):
    """交互取一个字段，支持速记符自动补全、? 查看字典、回车取默认值。"""
    entries = cfg.entries(key)
    label = cfg.label(key)
    hint = quick_hint(entries)
    default = "" if optional else str(cfg.defaults.get(key, ""))
    out(f"\n{label}（速记符：{hint}）" if hint else f"\n{label}")
    if optional:
        out("  可直接回车跳过" if not multi else "  多个用逗号分隔；可直接回车跳过")
    elif default:
        out(f"  回车采用默认值 {default}")

    while True:
        tag = f" [{default}]" if default and not multi else ""
        raw = input(f"  {label}{tag} > ").strip()
        if raw in ("?", "？"):
            rows = [[e["code"], e.get("name", ""), ", ".join(e.get("alias", []))] for e in entries]
            out(render_table(["编码", "名称", "速记符"], rows))
            continue
        if raw == "":
            if optional:
                return []
            if default:
                code, name = resolve_value(entries, default, key)
                out(f"  ✓ {label} → {code}" + (f"（{name}）" if name and name != code else ""))
                return code
            out("  × 不能为空，请重新输入（输入 ? 查看可选值）")
            continue
        try:
            if multi:
                vals = [x for x in raw.replace("，", ",").replace(" ", ",").split(",") if x.strip()]
                resolved = []
                for v in vals:
                    code, vname = resolve_value(entries, v, key, allow_passthrough=True)
                    out(f"  ✓ {label}「{v}」→ {code}" + (f"（{vname}）" if vname and vname != code else ""))
                    resolved.append(code)
                return resolved
            code, name = resolve_value(entries, raw, key, allow_passthrough=(key == "variant"))
            out(f"  ✓ {label}「{raw}」→ {code}" + (f"（{name}）" if name and name != code else ""))
            return code
        except AmbiguousError as ex:
            out(f"  × {ex}，请补全或直接输入编码")
            for code, name in ex.candidates:
                out(f"      {code}  ({name})")
        except UnknownError as ex:
            if key == "series" and cfg.allow_custom_series:
                return raw.upper()
            out(f"  × 字典里没有「{raw}」")
            out(f"      可选：{'、'.join(ex.known)}")
            out(f"      想新增系列？改 config/sku_config.json 里的 dicts.series")


def interactive(cfg: Config, ledger: Ledger, dry_run: bool, assume_yes: bool):
    out("=" * 68)
    out("  SKU 编码生成器 · 交互模式")
    out(f"  台账：{ledger.path}  （已有 {len(ledger.items)} 条 SKU）")
    out("=" * 68)

    while True:
        store = ask(cfg, "store")
        cat = ask(cfg, "cat")
        series = ask(cfg, "series")
        name = input("\n  商品名称（可留空）> ").strip()
        variants = ask(cfg, "variant", optional=True, multi=True)

        try:
            records, notes, _ = build_codes(cfg, ledger, store, cat, series, name, variants, dry_run)
        except ResolveError as ex:
            out(f"\n  × 失败：{ex}")
            continue

        out("\n" + "-" * 68)
        rows = [[r["sku"], r["name"] or "-", vlabel(r), r["status"], r["remark"] or "-"] for r in records]
        out(render_table(["SKU", "名称", "变体", "状态", "备注"], rows))
        for n in notes:
            out("  提示：" + n)

        new_cnt = sum(1 for r in records if r["status"] != "已存在")
        if dry_run:
            out("\n  [dry-run] 未写入台账。")
        elif new_cnt == 0:
            out("\n  本次没有新 SKU 需要写入。")
        else:
            if not assume_yes:
                ans = input(f"\n  写入台账？({new_cnt} 条新 SKU) [Y/n] > ").strip().lower()
                if ans not in ("", "y", "yes", "是"):
                    out("  已取消，台账未改动。")
                    continue
            added, bak = commit(cfg, ledger, records, "interactive", False)
            out(f"  ✓ 已写入 {added} 条。台账：{ledger.path}")
            if bak:
                out(f"    备份：{bak}")

        again = input("\n  继续生成下一个？[Y/n] > ").strip().lower()
        if again not in ("", "y", "yes", "是"):
            break

    out("\n完成。")


# ---------------------------------------------------------------- 批量模式

def _match_header(name: str):
    n = str(name).strip().lower()
    for key, alts in HEADER_ALIASES.items():
        for a in alts:
            if n == a.lower() or (len(n) >= 2 and n in a.lower()):
                return key
    return None


def read_table(path: Path):
    """读 CSV / TSV / XLSX，返回 (表头, 数据行列表)"""
    suffix = path.suffix.lower()
    if suffix in (".csv", ".tsv", ".txt"):
        delim = "\t" if suffix == ".tsv" else ","
        for enc in ("utf-8-sig", "gbk", "utf-8"):
            try:
                with path.open("r", encoding=enc, newline="") as f:
                    rows = list(csv.reader(f, delimiter=delim))
                break
            except UnicodeDecodeError:
                continue
        else:
            die(f"无法解码 CSV：{path}（试过 utf-8-sig / gbk / utf-8）")
        rows = [r for r in rows if any(str(c).strip() for c in r)]
        if not rows:
            die(f"空表格：{path}")
        return rows[0], rows[1:]

    if suffix in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError:
            die("读取 XLSX 需要 openpyxl。两个办法：\n"
                f"  ① 用带依赖的解释器跑：\"{VENV_PY}\" \"{SCRIPT_DIR / 'sku_gen.py'}\" -i \"{path}\"\n"
                f"  ② 把表格另存为 CSV 后重跑")
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        ws = wb.active
        rows = []
        for row in ws.iter_rows(values_only=True):
            vals = ["" if v is None else v for v in row]
            if any(str(v).strip() for v in vals):
                rows.append([str(v) for v in vals])
        wb.close()
        if not rows:
            die(f"空表格：{path}")
        return rows[0], rows[1:]

    die(f"不支持的文件类型：{suffix}（支持 .csv / .tsv / .xlsx）")


def write_table(path: Path, headers, rows):
    suffix = path.suffix.lower()
    path.parent.mkdir(parents=True, exist_ok=True)
    if suffix in (".csv", ".tsv"):
        delim = "\t" if suffix == ".tsv" else ","
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=delim)
            w.writerow(headers)
            w.writerows(rows)
        return
    if suffix in (".xlsx", ".xlsm"):
        try:
            import openpyxl
            from openpyxl.styles import Alignment, Font, PatternFill
        except ImportError:
            die("写出 XLSX 需要 openpyxl，请改用 .csv，或用带依赖的解释器：\n"
                f"  \"{VENV_PY}\" \"{SCRIPT_DIR / 'sku_gen.py'}\" -i <输入> -o <输出.xlsx>")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "SKU"
        ws.append(list(headers))
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="4472C4")
            c.alignment = Alignment(horizontal="center", vertical="center")
        fills = {"新增": "E2EFDA", "复用": "FFF2CC", "已存在": "F2F2F2", "失败": "FCE4E4"}
        for r in rows:
            ws.append(list(r))
            status = str(r[headers.index("状态")]) if "状态" in headers else ""
            if status in fills:
                fill = PatternFill("solid", fgColor=fills[status])
                for c in ws[ws.max_row]:
                    c.fill = fill
                    c.alignment = Alignment(vertical="center")
        for i, h in enumerate(headers, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = max(
                10, min(30, max(cjk_width(h), *(cjk_width(r[i - 1]) for r in rows)) + 2) if rows else 12)
        ws.freeze_panes = "A2"
        wb.save(path)
        return
    die(f"输出格式不支持：{suffix}（用 .csv 或 .xlsx）")


def batch(cfg: Config, ledger: Ledger, in_path: Path, out_path: Path, dry_run: bool, sheet_limit=None):
    headers, rows = read_table(in_path)
    mapping = {}
    for idx, h in enumerate(headers):
        key = _match_header(h)
        if key and key not in mapping:
            mapping[key] = idx

    if "quick" in mapping and "series" not in mapping:
        out(f"  检测到「速记」列，将按「店铺 品类 系列 变体」顺序解析")
    if not mapping or ("series" not in mapping and "quick" not in mapping):
        die(f"输入表缺少可用列。表头：{headers}\n"
            f"  至少需要「系列」（或「速记」）列，另可含 名称/店铺/品类/变体。支持中英文表头。")

    out(f"  读入 {len(rows)} 行，识别到列："
        + "、".join(f"{k}→第{v + 1}列" for k, v in mapping.items()))
    for k in ("store", "cat"):
        if k not in mapping and cfg.defaults.get(k):
            out(f"  未提供「{cfg.label(k)}」列 → 默认使用 {cfg.defaults[k]}（可在 config 的 defaults 里改）")

    result_rows = []
    errors = []
    seq = 0
    batch_added = 0

    for i, row in enumerate(rows, start=1):
        def cell(key, default=""):
            idx = mapping.get(key)
            if idx is None or idx >= len(row):
                return default
            return str(row[idx]).strip()

        name = cell("name")
        # 缺列时用 config.defaults 兜底（仅当整列不存在，避免把空单元格静默填成默认值）
        store = cell("store") or (str(cfg.defaults.get("store", "")) if "store" not in mapping else "")
        cat = cell("cat") or (str(cfg.defaults.get("cat", "")) if "cat" not in mapping else "")
        series = cell("series")
        variant_raw = cell("variant")
        quick = cell("quick")

        # 「速记」列兜底：拆成 店铺 品类 系列 变体
        if quick and not series:
            tokens = [t for t in quick.replace("，", " ").replace(",", " ").replace("-", " ").split() if t]
            if len(tokens) >= 3:
                store, cat, series = tokens[0], tokens[1], tokens[2]
                if len(tokens) >= 4:
                    variant_raw = tokens[3]
            elif len(tokens) == 2:
                series, variant_raw = tokens[0], tokens[1]
            elif len(tokens) == 1:
                series = tokens[0]

        variants = [v for v in variant_raw.replace("，", ",").replace(" ", ",").split(",") if v.strip()]

        try:
            records, notes, _ = build_codes(cfg, ledger, store, cat, series, name, variants, dry_run)
        except ResolveError as ex:
            msg = str(ex)
            if isinstance(ex, AmbiguousError):
                msg = f"{ex.raw} 歧义 → 候选：" + "、".join(c for c, _ in ex.candidates)
            errors.append({"row": i, "reason": msg,
                           "raw": f"店铺={store or '-'} 品类={cat or '-'} 系列={series or '-'} "
                                  f"变体={variant_raw or '-'} 名称={name or '-'}"})
            seq += 1
            result_rows.append([seq, "", "", name, store, cat, series, "", variant_raw, "失败", msg])
            continue

        added, bak = commit(cfg, ledger, records, f"batch:{in_path.name}", dry_run)
        batch_added += added
        for rec in records:
            seq += 1
            result_rows.append([seq, rec["sku"], rec["base"], rec["name"], rec["store"], rec["cat"],
                                rec["series"], rec["serial"], vlabel(rec), rec["status"], rec["remark"]])

    write_table(out_path, OUT_HEADERS, result_rows)
    out("\n" + "-" * 68)
    stat = {}
    for r in result_rows:
        stat[r[9]] = stat.get(r[9], 0) + 1
    out(f"  输出 {len(result_rows)} 条 SKU → {out_path}")
    out("  明细：" + "，".join(f"{k} {v}" for k, v in stat.items()))
    if errors:
        out(f"\n  ⚠ {len(errors)} 行解析失败（已写入输出表「状态=失败」，原因是字典里没有对应值）：")
        for e in errors[:10]:
            out(f"    第 {e['row']} 行 {e['raw']}  →  {e['reason']}")
        if len(errors) > 10:
            out(f"    …另有 {len(errors) - 10} 行")
        out(f"  修好输入的速记符，或把新系列加进 {cfg.path}")
    if dry_run:
        out("\n  [dry-run] 台账未写入（输出表仅作预览）。")


# ---------------------------------------------------------------- 台账子命令

def show_list(cfg: Config, ledger: Ledger, limit=200):
    items = list(reversed(ledger.items))
    if not items:
        out("台账为空：还没有生成过任何 SKU。")
        return
    rows = [[r.get("sku", ""), r.get("name", "") or "-", r.get("store", ""), r.get("series", ""),
             r.get("variant", "") or "-", r.get("created_at", "")] for r in items[:limit]]
    out(render_table(["SKU", "名称", "店铺", "系列", "变体", "生成时间"], rows))
    out(f"\n共 {len(items)} 条" + (f"（只显示最近 {limit} 条）" if len(items) > limit else ""))


def show_find(ledger: Ledger, kw: str):
    kw_low = kw.lower()
    hits = [r for r in ledger.items if any(kw_low in str(r.get(f, "")).lower()
                                          for f in ("sku", "name", "store", "series", "variant", "series_name"))]
    if not hits:
        out(f"没找到包含「{kw}」的 SKU。")
        return
    rows = [[r.get("sku", ""), r.get("name", "") or "-", r.get("status", ""), r.get("created_at", "")] for r in hits]
    out(render_table(["SKU", "名称", "状态", "生成时间"], rows))
    out(f"\n命中 {len(hits)} 条")


def show_stats(cfg: Config, ledger: Ledger):
    items = ledger.items
    if not items:
        out("台账为空。")
        return
    out(f"台账：{ledger.path}")
    out(f"SKU 总数：{len(items)}    基础编码数：{len(set(r.get('base') for r in items))}")
    out(f"时间跨度：{items[0].get('created_at','?')[:10]} → {items[-1].get('created_at','?')[:10]}")

    def group(field, title):
        cnt = {}
        for r in items:
            cnt[r.get(field, "") or "(空)"] = cnt.get(r.get(field, "") or "(空)", 0) + 1
        rows = sorted(cnt.items(), key=lambda x: -x[1])
        out(f"\n【{title}】")
        out(render_table(["值", "数量"], rows[:20]))

    group("store", "按店铺")
    group("series", "按系列")
    out("\n【流水号计数器】")
    rows = [[k, v] for k, v in sorted(ledger.data.get("counters", {}).items())]
    out(render_table(["作用域（店铺|系列）", "当前最大值"], rows) if rows else "  （空）")


def export_ledger(ledger: Ledger, path: Path):
    rows = [[r.get("sku", ""), r.get("base", ""), r.get("name", ""), r.get("store", ""), r.get("store_name", ""),
             r.get("cat", ""), r.get("cat_name", ""), r.get("series", ""), r.get("series_name", ""),
             r.get("serial", ""), r.get("variant", ""), r.get("variant_name", ""),
             r.get("created_at", ""), r.get("source", "")] for r in ledger.items]
    headers = ["SKU", "基础编码", "名称", "店铺", "店铺全称", "品类", "品类名", "系列", "系列全称",
               "流水号", "变体", "变体名", "生成时间", "来源"]
    write_table(path, headers, rows)
    out(f"已导出 {len(rows)} 条 → {path}")


# ---------------------------------------------------------------- 主程序

def setup_console():
    """Windows 控制台中文乱码修复：把控制台代码页切到 UTF-8，并同步输出流编码。"""
    if os.name == "nt" and sys.stdout.isatty():
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main():
    setup_console()

    ap = argparse.ArgumentParser(
        prog="sku_gen.py",
        description="SKU 编码自动生成器（速记符补全 + 台账防重）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例：
  python sku_gen.py                              交互模式
  python sku_gen.py -s mts -c tf -e s86 -v r,b   单条生成（速记符自动补全）
  python sku_gen.py -i 商品表.xlsx -o 结果.xlsx    批量
  python sku_gen.py --list / --find SS86 / --stats / --export out.csv
""")
    ap.add_argument("-s", "--store", help="店铺（速记符，如 mts）")
    ap.add_argument("-c", "--cat", help="品类（如 tf）")
    ap.add_argument("-e", "--series", help="系列（如 s86）")
    ap.add_argument("-v", "--variant", help="变体，多个用逗号分隔（如 r,b,k）")
    ap.add_argument("-n", "--name", default="", help="商品名称")
    ap.add_argument("-i", "--input", help="批量模式输入表（.csv/.tsv/.xlsx）")
    ap.add_argument("-o", "--output", help="批量模式输出表（默认 <输入名>_SKU.csv）")
    ap.add_argument("--reuse-base", help="在已有基础编码下追加变体，如 MTS-TF-SS86-0003")
    ap.add_argument("--dry-run", action="store_true", help="只预览，不写台账")
    ap.add_argument("-y", "--yes", action="store_true", help="交互模式跳过写入确认")
    ap.add_argument("--list", action="store_true", help="列出台账明细")
    ap.add_argument("--find", metavar="关键词", help="在台账中搜索")
    ap.add_argument("--stats", action="store_true", help="台账统计")
    ap.add_argument("--export", metavar="文件", help="导出台账（.csv/.xlsx）")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG), help="字典配置文件路径")
    ap.add_argument("--ledger", default=str(DEFAULT_LEDGER), help="台账文件路径")
    args = ap.parse_args()

    cfg = Config(Path(args.config).resolve())
    ledger = Ledger(Path(args.ledger).resolve())

    # ---- 台账类子命令
    if args.list:
        show_list(cfg, ledger)
        return
    if args.find:
        show_find(ledger, args.find)
        return
    if args.stats:
        show_stats(cfg, ledger)
        return
    if args.export:
        export_ledger(ledger, Path(args.export).resolve())
        return

    # ---- 批量模式
    if args.input:
        in_path = Path(args.input).resolve()
        if not in_path.exists():
            die(f"输入文件不存在：{in_path}")
        out_path = Path(args.output).resolve() if args.output else in_path.with_name(in_path.stem + "_SKU.csv")
        out(f"批量模式：{in_path.name} → {out_path.name}" + ("  [dry-run]" if args.dry_run else ""))
        batch(cfg, ledger, in_path, out_path, args.dry_run)
        return

    # ---- 单条生成
    if any([args.store, args.cat, args.series, args.reuse_base]):
        variants = [v for v in str(args.variant).replace("，", ",").split(",")] if args.variant else []
        reuse = None
        if args.reuse_base:
            reuse = ledger.find_base(args.reuse_base.strip().upper())
            if not reuse:
                die(f"台账里没有基础编码 {args.reuse_base}")
        if reuse:
            store, cat, series = reuse["store"], reuse["cat"], reuse["series"]
        else:
            if not (args.store and args.cat and args.series):
                die("单条模式需要同时给出 店铺(-s)、品类(-c)、系列(-e)；或用 --reuse-base 指定已有基础编码")
            store, cat, series = args.store, args.cat, args.series

        try:
            if reuse:
                serial_str = str(reuse["serial"]).zfill(cfg.width)
                base = reuse["base"]
                records = []
                vlist = [v for v in variants if str(v).strip()] or [None]
                for v in vlist:
                    vcode, vname = (None, "") if v is None else resolve_value(
                        cfg.entries("variant"), v, "variant", allow_passthrough=True)
                    parts = [store, cat, series, serial_str] + ([vcode] if vcode else [])
                    sku = cfg.sep.join(parts)
                    ex = ledger.exists(sku)
                    records.append({
                        "sku": sku, "base": base, "store": store, "cat": cat, "series": series,
                        "serial": reuse["serial"], "variant": vcode or "", "variant_name": vname or "",
                        "name": args.name or reuse.get("name", ""), "created_at": today(),
                        "source": "cli", "status": "已存在" if ex else "新增",
                        "remark": f"追加到已有基础编码 {base}" if not ex else "已存在",
                    })
            else:
                records, notes, _ = build_codes(cfg, ledger, store, cat, series, args.name, variants, args.dry_run)
        except ResolveError as ex:
            die(str(ex))

        rows = [[r["sku"], r["name"] or "-", vlabel(r), r["status"], r["remark"] or "-"] for r in records]
        out("")
        out(render_table(["SKU", "名称", "变体", "状态", "备注"], rows))

        new_cnt = sum(1 for r in records if r["status"] != "已存在")
        if args.dry_run:
            out("\n[dry-run] 未写入台账。")
        elif new_cnt:
            added, bak = commit(cfg, ledger, records, "cli", False)
            out(f"\n✓ 已写入 {added} 条 → {ledger.path}")
            if bak:
                out(f"  备份：{bak}")
        else:
            out("\n没有新增（全部已存在），台账未改动。")
        return

    # ---- 默认：交互模式
    interactive(cfg, ledger, args.dry_run, args.yes)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        out("\n已中断。")
        sys.exit(130)
