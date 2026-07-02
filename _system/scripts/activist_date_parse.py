"""Date parsing and normalization for activist report indexes."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from activist_common import firm_name, side_for_firm

DATE_IN_STEM_RE = [
    (re.compile(r"(20\d{2})-(\d{2})-(\d{2})"), "day"),
    (re.compile(r"(20\d{6})"), "day_compact"),
    (re.compile(r"(20\d{2})-(\d{2})(?:_|$|-)"), "month"),
    (re.compile(r"(20\d{4})(?:_|$|-)"), "year"),
]


def _iso_from_match(match: re.Match[str], precision_key: str) -> tuple[str, str]:
    if precision_key == "day":
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}", "day"
    if precision_key == "day_compact":
        raw = match.group(1)
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}", "day"
    if precision_key == "month":
        return f"{match.group(1)}-{match.group(2)}-01", "month"
    if precision_key == "year":
        return f"{match.group(1)}-01-01", "year"
    return match.group(0), "unknown"


def parse_date_from_stem(stem: str) -> tuple[str | None, str, str | None]:
    for pattern, precision_key in DATE_IN_STEM_RE:
        match = pattern.search(stem)
        if match:
            iso, precision = _iso_from_match(match, precision_key)
            return iso, precision, "filename"
    return None, "unknown", None


def normalize_partial_date(value: str | None) -> tuple[str | None, str, str | None]:
    text = str(value or "").strip()
    if not text:
        return None, "unknown", None
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", text):
        return text, "day", "normalized"
    if re.fullmatch(r"20\d{2}-\d{2}", text):
        return f"{text}-01", "month", "normalized"
    if re.fullmatch(r"20\d{4}", text):
        return f"{text[:4]}-01-01", "year", "normalized"
    parsed = parse_date_from_stem(text)
    if parsed[0]:
        return parsed
    return None, "unknown", None


def parse_html_filing_date(text: str) -> tuple[str | None, str]:
    head = (text or "")[:8000]
    for pattern in (
        r"FILED AS OF DATE:\s*(20\d{6})",
        r"CONFORMED PERIOD OF REPORT:\s*(20\d{6})",
        r"FILED:\s*(20\d{6})",
    ):
        match = re.search(pattern, head, re.I)
        if match:
            raw = match.group(1)
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}", "html_header"
    return None, "unknown"


def resolve_sec_filing_date(
    dest: Path,
    text: str,
    *,
    filing_date: str | None = None,
) -> dict:
    if filing_date:
        return {
            "report_date": filing_date[:10],
            "date_source": "sec_filing_date",
            "date_precision": "day",
        }

    parsed = parse_date_from_stem(dest.stem)
    if parsed[0]:
        return {
            "report_date": parsed[0],
            "date_source": parsed[2] or "filename",
            "date_precision": parsed[1],
        }

    html_date, html_source = parse_html_filing_date(text)
    if html_date:
        return {
            "report_date": html_date,
            "date_source": html_source,
            "date_precision": "day",
        }

    try:
        mtime = datetime.fromtimestamp(dest.stat().st_mtime, tz=timezone.utc)
        return {
            "report_date": mtime.strftime("%Y-%m-%d"),
            "date_source": "file_mtime",
            "date_precision": "day",
        }
    except OSError:
        pass

    return {
        "report_date": None,
        "date_source": "unknown",
        "date_precision": "unknown",
        "date_missing": True,
    }


def title_from_local_stem(stem: str, firm_id: str) -> str:
    parts = stem.split("_")
    if len(parts) >= 3:
        slug = "_".join(parts[2:])
    elif len(parts) == 2:
        slug = parts[1]
    else:
        slug = stem
    title = re.sub(r"[-_]+", " ", slug).strip()
    if title:
        return title[:120]
    return firm_name(firm_id)


def parse_local_report_metadata(path: Path, side: str) -> dict:
    stem = path.stem
    firm_id = stem.split("_")[0] if "_" in stem else "unknown"
    report_date, date_precision, date_source = parse_date_from_stem(stem)
    entry = {
        "firm_id": firm_id,
        "firm_name": firm_name(firm_id),
        "side": side,
        "local_file": str(path).replace("\\", "/"),
        "local_pdf": str(path).replace("\\", "/") if path.suffix.lower() == ".pdf" else None,
        "title": title_from_local_stem(stem, firm_id),
        "tier": "context",
        "include_in_feed": True,
        "filing_class": "local_cached",
    }
    if report_date:
        entry["report_date"] = report_date
        entry["date_precision"] = date_precision
        entry["date_source"] = date_source or "filename"
    else:
        entry["date_missing"] = True
        entry["date_source"] = "unknown"
        entry["date_precision"] = "unknown"
    if side_for_firm(firm_id, default=side) != side and firm_id != "unknown":
        entry["side"] = side_for_firm(firm_id, default=side)
    return entry
