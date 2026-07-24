#!/usr/bin/env python3
"""Robust letter date parsing: collect candidates, score, pick best."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
MONTH_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))
QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
MIN_SANE_YEAR = 1990
MIN_ACCEPTABLE_SCORE = 40
OCR_YEAR_RE = re.compile(r"\b20\s+1\s+1\b")
OCR_YEAR_RE2 = re.compile(r"\bfourth quarter of 201\s+1\b", re.I)

NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})[._/\-](\d{1,2})[._/\-](\d{2,4})\b")
# KEDM-style stems: 2026.06.14 or 2026_06_14
YMD_SEPARATOR_RE = re.compile(r"(?<!\d)(20\d{2})[._/\-](\d{1,2})[._/\-](\d{1,2})(?!\d)")
# HFA-style stems: HFA-061726 / HFA_061726 (MMDDYY after a fund token)
MMDDYY_STEM_RE = re.compile(
    r"(?:^|[^A-Za-z0-9])(?:[A-Za-z]{2,12})[-_ ]?(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(\d{2})(?:$|[^0-9])"
)
MONTH_DAY_YEAR_RE = re.compile(
    rf"\b({MONTH_ALT})[a-z]*\.?\s+(\d{{1,2}}),?\s+(20\d{{2}})\b",
    re.I,
)
MONTH_YEAR_ONLY_RE = re.compile(
    rf"\b({MONTH_ALT})[a-z]*\.?\s+(?!\d{{1,2}}\b)(20\d{{2}})\b",
    re.I,
)
ISO_IN_TEXT_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
COMPACT_YYYYMM_RE = re.compile(r"(?<!\d)(20\d{2})(0[1-9]|1[0-2])(?!\d)")
STEM_QUARTER_RE = re.compile(
    r"\b(20\d{2})\s*Q([1-4])\b|\bQ([1-4])\s*['']?(20\d{2})\b|\b([1-4])Q\s*(20\d{2})\b",
    re.I,
)


@dataclass(frozen=True)
class DateCandidate:
    iso_date: str
    source: str
    base_confidence: int
    consistency_bonus: int = 0

    @property
    def final_score(self) -> int:
        return self.base_confidence + self.consistency_bonus


def sanity_year(year: int | None, *, today: date | None = None) -> int | None:
    if year is None:
        return None
    today = today or datetime.now(timezone.utc).date()
    if year < MIN_SANE_YEAR or year > today.year + 1:
        return None
    return year


def repair_ocr_years(blob: str) -> str:
    out = OCR_YEAR_RE.sub("2011", blob)
    return OCR_YEAR_RE2.sub("fourth quarter of 2011", out)


def _coerce_year_token(y: str) -> int | None:
    y = y.strip()
    if len(y) == 4 and y.startswith("20"):
        return sanity_year(int(y))
    if len(y) == 2:
        yy = int(y)
        return sanity_year(2000 + yy if yy < 40 else 1900 + yy)
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        if not sanity_year(year) or not (1 <= month <= 12 and 1 <= day <= 31):
            return None
        return date(year, month, day)
    except ValueError:
        return None


def _month_num(name: str) -> int | None:
    key = name.lower()[:3]
    return MONTHS.get(key) or MONTHS.get(name.lower())


def _month_end(year: int, month: int) -> date | None:
    if month == 12:
        return _safe_date(year, 12, 31)
    nxt = _safe_date(year, month + 1, 1)
    if not nxt:
        return None
    return date.fromordinal(nxt.toordinal() - 1)


def _quarter_end_iso(quarter: str | None) -> str | None:
    if not quarter or not re.match(r"20\d{2}Q[1-4]", quarter, re.I):
        return None
    yr = int(quarter[:4])
    if sanity_year(yr) is None:
        return None
    mo, dy = QUARTER_END[int(quarter[5])]
    d = _safe_date(yr, mo, dy)
    return d.isoformat() if d else None


def _parse_quarter_token(text: str) -> str | None:
    m = STEM_QUARTER_RE.search(text.replace("_", " ").replace("-", " "))
    if not m:
        return None
    if m.group(1) and m.group(2):
        q = f"{m.group(1)}Q{m.group(2)}"
    elif m.group(3) and m.group(4):
        q = f"{m.group(4)}Q{m.group(3)}"
    elif m.group(5) and m.group(6):
        q = f"{m.group(6)}Q{m.group(5)}"
    else:
        return None
    if sanity_year(int(q[:4])) is None:
        return None
    return q.upper()


def _consistency_bonus(iso: str, folder_q: str | None, source: str) -> int:
    if not folder_q or not iso:
        return 0
    try:
        date_year = int(iso[:4])
        folder_year = int(folder_q[:4])
    except ValueError:
        return 0
    delta = date_year - folder_year
    if delta == 0:
        month = int(iso[5:7])
        date_q = f"{date_year}Q{(month - 1) // 3 + 1}"
        if date_q == folder_q.upper():
            return 15
        # Body text contains benchmark, chart, and publication dates.  A date
        # outside the containing quarter is weak evidence even in the same year.
        return -25 if source.startswith("content") else -5
    if abs(delta) == 1:
        return 5
    if abs(delta) >= 2:
        return -50
    return 0


def _add_candidate(
    out: list[DateCandidate],
    iso: str | None,
    source: str,
    base_confidence: int,
    folder_q: str | None,
) -> None:
    if not iso or sanity_year(int(iso[:4])) is None:
        return
    try:
        candidate_date = date.fromisoformat(iso)
    except ValueError:
        return
    if source.startswith("content") and candidate_date > datetime.now(timezone.utc).date():
        return
    bonus = _consistency_bonus(iso, folder_q, source)
    if any(c.iso_date == iso and c.source == source for c in out):
        return
    out.append(DateCandidate(iso_date=iso, source=source, base_confidence=base_confidence, consistency_bonus=bonus))


def load_date_overrides(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return doc.get("patterns") or []


def _override_candidates(stem: str, overrides: list[dict], folder_q: str | None) -> list[DateCandidate]:
    out: list[DateCandidate] = []
    for row in overrides:
        pattern = row.get("filename_regex")
        if not pattern:
            continue
        m = re.search(pattern, stem, re.I)
        if not m:
            continue
        raw = m.group(1) if m.lastindex else m.group(0)
        fmt = row.get("date_format") or "%B %d %Y"
        try:
            dt = datetime.strptime(raw.strip().replace(",", ""), fmt)
        except ValueError:
            continue
        _add_candidate(out, dt.date().isoformat(), "override", 100, folder_q)
    return out


def collect_date_candidates(
    stem: str,
    text: str | None = None,
    folder_q: str | None = None,
    *,
    overrides: list[dict] | None = None,
) -> list[DateCandidate]:
    stem = repair_ocr_years(stem)
    body = repair_ocr_years(text) if text else None
    out: list[DateCandidate] = []

    for row in _override_candidates(stem, overrides or [], folder_q):
        out.append(row)

    for blob, source, conf in (
        (stem, "filename", 95),
        (body[:3000] if body else None, "content", 85),
    ):
        if not blob:
            continue
        if source == "filename":
            for m in COMPACT_YYYYMM_RE.finditer(blob):
                end = _month_end(int(m.group(1)), int(m.group(2)))
                if end:
                    _add_candidate(out, end.isoformat(), "filename_compact_month", 92, folder_q)
            for m in YMD_SEPARATOR_RE.finditer(blob):
                d = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                if d:
                    _add_candidate(out, d.isoformat(), "filename_ymd", 96, folder_q)
            for m in MMDDYY_STEM_RE.finditer(blob):
                yr = _coerce_year_token(m.group(3))
                if yr is None:
                    continue
                d = _safe_date(yr, int(m.group(1)), int(m.group(2)))
                if d:
                    _add_candidate(out, d.isoformat(), "filename_mmddyy", 94, folder_q)
        for m in NUMERIC_DATE_RE.finditer(blob):
            yr = _coerce_year_token(m.group(3))
            if yr is None:
                continue
            d = _safe_date(yr, int(m.group(1)), int(m.group(2)))
            if d:
                _add_candidate(out, d.isoformat(), source, conf, folder_q)
        for m in MONTH_DAY_YEAR_RE.finditer(blob):
            month = _month_num(m.group(1))
            if not month:
                continue
            d = _safe_date(int(m.group(3)), month, int(m.group(2)))
            if d:
                tag = "filename_month_day" if source == "filename" else "content_month_day"
                _add_candidate(out, d.isoformat(), tag, conf - 5, folder_q)
        for m in MONTH_YEAR_ONLY_RE.finditer(blob):
            month = _month_num(m.group(1))
            yr = sanity_year(int(m.group(2)))
            if month and yr:
                end = _month_end(yr, month)
                if end:
                    tag = "filename_month_year" if source == "filename" else "content_month_year"
                    _add_candidate(out, end.isoformat(), tag, 88 if source == "filename" else 60, folder_q)
        for m in ISO_IN_TEXT_RE.finditer(blob):
            d = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if d:
                _add_candidate(out, d.isoformat(), source, conf, folder_q)

    stem_q = _parse_quarter_token(stem)
    if stem_q:
        iso = _quarter_end_iso(stem_q)
        _add_candidate(out, iso, "stem_quarter", 60, folder_q)

    if folder_q:
        iso = _quarter_end_iso(folder_q)
        _add_candidate(out, iso, "folder_quarter", 50, folder_q)

    return out


def pick_letter_date(
    stem: str,
    text: str | None = None,
    folder_q: str | None = None,
    *,
    overrides: list[dict] | None = None,
) -> tuple[str | None, str, int]:
    """Return (iso_date, date_source, confidence)."""
    candidates = collect_date_candidates(stem, text, folder_q, overrides=overrides)
    if not candidates:
        iso = _quarter_end_iso(folder_q)
        if iso:
            return iso, "quarter_inferred", 50
        return None, "none", 0

    best = max(candidates, key=lambda c: c.final_score)
    if best.final_score < MIN_ACCEPTABLE_SCORE:
        iso = _quarter_end_iso(folder_q)
        if iso:
            return iso, "quarter_inferred", 50
        return None, "none", 0
    return best.iso_date, best.source, best.final_score


def parse_letter_date(
    stem: str,
    text: str | None,
    quarter: str | None,
    *,
    overrides: list[dict] | None = None,
) -> tuple[str | None, str]:
    """Backward-compatible wrapper used by fund_registry."""
    iso, source, _conf = pick_letter_date(stem, text, quarter, overrides=overrides)
    return iso, source


def parse_letter_date_with_confidence(
    stem: str,
    text: str | None,
    quarter: str | None,
    *,
    overrides: list[dict] | None = None,
) -> tuple[str | None, str, int]:
    return pick_letter_date(stem, text, quarter, overrides=overrides)
