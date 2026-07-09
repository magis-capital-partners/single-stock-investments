#!/usr/bin/env python3
"""Fetch SEC 13F-HR holdings for curated great / value-shop funds.

Writes portfolio-ticker overlay under:
  _system/reference/market-data/ownership/tracked_funds/records/
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from ownership_common import (  # noqa: E402
    OWNERSHIP_DIR,
    cik_padded,
    filing_info_table_url,
    latest_13f_filings,
    load_cusip_map,
    load_json,
    match_holding_to_ticker,
    now_iso,
    parse_13f_info_table_xml,
    portfolio_universe,
    quarter_from_date,
    save_cusip_map,
    save_json,
    sec_fetch_bytes,
    sleep,
    slug,
)

TRACKED_DIR = OWNERSHIP_DIR / "tracked_funds"
FUNDS_PATH = OWNERSHIP_DIR / "tracked_funds.json"
CIK_PATH = OWNERSHIP_DIR / "tracked_fund_cik_registry.json"
RECORDS_DIR = TRACKED_DIR / "records"
CACHE_DIR = TRACKED_DIR / "cache"


def tracked_funds_for_ingest() -> list[dict]:
    funds_doc = load_json(FUNDS_PATH, {"funds": []})
    cik_doc = load_json(CIK_PATH, {"funds": {}})
    cik_by_id = cik_doc.get("funds") or {}
    out: list[dict] = []
    for fund in funds_doc.get("funds") or []:
        if fund.get("signal_role") != "tracked_fund_13f":
            continue
        if fund.get("ingest_13f") is False:
            continue
        fid = fund.get("fund_id") or slug(fund.get("fund"))
        cik_entry = cik_by_id.get(fid) or {}
        cik = fund.get("cik") or cik_entry.get("cik")
        if not cik:
            continue
        out.append({**fund, "fund_id": fid, "cik": str(cik).lstrip("0")})
    return out


def _parse_shares(row: dict) -> int | None:
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
    if not digits:
        return None
    return int(digits)


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
    quarters = sorted(
        p.stem
        for p in RECORDS_DIR.glob("*.json")
        if p.stem not in {"latest", "cached", "unknown"} and len(p.stem) == 6 and p.stem[4] == "Q"
    )
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


def holdings_book_rows(
    fund: dict,
    xml_bytes: bytes,
    filing: dict | None,
    names: dict[str, str],
    cusip_map: dict[str, str],
    prior: dict,
    info_url: str | None,
) -> tuple[list[dict], dict[str, str]]:
    raw = parse_13f_info_table_xml(xml_bytes)
    quarter = quarter_from_date((filing or {}).get("filing_date")) or "unknown"
    book_set = {t.upper() for t in names}
    book_rows: list[dict] = []
    for holding in raw:
        cusip = (holding.get("cusip") or "").upper().strip()
        shares = _parse_shares(holding)
        value = _parse_value(holding)
        issuer = holding.get("nameOfIssuer")
        ticker = match_holding_to_ticker(holding, names, cusip_map)
        if ticker and cusip and ticker in book_set:
            cusip_map[cusip] = ticker
        elif ticker and cusip and cusip not in cusip_map:
            cusip_map[cusip] = ticker
        if not ticker or ticker.upper() not in book_set:
            continue
        prior_row = prior.get((fund["fund_id"], ticker))
        row = {
            "fund_id": fund["fund_id"],
            "fund": fund.get("fund"),
            "ticker": ticker,
            "quarter": quarter,
            "filing_date": (filing or {}).get("filing_date"),
            "shares": shares,
            "market_value_usd": value,
            "cusip": cusip,
            "issuer": issuer,
            "source_url": info_url,
            "cik": cik_padded(fund["cik"]),
            "change_type": change_type({"shares": shares}, prior_row),
        }
        if prior_row and prior_row.get("shares"):
            row["change_shares_pct"] = round(
                ((shares or 0) - prior_row["shares"]) / prior_row["shares"] * 100,
                2,
            )
        book_rows.append(row)
    return book_rows, cusip_map


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Use cached XML only; do not fetch SEC")
    parser.add_argument("--max-funds", type=int, default=0, help="Limit funds for testing")
    args = parser.parse_args()

    if args.offline and not CACHE_DIR.exists():
        print("No tracked-funds cache directory; run without --offline first")
        # Still write empty latest so source_health can report empty/missing cleanly
        RECORDS_DIR.mkdir(parents=True, exist_ok=True)
        empty = {
            "generated_at": now_iso(),
            "quarter": None,
            "fund_count": 0,
            "record_count": 0,
            "records": [],
            "status": "empty",
            "notes": "No cache yet for offline tracked-funds ingest.",
        }
        save_json(RECORDS_DIR / "latest.json", empty)
        return 0

    tickers, names = portfolio_universe()
    funds = tracked_funds_for_ingest()
    if args.max_funds:
        funds = funds[: args.max_funds]
    if not funds:
        print("No tracked funds with CIKs configured")
        return 0

    cusip_map = load_cusip_map()
    all_book: list[dict] = []
    quarter_counts: dict[str, int] = {}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    RECORDS_DIR.mkdir(parents=True, exist_ok=True)

    prior_quarter = latest_record_quarter()
    prior = load_prior_records(prior_quarter) if prior_quarter else {}

    for fund in funds:
        book_rows: list[dict] = []
        if args.offline:
            cache_files = sorted(CACHE_DIR.glob(f"{fund['fund_id']}_*.xml"), reverse=True)
            if not cache_files:
                print(f"{fund['fund_id']}: no cache")
                continue
            xml_bytes = cache_files[0].read_bytes()
            book_rows, cusip_map = holdings_book_rows(fund, xml_bytes, None, names, cusip_map, prior, None)
            # Prefer quarter from prior latest if present
            if book_rows and book_rows[0].get("quarter") in {None, "unknown"}:
                q = prior_quarter or "unknown"
                for row in book_rows:
                    row["quarter"] = q
        else:
            filings = latest_13f_filings(fund["cik"], limit=2)
            if not filings:
                print(f"{fund['fund_id']}: no 13F filings")
                continue
            filing = filings[0]
            info_url = filing_info_table_url(filing)
            sleep()
            if not info_url:
                print(f"{fund['fund_id']}: no InfoTable")
                continue
            cache_path = CACHE_DIR / f"{fund['fund_id']}_{filing['accession'].replace('-', '')}.xml"
            if cache_path.exists():
                xml_bytes = cache_path.read_bytes()
            else:
                try:
                    xml_bytes = sec_fetch_bytes(info_url)
                    cache_path.write_bytes(xml_bytes)
                except Exception as exc:  # noqa: BLE001
                    print(f"{fund['fund_id']}: fetch failed ({exc})")
                    continue
                sleep()
            book_rows, cusip_map = holdings_book_rows(
                fund, xml_bytes, filing, names, cusip_map, prior, info_url
            )

        all_book.extend(book_rows)
        for row in book_rows:
            q = row.get("quarter") or "unknown"
            quarter_counts[q] = quarter_counts.get(q, 0) + 1
        print(f"{fund['fund_id']}: {len(book_rows)} book matches")

    save_cusip_map(cusip_map)

    if not all_book:
        payload = {
            "generated_at": now_iso(),
            "quarter": prior_quarter,
            "fund_count": 0,
            "record_count": 0,
            "records": [],
            "status": "empty",
            "notes": "No portfolio-matched tracked-fund holdings this run.",
        }
        save_json(RECORDS_DIR / "latest.json", payload)
        print("No portfolio-matched tracked-fund records")
        return 0

    quarter = max(quarter_counts, key=quarter_counts.get) if quarter_counts else all_book[0].get("quarter") or "latest"
    payload = {
        "generated_at": now_iso(),
        "quarter": quarter,
        "fund_count": len({r["fund_id"] for r in all_book}),
        "record_count": len(all_book),
        "records": sorted(all_book, key=lambda r: (r.get("ticker") or "", r.get("fund_id") or "")),
        "status": "ok",
        "notes": "Portfolio/watchlist overlay only for curated great funds.",
    }
    save_json(RECORDS_DIR / f"{quarter}.json", payload)
    save_json(RECORDS_DIR / "latest.json", payload)
    print(f"Wrote {len(all_book)} tracked-fund book records for {quarter}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
