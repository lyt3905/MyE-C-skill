# -*- coding: utf-8 -*-
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta

ROOT = r"C:\Users\shana\Documents\GitHub\MyE-C-skill\purchase-ledger-registration"
PYTHON = r"C:\Users\shana\AppData\Local\Programs\Python\Python312\python.exe"
LEDGER = r"C:\Users\shana\Desktop\62店8月-采购登记表.xlsx"
APPEND = os.path.join(ROOT, "scripts", "append_purchase_row.py")
VERIFY = os.path.join(ROOT, "scripts", "verify_ledger.py")
SHOT_ROOT = r"C:\Users\shana\Desktop\62店台账备份\进货表备份\截图备份"
XLSX_ROOT = r"C:\Users\shana\Desktop\62店台账备份\进货表备份\Excel备份"
STATE = os.path.join(ROOT, "scripts", ".batch_aug18_21_state.json")
SRC = r"C:\Users\shana\AppData\Local\Temp"

LI_HUI = "亲情卡(李辉（进货）(李金贤))"
LI_MAN = "亲情卡(李慢慢(李慢慢))"


def src(name):
    return os.path.join(SRC, name)


RECORDS = [
    dict(dt="2026-08-18T13:05:38", amount=210, series="变形金刚", name="铁工厂 IF EX-27G 红蜘蛛 红惊闹娘化 飞机小队", unit="闲鱼", method=LI_MAN, key="IF-EX27G红蜘蛛", prod=None, pay="codex-clipboard-c62e4972-90ab-4499-8f8a-16fecc7863ef.jpg"),
    dict(dt="2026-08-18T13:44:58", amount=128, series="变形金刚", name="BPF通天副官晓 围城系列 L级", unit="闲鱼", method=LI_HUI, key="BPF通天副官晓", prod="codex-clipboard-e2d41286-0483-40ae-9e6f-0413644a6878.jpg", pay="codex-clipboard-f0270e9a-3a58-4913-97fe-9c6dae361b85.jpg"),
    dict(dt="2026-08-18T14:23:22", amount=58, series="变形金刚", name="银河玩具社 彩透红蜘蛛 鬼魂红 闹翻V天 带支架地台", unit="拼多多", method=LI_HUI, key="银河彩透红蜘蛛", prod="codex-clipboard-d85a7950-10ed-495e-84d7-cb6e4b76f039.jpg", pay="codex-clipboard-f251c395-7000-4b61-acdf-ea388e26d8a5.jpg"),
    dict(dt="2026-08-18T15:35:47", amount=249, series="变形金刚", name="变形金刚玩具天尊世代吵闹3C（百分之一）", unit="闲鱼", method=LI_HUI, key="天尊世代吵闹3C", prod="codex-clipboard-34ca58a4-9a59-4001-8213-e1efc037128b.jpg", pay="codex-clipboard-243c33c6-451a-4ffe-a285-a01d3f9ddabd.jpg"),
    dict(dt="2026-08-18T16:52:07", amount=420, series="其他", name="大漫匠瑠美美术老师+希维尔", unit="闲鱼", method=LI_MAN, key="瑠美美术老师希维尔", prod="codex-clipboard-949c8fe7-8151-4a0c-8f24-b12a0a693b0d.jpg", pay="codex-clipboard-42c42eee-12dc-4b75-946d-0ba4e8b515d5.jpg"),
    dict(dt="2026-08-18T17:28:03", amount=210, series="其他", name="专拍", unit="闲鱼", method=LI_HUI, key="专拍", prod="codex-clipboard-220704db-8eef-4e58-ab98-ec9604562af0.jpg", pay="codex-clipboard-0033c673-fb02-4351-844b-42ec47fe9232.jpg"),
    dict(dt="2026-08-18T21:17:33", amount=260, series="变形金刚", name="全新未拆封 Newage NA照相机三兄弟 H22 小比例变形金刚", unit="闲鱼", method=LI_MAN, key="Newage-NA照相机三兄弟", prod="codex-clipboard-ed410546-9a56-4e17-b2d5-a759d24e5f6b.jpg", pay="codex-clipboard-907e7dd3-4ebe-401a-8b2d-d71be970ed53.jpg"),
    dict(dt="2026-08-19T09:07:00", amount=179, series="变形金刚", name="孩之宝 变形金刚 SS86 警车 G2253 加强级 40周年", unit="闲鱼", method=LI_MAN, key="SS86警车G2253", prod="codex-clipboard-630b54ab-d6dd-430e-87c6-aa37f378a200.jpg", pay="codex-clipboard-23f22a56-a6f5-44b0-9e4e-ef6bef6c09ef.jpg"),
    dict(dt="2026-08-19T09:18:55", amount=170, series="变形金刚", name="全新现货孩之宝变形金刚SS86D级警车", unit="闲鱼", method=LI_MAN, key="SS86D级警车", prod="codex-clipboard-e5609def-c765-4bca-9ca7-017d7112371e.jpg", pay="codex-clipboard-c762ff96-30dd-49cf-a918-efdc244d771a.jpg"),
    dict(dt="2026-08-19T10:09:27", amount=177, series="变形金刚", name="全新未拆变形金刚SS86警车", unit="闲鱼", method=LI_MAN, key="SS86警车", prod="codex-clipboard-f050d5fc-54a7-4574-b0d7-2cf9a8f81893.jpg", pay="codex-clipboard-53eab309-971f-42d4-b4b7-5653ac5e736a.jpg"),
    dict(dt="2026-08-19T10:16:14", amount=118, series="变形金刚", name="孩之宝 变形金刚 复古挂卡 转轮 3C行货 正版", unit="闲鱼", method=LI_MAN, key="复古挂卡转轮", prod="codex-clipboard-7c9e0795-af65-4bb4-bad7-347791932ee5.jpg", pay="codex-clipboard-419577c3-f9d1-476a-a52e-467568193af3.jpg"),
    dict(dt="2026-08-19T10:23:17", amount=669.5, series="变形金刚", name="优质版KO变形模型SS86雷将×4+巨齿蛇升级SS86惊天雷×4+小号手大黄蜂外传阿尔茜+JCS-001惊天雷+TOHO Seeker小队雷公", unit="拼多多", method=LI_HUI, key="SS86惊天雷等合并5单", prod="codex-clipboard-738fc025-3619-4ab5-b0ee-7cd414d49142.jpg", pay="codex-clipboard-5b61d15f-743f-4fcb-a512-b76ce360db06.jpg"),
    dict(dt="2026-08-19T12:36:05", amount=348, series="其他", name="现货2025 少女前线2：追放 可露凯-蔚蓝轨迹1/", unit="闲鱼", method=LI_HUI, key="AniMester可露凯348", prod="codex-clipboard-580afc7e-45b4-4273-912f-9ae8bca8f4c5.jpg", pay="codex-clipboard-6ff496da-39c3-4a33-8bfb-4d608d24a058.jpg"),
    dict(dt="2026-08-19T17:44:03", amount=122, series="变形金刚", name="MFT照相机3兄弟 全新未拆封 小比例变形金刚", unit="闲鱼", method=LI_MAN, key="MFT照相机3兄弟", prod="codex-clipboard-6b188023-607e-4eca-90be-731ef84c0ed3.jpg", pay="codex-clipboard-4af316b6-706a-43a7-b56d-245fff4be97c.jpg"),
    dict(dt="2026-08-19T18:57:07", amount=116.5, series="其他", name="四季龙宝采购（物流单号435320030186542）", unit="个人收款", method=LI_MAN, key="四季龙宝物流", prod="codex-clipboard-ded87bd5-ff48-4a20-a2bb-2beed8bad5b4.jpg", pay="codex-clipboard-18c34fef-8a12-453d-a53c-903721ec28b6.jpg"),
    dict(dt="2026-08-20T11:03:43", amount=515, series="变形金刚", name="全新现货 ROBOT TOYS RT-D02黄蜂勇士变形玩具", unit="拼多多", method=LI_HUI, key="ROBOT-TOYS-RT-D02", prod="codex-clipboard-32c54eac-4a1f-4d4b-a1f2-153b7e1db828.jpg", pay="codex-clipboard-5e301f2d-9d1a-4841-acb0-62a611192713.jpg"),
    dict(dt="2026-08-20T11:11:01", amount=340.7, series="变形金刚", name="银河玩具社彩透红蜘蛛F16+三尖头冲锋喷气机挽歌+mini14J翻云雨+MINI02装甲奇兵绿色极小战车", unit="拼多多", method=LI_HUI, key="银河玩具社合并4单", prod="codex-clipboard-e7199961-7878-49fa-aba2-0a5a96ec5d38.jpg", pay="codex-clipboard-aa5bc406-7ae3-4b63-bcf5-d13051f1f9cc.jpg"),
    dict(dt="2026-08-20T11:40:51", amount=61, series="变形金刚", name="金宝变形玩具 FG04篡位者红蜘蛛战机 加冕版", unit="拼多多", method=LI_HUI, key="FG04红蜘蛛战机", prod="codex-clipboard-132531bb-f845-4222-8b1a-6d185d6e064e.jpg", pay="codex-clipboard-fc18089b-a732-4427-85aa-d67012f7ecb0.jpg"),
    dict(dt="2026-08-20T11:47:46", amount=688.2, series="变形金刚", name="JCS-001惊天雷×4+巨齿蛇升级SS86惊天雷×4+优质版KO变形模型SS86惊天雷×3", unit="拼多多", method=LI_HUI, key="惊天雷合并3单", prod="codex-clipboard-4eda21db-861c-4149-9309-cdfcaff998c0.jpg", pay="codex-clipboard-bdd8e3ad-992d-43b2-bf80-2db08425669a.jpg"),
    dict(dt="2026-08-20T13:01:43", amount=205, series="变形金刚", name="变形金刚 DNA 第三方配件包DK31 适用于方舟号", unit="闲鱼", method=LI_MAN, key="DNA-DK31配件包", prod="codex-clipboard-72432bb9-9c55-4556-8b55-8153b8f37aca.jpg", pay="codex-clipboard-540c1fb4-6b31-4e33-aafa-45ee0dc325b3.jpg"),
    dict(dt="2026-08-20T13:38:00", amount=20, series="其他", name="补邮费", unit="个人收款", method=LI_MAN, key="补邮费", prod=None, pay="codex-clipboard-82e7e5b4-4c07-4605-9827-59e6fe34484b.jpg"),
    dict(dt="2026-08-20T16:35:46", amount=49, series="变形金刚", name="新品第三方人仔BM声波积木人仔 乐高拼装灯光摆件 限定版套装", unit="拼多多", method=LI_HUI, key="BM声波积木人仔", prod="codex-clipboard-144405b4-b869-4b91-8543-e2f561be9a2a.jpg", pay="codex-clipboard-7294bb06-96aa-4f0d-9f84-068e89b10091.jpg"),
    dict(dt="2026-08-20T17:14:50", amount=59, series="变形金刚", name="变形玩具 MFT MF-51 反抗者 奥利安 口袋系列小比例", unit="闲鱼", method=LI_HUI, key="MFT-MF51反抗者", prod="codex-clipboard-6ed78e93-364a-40db-be67-c25cdbcae51c.jpg", pay="codex-clipboard-89bb9645-a932-4112-90b6-684294ccabe2.jpg"),
    dict(dt="2026-08-21T09:08:41", amount=345, series="其他", name="【现货】AniMester 少女前线2：追放 可露凯-蔚蓝", unit="闲鱼", method=LI_HUI, key="AniMester可露凯345", prod="codex-clipboard-35d94a4f-6e60-492c-a2e3-26269343ea76.jpg", pay="codex-clipboard-5490b1c3-a338-4744-bfd9-701a18550105.jpg"),
    dict(dt="2026-08-21T09:12:06", amount=228, series="变形金刚", name="最新批次 现货【修复版】MP44变形放大版w8020摆件模型", unit="闲鱼", method=LI_HUI, key="修复版MP44-W8020", prod="codex-clipboard-fe73e77b-2504-492c-8c26-2310ec6cc6b9.jpg", pay="codex-clipboard-3d9fda91-e22b-4f3e-90f1-23c0b1e10e2e.jpg"),
    dict(dt="2026-08-21T09:40:08", amount=499.8, series="变形金刚", name="DNA DK61配件包+DW-E36吴医生威震天+银河玩具社mini14J翻云雨+WAY STUDIOS擎天柱领袖套装", unit="拼多多", method=LI_HUI if False else LI_HUI, key="DK61-DWE36-mini14J-WAY合并", prod="codex-clipboard-4e439bc8-cdb5-4e87-b00c-4a89e33c7e6a.jpg", pay="codex-clipboard-d35f6eec-2f45-49f8-ae58-a4f900e907cf.jpg"),
    dict(dt="2026-08-21T10:22:14", amount=183.8, series="变形金刚", name="银河玩具社MP52红蜘蛛F16+彩透红蜘蛛F15+MINI08B破坏大帝邪恶轴心枪威", unit="拼多多", method=LI_HUI, key="银河红蜘蛛-MINI08B合并", prod="codex-clipboard-5f42e387-4e90-4006-be51-b0b9c45bf1e1.jpg", pay="codex-clipboard-aa1efaf8-ceab-4503-b427-9dc45e328a07.jpg"),
    dict(dt="2026-08-21T11:11:39", amount=211, series="其他", name="泡泡玛特+Hirono X Kodak咔哒小野", unit="闲鱼", method=LI_HUI, key="Hirono-X-Kodak", prod="codex-clipboard-3e5d89c8-ab7e-4469-9811-5bb78f68772f.jpg", pay="codex-clipboard-476b8e00-5adb-4864-b6e2-a7f1fdaa7991.jpg"),
    dict(dt="2026-08-21T16:03:25", amount=792, series="变形金刚", name="X-Transbot X社 MX-70扎克领主萨克头 头领战士变形金刚", unit="拼多多", method=LI_HUI, key="X-Transbot-MX70", prod="codex-clipboard-c5a734de-dd28-47cf-9889-435a8b6843ce.jpg", pay="codex-clipboard-ecedfc4c-5102-41dd-9056-6607ee668c85.jpg"),
    dict(dt="2026-08-21T16:03:53", amount=55, series="变形金刚", name="银河玩具社 彩虹擎天小柱 Galaxy toys迷你版口袋极小（7cm）", unit="闲鱼", method=LI_HUI, key="银河彩虹擎天小柱", prod="codex-clipboard-4b05df98-303a-43f6-b647-b768738f52d9.jpg", pay="codex-clipboard-a9b1c162-cd67-422c-a087-cdc4ac6208d0.jpg"),
]


