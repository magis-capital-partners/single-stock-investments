#!/usr/bin/env python3
"""Fetch one manager's 13F period and return a merged, aggregated book."""
from __future__ import annotations

import json
from pathlib import Path

from ownership_common import filing_document_urls, sec_fetch_bytes, sleep
from thirteenf_core import (
    aggregate_positions,
    group_filings_by_period,
    merge_filings,
    normalize_info_rows,
    parse_info_table_xml,
    parse_primary_doc_xml,
    quarter_from_period,
    reconcile,
)


def _cache_paths(cache_dir: Path, fund_id: str, accession: str) -> tuple[Path, Path, Path]:
    stem = f"{fund_id}_{accession.replace('-', '')}"
    return (
        cache_dir / f"{stem}.xml",
        cache_dir / f"{stem}.primary.xml",
        cache_dir / f"{stem}.meta.json",
    )


def _read_cached(path: Path) -> bytes | None:
    if path.exists() and path.stat().st_size > 0:
        return path.read_bytes()
    return None


def fetch_filing_tables(filing: dict, *, fund_id: str, cache_dir: Path, offline: bool) -> dict | None:
    """Return parsed rows plus cover-page fields for one accession."""
    accession = filing.get("accession") or "unknown"
    info_path, primary_path, meta_path = _cache_paths(cache_dir, fund_id, accession)
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {}
    info_url = meta.get("info_url")
    primary_url = meta.get("primary_url")
    info_bytes = _read_cached(info_path)
    primary_bytes = _read_cached(primary_path)
    if info_bytes is None:
        if offline:
            return None
        urls = filing_document_urls(filing)
        sleep()
        info_url = urls.get("info_table")
        primary_url = urls.get("primary")
        if not info_url:
            return None
        info_bytes = sec_fetch_bytes(info_url)
        info_path.parent.mkdir(parents=True, exist_ok=True)
        info_path.write_bytes(info_bytes)
        sleep()
        if primary_url:
            primary_bytes = sec_fetch_bytes(primary_url)
            primary_path.write_bytes(primary_bytes)
            sleep()
        meta_path.write_text(
            json.dumps({"info_url": info_url, "primary_url": primary_url, "form": filing.get("form"), "report_date": filing.get("report_date"), "filing_date": filing.get("filing_date")})
            + "\n",
            encoding="utf-8",
        )
    elif primary_bytes is None and not offline and primary_url:
        primary_bytes = sec_fetch_bytes(primary_url)
        primary_path.write_bytes(primary_bytes)
        sleep()
    raw = parse_info_table_xml(info_bytes)
    filing_date = filing.get("filing_date") or meta.get("filing_date")
    rows = normalize_info_rows(raw, filing_date=filing_date)
    primary = parse_primary_doc_xml(primary_bytes) if primary_bytes else {}
    if primary.get("table_value_total_usd") is not None and filing_date:
        # Cover-page total uses the same units as the info-table value column.
        from thirteenf_core import value_to_usd

        primary = dict(primary)
        primary["table_value_total_usd"] = value_to_usd(primary["table_value_total_usd"], filing_date)
    return {
        "form": filing.get("form"),
        "filing_date": filing_date,
        "report_date": filing.get("report_date") or meta.get("report_date") or primary.get("period_end"),
        "accession": accession,
        "info_url": info_url,
        "rows": rows,
        "raw_count": len(raw),
        "amendment_type": primary.get("amendment_type"),
        "primary": primary,
    }


def build_period(filings: list[dict], *, fund_id: str, cache_dir: Path, offline: bool) -> dict | None:
    """Merge every holdings filing in one period. Notices never become the book."""
    parsed = []
    for filing in filings:
        if filing.get("form") not in {"13F-HR", "13F-HR/A"}:
            continue
        loaded = fetch_filing_tables(filing, fund_id=fund_id, cache_dir=cache_dir, offline=offline)
        if loaded is None:
            continue
        parsed.append(loaded)
    if not parsed:
        return None
    merged = merge_filings(parsed)
    # Reconcile against the latest full book (a restatement, or the original HR).
    anchor = parsed[-1]
    for item in reversed(parsed):
        if item.get("form") == "13F-HR" or item.get("amendment_type") == "RESTATEMENT":
            anchor = item
            break
    period = anchor.get("report_date") or parsed[-1].get("report_date")
    report = reconcile(anchor.get("raw_count") or 0, aggregate_positions(anchor.get("rows") or []), anchor.get("primary") or {})
    # Merged value can exceed the anchor when NEW HOLDINGS rows were added.
    if any(item.get("amendment_type") == "NEW HOLDINGS" for item in parsed):
        report = dict(report)
        report["includes_new_holdings"] = True
    return {
        "period_end": period,
        "quarter": quarter_from_period(period) or "unknown",
        "filing_date": parsed[-1].get("filing_date"),
        "accession": parsed[-1].get("accession"),
        "source_url": anchor.get("info_url") or parsed[-1].get("info_url"),
        "rows": merged,
        "reconciliation": report,
        "confidential_omitted": any((item.get("primary") or {}).get("confidential_omitted") for item in parsed),
        "forms": [item.get("form") for item in parsed],
    }


def periods_for_fund(filings: list[dict], count: int) -> list[list[dict]]:
    return group_filings_by_period(filings, periods=count)
