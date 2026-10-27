"""Parse ValueLine filenames. The ticker token is trusted only when it is in the registry."""
from __future__ import annotations

import re
from pathlib import Path

TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")
ISSUE_RE = re.compile(r"^SS(?:_|\b)", re.IGNORECASE)
SURVEY_DATE_RE = re.compile(r"(20\d{2})[.\-](\d{1,2})[.\-](\d{1,2})")


def parse_company_report(name: str) -> dict | None:
    """Split company, ticker, and date on the last underscore before the date.

    A greedy regex would treat ``BRK-B`` as ticker ``B``. The date is anchored
    at the end, then the ticker is the last remaining underscore token.
    """
    base = Path(str(name or "")).name
    if not base.lower().endswith(".pdf"):
        return None
    stem = base[:-4]
    date_at = stem.rfind("_")
    if date_at < 0:
        return None
    report_date = stem[date_at + 1 :]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_date):
        return None
    left = stem[:date_at]
    ticker_at = left.rfind("_")
    if ticker_at < 0:
        return None
    company = left[:ticker_at].strip()
    ticker = left[ticker_at + 1 :].strip().upper()
    if not company or not TICKER_RE.fullmatch(ticker):
        return None
    return {"company": company, "ticker": ticker, "report_date": report_date}


def parse_survey_date(name: str) -> str | None:
    match = SURVEY_DATE_RE.search(Path(str(name or "")).name)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def map_valueline_ticker(ticker: str, registry: dict[str, str], aliases: dict[str, str]) -> tuple[str | None, str]:
    """Return (registry ticker, reason). Never invent a ticker from the company text."""
    raw = str(ticker or "").upper()
    mapped = aliases.get(raw, raw)
    if mapped in registry:
        return mapped, "alias" if mapped != raw else "registry"
    return None, "ticker_not_in_registry"


def edition_from_path(path: str) -> str | None:
    text = str(path or "").replace("\\", "/")
    if "Full Surveys" in text:
        return "full_survey"
    if "Special Situations" in text:
        return "special_situations"
    if "/Old" in text or text.endswith("/Old") or "/Company Reports/Old" in text:
        return "old"
    if "/Current" in text or text.endswith("/Current"):
        return "current"
    return None


def classify_valueline_file(
    *,
    name: str,
    file_id: str,
    parents: list[str] | None,
    web_view: str | None,
    path: str,
    registry: dict[str, str],
    aliases: dict[str, str],
    edition_by_id: dict[str, str],
) -> dict:
    edition = edition_from_path(path)
    if edition is None:
        for parent in parents or []:
            if parent in edition_by_id:
                edition = edition_by_id[parent]
                break
    edition = edition or "unknown"
    base = Path(name).name
    row = {
        "original_name": base,
        "drive_file_id": file_id,
        "drive_url": web_view or "",
        "edition": edition,
        "path": path,
        "ticker": "",
        "company": "",
        "report_date": "",
        "status": "unmatched",
        "reason": "unparsed_name",
    }
    if edition == "full_survey" or (edition == "unknown" and "survey" in base.lower()):
        row["status"] = "survey"
        row["reason"] = "full_survey"
        row["report_date"] = parse_survey_date(base) or ""
        row["company"] = Path(base).stem
        return row
    if edition == "special_situations" and ISSUE_RE.match(base):
        row["status"] = "special_situation_issue"
        row["reason"] = "monthly_or_archive_issue"
        row["company"] = Path(base).stem
        row["report_date"] = parse_survey_date(base) or ""
        return row
    parsed = parse_company_report(base)
    if not parsed:
        row["reason"] = "ticker_not_in_filename"
        return row
    row["company"] = parsed["company"]
    row["report_date"] = parsed["report_date"]
    mapped, reason = map_valueline_ticker(parsed["ticker"], registry, aliases)
    row["reason"] = reason
    if mapped:
        row["ticker"] = mapped
        row["status"] = "matched"
        row["parsed_ticker"] = parsed["ticker"]
    else:
        row["parsed_ticker"] = parsed["ticker"]
        row["status"] = "unmatched"
    return row