def md5_bytes(data):
    return hashlib.md5(data).hexdigest()


def cellimage_manifest(path):
    with zipfile.ZipFile(path) as z:
        rel_name = "xl/_rels/cellimages.xml.rels"
        if rel_name not in z.namelist():
            return {}
        import xml.etree.ElementTree as ET
        root = ET.fromstring(z.read(rel_name))
        result = {}
        for rel in root:
            rid = rel.attrib.get("Id")
            target = rel.attrib.get("Target", "")
            if target.startswith("../"):
                target = "xl/" + target[3:]
            elif target.startswith("/"):
                target = target[1:]
            elif not target.startswith("xl/"):
                target = "xl/" + target
            result[rid] = (target, md5_bytes(z.read(target)))
        return result


def backup_path_for(rec, kind):
    day = rec["dt"][:10].replace("-", "")
    folder = os.path.join(SHOT_ROOT, f"{day}-{rec['key']}-{rec['series'].replace('/', '-')}")
    ext = os.path.splitext(rec[kind])[1].lower()
    name = ("产品订单图" if kind == "prod" else "财务付款截图") + ext
    return folder, os.path.join(folder, name)


def ensure_no_duplicates():
    import openpyxl
    wb = openpyxl.load_workbook(LEDGER, read_only=True, data_only=False)
    ws = wb["自发货采购登记表"]
    existing = set()
    for row in range(2, ws.max_row + 1):
        dt = ws.cell(row, 14).value or ws.cell(row, 2).value
        amount = ws.cell(row, 13).value
        if hasattr(dt, "isoformat"):
            dt = dt.isoformat(timespec="seconds")
        existing.add((str(dt).replace(" ", "T"), float(amount) if amount is not None else None))
    wb.close()
    dup = [(r["dt"], r["amount"], r["name"]) for r in RECORDS if (r["dt"], float(r["amount"])) in existing]
    if dup:
        raise RuntimeError("发现已登记记录，停止追加: " + json.dumps(dup, ensure_ascii=False))


