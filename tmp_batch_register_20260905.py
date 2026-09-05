from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

PYTHON = r"C:\Users\shana\AppData\Local\Programs\Python\Python312\python.exe"
LEDGER = Path(r"C:\Users\shana\Desktop\62店8月-采购登记表.xlsx")
SRC = Path(r"C:\Users\shana\Downloads\新建文件夹")
OCR_JSON = Path(r"C:\Users\shana\AppData\Local\Temp\purchase_ocr_20260905.json")
APPEND_WRAPPER = Path(r"C:\Users\shana\Documents\GitHub\MyE-C-skill\tmp_append_no_delete.py")
VERIFY = Path(r"C:\Users\shana\.codex\skills\purchase-ledger-registration\scripts\verify_ledger.py")
SHOT_ROOT = Path(r"C:\Users\shana\Desktop\62店台账备份\进货表备份\截图备份")
XLSX_ROOT = Path(r"C:\Users\shana\Desktop\62店台账备份\进货表备份\Excel备份")
STATE = Path(r"C:\Users\shana\AppData\Local\Temp\purchase_batch_20260905_state.json")

LI_HUI = "亲情卡(李辉（进货）(李金贤))"
LI_YONGJUN = "亲情卡(李永军(李永军))"

# (支付图序号, 产品/订单图序号, 净付款额覆盖, 商品名覆盖, 净额构成)
SPECS = [
    (1, 2, None, "银河玩具社彩透威震天mini08C+BM声波积木人仔限定版套装+SD01B白色精涂版声波", [80.36, 48.03, 68.11]),
    (3, 4, None, None, None), (5, 6, None, None, None), (7, 8, None, None, None),
    (9, 10, None, None, None), (11, 12, None, None, None), (13, 14, None, None, None),
    (15, 16, None, None, None),
    (17, 18, None, "JCS001惊天雷机器人变形金刚可动手办×5", [63.48] * 5),
    (19, 20, None, "JCS001惊天雷机器人变形金刚可动手办×3", [63.48] * 3),
    (21, 22, None, "手办专拍", None),
    (23, 24, None, "械壳工作室MSS-01天狼星A版红蜘蛛×2+NE01手枪威", [323.27, 229.06]),
    (25, 26, None, None, None), (27, 28, None, None, None),
    (29, 30, 125.06, "银河玩具社彩透红蜘蛛鬼魂红闹翻天+魔方MS-G01X金属色大头阿尔西", [56.14, 68.92]),
    (31, 32, None, None, None), (33, 34, None, None, None), (35, 36, None, None, None),
    (37, 38, None, None, None), (39, 40, None, None, None),
    (41, 42, None, "银河玩具社彩透红翼路西法+银河玩具社镜像惊天雷+银河玩具社mini14J翻云雨+孩之宝天尊世代战车队诈骗+银河玩具社紫透色闹翻天", [56.30, 55.14, 61.93, 267.92, 56.31]),
    (43, 44, None, None, None), (45, 46, None, "Threezero变形金刚漫画版MDLX擎天柱", [583.00]),
    (47, 48, None, None, None),
    (49, 50, None, "优质版KO变形模型SS86雷霆司令官×4+TOHO Seeker小队雷公SS86惊天雷×4", [248.90, 248.90]),
    (51, 52, None, None, None), (53, 54, None, None, None), (55, 56, None, None, None),
    (57, 58, None, None, None),
    (59, 60, None, "吴医生DWE68黑瘟疫+DWE69黑横炮套装", [154.84]),
    (61, 62, None, None, None), (63, 64, None, None, None),
    (65, 66, None, "吴医生MC-03T彩透色小怪兽", [135.00]),
    (67, 68, None, None, None), (69, 70, None, "DNA DK-61传世进化引天行配件包", [223.00]),
    (71, 72, None, None, None),
    (73, 74, None, "银河玩具社金属色小枪威mini08 EX限定版", [79.83]),
    (75, 76, None, None, None), (77, 78, None, None, None), (79, 80, None, None, None),
    (81, 82, None, None, None), (83, 84, None, None, None), (85, 86, None, None, None),
    (87, 88, None, None, None),
    # 89为用户确认整单退款，明确跳过。
    (90, 91, None, None, None), (92, 93, None, None, None),
    (94, 95, None, "银河玩具社警车烟幕蓝霹雳三兄弟口袋金刚", [45.00]),
    (96, None, None, "散单运费-顺丰速运", None),
    (97, 98, None, None, None), (99, 100, None, None, None),
    (101, 102, None, "银河玩具社MINI08B破坏大帝邪恶轴心枪威+MINI08JX毁灭者镜像枪威+银河玩具社二次元色擎天小柱", [77.77, 78.83, 62.00]),
    (103, None, None, "变形金刚CT10擎天柱线下进货", None),
    (104, 105, None, None, None), (106, 107, None, None, None), (108, 109, None, None, None),
    (110, 111, None, "新成澳HP01横炮战舞者变形金刚", [66.00]),
    (112, 113, None, None, None), (114, 115, None, None, None),
    (116, 117, 365.87, "优质版KO变形模型SS86雷霆司令官×3+TOHO Seeker小队雷公SS86惊天雷×3", [182.94, 182.93]),
    (118, 119, None, "X-TRANSBOTS X社MX-32直升机刀刃守护神", [609.00]),
    (120, 121, 281.56, "Newage NA H21B音板再版", [281.56]),
    (122, 123, 219.85, "DNA DK-76领袖纪元星际擎天柱热破配件包", [219.85]),
    (124, 125, None, None, None),
    (126, 127, 41.31, "星克战警变形奶茶咖啡武士+麦英雄变形奶茶咖啡武士", [20.65, 20.66]),
    (128, 129, None, None, None), (130, 131, None, None, None),
    (132, 133, None, "TFC恶魔五合体撒旦鬼S-02求雨鬼玛蒙", [325.00]),
    (134, 135, None, None, None),
    (136, 137, None, "新成澳HP-01电影版横炮+TFC求雨鬼合体S05暴力龙双头龙杰奇洛", [64.13, 380.67]),
]


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text).replace("&middot;", "·")


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def cellimage_manifest(path: Path) -> dict[str, tuple[str, str, int]]:
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(path) as z:
        rel_name = "xl/_rels/cellimages.xml.rels"
        if rel_name not in z.namelist():
            return {}
        result = {}
        for rel in ET.fromstring(z.read(rel_name)):
            rid = rel.attrib.get("Id", "")
            target = rel.attrib.get("Target", "")
            if target.startswith("../"):
                target = "xl/" + target[3:]
            elif target.startswith("/"):
                target = target[1:]
            elif not target.startswith("xl/"):
                target = "xl/" + target
            data = z.read(target)
            result[rid] = (target, hashlib.md5(data).hexdigest(), len(data))
        return result


