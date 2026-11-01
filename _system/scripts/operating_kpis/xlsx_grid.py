"""Read a simple xlsx grid with the standard library. No openpyxl."""
from __future__ import annotations

import zipfile
import re
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _date_style_ids(book: zipfile.ZipFile) -> set[int]:
    if "xl/styles.xml" not in book.namelist():
        return set()
    root = ET.fromstring(book.read("xl/styles.xml"))
    formats = {int(n.get("numFmtId")): n.get("formatCode", "")
               for n in root.findall("m:numFmts/m:numFmt", NS)}
    result = set()
    for index, cell in enumerate(root.findall("m:cellXfs/m:xf", NS)):
        fmt = int(cell.get("numFmtId") or 0)
        code = re.sub(r'"[^\"]*"|\[[^\]]*\]', '', formats.get(fmt, "")).lower()
        if fmt in set(range(14, 23)) | {45, 46, 47} or ("y" in code and ("m" in code or "d" in code)):
            result.add(index)
    return result


def _col_index(ref: str) -> int:
    letters = "".join(ch for ch in ref if ch.isalpha())
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch.upper()) - 64)
    return index - 1


def _shared_strings(book: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in book.namelist():
        return []
    root = ET.fromstring(book.read("xl/sharedStrings.xml"))
    strings = []
    for item in root.findall("m:si", NS):
        strings.append("".join(node.text or "" for node in item.iter(MAIN + "t")))
    return strings


def sheet_names(book: zipfile.ZipFile) -> list[tuple[str, str]]:
    root = ET.fromstring(book.read("xl/workbook.xml"))
    rels = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
    rel_ns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
    targets = {
        node.get("Id"): node.get("Target")
        for node in rels.findall("r:Relationship", rel_ns)
    }
    out = []
    for sheet in root.findall("m:sheets/m:sheet", NS):
        rel_id = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = targets.get(rel_id) or ""
        if target and not target.startswith("xl/"):
            target = "xl/" + target.lstrip("/")
        out.append((sheet.get("name") or "", target))
    return out


def read_sheet(raw: bytes, *, sheet_name: str | None = None) -> list[list[str]]:
    with zipfile.ZipFile(__import__("io").BytesIO(raw)) as book:
        names = sheet_names(book)
        chosen = None
        if sheet_name:
            for name, target in names:
                if name == sheet_name:
                    chosen = target
                    break
        if chosen is None:
            for name, target in names:
                if name.isdigit() and target:
                    chosen = target
                    break
        if chosen is None:
            for _name, target in names:
                if target and "sheet" in target:
                    chosen = target
                    break
        if not chosen or chosen not in book.namelist():
            return []
        strings = _shared_strings(book)
        date_styles = _date_style_ids(book)
        props = ET.fromstring(book.read("xl/workbook.xml")).find("m:workbookPr", NS)
        epoch = datetime(1904, 1, 1) if props is not None and props.get("date1904") in {"1", "true"} else datetime(1899, 12, 30)
        root = ET.fromstring(book.read(chosen))
        grid: dict[int, dict[int, str]] = {}
        max_col = 0
        for row in root.findall("m:sheetData/m:row", NS):
            row_index = int(row.get("r") or 0) - 1
            grid[row_index] = {}
            for cell in row.findall("m:c", NS):
                ref = cell.get("r") or "A1"
                kind = cell.get("t")
                node = cell.find("m:v", NS)
                if node is None or node.text is None:
                    inline = cell.find("m:is", NS)
                    text = ""
                    if inline is not None:
                        text = "".join(item.text or "" for item in inline.iter(MAIN + "t"))
                elif kind == "s":
                    text = strings[int(node.text)]
                else:
                    text = node.text
                    if int(cell.get("s") or 0) in date_styles:
                        try:
                            text = (epoch + timedelta(days=float(text))).strftime("%Y-%m-%d")
                        except (ValueError, OverflowError):
                            pass
                col = _col_index(ref)
                grid[row_index][col] = text
                max_col = max(max_col, col)
        if not grid:
            return []
        rows = []
        for row_index in range(max(grid) + 1):
            cells = grid.get(row_index) or {}
            rows.append([cells.get(col, "") for col in range(max_col + 1)])
        return rows