def do_backup():
    ensure_no_duplicates()
    missing = []
    copied = []
    for rec in RECORDS:
        for kind in ("prod", "pay"):
            if rec[kind] is None:
                continue
            source = src(rec[kind])
            if not os.path.exists(source):
                missing.append(source)
                continue
            folder, dest = backup_path_for(rec, kind)
            os.makedirs(folder, exist_ok=True)
            shutil.copy2(source, dest)
            if hashlib.md5(open(source, "rb").read()).digest() != hashlib.md5(open(dest, "rb").read()).digest():
                raise RuntimeError("截图备份校验失败: " + source)
            copied.append(dest)
    if missing:
        raise FileNotFoundError("缺少源截图:\n" + "\n".join(missing))
    os.makedirs(XLSX_ROOT, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = os.path.join(XLSX_ROOT, f"62店8月-采购登记表_{stamp}.xlsx")
    shutil.copy2(LEDGER, backup)
    if hashlib.md5(open(LEDGER, "rb").read()).digest() != hashlib.md5(open(backup, "rb").read()).digest():
        raise RuntimeError("Excel 备份校验失败")
    state = {"backup": backup, "cellimages": cellimage_manifest(backup), "copied": copied}
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(json.dumps({"records": len(RECORDS), "screenshots": len(copied), "backup": backup}, ensure_ascii=False))


def do_append():
    if not os.path.exists(STATE):
        raise RuntimeError("未找到备份状态，请先运行 --phase backup")
    with open(STATE, encoding="utf-8") as f:
        state = json.load(f)
    import openpyxl
    wb = openpyxl.load_workbook(LEDGER, read_only=True, data_only=False)
    ws = wb["自发货采购登记表"]
    seq = int(ws.cell(ws.max_row, 1).value)
    row = ws.max_row
    existing = set()
    for check_row in range(2, ws.max_row + 1):
        check_dt = ws.cell(check_row, 14).value or ws.cell(check_row, 2).value
        check_amount = ws.cell(check_row, 13).value
        if hasattr(check_dt, "isoformat"):
            check_dt = check_dt.isoformat(timespec="seconds")
        existing.add((str(check_dt).replace(" ", "T"), float(check_amount) if check_amount is not None else None))
    wb.close()
    pending = [rec for rec in RECORDS if (rec["dt"], float(rec["amount"])) not in existing]
    all_expects = []
    for idx, rec in enumerate(pending, 1):
        seq += 1
        row += 1
        dt = datetime.fromisoformat(rec["dt"])
        eta = dt + timedelta(days=3)
        data = [seq, rec["dt"], None, "备货进货", rec["series"], rec["name"], rec["unit"], 1,
                rec["amount"], rec["amount"], "刘宇彤", rec["method"], rec["amount"], rec["dt"],
                eta.isoformat(timespec="seconds"), None, None, None, eta.isoformat(timespec="seconds"), "刘宇彤"]
        cmd = [PYTHON, APPEND, "--file", LEDGER, "--data", json.dumps(data, ensure_ascii=False)]
        expects = []
        if rec["prod"]:
            _, p = backup_path_for(rec, "prod")
            cmd += ["--img-prod", p]
            expects.append((row, 16, p))
        _, p = backup_path_for(rec, "pay")
        cmd += ["--img-pay", p]
        expects.append((row, 18, p))
        subprocess.run(cmd, check=True)
        verify_cmd = [PYTHON, VERIFY, LEDGER]
        for erow, col, path in expects:
            verify_cmd += ["--expect", f"{erow},{col},{path}"]
            all_expects.append((erow, col, path))
        subprocess.run(verify_cmd, check=True)
        print(f"[{idx:02d}/{len(pending)}] row{row} seq{seq} {rec['dt']} CNY {rec['amount']} {rec['key']}", flush=True)
    current_manifest = cellimage_manifest(LEDGER)
    original_manifest = {k: tuple(v) for k, v in state["cellimages"].items()}
    if current_manifest != original_manifest:
        raise RuntimeError("历史 cellimages 映射或媒体字节发生变化")
    verify_cmd = [PYTHON, VERIFY, LEDGER]
    for erow, col, path in all_expects:
        verify_cmd += ["--expect", f"{erow},{col},{path}"]
    subprocess.run(verify_cmd, check=True)
    print(json.dumps({"completed_records": len(RECORDS), "added_this_run": len(pending), "last_row": row,
                      "last_seq": seq,
                      "historical_cellimages": len(current_manifest), "all_expect_count": len(all_expects)}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["backup", "append"], required=True)
    args = ap.parse_args()
    if args.phase == "backup":
        do_backup()
    else:
        do_append()


if __name__ == "__main__":
    main()
