#!/usr/bin/env python3
"""Fetch SEC 13F-HR holdings for biotech specialist funds (portfolio tickers only)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from ownership_common import (  # noqa: E402
    CACHE_DIR,
    RECORDS_DIR,
    cik_padded,
    filing_info_table_url,
    latest_13f_filings,
    load_cusip_map,
    match_holding_to_ticker,
    now_iso,
    parse_13f_info_table_xml,
    portfolio_universe,
    quarter_from_date,
    save_cusip_map,
    save_json,
    sec_fetch_bytes,
    sleep,
    specialist_funds_for_ingest,
)


def _parse_shares(row: dict) -> int | None:
    for key in ("sshPrnamt", "shrsOrPrnAmt", "sshPrnamtType"):
        if key in row and str(row[key]).isdigit():
            return int(str(row[key]))
    nested = row.get("shrsOrPrnAmt")
    if isinstance(nested, dict):
        val = nested.get("sshPrnamt")
        if val is not None and str(val).isdigit():
            return int(str(val))
    raw = row.get("sshPrnamt")
    if raw is not None:
        digits = "".join(ch for ch in str(raw) if ch.isdigit())
        if digits:
            return int(digits)
    return None


def _parse_value(row: dict) -> int | None:
    raw = row.get("value")
    if raw is None:
        return None
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    return int(digits) * 1000 if digits else None


def load_prior_records(quarter: str) -> dict[tuple[str, str], dict]:
    path = RECORDS_DIR / f"{quarter}.json"
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    out: dict[tuple[str, str], dict] = {}
    for row in doc.get("records") or []:
        out[(row.get("fund_id") or "", row.get("ticker") or "")] = row
    return out


def latest_record_quarter(exclude: str | None = None) -> str | None:
    if not RECORDS_DIR.exists():
        return None
    quarters = sorted(p.stem for p in RECORDS_DIR.glob("*.json") if p.stem != "latest")
    for quarter in reversed(quarters):
        if quarter != exclude:
            return quarter
    return None


def change_type(current: dict, prior: dict | None) -> str:
    if not prior:
        return "new"
    cur_sh = current.get("shares") or 0
    prior_sh = prior.get("shares") or 0
    if cur_sh <= 0 and prior_sh > 0:
        return "exit"
    if prior_sh <= 0 and cur_sh > 0:
        return "new"
    if prior_sh <= 0 and cur_sh <= 0:
        return "unchanged"
    delta_pct = (cur_sh - prior_sh) / prior_sh * 100
    if abs(delta_pct) < 1:
        return "unchanged"
    return "add" if delta_pct > 0 else "trim"


def ingest_fund(fund: dict, names: dict[str, str], cusip_map: dict[str, str], prior: dict) -> tuple[list[dict], dict[str, str]]:
    cik = fund["cik"]
    filings = latest_13f_filings(cik, limit=2)
    if not filings:
        return [], cusip_map
    filing = filings[0]
    quarter = quarter_from_date(filing.get("filing_date")) or "unknown"
    cache_path = CACHE_DIR / f"{fund['fund_id']}_{filing['accession'].replace('-', '')}.xml"
    info_url = filing_info_table_url(filing)
    if not info_url:
        return [], cusip_map
    if cache_path.exists():
        xml_bytes = cache_path.read_bytes()
    else:
        try:
            xml_bytes = sec_fetch_bytes(info_url)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(xml_bytes)
        except Exception:
            return [], cusip_map
        sleep()
    holdings = parse_13f_info_table_xml(xml_bytes)
    records: list[dict] = []
    for holding in holdings:
        ticker = match_holding_to_ticker(holding, names, cusip_map)
        cusip = (holding.get("cusip") or "").upper().strip()
        if ticker and cusip:
            cusip_map[cusip] = ticker
        if not ticker:
            continue
        shares = _parse_shares(holding)
        value = _parse_value(holding)
        row = {
            "fund_id": fund["fund_id"],
            "fund": fund.get("fund"),
            "ticker": ticker,
            "quarter": quarter,
            "filing_date": filing.get("filing_date"),
            "shares": shares,
            "market_value_usd": value,
            "cusip": cusip,
            "issuer": holding.get("nameOfIssuer"),
            "source_url": info_url,
            "cik": cik_padded(cik),
        }
        prior_row = prior.get((fund["fund_id"], ticker))
        row["change_type"] = change_type(row, prior_row)
        if prior_row and prior_row.get("shares"):
            row["change_shares_pct"] = round(
                ((row.get("shares") or 0) - prior_row["shares"]) / prior_row["shares"] * 100,
                2,
            )
        records.append(row)
    return records, cusip_map


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Use cached XML only; do not fetch SEC")
    parser.add_argument("--max-funds", type=int, default=0, help="Limit funds for testing")
    args = parser.parse_args()

    if args.offline and not CACHE_DIR.exists():
        print("No cache directory; run without --offline first")
        return 0

    _, names = portfolio_universe()
    funds = specialist_funds_for_ingest()
    if args.max_funds:
        funds = funds[: args.max_funds]
    if not funds:
        print("No specialist funds with CIKs configured")
        return 0

    cusip_map = load_cusip_map()
    all_records: list[dict] = []
    quarter_counts: dict[str, int] = {}

    for fund in funds:
        prior_quarter = latest_record_quarter()
        prior = load_prior_records(prior_quarter) if prior_quarter else {}
        if args.offline:
            # offline mode: rebuild from existing cache files only
            cache_files = sorted(CACHE_DIR.glob(f"{fund['fund_id']}_*.xml"), reverse=True)
            if not cache_files:
                continue
            xml_bytes = cache_files[0].read_bytes()
            holdings = parse_13f_info_table_xml(xml_bytes)
            prior = {}
            for holding in holdings:
                ticker = match_holding_to_ticker(holding, names, cusip_map)
                cusip = (holding.get("cusip") or "").upper().strip()
                if ticker and cusip:
                    cusip_map[cusip] = ticker
                if not ticker:
                    continue
                row = {
                    "fund_id": fund["fund_id"],
                    "fund": fund.get("fund"),
                    "ticker": ticker,
                    "quarter": "cached",
                    "shares": _parse_shares(holding),
                    "market_value_usd": _parse_value(holding),
                    "cusip": cusip,
                    "issuer": holding.get("nameOfIssuer"),
                    "source_url": None,
                    "change_type": "unchanged",
                }
                all_records.append(row)
            continue

        records, cusip_map = ingest_fund(fund, names, cusip_map, prior)
        all_records.extend(records)
        for row in records:
            quarter_counts[row.get("quarter") or "unknown"] = quarter_counts.get(row.get("quarter") or "unknown", 0) + 1
        print(f"{fund['fund_id']}: {len(records)} portfolio holdings")
        sleep()

    save_cusip_map(cusip_map)

    if not all_records:
        print("No ownership records produced")
        return 0

    quarter = max(quarter_counts, key=quarter_counts.get) if quarter_counts else all_records[0].get("quarter") or "latest"
    payload = {
        "generated_at": now_iso(),
        "quarter": quarter,
        "fund_count": len({r['fund_id'] for r in all_records}),
        "record_count": len(all_records),
        "records": sorted(all_records, key=lambda r: (r.get("ticker") or "", r.get("fund_id") or "")),
    }
    RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    save_json(RECORDS_DIR / f"{quarter}.json", payload)
    save_json(RECORDS_DIR / "latest.json", payload)
    print(f"Wrote {len(all_records)} records for {quarter}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
