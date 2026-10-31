"""Parse legacy EDGAR tables while retaining original identifiers and rows."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

from thirteenf_core import parse_amount

PARSER_VERSION = "legacy-7"


class LegacyParseError(ValueError):
    def __init__(self, message, raw, rows=None, primary=None):
        super().__init__(message)
        self.raw_document = raw
        self.partial_rows = rows
        self.primary = primary


class TableText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.cell_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"td", "th"}:
            self.cell_depth += 1
            self.parts.append("  ")
        elif tag == "tr":
            self.parts.append("\n")
        elif tag in {"p", "br", "div"}:
            self.parts.append(" " if self.cell_depth else "\n")

    def handle_endtag(self, tag):
        if tag in {"td", "th"}:
            self.cell_depth = max(0, self.cell_depth - 1)
            self.parts.append("  ")
        elif tag == "tr" or tag in {"p", "div"} and not self.cell_depth:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(
            re.sub(r"\s+", " ", data) if self.cell_depth or data.isspace() else data
        )


def plain_text(raw):
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    if re.search(r"<(?:html|td|tr)\b", text, re.IGNORECASE):
        parser = TableText()
        parser.feed(text)
        text = "".join(parser.parts)
    else:
        text = re.sub(
            r"</?(?:S|C|TABLE|PAGE|CAPTION|TEXT)[^>]*>", "", text, flags=re.IGNORECASE
        )
    return html.unescape(text).replace("\xa0", " ")


def complete_cusip(value):
    if len(value) != 8:
        return value
    total = 0
    for index, character in enumerate(value.upper()):
        digit = (
            int(character)
            if character.isdigit()
            else ord(character) - 55
            if character.isalpha()
            else {"*": 36, "@": 37, "#": 38}[character]
        )
        digit *= 2 if index % 2 else 1
        total += digit // 10 + digit % 10
    return value + str((10 - total % 10) % 10)


def _information_text(raw, full):
    source = raw.decode("utf-8", errors="replace")
    tables = re.findall(
        r"<TABLE\b[^>]*>(.*?)</TABLE>", source, re.IGNORECASE | re.DOTALL
    )
    selected = []
    started = False
    for block in tables:
        text = plain_text(block)
        if re.search(r"\bCUSIP\b", text, re.IGNORECASE):
            started = True
        if started or re.search(
            r"\b[A-Z0-9*@#]{7,9}\s+[\d,]+\s+[\d,]+\s+(?:SH|PRN)\b", text, re.IGNORECASE
        ):
            selected.append(text)
    if selected:
        return "\n".join(selected)
    heading = re.search(r"(?im)^.*\bCUSIP\b.*$", full)
    if heading:
        return full[heading.start() :]
    # Some minimal electronic reports omit column headings. An explicit entry
    # count and typed stock rows are still required; cover-page dates are not rows.
    if re.search(r"Table Entry Total", full, re.IGNORECASE):
        return full
    raise LegacyParseError(
        "Legacy table requires review: information-table header is missing", raw
    )


def _primary(full, rows):
    result = {
        "parser": "legacy-text",
        "parser_version": PARSER_VERSION,
        "raw_row_count": len(rows),
    }
    result["confidential_omitted"] = bool(
        re.search(
            r"Confidential\s+Information\s+has\s+been\s+omitted|pursuant\s+to\s+(?:a\s+)?request\s+for\s+confidential\s+treatment",
            full,
            re.IGNORECASE,
        )
    )
    period = re.search(
        r"CONFORMED PERIOD OF REPORT:\s*(\d{8})|<PERIOD>\s*(\d{8})", full, re.IGNORECASE
    )
    if period:
        value = period[1] or period[2]
        result["period_end"] = f"{value[:4]}-{value[4:6]}-{value[6:]}"
    entry = re.search(
        r"(?:Information Table Entry Total|Table Entry Total)\s*:?\s*([\d,]+)",
        full,
        re.IGNORECASE,
    )
    total = re.search(
        r"(?:Information Table Value Total|Table Value Total)\s*:?\s*\$?\s*([\d,]+)",
        full,
        re.IGNORECASE,
    )
    if entry:
        result["table_entry_total"] = parse_amount(entry[1])
    if total:
        reported = parse_amount(total[1])
        actual = sum(row["value_usd"] or 0 for row in rows)
        dollars = abs(actual - reported) <= max(1, reported * 0.01)
        result["table_value_total_usd"] = reported if dollars else reported * 1000
        result["cover_total_units"] = "dollars" if dollars else "thousands"
    checked = r"(?:\[\s*[Xx]\s*\]|\(\s*[Xx]\s*\)|/\s*[Xx]\s*/)"
    if re.search(
        checked + r"\s*(?:adds\s+new\s+holdings|new\s+holdings)", full, re.IGNORECASE
    ):
        result["amendment_type"] = "NEW HOLDINGS"
    elif re.search(checked + r"\s*(?:is\s+a\s+)?restatement", full, re.IGNORECASE):
        result["amendment_type"] = "RESTATEMENT"
    else:
        result["amendment_type"] = None
    return result


def parse_legacy_document(raw):
    full = plain_text(raw)
    cover = _primary(full, [])
    if cover.get("table_entry_total") == 0:
        return [], cover
    body = _information_text(raw, full)
    # Legacy filers sometimes separate issuer, issue and check-digit groups.
    body = re.sub(
        r"\b([A-Z0-9*@#]{6})[\s-]+([A-Z0-9*@#]{2})[\s-]+([A-Z0-9])(?=\s+\$?\s*[\d,]+)",
        r"\1\2\3",
        body,
        flags=re.IGNORECASE,
    )
    body = re.sub(
        r"\b([A-Z0-9*@#]{6})[\s-]+([A-Z0-9*@#]{3})(?=\s+\$?\s*[\d,]+\s+[\d,]+)",
        r"\1\2",
        body,
        flags=re.IGNORECASE,
    )
    pattern = re.compile(
        r"^(?P<head>.*?)\s+\"?(?P<cusip>(?=[A-Z0-9*@#]*[0-9])[A-Z0-9*@#]{7,9})\"?\s+"
        r"\$?\s*(?P<value>[\d,]+(?:\.\d*)?)\s+(?P<shares>[\d,]+(?:\.\d*)?)"
        r"\s*(?P<unit>SHS?|PRN)?\b(?P<tail>.*)$",
        re.IGNORECASE,
    )
    strong_pattern = re.compile(
        pattern.pattern.replace("(?=[A-Z0-9*@#]*[0-9])", "(?=[A-Z0-9*@#]{0,5}[0-9])"),
        re.IGNORECASE,
    )
    rows, candidates = [], []
    missing_value = re.compile(
        r"^(?P<head>.*?)\s+(?P<cusip>(?=[A-Z0-9*@#]*[0-9])[A-Z0-9*@#]{7,9})\s{10,}(?P<shares>[\d,]+(?:\.\d*)?)\s+(?P<unit>SHS?|PRN)\b(?P<tail>.*)$",
        re.IGNORECASE,
    )
    pending = ""
    previous = None
    lines = body.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line:
            continue
        original_line = line
        if re.search(
            r"\bCUSIP\b|Column\s+\d|Name\s+of\s+Issuer|Title\s+of|Thousands|Voting\s+Authority",
            line,
            re.IGNORECASE,
        ):
            pending = ""
            continue
        if (
            previous
            and not pending
            and re.match(
                r"^[\d,]+\s+[\d,]+\s+(?:X\b|SH\b|PRN\b|Shared\b|SOLE\b)",
                line,
                re.IGNORECASE,
            )
        ):
            line = f"{previous['issuer']}  {previous['title_of_class']}  {previous['cusip']}  {line}"
        if (
            re.search(r"\b[A-Z0-9*@#]{7,9}\s+[\d,]+", line)
            and not pattern.match(line)
            and not missing_value.match(line)
        ):
            while (
                index < len(lines)
                and re.match(r"^\s*[\d,.]+\b", lines[index])
                and not pattern.match(line)
            ):
                line += " " + lines[index].strip()
                index += 1
        match = pattern.match(line)
        if match and not match["unit"]:
            stronger = strong_pattern.match(line)
            if stronger and stronger["unit"]:
                match = stronger
        if not match and (unvalued := missing_value.match(line)):
            match = {**unvalued.groupdict(), "value": None}
        if not match:
            if re.search(r"\b(?=[A-Z0-9*@#]*[0-9])[A-Z0-9*@#]{7,9}\s+[\d,]+", line):
                candidates.append(line)
                pending = ""
            elif (
                re.match(r"^[A-Za-z]", line)
                and len(line) < 100
                and not re.search(
                    r"\d{2}|Form\s+13F|Investment\s+Discretion|Principal|Shared|Managers|^\s*(?:Sole|None|Class|Number)\s*$",
                    line,
                    re.IGNORECASE,
                )
            ):
                pending = (pending + " " + line).strip()
            continue
        head = match["head"].strip()
        if (
            previous
            and not pending
            and re.fullmatch(
                r"(?:PFD|PREF|COM|CL|C1|ORD|ADR)(?:\s+[A-Z0-9]+)*", head, re.IGNORECASE
            )
        ):
            head = previous["issuer"] + "  " + head
        if pending:
            head = pending + " " + head
            pending = ""
        fields = re.split(r"\s{2,}|\t+", head)
        issuer = fields[0]
        title = " ".join(fields[1:]) if len(fields) > 1 else ""
        if not title:
            split = re.match(
                r"^(.*?)\s+((?:COM(?:MON(?:\s+STOCK)?)?|ORD(?:INARY)?|CL(?:ASS)?\s+[A-Z0-9]+|NOTE.*|BOND.*|DEB.*|ADR.*|PFD.*|SHS.*|PUT|CALL))$",
                head,
                re.IGNORECASE,
            )
            if split:
                issuer, title = split[1], split[2]
        known_class = re.search(
            r"\bCOM|COMMON|ORD|ADR|C[1L][A-Z]?\b|CLASS|SHS|PFD|PREF|NOTE|BOND|DEB|STOCK|UNIT|RIGHT|DEP\s+RCPT|ISHARES|BEN\s+INT|ETF|SBI|SDCV|DBCV|ZONES|PUT|CALL",
            title,
            re.IGNORECASE,
        )
        verified_cusip = (
            len(match["cusip"]) == 9
            and complete_cusip(match["cusip"][:8]) == match["cusip"]
        )
        if (
            not match["unit"]
            and not known_class
            and not verified_cusip
            and not head.endswith(("COM", "com"))
        ):
            candidates.append(line)
            continue
        tail = match["tail"]
        option = re.search(r"\b(PUT|CALL)\b", tail + " " + title, re.IGNORECASE)
        discretion = re.search(
            r"\b(SOLE|SHARED|DEFINED|OTHER|DFND)\b", tail, re.IGNORECASE
        )
        unit = match["unit"] or (
            "PRN"
            if re.search(r"NOTE|BOND|DEB|DEBT|SDCV|DBCV", title, re.IGNORECASE)
            else "SH"
        )
        rows.append(
            {
                "cusip": match["cusip"].upper(),
                "raw_cusip": match["cusip"].upper(),
                "issuer": issuer,
                "title_of_class": title,
                "shares": parse_amount(match["shares"]),
                "value_usd": parse_amount(match["value"]) * 1000
                if match["value"] is not None
                else None,
                "sh_prn": "SH" if unit.upper() == "SHS" else unit.upper(),
                "put_call": option[1].upper() if option else None,
                "discretion": discretion[1].upper() if discretion else "",
                "as_filed": {"line": original_line},
            }
        )
        previous = rows[-1]
    if not rows and not candidates and cover.get("confidential_omitted"):
        return [], cover
    if not rows or candidates:
        raise LegacyParseError(
            f"Legacy table requires review: parsed={len(rows)}, unmatched={len(candidates)}; {candidates[:2]}",
            raw,
            rows,
            _primary(full, rows),
        )
    return rows, _primary(full, rows)
