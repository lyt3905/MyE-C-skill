# -*- coding: utf-8 -*-
"""Delete the mistaken IF EX-27G row and merge the CNY20 postage into row 45.

This performs a ZIP-level edit so WPS cell-image parts and historical image bytes
remain untouched. The supplementary postage receipt is moved from its former row
to Q45, next to the original order/payment images in P45/R45.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET


LEDGER = Path(r"C:\Users\shana\Desktop\62店8月-采购登记表.xlsx")
BACKUP_DIR = Path(r"C:\Users\shana\Desktop\62店台账备份\进货表备份\Excel备份")
POSTAGE_SOURCE = Path(
    r"C:\Users\shana\Desktop\62店台账备份\进货表备份\截图备份"
    r"\20260820-补邮费-其他\财务付款截图.jpg"
)
VERIFY = Path(__file__).with_name("verify_ledger.py")
PYTHON = Path(sys.executable)

SHEET_XML = "xl/worksheets/sheet2.xml"
DRAWING_XML = "xl/drawings/drawing1.xml"
DRAWING_RELS = "xl/drawings/_rels/drawing1.xml.rels"

DELETE_ROWS = {64, 84}
REMOVE_RID = "rId3"
MOVE_RID = "rId42"


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def shifted_row(old_row: int) -> int:
    return old_row - int(old_row > 64) - int(old_row > 84)


def cellimage_manifest(path: Path) -> dict[str, tuple[str, str]]:
    rel_name = "xl/_rels/cellimages.xml.rels"
    with zipfile.ZipFile(path) as zf:
        if rel_name not in zf.namelist():
            return {}
        root = ET.fromstring(zf.read(rel_name))
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
            result[rid] = (target, md5(zf.read(target)))
        return result


def replace_numeric_cell(row_xml: str, col: str, row: int, value: int) -> str:
    pattern = rf'(<c\b[^>]*\br="{col}{row}"[^>]*>.*?<v>)(.*?)(</v>.*?</c>)'
    updated, count = re.subn(pattern, rf"\g<1>{value}\g<3>", row_xml, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"Could not update {col}{row}")
    return updated


def edit_sheet(data: bytes) -> bytes:
    text = data.decode("utf-8")
    row_pattern = re.compile(r'<row\b[^>]*\br="(\d+)"[^>]*>.*?</row>', re.S)
    seen = set()

    def rewrite(match: re.Match[str]) -> str:
        old = int(match.group(1))
        block = match.group(0)
        if old in DELETE_ROWS:
            seen.add(old)
            return ""
        if old == 45:
            for col in ("I", "J", "M"):
                block = replace_numeric_cell(block, col, old, 380)
        new = shifted_row(old)
        if new != old:
            block = re.sub(rf'(<row\b[^>]*\br="){old}(\")', rf"\g<1>{new}\g<2>", block, count=1)
            block = re.sub(rf'(\br="[A-Z]{{1,3}}){old}(\")', rf"\g<1>{new}\g<2>", block)
            block = replace_numeric_cell(block, "A", new, new - 1)
        return block

    text = row_pattern.sub(rewrite, text)
    if seen != DELETE_ROWS:
        raise RuntimeError(f"Expected deleted rows {DELETE_ROWS}, found {seen}")
    text, count = re.subn(r'(<dimension\b[^>]*\bref="[A-Z]+\d+:[A-Z]+)93(\")', r"\g<1>91\g<2>", text, count=1)
    if count != 1:
        raise RuntimeError("Worksheet dimension did not end at row 93")
    return text.encode("utf-8")


def edit_drawing(data: bytes) -> bytes:
    text = data.decode("utf-8")
    anchor_pattern = re.compile(r'<(?:xdr:)?oneCellAnchor\b.*?</(?:xdr:)?oneCellAnchor>', re.S)
    removed = 0
    moved = 0

    def rewrite(match: re.Match[str]) -> str:
        nonlocal removed, moved
        block = match.group(0)
        row_match = re.search(r'<(?:xdr:)?row>(\d+)</(?:xdr:)?row>', block)
        col_match = re.search(r'<(?:xdr:)?col>(\d+)</(?:xdr:)?col>', block)
        rid_match = re.search(r'\br:embed="([^"]+)"', block)
        if not (row_match and col_match and rid_match):
            raise RuntimeError("Malformed oneCellAnchor")
        excel_row = int(row_match.group(1)) + 1
        rid = rid_match.group(1)
        if rid == REMOVE_RID:
            if excel_row != 64:
                raise RuntimeError(f"{REMOVE_RID} was unexpectedly anchored at row {excel_row}")
            removed += 1
            return ""
        if rid == MOVE_RID:
            if excel_row != 84:
                raise RuntimeError(f"{MOVE_RID} was unexpectedly anchored at row {excel_row}")
            block = re.sub(r'(<(?:xdr:)?row>)\d+(</(?:xdr:)?row>)', r"\g<1>44\g<2>", block, count=1)
            block = re.sub(r'(<(?:xdr:)?col>)\d+(</(?:xdr:)?col>)', r"\g<1>16\g<2>", block, count=1)
            moved += 1
            return block
        new_excel_row = shifted_row(excel_row)
        if new_excel_row != excel_row:
            new_zero = new_excel_row - 1
            block = re.sub(
                r'(<(?:xdr:)?row>)\d+(</(?:xdr:)?row>)',
                rf"\g<1>{new_zero}\g<2>",
                block,
                count=1,
            )
        return block

    text = anchor_pattern.sub(rewrite, text)
    if removed != 1 or moved != 1:
        raise RuntimeError(f"Expected one removed and one moved anchor, got {removed}/{moved}")
    return text.encode("utf-8")


def edit_drawing_rels(data: bytes) -> tuple[bytes, str]:
    text = data.decode("utf-8")
    tag_pattern = re.compile(r'<Relationship\b[^>]*/>')
    removed_target = None

    def rewrite(match: re.Match[str]) -> str:
        nonlocal removed_target
        tag = match.group(0)
        id_match = re.search(r'\bId="([^"]+)"', tag)
        if id_match and id_match.group(1) == REMOVE_RID:
            target_match = re.search(r'\bTarget="([^"]+)"', tag)
            if not target_match:
                raise RuntimeError(f"{REMOVE_RID} relationship has no target")
            removed_target = target_match.group(1)
            return ""
        return tag

    text = tag_pattern.sub(rewrite, text)
    if removed_target is None:
        raise RuntimeError(f"Could not find relationship {REMOVE_RID}")
    return text.encode("utf-8"), removed_target


def target_to_zip_name(target: str) -> str:
    if target.startswith("../"):
        return "xl/" + target[3:]
    if target.startswith("/"):
        return target[1:]
    return "xl/drawings/" + target


def validate_values(path: Path) -> None:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=False)
    ws = wb["自发货采购登记表"]
    if ws.max_row != 91:
        raise RuntimeError(f"Expected max row 91, got {ws.max_row}")
    seq = [ws.cell(row, 1).value for row in range(2, 92)]
    if seq != list(range(1, 91)):
        raise RuntimeError("Sequence is not 1..90")
    if [ws.cell(45, col).value for col in (9, 10, 13)] != [380, 380, 380]:
        raise RuntimeError("Row 45 amounts are not all 380")
    names = [ws.cell(row, 6).value for row in range(2, 92)]
    if any(name == "铁工厂 IF EX-27G 红蜘蛛 红惊闹娘化 飞机小队" for name in names):
        raise RuntimeError("IF EX-27G row still exists")
    if any(name == "补邮费" for name in names):
        raise RuntimeError("Standalone postage row still exists")
    wb.close()


def validate_drawing(path: Path) -> None:
    ns = {
        "x": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read(DRAWING_XML))
        anchors = []
        for anchor in root.findall("x:oneCellAnchor", ns):
            start = anchor.find("x:from", ns)
            blip = anchor.find(".//a:blip", ns)
            anchors.append(
                (
                    int(start.find("x:row", ns).text) + 1,
                    int(start.find("x:col", ns).text) + 1,
                    blip.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"],
                )
            )
        if len(anchors) != 59:
            raise RuntimeError(f"Expected 59 floating anchors, got {len(anchors)}")
        if (45, 17, MOVE_RID) not in anchors:
            raise RuntimeError(f"Supplementary postage image is not at Q45: {anchors}")
        if any(rid == REMOVE_RID for _, _, rid in anchors):
            raise RuntimeError(f"Removed image {REMOVE_RID} still has an anchor")


def main() -> None:
    if not LEDGER.is_file() or not POSTAGE_SOURCE.is_file():
        raise FileNotFoundError("Ledger or supplementary postage source image is missing")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"62店8月-采购登记表_{stamp}.xlsx"
    shutil.copy2(LEDGER, backup)
    if md5(LEDGER.read_bytes()) != md5(backup.read_bytes()):
        raise RuntimeError("Workbook backup MD5 mismatch")
    historical_manifest = cellimage_manifest(backup)

    fd, tmp_name = tempfile.mkstemp(prefix="62店8月-采购登记表_", suffix=".xlsx", dir=str(LEDGER.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with zipfile.ZipFile(LEDGER, "r") as source:
            rels_data, removed_target = edit_drawing_rels(source.read(DRAWING_RELS))
            removed_media = target_to_zip_name(removed_target)
            with zipfile.ZipFile(tmp, "w", allowZip64=True) as target:
                for info in source.infolist():
                    if info.filename == removed_media:
                        continue
                    data = source.read(info.filename)
                    if info.filename == SHEET_XML:
                        data = edit_sheet(data)
                    elif info.filename == DRAWING_XML:
                        data = edit_drawing(data)
                    elif info.filename == DRAWING_RELS:
                        data = rels_data
                    target.writestr(info, data)

        validate_values(tmp)
        validate_drawing(tmp)
        if cellimage_manifest(tmp) != historical_manifest:
            raise RuntimeError("Historical WPS cell-image mapping or bytes changed")

        import subprocess

        subprocess.run(
            [
                str(PYTHON),
                str(VERIFY),
                str(tmp),
                "--expect",
                f"45,17,{POSTAGE_SOURCE}",
            ],
            check=True,
        )
        os.replace(tmp, LEDGER)
    finally:
        if tmp.exists():
            tmp.unlink()

    print(
        {
            "backup": str(backup),
            "deleted_rows": sorted(DELETE_ROWS),
            "row45_amount": 380,
            "postage_image": "Q45",
            "last_row": 91,
            "last_seq": 90,
            "historical_cellimages": len(historical_manifest),
        }
    )


if __name__ == "__main__":
    main()
