#!/usr/bin/env python3
"""Canonical fund resolution for superinvestor letters.

Replaces filename-derived fund identity with a stable ``fund_id`` so the same
fund reconciles across quarters, and parses the real letter date instead of
relying on file mtime.

Resolution order for each letter file:
  1. Curated override in ``funds.json`` whose ``filename_patterns`` match.
  2. Deterministic normalization of the filename (strip date/quarter/boilerplate
     tokens, slugify) -> stable ``fund_id`` + cleaned display name.

Unresolved-to-curation files are still grouped deterministically by the
normalized slug and recorded in ``funds_unresolved.json`` for one-time review.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LETTERS_ROOT = ROOT / "_system" / "reference" / "superinvestor-letters"
FUNDS_PATH = LETTERS_ROOT / "funds.json"
UNRESOLVED_PATH = LETTERS_ROOT / "funds_unresolved.json"

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}

# tokens stripped from filenames to derive a stable fund slug
_BOILERPLATE = re.compile(
    r"\b(letter|letters|investor|investors|quarterly|quarter|update|updates|commentary|"
    r"comment|factsheet|fact|sheet|tear|newsletter|news|memo|review|report|final|draft|"
    r"vol|volume|compact|presentation|deck|fund|capital|partners|management|mgmt|lp|llc|"
    r"ltd|inc|the|and|copy|pdf|q[1-4]|[1-4]q|fy|h[12]|annual|mid|year)\b",
    re.I,
)
_DATE_TOKENS = re.compile(
    r"\b20\d{2}\b|\b\d{1,2}[._/\-]\d{1,2}[._/\-]\d{2,4}\b|\b\d{1,2}[._/\-]\d{2,4}\b|"
    r"\b(?:" + "|".join(MONTHS) + r")\b|\b\d{2}\b",
    re.I,
)


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return s or "unknown-fund"


def normalize_fund_key(stem: str) -> tuple[str, str]:
    """Return (fund_id, display_name) from a raw filename stem."""
    s = stem.replace("_", " ").replace("-", " ")
    s = re.sub(r"\(.*?\)", " ", s)            # drop parentheticals like (1), (Prospect)
    s = _DATE_TOKENS.sub(" ", s)              # drop dates / years / quarters
    s = _BOILERPLATE.sub(" ", s)              # drop boilerplate words
    s = re.sub(r"\b\d+\b", " ", s)            # drop stray numbers
    s = re.sub(r"\s+", " ", s).strip()
    tokens = [t for t in s.split() if len(t) > 1]
    if not tokens:
        # fall back to first alpha chunk of original stem
        alpha = re.sub(r"[^a-zA-Z ]+", " ", stem).split()
        tokens = alpha[:2] or ["unknown"]
    display = " ".join(w.capitalize() for w in tokens[:4])
    fund_id = slugify(" ".join(tokens[:4]))
    return fund_id, display


def parse_letter_date(stem: str, text: str | None, quarter: str | None) -> tuple[str | None, str]:
    """Return (iso_date, source). source in {filename, content, quarter, none}."""
    # 1. explicit m.d.yy or m/d/yyyy in filename
    for m in re.finditer(r"\b(\d{1,2})[._/\-](\d{1,2})[._/\-](\d{2,4})\b", stem):
        d = _coerce_date(m.group(1), m.group(2), m.group(3))
        if d:
            return d.isoformat(), "filename"
    # 2. Month YYYY in filename
    mm = re.search(r"\b(" + "|".join(MONTHS) + r")[a-z]*\.?\s*'?(\d{2,4})\b", stem, re.I)
    if mm:
        month = MONTHS.get(mm.group(1).lower()[:3]) or MONTHS.get(mm.group(1).lower())
        yr = _coerce_year(mm.group(2))
        if month and yr:
            return _month_end(yr, month).isoformat(), "filename"
    # 3. quarter folder/path -> quarter-end date
    if quarter and re.match(r"20\d{2}Q[1-4]", quarter or "", re.I):
        yr = int(quarter[:4])
        q = int(quarter[5])
        mo, dy = QUARTER_END[q]
        return date(yr, mo, dy).isoformat(), "quarter"
    # 4. scan content head for "as of <date>" / Month DD, YYYY
    if text:
        head = text[:3000]
        m = re.search(r"\b(" + "|".join(MONTHS) + r")[a-z]*\.?\s+(\d{1,2}),?\s+(20\d{2})\b", head, re.I)
        if m:
            month = MONTHS.get(m.group(1).lower()[:3]) or MONTHS.get(m.group(1).lower())
            d = _coerce_date(str(month), m.group(2), m.group(3))
            if d:
                return d.isoformat(), "content"
    return None, "none"


def _coerce_year(y: str) -> int | None:
    y = y.strip()
    if len(y) == 2:
        return 2000 + int(y)
    if len(y) == 4 and y.startswith("20"):
        return int(y)
    return None


def _coerce_date(mo: str, dy: str, yr: str) -> date | None:
    try:
        month, day = int(mo), int(dy)
        year = _coerce_year(yr)
        if year and 1 <= month <= 12 and 1 <= day <= 31:
            return date(year, month, day)
    except (ValueError, TypeError):
        return None
    return None


def _month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    nxt = date(year, month + 1, 1)
    return date(nxt.year, nxt.month, 1).fromordinal(nxt.toordinal() - 1)


def quarter_from_path(path: Path) -> str | None:
    for part in path.parts:
        if re.match(r"20\d{2}Q[1-4]", part, re.I):
            return part.upper()
    return None


STEM_QUARTER_RE = re.compile(
    r"\b(20\d{2})\s*Q([1-4])\b|\bQ([1-4])\s*['']?(20\d{2})\b|\b([1-4])Q\s*(20\d{2})\b",
    re.I,
)


def parse_quarter_from_stem(stem: str) -> str | None:
    text = stem.replace("_", " ").replace("-", " ")
    m = STEM_QUARTER_RE.search(text)
    if not m:
        return None
    if m.group(1) and m.group(2):
        return f"{m.group(1)}Q{m.group(2)}"
    if m.group(3) and m.group(4):
        return f"{m.group(4)}Q{m.group(3)}"
    if m.group(5) and m.group(6):
        return f"{m.group(6)}Q{m.group(5)}"
    return None


def _quarter_from_date(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        d = datetime.strptime(iso, "%Y-%m-%d").date()
    except ValueError:
        return None
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def resolve_quarter(
    path: Path,
    stem: str,
    iso_date: str | None,
    date_source: str,
) -> str | None:
    folder_q = quarter_from_path(path)
    stem_q = parse_quarter_from_stem(stem)
    date_q = _quarter_from_date(iso_date)
    if date_source in ("filename", "content") and date_q:
        return date_q
    if stem_q:
        return stem_q
    if folder_q:
        return folder_q
    return date_q


class FundResolver:
    def __init__(self) -> None:
        cfg = load_json(FUNDS_PATH) or {}
        raw = cfg.get("funds") if isinstance(cfg, dict) else None
        self.funds: list[dict] = raw if isinstance(raw, list) else []
        self._compiled = [
            (f, [re.compile(p, re.I) for p in (f.get("filename_patterns") or [])])
            for f in self.funds
        ]
        self.unresolved: dict[str, dict] = {}

    def resolve(self, path: Path, text: str | None = None) -> dict:
        stem = path.stem
        quarter = quarter_from_path(path)
        iso_date, date_source = parse_letter_date(stem, text, quarter)
        if date_source == "none":
            iso_date = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
            date_source = "mtime"

        # 1. curated override
        for fund, patterns in self._compiled:
            if any(p.search(stem) for p in patterns):
                return {
                    "fund_id": fund["fund_id"],
                    "fund": fund.get("fund") or fund["fund_id"],
                    "manager": fund.get("manager", ""),
                    "strategy": fund.get("strategy", ""),
                    "maps_to_persona": fund.get("persona_map") or fund.get("maps_to_persona") or [],
                    "letter_date": iso_date,
                    "date_source": date_source,
                    "quarter": resolve_quarter(path, stem, iso_date, date_source),
                    "resolution": "curated",
                }

        # 2. deterministic normalization
        fund_id, display = normalize_fund_key(stem)
        self.unresolved.setdefault(
            fund_id,
            {"fund_id": fund_id, "fund": display, "examples": []},
        )
        ex = self.unresolved[fund_id]["examples"]
        if len(ex) < 5 and stem not in ex:
            ex.append(stem)
        return {
            "fund_id": fund_id,
            "fund": display,
            "manager": "",
            "strategy": "",
            "maps_to_persona": [],
            "letter_date": iso_date,
            "date_source": date_source,
            "quarter": resolve_quarter(path, stem, iso_date, date_source),
            "resolution": "normalized",
        }

    def write_unresolved(self) -> None:
        payload = {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "note": "Funds grouped by normalized filename slug. Promote real funds into funds.json with filename_patterns + manager + persona_map.",
            "count": len(self.unresolved),
            "funds": sorted(self.unresolved.values(), key=lambda x: x["fund_id"]),
        }
        UNRESOLVED_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
