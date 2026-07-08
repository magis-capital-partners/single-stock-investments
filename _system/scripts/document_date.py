#!/usr/bin/env python3
"""Infer document reporting period from folder, path, and title — not sync timestamps."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

CURRENT_YEAR = date.today().year
MIN_DOCUMENT_YEAR = 1990
MAX_DOCUMENT_YEAR = CURRENT_YEAR + 1

QUARTER_PATTERNS = [
    re.compile(r"(?<!\d)(20\d{2})\s*Q([1-4])(?!\d)", re.IGNORECASE),
    re.compile(r"(?<!\d)(20\d{2})\s*([1-4])Q(?:\s+Letters)?(?!\d)", re.IGNORECASE),
    re.compile(r"(?<!\d)(20\d{2})Q([1-4])(?!\d)", re.IGNORECASE),
    re.compile(r"(?<!\d)Q([1-4])\s*(20\d{2})(?!\d)", re.IGNORECASE),
    re.compile(r"(?<!\d)([1-4])Q\s*(20\d{2})(?!\d)", re.IGNORECASE),
]

ISO_DATE_RE = re.compile(r"(?<!\d)(20\d{2}|19\d{2})[-_. ]([01]?\d)[-_. ]([0-3]?\d)(?!\d)")
YYYYMM_RE = re.compile(r"(?<!\d)(20\d{2})([01]\d)(?!\d)")
YYMMDD_COMPACT_RE = re.compile(r"(?<!\d)([0-2]\d)([01]\d)([0-3]\d)(?!\d)")
YYMMDD_SEPARATED_RE = re.compile(r"(?<!\d)([0-3]?\d)[._\-/ ]([0-3]?\d)[._\-/ ]([0-2]\d{1,2})(?!\d)")
FY_RE = re.compile(r"\bFY\s*(20\d{2}|19\d{2})\b", re.IGNORECASE)
FISCAL_Q_RE = re.compile(r"\bQ([1-4])\s*FY\s*(20\d{2}|19\d{2})\b", re.IGNORECASE)
HALF_RE = re.compile(r"\b([12])H[\s\-_]*(20\d{2}|19\d{2})\b", re.IGNORECASE)
BARE_YEAR_RE = re.compile(r"(?<!\d)(20\d{2}|19\d{2})(?!\d)")

SOURCE_PRIORITY = {
    "superinvestor_letter": 0,
    "company_document": 1,
    "third_party": 2,
    "sumzero_research": 3,
    "research": 4,
    "dropbox_ingestion": 5,
    "pdf": 6,
}


@dataclass(frozen=True)
class DocumentPeriod:
    document_date: str | None
    document_year: int | None
    document_quarter: str | None
    period_label: str | None
    period_source: str
    quarter_display: str | None


def valid_year(year: int) -> bool:
    return MIN_DOCUMENT_YEAR <= year <= MAX_DOCUMENT_YEAR


def is_hash_like_title(title: str) -> bool:
    stem = re.sub(r"\.pdf$", "", str(title or ""), flags=re.I).strip()
    if not stem:
        return False
    if re.fullmatch(r"[0-9a-f]{8,}", stem, re.I):
        return True
    parts = stem.split()
    if len(parts) >= 2 and sum(1 for part in parts if re.fullmatch(r"[0-9a-f]{4,}", part, re.I)) >= 2:
        return True
    return False


def _in_hex_token(text: str, start: int, end: int) -> bool:
    left = start
    while left > 0 and re.match(r"[0-9a-f]", text[left - 1], re.I):
        left -= 1
    right = end
    while right < len(text) and re.match(r"[0-9a-f]", text[right], re.I):
        right += 1
    token = text[left:right]
    return len(token) >= 8 and re.fullmatch(r"[0-9a-f]+", token, re.I) is not None


def quarter_id(year: int, quarter: int) -> str:
    return f"{year}Q{quarter}"


def quarter_from_month(year: int, month: int) -> tuple[int, str]:
    q = max(1, min(4, (month - 1) // 3 + 1))
    return q, quarter_id(year, q)


def quarter_label(quarter_id_str: str) -> str:
    m = re.match(r"^(20\d{2})Q([1-4])$", quarter_id_str)
    if not m:
        return quarter_id_str
    return f"Q{m.group(2)} {m.group(1)}"


def quarter_display(quarter_id_str: str) -> str:
    m = re.match(r"^(20\d{2})Q([1-4])$", quarter_id_str)
    if not m:
        return quarter_id_str
    return f"{m.group(1)} Q{m.group(2)}"


def _finish(iso: str, source: str) -> DocumentPeriod:
    try:
        dt = date.fromisoformat(iso)
    except ValueError:
        return DocumentPeriod(None, None, None, None, "unknown", None)
    if not valid_year(dt.year):
        return DocumentPeriod(None, None, None, None, "unknown", None)
    qnum, qid = quarter_from_month(dt.year, dt.month)
    label = quarter_label(qid)
    return DocumentPeriod(
        document_date=iso,
        document_year=dt.year,
        document_quarter=qid,
        period_label=label,
        period_source=source,
        quarter_display=quarter_display(qid),
    )


def _from_quarter_match(year: int, quarter: int, source: str) -> DocumentPeriod:
    if not valid_year(year):
        return DocumentPeriod(None, None, None, None, "unknown", None)
    qid = quarter_id(year, quarter)
    month = quarter * 3
    day = 30 if quarter in (2, 3) else 31 if quarter == 1 else 31
    if quarter == 4:
        iso = f"{year}-12-31"
    elif quarter == 3:
        iso = f"{year}-09-30"
    elif quarter == 2:
        iso = f"{year}-06-30"
    else:
        iso = f"{year}-03-31"
    return DocumentPeriod(
        document_date=iso,
        document_year=year,
        document_quarter=qid,
        period_label=quarter_label(qid),
        period_source=source,
        quarter_display=quarter_display(qid),
    )


def parse_quarter_text(text: str) -> DocumentPeriod | None:
    for pattern in QUARTER_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        groups = m.groups()
        if len(groups) == 2:
            if groups[0].startswith("20") or groups[0].startswith("19"):
                year, quarter = int(groups[0]), int(groups[1])
            else:
                quarter, year = int(groups[0]), int(groups[1])
            return _from_quarter_match(year, quarter, "title")
    return None


def parse_iso_date_text(text: str, source: str) -> DocumentPeriod | None:
    m = ISO_DATE_RE.search(text)
    if not m:
        return None
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    try:
        iso = date(year, month, day).isoformat()
    except ValueError:
        return None
    return _finish(iso, source)


def parse_yyyymm(text: str) -> DocumentPeriod | None:
    for m in YYYYMM_RE.finditer(text.replace("_", " ").replace("-", " ")):
        if _in_hex_token(text, m.start(), m.end()):
            continue
        year, month = int(m.group(1)), int(m.group(2))
        if not valid_year(year) or month < 1 or month > 12:
            continue
        day = 28 if month == 2 else 30 if month in (4, 6, 9, 11) else 31
        return _finish(date(year, month, day).isoformat(), "title")
    return None


def parse_yymmdd(text: str) -> DocumentPeriod | None:
    cleaned = text.replace("_", " ").replace("-", " ")
    m = YYMMDD_COMPACT_RE.search(cleaned.replace(" ", ""))
    if m:
        yy, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        year = 2000 + yy if yy < 40 else 1900 + yy
        if 1 <= month <= 12 and 1 <= day <= 31:
            try:
                return _finish(date(year, month, day).isoformat(), "title")
            except ValueError:
                pass
    m = YYMMDD_SEPARATED_RE.search(cleaned)
    if not m:
        return None
    month, day, yr = int(m.group(1)), int(m.group(2)), m.group(3)
    year = int(yr) if len(yr) == 4 else (2000 + int(yr) if int(yr) < 40 else 1900 + int(yr))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    try:
        iso = date(year, month, day).isoformat()
    except ValueError:
        return None
    return _finish(iso, "title")


def fiscal_quarter_to_calendar(fiscal_q: int, fiscal_year: int) -> tuple[int, int]:
    """Approximate calendar (year, quarter) for Qn FY20YY (Jan fiscal year-end default)."""
    mapping = {
        1: (fiscal_year - 1, 2),
        2: (fiscal_year - 1, 3),
        3: (fiscal_year - 1, 4),
        4: (fiscal_year, 1),
    }
    return mapping[fiscal_q]


def parse_fiscal_quarter(text: str) -> DocumentPeriod | None:
    m = FISCAL_Q_RE.search(text)
    if not m:
        return None
    fiscal_q, fiscal_year = int(m.group(1)), int(m.group(2))
    if not valid_year(fiscal_year):
        return None
    cal_year, cal_q = fiscal_quarter_to_calendar(fiscal_q, fiscal_year)
    if not valid_year(cal_year):
        return None
    month_ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    month, day = month_ends[cal_q]
    qid = quarter_id(cal_year, cal_q)
    return DocumentPeriod(
        document_date=f"{cal_year}-{month:02d}-{day:02d}",
        document_year=cal_year,
        document_quarter=qid,
        period_label=f"Q{fiscal_q} FY{fiscal_year}",
        period_source="fy_quarter",
        quarter_display=quarter_display(qid),
    )


def parse_fy(text: str) -> DocumentPeriod | None:
    if FISCAL_Q_RE.search(text):
        return None
    m = FY_RE.search(text)
    if not m:
        return None
    year = int(m.group(1))
    return DocumentPeriod(
        document_date=f"{year}-12-31",
        document_year=year,
        document_quarter=quarter_id(year, 4),
        period_label=f"FY {year}",
        period_source="fy",
        quarter_display=quarter_display(quarter_id(year, 4)),
    )


def parse_half(text: str) -> DocumentPeriod | None:
    m = HALF_RE.search(text)
    if not m:
        return None
    half, year = int(m.group(1)), int(m.group(2))
    if half == 1:
        return DocumentPeriod(
            document_date=f"{year}-06-30",
            document_year=year,
            document_quarter=quarter_id(year, 2),
            period_label=f"1H {year}",
            period_source="half",
            quarter_display=quarter_display(quarter_id(year, 2)),
        )
    return DocumentPeriod(
        document_date=f"{year}-12-31",
        document_year=year,
        document_quarter=quarter_id(year, 4),
        period_label=f"2H {year}",
        period_source="half",
        quarter_display=quarter_display(quarter_id(year, 4)),
    )


def parse_bare_year(text: str) -> DocumentPeriod | None:
    if is_hash_like_title(text):
        return None
    for m in BARE_YEAR_RE.finditer(text):
        if _in_hex_token(text, m.start(), m.end()):
            continue
        year = int(m.group(1))
        if not valid_year(year):
            continue
        return DocumentPeriod(
            document_date=f"{year}-12-31",
            document_year=year,
            document_quarter=quarter_id(year, 4),
            period_label=str(year),
            period_source="title",
            quarter_display=quarter_display(quarter_id(year, 4)),
        )
    return None


def infer_from_folder(doc: dict) -> DocumentPeriod | None:
    folder = str(doc.get("drive_folder_path") or "")
    parts = [p for p in folder.split("/") if p]
    if len(parts) >= 2 and parts[0] == "Letters":
        hit = parse_quarter_text(parts[1])
        if hit:
            return DocumentPeriod(
                document_date=hit.document_date,
                document_year=hit.document_year,
                document_quarter=hit.document_quarter,
                period_label=hit.period_label,
                period_source="folder",
                quarter_display=hit.quarter_display,
            )
    local = str(doc.get("local_pdf_path") or "")
    m = re.search(r"superinvestor-letters/(\d{4})Q([1-4])/", local, re.I)
    if m:
        return _from_quarter_match(int(m.group(1)), int(m.group(2)), "folder")
    for part in parts:
        parsed = parse_quarter_text(part)
        if parsed:
            return DocumentPeriod(
                document_date=parsed.document_date,
                document_year=parsed.document_year,
                document_quarter=parsed.document_quarter,
                period_label=parsed.period_label,
                period_source="folder",
                quarter_display=parsed.quarter_display,
            )
    return None


def infer_document_period(doc: dict) -> DocumentPeriod:
    folder_hit = infer_from_folder(doc)
    if folder_hit:
        return folder_hit

    title = str(doc.get("title") or "")
    if is_hash_like_title(title):
        return DocumentPeriod(None, None, None, "Unknown date", "unknown", None)

    stem = title.rsplit(".", 1)[0] if title else ""
    local = str(doc.get("local_pdf_path") or "")
    path = str(doc.get("drive_folder_path") or "")
    candidates = [
        (stem, "title"),
        (title, "title"),
        (local.replace("/", " "), "path"),
        (path.replace("/", " "), "path"),
    ]
    for text, source in candidates:
        for parser in (
            lambda t, s=source: parse_quarter_text(t),
            lambda t, s=source: parse_fiscal_quarter(t),
            lambda t, s=source: parse_half(t),
            lambda t, s=source: parse_fy(t),
            lambda t, s=source: parse_yyyymm(t),
            lambda t, s=source: parse_yymmdd(t),
            lambda t, s=source: parse_iso_date_text(t, s),
        ):
            hit = parser(text)
            if hit:
                if hit.period_source == "folder":
                    hit = DocumentPeriod(
                        document_date=hit.document_date,
                        document_year=hit.document_year,
                        document_quarter=hit.document_quarter,
                        period_label=hit.period_label,
                        period_source=source,
                        quarter_display=hit.quarter_display,
                    )
                return hit

    for text, source in candidates:
        hit = parse_bare_year(text)
        if hit:
            return DocumentPeriod(
                document_date=hit.document_date,
                document_year=hit.document_year,
                document_quarter=hit.document_quarter,
                period_label=hit.period_label,
                period_source=source,
                quarter_display=hit.quarter_display,
            )

    return DocumentPeriod(None, None, None, "Unknown date", "unknown", None)


def catalog_sort_key(row: dict) -> tuple:
    date_key = row.get("document_date") or ""
    source_type = row.get("source_type") or "pdf"
    priority = SOURCE_PRIORITY.get(source_type, 99)
    return (
        0 if date_key else 1,
        "" if date_key else "z",
        tuple(-ord(c) for c in date_key) if date_key else (),
        priority,
        (row.get("ticker") or "").lower(),
        (row.get("title") or "").lower(),
    )