def extract_between(tokens, start_names, end_names):
    for start in start_names:
        if start in tokens:
            i = tokens.index(start) + 1
            vals = []
            while i < len(tokens) and tokens[i] not in end_names:
                vals.append(tokens[i])
                i += 1
            return compact("".join(vals))
    return ""


def parse_records():
    raw = json.loads(OCR_JSON.read_text(encoding="utf-8"))
    if len(raw) != 137:
        raise RuntimeError(f"OCR图片数异常: {len(raw)}")
    records = []
    used = set()
    for pay_idx, prod_idx, net_override, name_override, parts in SPECS:
        pay = raw[pay_idx - 1]
        pt = pay["text"]
        joined = " | ".join(pt)
        if "账单详情" not in pt:
            raise RuntimeError(f"支付图内容断言失败 #{pay_idx}: {pay['name']}")
        date_m = re.search(r"2026-\d{2}-\d{2}\s*\d{2}:\d{2}:\d{2}", joined)
        if not date_m:
            raise RuntimeError(f"支付时间不可读 #{pay_idx}")
        dt_raw = re.sub(r"\s+", "", date_m.group(0))
        dt = dt_raw[:10] + "T" + dt_raw[-8:]
        amount = None
        for token in pt:
            if re.fullmatch(r"\d{1,3}(?:,\d{3})*(?:\.\d{2})", token):
                amount = float(token.replace(",", ""))
                break
        if amount is None:
            raise RuntimeError(f"支付金额不可读 #{pay_idx}")
        net = float(net_override if net_override is not None else amount)
        name = name_override or extract_between(pt, ["商品说明", "交易详情"], {"订单号", "商家订单号", "账单管理", "支付奖励", "收单机构", "付款备注"})
        if not name:
            raise RuntimeError(f"商品名称不可读 #{pay_idx}")
        if "拼多多平台商户" in pt:
            unit = "拼多多"
        elif "顺丰速运" in pt:
            unit = "顺丰速运"
        elif "收钱码收款" in pt:
            unit = "个人收款"
        elif "淘" in pt and "闲鱼" not in pt[:pt.index("全部账单") + 2] if "全部账单" in pt else False:
            unit = "淘宝"
        elif "淘" in pt and pt[pt.index("全部账单") + 1:pt.index("全部账单") + 3] == ["淘"] if "全部账单" in pt else False:
            unit = "淘宝"
        else:
            unit = "闲鱼"
        # 明确的淘宝账单序号。
        if pay_idx in {17, 19, 59, 73}:
            unit = "淘宝"
        method = LI_YONGJUN if "李永军" in joined else LI_HUI
        series = "其他" if any(k in name for k in ["绝区零", "艾莲", "美术教师", "少女前线", "可露凯", "手办专拍", "散单运费"]) else "变形金刚"
        prod = raw[prod_idx - 1] if prod_idx else None
        if prod:
            prod_joined = compact(" ".join(prod["text"]))
            if pay_idx != 21 and not any(k in prod_joined for k in ["订单编号", "订单详情", "待评价", "待收货", "退款成功", "交易成功", "成交价", "已付款", "卖家已发货"]):
                raise RuntimeError(f"产品/订单图内容断言失败 #{prod_idx}: {prod['name']}")
            # T200P订单以订单编号或交易号尾段交叉核对；手办专拍聊天图用卖家掩码+金额核对。
            merchant = extract_between(pt, ["商家订单号"], {"账单管理", "反馈与投诉"})
            digits = re.sub(r"\D", "", merchant)
            if unit in {"闲鱼", "淘宝"} and pay_idx not in {21, 59, 73} and digits and digits[-12:] not in prod_joined:
                raise RuntimeError(f"订单号配对失败 pay#{pay_idx}/prod#{prod_idx}: {digits[-12:]}")
            if pay_idx in {59, 73} and f"{net:.2f}" not in prod_joined:
                raise RuntimeError(f"淘宝订单页金额配对失败 pay#{pay_idx}/prod#{prod_idx}")
            if unit == "拼多多" and digits and digits[-12:] not in prod_joined:
                raise RuntimeError(f"拼多多商户单号配对失败 pay#{pay_idx}/prod#{prod_idx}: {digits[-12:]}")
            if pay_idx == 21 and not ("怪***d" in joined and "怪***d" in " ".join(prod["text"]) and "200.00" in " ".join(prod["text"])):
                raise RuntimeError("手办专拍聊天图无法可靠配对")
        if parts and abs(sum(parts) - net) > 0.011:
            raise RuntimeError(f"金额构成不平 pay#{pay_idx}: {sum(parts)} != {net}")
        suffix_source = extract_between(pt, ["商家订单号"], {"账单管理", "反馈与投诉"}) or extract_between(pt, ["订单号"], {"商家订单号", "账单管理"})
        suffix = re.sub(r"\D", "", suffix_source)[-6:] or f"p{pay_idx}"
        records.append({
            "pay_idx": pay_idx, "prod_idx": prod_idx, "dt": dt,
            "original_amount": amount, "amount": round(net, 2), "name": name,
            "series": series, "unit": unit, "method": method, "suffix": suffix,
            "pay_source": str(SRC / pay["name"]),
            "prod_source": str(SRC / prod["name"]) if prod else None,
            "partial_refund": net_override is not None,
        })
        used.add(pay_idx)
        if prod_idx:
            used.add(prod_idx)
    expected_unused = {89}
    actual_unused = set(range(1, 138)) - used
    if actual_unused != expected_unused:
        raise RuntimeError(f"截图使用范围异常，未使用={sorted(actual_unused)}")
    return records


