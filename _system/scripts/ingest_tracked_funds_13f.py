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
    latest_13f_filings,
    load_cusip_map,
    load_json,
    match_holding_to_ticker,
    now_iso,
    portfolio_universe,
    save_json,
    slug,
)
from thirteenf_period import build_period, periods_for_fund  # noqa: E402

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


def _saved_accession(fund_id: str, quarter: str) -> str | None:
    path = RECORDS_DIR / f"{quarter}.json"
    if not path.exists():
        return None
    rows = [row for row in json.loads(path.read_text(encoding="utf-8")).get("records") or [] if row.get("fund_id") == fund_id]
    if not rows or any(row.get("shares") in (None, "") for row in rows):
        return None
    accessions = {row.get("accession") for row in rows}
    if len(accessions) == 1:
        return next(iter(accessions))
    return None


def _periods_already_saved(fund_id: str, groups: list[list[dict]]) -> bool:
    from thirteenf_core import quarter_from_period

    for group in groups:
        quarter = quarter_from_period(group[-1].get("report_date"))
        if not quarter or _saved_accession(fund_id, quarter) != group[-1].get("accession"):
            return False
    return True


def _keep_saved(fund_id: str, groups: list[list[dict]], by_quarter: dict[str, list[dict]]) -> None:
    from thirteenf_core import quarter_from_period

    for group in groups:
        quarter = quarter_from_period(group[-1].get("report_date"))
        path = RECORDS_DIR / f"{quarter}.json"
        if not path.exists():
            continue
        rows = [row for row in json.loads(path.read_text(encoding="utf-8")).get("records") or [] if row.get("fund_id") == fund_id]
        by_quarter.setdefault(quarter, []).extend(rows)


def holdings_book_rows(
    fund: dict,
    positions: list[dict],
    filing: dict | None,
    names: dict[str, str],
    cusip_map: dict[str, str],
    prior: dict,
    info_url: str | None,
    quarter: str,
) -> list[dict]:
    """Portfolio overlay. Name matches are not written back into the CUSIP map."""
    book_set = {t.upper() for t in names}
    book_rows: list[dict] = []
    for holding in positions:
        if holding.get("put_call"):
            continue
        if (holding.get("sh_prn") or "SH").upper() not in {"SH", ""}:
            continue
        cusip = (holding.get("cusip") or "").upper().strip()
        shares = holding.get("shares")
        value = holding.get("value_usd")
        issuer = holding.get("issuer")
        probe = {"cusip": cusip, "nameOfIssuer": issuer}
        ticker = match_holding_to_ticker(probe, names, cusip_map)
        if not ticker or ticker.upper() not in book_set:
            continue
        prior_row = prior.get((fund["fund_id"], ticker))
        row = {
            "fund_id": fund["fund_id"],
            "fund": fund.get("fund"),
            "ticker": ticker,
            "quarter": quarter,
            "period_end": (filing or {}).get("period_end"),
            "filing_date": (filing or {}).get("filing_date"),
            "accession": (filing or {}).get("accession"),
            "shares": shares,
            "market_value_usd": value,
            "cusip": cusip,
            "issuer": issuer,
            "source_url": info_url,
            "cik": cik_padded(fund["cik"]),
            "change_type": change_type({"shares": shares}, prior_row),
            "in_base_irr": False,
        }
        if prior_row and prior_row.get("shares"):
            row["change_shares_pct"] = round(
                ((shares or 0) - prior_row["shares"]) / prior_row["shares"] * 100,
                2,
            )
        book_rows.append(row)
    return book_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Use cached XML only; do not fetch SEC")
    parser.add_argument("--max-funds", type=int, default=0, help="Limit funds for testing")
    parser.add_argument("--periods", type=int, default=2, help="How many report periods to write (default 2)")
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
    by_quarter: dict[str, list[dict]] = {}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    RECORDS_DIR.mkdir(parents=True, exist_ok=True)

    for fund in funds:
        if args.offline:
            filings = []
            for meta_path in sorted(CACHE_DIR.glob(f"{fund['fund_id']}_*.meta.json")):
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                accession = meta_path.name[len(fund["fund_id"]) + 1 : -len(".meta.json")]
                filings.append(
                    {
                        "form": meta.get("form") or "13F-HR",
                        "filing_date": meta.get("filing_date"),
                        "report_date": meta.get("report_date"),
                        "accession": accession,
                        "index_url": "",
                    }
                )
        else:
            filings = latest_13f_filings(fund["cik"], limit=12)
        groups = periods_for_fund(filings, args.periods)
        if not groups:
            print(f"{fund['fund_id']}: no 13F-HR period")
            continue
        if _periods_already_saved(fund["fund_id"], groups):
            print(f"{fund['fund_id']}: unchanged")
            _keep_saved(fund["fund_id"], groups, by_quarter)
            continue
        fund_rows = 0
        running_prior: dict[tuple[str, str], dict] = {}
        for group in groups:
            built = build_period(group, fund_id=fund["fund_id"], cache_dir=CACHE_DIR, offline=args.offline)
            if not built:
                continue
            quarter = built["quarter"]
            prior = running_prior
            filing_meta = {
                "period_end": built["period_end"],
                "filing_date": built["filing_date"],
                "accession": built["accession"],
            }
            book_rows = holdings_book_rows(
                fund, built["rows"], filing_meta, names, cusip_map, prior, built["source_url"], quarter
            )
            by_quarter.setdefault(quarter, []).extend(book_rows)
            running_prior = {(row["fund_id"], row["ticker"]): row for row in book_rows}
            fund_rows += len(book_rows)
            if not built["reconciliation"].get("ok"):
                print(f"{fund['fund_id']} {quarter}: reconciliation {built['reconciliation']}")
        print(f"{fund['fund_id']}: {fund_rows} book matches")

    if not by_quarter:
        payload = {
            "generated_at": now_iso(),
            "quarter": None,
            "fund_count": 0,
            "record_count": 0,
            "records": [],
            "status": "empty",
            "notes": "No portfolio-matched tracked-fund holdings this run.",
            "in_base_irr": False,
        }
        save_json(RECORDS_DIR / "latest.json", payload)
        print("No portfolio-matched tracked-fund records")
        return 0

    latest_quarter = sorted(by_quarter)[-1]
    for quarter, rows in by_quarter.items():
        payload = {
            "generated_at": now_iso(),
            "quarter": quarter,
            "period_end": rows[0].get("period_end") if rows else None,
            "fund_count": len({r["fund_id"] for r in rows}),
            "record_count": len(rows),
            "records": sorted(rows, key=lambda r: (r.get("ticker") or "", r.get("fund_id") or "")),
            "status": "ok",
            "in_base_irr": False,
            "notes": "Portfolio overlay only. Quarter is the period of report, not the filing date. Context tier, not base IRR.",
        }
        save_json(RECORDS_DIR / f"{quarter}.json", payload)
        if quarter == latest_quarter:
            save_json(RECORDS_DIR / "latest.json", payload)
        print(f"Wrote {len(rows)} tracked-fund book records for {quarter}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
