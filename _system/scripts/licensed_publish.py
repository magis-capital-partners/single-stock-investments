"""Build the public ValueLine and Expert Call metadata.

Dashboard files get a date, a company name, and a Drive link.
Report text and call transcripts stay out of this module's outputs.
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from licensed_drive_common import (
    assert_public_csv_field,
    assert_public_metadata,
    now_iso,
    write_json,
)

EDITION_RANK = {"current": 0, "special_situations": 1, "old": 2}
PUBLIC_CALL_CAP = 12
CSV_CELL_MAX = 380

PLAN_COLUMNS = (
    "file_id",
    "original_name",
    "new_name",
    "dest_folder",
    "bucket",
    "ticker",
    "company",
    "date",
    "confidence",
    "reason",
    "size_bytes",
    "extension",
    "drive_url",
    "parsed_company",
    "truncated",
    "drive_description",
)

VALUELINE_UNMATCHED_COLUMNS = (
    "original_name",
    "parsed_ticker",
    "company",
    "report_date",
    "edition",
    "reason",
    "drive_file_id",
    "drive_url",
)

EXPERT_UNMATCHED_COLUMNS = (
    "original_name",
    "parsed_company",
    "ticker",
    "confidence",
    "reason",
    "truncated",
    "drive_file_id",
    "drive_url",
)


def valueline_label(edition: str, report_date: str) -> str:
    date = report_date or "an unknown date"
    if edition == "special_situations":
        return f"ValueLine Special Situations report dated {date} available"
    if edition == "old":
        return f"ValueLine report dated {date} available (older edition)"
    if edition == "full_survey":
        return f"ValueLine Investment Survey dated {date} available"
    return f"ValueLine report dated {date} available"


def _better_valueline(candidate: dict, current: dict) -> bool:
    rank_new = EDITION_RANK.get(candidate.get("edition") or "", 9)
    rank_old = EDITION_RANK.get(current.get("edition") or "", 9)
    if rank_new != rank_old:
        return rank_new < rank_old
    return (candidate.get("report_date") or "") > (current.get("report_date") or "")


def _link_row(row: dict) -> dict:
    date = row.get("report_date") or ""
    edition = row.get("edition") or ""
    return {
        "label": valueline_label(edition, date),
        "report_date": date,
        "edition": edition,
        "drive_url": row.get("drive_url") or "",
    }


def summarize_valueline(rows: list[dict]) -> dict:
    statuses = Counter(row.get("status") or "" for row in rows)
    reasons = Counter(row.get("reason") or "" for row in rows)
    parsed = sum(1 for row in rows if row.get("parsed_ticker"))
    matched_tickers = {row.get("ticker") for row in rows if row.get("status") == "matched" and row.get("ticker")}
    return {
        "generated_at": now_iso(),
        "index_rows": len(rows),
        "parsed_ticker_rows": parsed,
        "registry_matched_rows": statuses.get("matched", 0),
        "registry_matched_tickers": len(matched_tickers),
        "unmatched_rows": statuses.get("unmatched", 0),
        "ticker_not_in_registry": reasons.get("ticker_not_in_registry", 0),
        "ticker_not_in_filename": reasons.get("ticker_not_in_filename", 0),
        "survey_rows": statuses.get("survey", 0),
        "special_situation_issue_rows": statuses.get("special_situation_issue", 0),
        "note": (
            "Counts are filename-index rows. The index keeps one row per lowercase "
            "name, so an Old copy that shares a Current filename is not a second row. "
            "Tickers outside the registry are listed, not guessed."
        ),
    }


def valueline_public(rows: list[dict]) -> tuple[dict[str, dict], dict]:
    by_ticker: dict[str, dict] = {}
    surveys: list[dict] = []
    issues: list[dict] = []
    for row in rows:
        status = row.get("status")
        if status == "survey":
            surveys.append(_link_row(row))
            continue
        if status == "special_situation_issue":
            issues.append(_link_row(row))
            continue
        if status != "matched" or not row.get("ticker"):
            continue
        candidate = _link_row(row)
        current = by_ticker.get(row["ticker"])
        if current is None or _better_valueline(candidate, current):
            by_ticker[row["ticker"]] = candidate
    insights = {
        "generated_at": now_iso(),
        "source": "valueline_filename_classification",
        "note": "Dates and Drive links only. Report text stays in the private vault.",
        "matched_ticker_count": len(by_ticker),
        "by_ticker": by_ticker,
        "surveys": surveys,
        "special_situation_issues": issues,
    }
    assert_public_metadata(insights)
    return by_ticker, insights


def expert_public(plans: list[dict]) -> tuple[dict[str, dict], dict]:
    grouped: dict[str, list[dict]] = {}
    for row in plans:
        if row.get("bucket") != "ticker" or row.get("extension") != "md":
            continue
        ticker = row.get("ticker") or ""
        if not ticker:
            continue
        grouped.setdefault(ticker, []).append(row)
    by_ticker: dict[str, dict] = {}
    for ticker, rows in grouped.items():
        rows.sort(key=lambda item: (item.get("date") or "", item.get("file_id") or ""), reverse=True)
        calls = []
        for row in rows[:PUBLIC_CALL_CAP]:
            date = row.get("date") or ""
            calls.append(
                {
                    "date": date,
                    "company": row.get("company") or ticker,
                    "drive_url": row.get("drive_url") or "",
                    "label": f"Expert call dated {date or 'an unknown date'}",
                }
            )
        by_ticker[ticker] = {"expert_calls": calls, "expert_call_count": len(rows)}
    insights = {
        "generated_at": now_iso(),
        "source": "expert_call_filename_match",
        "note": "Date, company, and Drive link only. Transcripts stay in the private vault.",
        "matched_ticker_count": len(by_ticker),
        "by_ticker": by_ticker,
    }
    assert_public_metadata(insights)
    return by_ticker, insights


def upsert_licensed_sources(
    existing: dict | None,
    *,
    valueline: dict[str, dict] | None = None,
    expert: dict[str, dict] | None = None,
) -> dict:
    """Replace one section and leave the other section alone."""
    by = {ticker: dict(entry) for ticker, entry in ((existing or {}).get("by_ticker") or {}).items()}
    if valueline is not None:
        for ticker, entry in list(by.items()):
            if ticker not in valueline:
                entry.pop("valueline", None)
            if not entry:
                by.pop(ticker, None)
        for ticker, card in valueline.items():
            by.setdefault(ticker, {})["valueline"] = card
    if expert is not None:
        for ticker, entry in list(by.items()):
            if ticker not in expert:
                entry.pop("expert_calls", None)
                entry.pop("expert_call_count", None)
            if not entry:
                by.pop(ticker, None)
        for ticker, card in expert.items():
            slot = by.setdefault(ticker, {})
            slot["expert_calls"] = card.get("expert_calls") or []
            slot["expert_call_count"] = card.get("expert_call_count") or 0
    payload = {
        "generated_at": now_iso(),
        "note": "Safe labels and Drive links. Licensed text is not in this file.",
        "by_ticker": by,
    }
    assert_public_metadata(payload)
    return payload


def csv_cell(value) -> str:
    text = str("" if value is None else value).replace("\r", " ").replace("\n", " ")
    if len(text) > CSV_CELL_MAX:
        text = text[: CSV_CELL_MAX - 3] + "..."
    return assert_public_csv_field(text)


def write_csv(path: Path, columns: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: csv_cell(row.get(column, "")) for column in columns})


def plan_csv_rows(plans: list[dict]) -> list[dict]:
    rows = []
    for row in plans:
        original = row.get("original_name") or ""
        renamed = row.get("new_name") or original
        item = dict(row)
        item["drive_file_id"] = row.get("file_id") or ""
        item["drive_description"] = f"Original filename: {original}" if renamed != original else ""
        rows.append(item)
    rows.sort(key=lambda item: (item.get("bucket") or "", item.get("ticker") or "", item.get("original_name") or ""))
    return rows


def write_plan_csv(path: Path, plans: list[dict]) -> None:
    write_csv(path, PLAN_COLUMNS, plan_csv_rows(plans))


def write_valueline_unmatched(path: Path, rows: list[dict]) -> int:
    unmatched = [row for row in rows if row.get("status") == "unmatched"]
    unmatched.sort(key=lambda row: (row.get("reason") or "", row.get("parsed_ticker") or "", row.get("original_name") or ""))
    prepared = []
    for row in unmatched:
        prepared.append(
            {
                "original_name": row.get("original_name") or "",
                "parsed_ticker": row.get("parsed_ticker") or "",
                "company": row.get("company") or "",
                "report_date": row.get("report_date") or "",
                "edition": row.get("edition") or "",
                "reason": row.get("reason") or "",
                "drive_file_id": row.get("drive_file_id") or "",
                "drive_url": row.get("drive_url") or "",
            }
        )
    write_csv(path, VALUELINE_UNMATCHED_COLUMNS, prepared)
    return len(prepared)


def write_expert_unmatched(path: Path, plans: list[dict]) -> int:
    unmatched = [row for row in plans if row.get("bucket") == "unmatched"]
    unmatched.sort(key=lambda row: (row.get("original_name") or ""))
    prepared = []
    for row in unmatched:
        prepared.append(
            {
                "original_name": row.get("original_name") or "",
                "parsed_company": row.get("parsed_company") or "",
                "ticker": row.get("ticker") or "",
                "confidence": row.get("confidence") or 0,
                "reason": row.get("reason") or "",
                "truncated": row.get("truncated") or False,
                "drive_file_id": row.get("file_id") or "",
                "drive_url": row.get("drive_url") or "",
            }
        )
    write_csv(path, EXPERT_UNMATCHED_COLUMNS, prepared)
    return len(prepared)


def write_json_public(path: Path, payload: dict) -> None:
    assert_public_metadata(payload)
    write_json(path, payload)