def check_write_lock(path: Path):
    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    OPEN_EXISTING = 3
    handle = ctypes.windll.kernel32.CreateFileW(str(path), GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, None)
    if handle == ctypes.c_void_p(-1).value:
        raise PermissionError(f"台账被锁定，Win32错误={ctypes.get_last_error()}")
    ctypes.windll.kernel32.CloseHandle(handle)


def safe_component(value: str, limit=42):
    value = re.sub(r'[<>:"/\\|?*]', "-", value)
    return value[:limit].strip(" .-") or "采购"


def backup_screens(rec):
    day = rec["dt"][:10].replace("-", "")
    folder = SHOT_ROOT / f"{day}-{safe_component(rec['name'])}-{rec['suffix']}-{rec['series']}"
    folder.mkdir(parents=True, exist_ok=True)
    copies = {}
    for kind in ("prod", "pay"):
        src = rec[f"{kind}_source"]
        if not src:
            continue
        srcp = Path(src)
        dest = folder / srcp.name
        if dest.exists() and md5_file(dest) != md5_file(srcp):
            raise RuntimeError(f"截图备份路径已有异内容: {dest}")
        if not dest.exists():
            shutil.copy2(srcp, dest)
        if md5_file(dest) != md5_file(srcp):
            raise RuntimeError(f"截图备份MD5失败: {srcp}")
        copies[kind] = str(dest)
    return str(folder), copies


