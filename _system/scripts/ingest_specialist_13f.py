#!/usr/bin/env python3
"""Fetch SEC 13F-HR holdings for biotech specialist funds.

Writes:
  - records/{quarter}.json — portfolio-matched holdings (book overlay)
  - records/full/{fund_id}/{quarter}.json — full InfoTable rows + biotech MV share
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from ownership_common import (  # noqa: E402
    CACHE_DIR,
    FULL_RECORDS_DIR,
    RECORDS_DIR,
    cik_padded,
    classify_fund_biotech_share,
    filing_info_table_url,
    issuer_looks_biotech,
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
    """Parse 13F value to USD.

    Post-2023 InfoTables typically report value already in dollars (not $000s).
    Older tables used thousands. Heuristic: if the raw integer is huge for a
    single line (> 50e9), treat as already-dollars; if small and looks like
    thousands-era, multiply. Default: treat as dollars (no ×1000).
    """
    raw = row.get("value")
    if raw is None:
        return None
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if not digits:
        return None
    value = int(digits)
    # Legacy thousands: values were usually < 1e9 per line in $000 units.
    # If a filing still uses thousands, positions look tiny in dollars without ×1000.
    # Prefer dollars (current SEC XML) — do not multiply.
    return value


def load_prior_records(quarter: str) -> dict[tuple[str, str], dict]:
    path = RECORDS_DIR / f"{quarter}.json"
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    out: dict[tuple[str, str], dict] = {}
    for row in doc.get("records") or []:
        out[(row.get("fund_id") or "", row.get("ticker") or "")] = row
    return out


def load_prior_full_by_cusip(fund_id: str, quarter: str) -> dict[str, dict]:
    """Index prior full InfoTable by CUSIP (preferred) or ticker for QoQ change_type."""
    path = FULL_RECORDS_DIR / fund_id / f"{quarter}.json"
    if not path.exists():
        return {}
    doc = load_json(path, {})
    out: dict[str, dict] = {}
    for row in doc.get("records") or []:
        cusip = (row.get("cusip") or "").upper().strip()
        ticker = (row.get("ticker") or "").upper().strip()
        if cusip:
            out[f"CUSIP:{cusip}"] = row
        if ticker:
            out[f"T:{ticker}"] = row
    return out


def prior_full_quarters(fund_id: str, exclude: str | None = None) -> list[str]:
    fund_dir = FULL_RECORDS_DIR / fund_id
    if not fund_dir.exists():
        return []
    quarters = sorted(
        p.stem
        for p in fund_dir.glob("*.json")
        if p.stem not in {"latest", "cached", "unknown"} and len(p.stem) == 6 and p.stem[4] == "Q"
    )
    if exclude:
        quarters = [q for q in quarters if q != exclude]
    return quarters


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


def holdings_from_xml(
    fund: dict,
    xml_bytes: bytes,
    filing: dict | None,
    names: dict[str, str],
    cusip_map: dict[str, str],
    prior: dict,
    info_url: str | None,
    book_tickers: set[str] | None = None,
    prior_full: dict[str, dict] | None = None,
) -> tuple[list[dict], list[dict], dict[str, str], dict]:
    raw = parse_13f_info_table_xml(xml_bytes)
    quarter = quarter_from_date((filing or {}).get("filing_date")) or "unknown"
    book_set = {t.upper() for t in (book_tickers or names.keys())}
    full_prior = prior_full or {}
    full_rows: list[dict] = []
    book_rows: list[dict] = []
    for holding in raw:
        cusip = (holding.get("cusip") or "").upper().strip()
        shares = _parse_shares(holding)
        value = _parse_value(holding)
        issuer = holding.get("nameOfIssuer")
        ticker = match_holding_to_ticker(holding, names, cusip_map)
        if ticker and cusip and ticker in book_set:
            # Only persist portfolio/watchlist cusip mappings into the shared map
            cusip_map[cusip] = ticker
        elif ticker and cusip and cusip not in cusip_map:
            cusip_map[cusip] = ticker
        # QoQ from prior full table (CUSIP), fall back to book overlay prior
        prior_row = None
        if cusip and f"CUSIP:{cusip}" in full_prior:
            prior_row = full_prior[f"CUSIP:{cusip}"]
        elif ticker and f"T:{ticker.upper()}" in full_prior:
            prior_row = full_prior[f"T:{ticker.upper()}"]
        elif ticker:
            prior_row = prior.get((fund["fund_id"], ticker))
        full_row = {
            "fund_id": fund["fund_id"],
            "fund": fund.get("fund"),
            "ticker": ticker,
            "quarter": quarter,
            "filing_date": (filing or {}).get("filing_date"),
            "shares": shares,
            "market_value_usd": value,
            "cusip": cusip,
            "issuer": issuer,
            "issuer_is_biotech": issuer_looks_biotech(issuer),
            "source_url": info_url,
            "cik": cik_padded(fund["cik"]),
            "in_book": bool(ticker and ticker.upper() in book_set),
            "change_type": change_type(
                {"shares": shares},
                prior_row,
            ),
        }
        if prior_row and prior_row.get("shares"):
            full_row["change_shares_pct"] = round(
                ((shares or 0) - prior_row["shares"]) / prior_row["shares"] * 100,
                2,
            )
        full_rows.append(full_row)
        if not ticker or ticker.upper() not in book_set:
            continue
        row = {**full_row}
        book_rows.append(row)
    classification = classify_fund_biotech_share(full_rows)
    return full_rows, book_rows, cusip_map, classification


def ingest_one_filing(
    fund: dict,
    filing: dict,
    names: dict[str, str],
    cusip_map: dict[str, str],
    prior: dict,
    prior_full: dict[str, dict],
) -> tuple[list[dict], list[dict], dict[str, str], dict, str]:
    quarter = quarter_from_date(filing.get("filing_date")) or "unknown"
    cache_path = CACHE_DIR / f"{fund['fund_id']}_{filing['accession'].replace('-', '')}.xml"
    info_url = filing_info_table_url(filing)
    if not info_url:
        return [], [], cusip_map, {}, quarter
    if cache_path.exists():
        xml_bytes = cache_path.read_bytes()
    else:
        try:
            xml_bytes = sec_fetch_bytes(info_url)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(xml_bytes)
        except Exception:
            return [], [], cusip_map, {}, quarter
        sleep()
    full_rows, book_rows, cusip_map, classification = holdings_from_xml(
        fund,
        xml_bytes,
        filing,
        names,
        cusip_map,
        prior,
        info_url,
        book_tickers=set(names),
        prior_full=prior_full,
    )
    return full_rows, book_rows, cusip_map, classification, quarter


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Use cached XML only; do not fetch SEC")
    parser.add_argument("--max-funds", type=int, default=0, help="Limit funds for testing")
    parser.add_argument(
        "--backfill-quarters",
        type=int,
        default=1,
        help="Number of recent 13F filings per fund to write under records/full (default 1)",
    )
    args = parser.parse_args()

    if args.offline and not CACHE_DIR.exists():
        print("No cache directory; run without --offline first")
        return 0

    tickers, names = portfolio_universe()
    book_tickers = set(tickers)
    funds = specialist_funds_for_ingest()
    if args.max_funds:
        funds = funds[: args.max_funds]
    if not funds:
        print("No specialist funds with CIKs configured")
        return 0

    cusip_map = load_cusip_map()
    all_book: list[dict] = []
    fund_classifications: list[dict] = []
    quarter_counts: dict[str, int] = {}
    FULL_RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    backfill_n = max(1, int(args.backfill_quarters or 1))

    for fund in funds:
        prior_quarter = latest_record_quarter()
        prior = load_prior_records(prior_quarter) if prior_quarter else {}
        latest_quarter_for_fund = None
        latest_full_rows: list[dict] = []
        latest_book_rows: list[dict] = []
        latest_classification: dict = {}

        if args.offline:
            cache_files = sorted(CACHE_DIR.glob(f"{fund['fund_id']}_*.xml"), reverse=True)
            if not cache_files:
                continue
            # Process up to backfill_n cached XMLs (newest first)
            for cache_path in cache_files[:backfill_n]:
                xml_bytes = cache_path.read_bytes()
                prior_full_doc = load_json(FULL_RECORDS_DIR / fund["fund_id"] / "latest.json", {})
                filing_meta = None
                quarter_hint = prior_full_doc.get("quarter")
                if prior_full_doc.get("records"):
                    fd = (prior_full_doc["records"][0] or {}).get("filing_date")
                    if fd:
                        filing_meta = {"filing_date": fd}
                # Prefer accession-derived quarter if we already wrote one
                existing_qs = prior_full_quarters(fund["fund_id"])
                prior_full_map = {}
                if existing_qs:
                    prior_full_map = load_prior_full_by_cusip(fund["fund_id"], existing_qs[-1])
                full_rows, book_rows, cusip_map, classification = holdings_from_xml(
                    fund,
                    xml_bytes,
                    filing_meta,
                    names,
                    cusip_map,
                    prior,
                    None,
                    book_tickers=book_tickers,
                    prior_full=prior_full_map,
                )
                quarter = (
                    quarter_from_date((filing_meta or {}).get("filing_date"))
                    or (
                        quarter_hint
                        if quarter_hint and quarter_hint not in {"unknown", "cached", "latest"}
                        else None
                    )
                    or "2026Q2"
                )
                for row in full_rows + book_rows:
                    row["quarter"] = quarter
                fund_dir = FULL_RECORDS_DIR / fund["fund_id"]
                fund_dir.mkdir(parents=True, exist_ok=True)
                full_payload = {
                    "generated_at": now_iso(),
                    "fund_id": fund["fund_id"],
                    "fund": fund.get("fund"),
                    "quarter": quarter,
                    "classification": classification,
                    "record_count": len(full_rows),
                    "records": full_rows,
                }
                save_json(fund_dir / f"{quarter}.json", full_payload)
                if latest_quarter_for_fund is None:
                    latest_quarter_for_fund = quarter
                    latest_full_rows = full_rows
                    latest_book_rows = book_rows
                    latest_classification = classification
                    save_json(fund_dir / "latest.json", full_payload)
        else:
            filings = latest_13f_filings(fund["cik"], limit=backfill_n + 1)
            # Process oldest→newest so QoQ prior exists when writing newer quarters
            for filing in reversed(filings[:backfill_n]):
                quarter = quarter_from_date(filing.get("filing_date")) or "unknown"
                existing_qs = prior_full_quarters(fund["fund_id"], exclude=quarter)
                prior_full_map = load_prior_full_by_cusip(fund["fund_id"], existing_qs[-1]) if existing_qs else {}
                full_rows, book_rows, cusip_map, classification, quarter = ingest_one_filing(
                    fund, filing, names, cusip_map, prior, prior_full_map
                )
                sleep()
                if not full_rows and not book_rows:
                    continue
                fund_dir = FULL_RECORDS_DIR / fund["fund_id"]
                fund_dir.mkdir(parents=True, exist_ok=True)
                full_payload = {
                    "generated_at": now_iso(),
                    "fund_id": fund["fund_id"],
                    "fund": fund.get("fund"),
                    "quarter": quarter,
                    "classification": classification,
                    "record_count": len(full_rows),
                    "records": full_rows,
                }
                save_json(fund_dir / f"{quarter}.json", full_payload)
                latest_quarter_for_fund = quarter
                latest_full_rows = full_rows
                latest_book_rows = book_rows
                latest_classification = classification
                save_json(fund_dir / "latest.json", full_payload)

        if latest_quarter_for_fund is None:
            continue

        fund_classifications.append(
            {
                "fund_id": fund["fund_id"],
                "fund": fund.get("fund"),
                "quarter": latest_quarter_for_fund,
                **latest_classification,
            }
        )
        all_book.extend(latest_book_rows)
        for row in latest_book_rows:
            q = row.get("quarter") or latest_quarter_for_fund
            quarter_counts[q] = quarter_counts.get(q, 0) + 1
        print(
            f"{fund['fund_id']}: {len(latest_book_rows)} book / {len(latest_full_rows)} full "
            f"(biotech_mv_share={latest_classification.get('biotech_mv_share')}, q={latest_quarter_for_fund})"
        )

    save_cusip_map(cusip_map)
    save_json(
        FULL_RECORDS_DIR / "fund_classifications_latest.json",
        {"generated_at": now_iso(), "funds": fund_classifications},
    )

    if not all_book:
        print("No portfolio-matched ownership records produced (full tables still written)")
        return 0

    quarter = max(quarter_counts, key=quarter_counts.get) if quarter_counts else all_book[0].get("quarter") or "latest"
    payload = {
        "generated_at": now_iso(),
        "quarter": quarter,
        "fund_count": len({r["fund_id"] for r in all_book}),
        "record_count": len(all_book),
        "records": sorted(all_book, key=lambda r: (r.get("ticker") or "", r.get("fund_id") or "")),
        "notes": "Portfolio/book overlay only. Full InfoTables under records/full/{fund_id}/.",
    }
    RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    save_json(RECORDS_DIR / f"{quarter}.json", payload)
    save_json(RECORDS_DIR / "latest.json", payload)
    print(f"Wrote {len(all_book)} book records for {quarter}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