def backup_excel():
    XLSX_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dest = XLSX_ROOT / f"62店8月-采购登记表_{stamp}.xlsx"
    shutil.copy2(LEDGER, dest)
    if md5_file(dest) != md5_file(LEDGER):
        raise RuntimeError("Excel备份MD5失败")
    return str(dest)


def workbook_tail():
    import openpyxl
    wb = openpyxl.load_workbook(LEDGER, read_only=True, data_only=False)
    ws = wb["自发货采购登记表"]
    row = ws.max_row
    while row > 1 and all(ws.cell(row, c).value is None for c in range(1, 21)):
        row -= 1
    result = (row, int(ws.cell(row, 1).value))
    wb.close()
    return result


def existing_keys():
    import openpyxl
    wb = openpyxl.load_workbook(LEDGER, read_only=True, data_only=False)
    ws = wb["自发货采购登记表"]
    keys = set()
    for r in range(2, ws.max_row + 1):
        dt = ws.cell(r, 14).value or ws.cell(r, 2).value
        amt = ws.cell(r, 13).value
        if hasattr(dt, "isoformat"):
            dt = dt.isoformat(timespec="seconds")
        if dt and amt is not None:
            keys.add((str(dt).replace(" ", "T"), round(float(amt), 2)))
    wb.close()
    return keys


def verify(expects=None):
    cmd = [PYTHON, str(VERIFY), str(LEDGER)]
    for row, col, path in (expects or []):
        cmd += ["--expect", f"{row},{col},{path}"]
    return subprocess.run(cmd, check=True, text=True, encoding="utf-8", errors="replace", capture_output=True).stdout


def preflight(records):
    if len(records) != 69:
        raise RuntimeError(f"记录数异常: {len(records)}")
    for rec in records:
        for key in ["pay_source", "prod_source"]:
            if rec[key] and not Path(rec[key]).is_file():
                raise FileNotFoundError(rec[key])
    check_write_lock(LEDGER)
    output = verify()
    row, seq = workbook_tail()
    dup = [(r["dt"], r["amount"], r["name"]) for r in records if (r["dt"], r["amount"]) in existing_keys()]
    if dup:
        raise RuntimeError("发现疑似重复记录: " + json.dumps(dup, ensure_ascii=False))
    summary = {
        "records": len(records), "start_row": row + 1, "start_seq": seq + 1,
        "end_row": row + len(records), "end_seq": seq + len(records),
        "partial_refunds": [r["pay_idx"] for r in records if r["partial_refund"]],
        "pay_only": [r["pay_idx"] for r in records if not r["prod_source"]],
        "skipped": 89, "verify": output.strip().splitlines()[-1],
        "historical_cellimages": len(cellimage_manifest(LEDGER)),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def run(records):
    baseline = cellimage_manifest(LEDGER)
    row, seq = workbook_tail()
    state = {"started": datetime.now().isoformat(), "records": [], "baseline_cellimages": len(baseline)}
    if STATE.exists():
        old = json.loads(STATE.read_text(encoding="utf-8"))
        done_keys = {(x["dt"], x["amount"]) for x in old.get("records", []) if x.get("verified")}
        state = old
    else:
        done_keys = set()
    for idx, rec in enumerate(records, 1):
        if (rec["dt"], rec["amount"]) in done_keys:
            print(f"[{idx:02d}/{len(records)}] 已完成，跳过 {rec['dt']} {rec['amount']}", flush=True)
            continue
        check_write_lock(LEDGER)
        folder, copies = backup_screens(rec)
        excel_backup = backup_excel()
        old_row, old_seq = workbook_tail()
        if old_row != row or old_seq != seq:
            row, seq = old_row, old_seq
        dt = datetime.fromisoformat(rec["dt"])
        eta = dt + timedelta(days=3)
        data = [
            seq + 1, rec["dt"], None, "备货进货", rec["series"], rec["name"], rec["unit"], 1,
            rec["amount"], rec["amount"], "刘宇彤", rec["method"], rec["amount"], rec["dt"],
            eta.isoformat(timespec="seconds"), None, None, None, eta.isoformat(timespec="seconds"), "刘宇彤",
        ]
        cmd = [PYTHON, str(APPEND_WRAPPER), "--file", str(LEDGER), "--data", json.dumps(data, ensure_ascii=False)]
        expects = []
        if copies.get("prod"):
            cmd += ["--img-prod", copies["prod"]]
            expects.append((row + 1, 16, copies["prod"]))
        cmd += ["--img-pay", copies["pay"]]
        expects.append((row + 1, 18, copies["pay"]))
        proc = subprocess.run(cmd, check=True, text=True, encoding="utf-8", errors="replace", capture_output=True)
        new_row, new_seq = workbook_tail()
        if (new_row, new_seq) != (row + 1, seq + 1):
            raise RuntimeError(f"自动追加位置异常: {(new_row,new_seq)} != {(row+1,seq+1)}")
        verify_out = verify(expects)
        if cellimage_manifest(LEDGER) != baseline:
            raise RuntimeError(f"row{new_row} 后历史cellimages字节或映射改变")
        entry = {
            **rec, "row": new_row, "seq": new_seq, "screenshot_folder": folder,
            "prod_backup": copies.get("prod"), "pay_backup": copies["pay"],
            "excel_backup": excel_backup, "verified": True,
            "verify_summary": verify_out.strip().splitlines()[-1],
            "append_output": proc.stdout.strip().splitlines(),
        }
        state["records"].append(entry)
        state["last_updated"] = datetime.now().isoformat()
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        row, seq = new_row, new_seq
        print(f"[{idx:02d}/{len(records)}] row{row} seq{seq} {rec['dt']} CNY {rec['amount']:.2f} {rec['name']} | VERIFY OK", flush=True)
    final_out = verify()
    state["completed"] = datetime.now().isoformat()
    state["final_row"] = row
    state["final_seq"] = seq
    state["final_verify"] = final_out.strip().splitlines()
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"completed": len(state["records"]), "final_row": row, "final_seq": seq, "state": str(STATE)}, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["preflight", "run"])
    args = ap.parse_args()
    recs = parse_records()
    if args.phase == "preflight":
        preflight(recs)
    else:
        run(recs)
