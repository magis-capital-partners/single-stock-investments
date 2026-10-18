#!/usr/bin/env python3
"""N-PORT holdings for non-US names in the SSI book.

Uses SEC EDGAR only. OpenFIGI is optional and unused here: a holding is kept
when the issuer name matches one portfolio company. Missing matches stay out
of the file rather than being guessed. Holdings are context, not a valuation input.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_managers_json import distinctive_tokens  # noqa: E402
from intl_holdings import is_international, match_portfolio_ticker, parse_nport_holdings  # noqa: E402
from ownership_common import (  # noqa: E402
    cik_padded,
    fetch_submissions,
    portfolio_universe,
    sec_fetch_bytes,
    sec_fetch_json,
)
from sec_client import get_json  # noqa: E402

OWNERSHIP = ROOT / "_system" / "reference" / "market-data" / "ownership"
MANAGERS = OWNERSHIP / "managers.json"
OUT_DIR = OWNERSHIP / "intl" / "nport"
DASH = ROOT / "dashboard" / "data" / "holdings" / "intl"
STATUS = OUT_DIR / "status.json"

# Public registered-fund names. The adviser CIK often does not file N-PORT; the trust does.
FUND_FAMILY = {
    "harris-associates": ["Oakmark Funds"],
    "ruane-cunniff": ["Sequoia Fund"],
    "dodge-cox": ["Dodge & Cox Funds"],
    "tweedy-browne": ["Tweedy Browne Fund"],
    "first-eagle": ["First Eagle Funds"],
}


def _managers(tracked_only: bool) -> list[dict]:
    rows = json.loads(MANAGERS.read_text(encoding="utf-8")).get("managers") or []
    kept = []
    for row in rows:
        if row.get("book") != "full" or not row.get("cik"):
            continue
        if tracked_only and "tracked" not in (row.get("roles") or []):
            continue
        kept.append(row)
    return kept


def _nport_from_submissions(cik: str) -> dict | None:
    submissions = fetch_submissions(cik)
    recent = ((submissions.get("filings") or {}).get("recent") or {})
    forms = recent.get("form") or []
    accessions = recent.get("accessionNumber") or []
    dates = recent.get("reportDate") or []
    for form, accession, period in zip(forms, accessions, dates):
        if form in {"NPORT-P", "NPORT-P/A"}:
            return {"cik": cik_padded(cik), "accession": accession, "period": (period or "")[:10], "name": submissions.get("name") or ""}
    return None


def _hit_matches(firm: str, display: str) -> bool:
    compact = "".join(ch for ch in display.lower() if ch.isalnum())
    tokens = [token for token in distinctive_tokens(firm) if len(token) >= 4]
    return any(token in compact for token in tokens)


def _nport_from_search(firm: str) -> dict | None:
    query = urlencode({"q": f'"{firm}"', "forms": "NPORT-P"})
    payload = get_json(f"https://efts.sec.gov/LATEST/search-index?{query}")
    hits = ((payload.get("hits") or {}).get("hits") or [])[:8]
    for hit in hits:
        source = hit.get("_source") or {}
        ciks = source.get("ciks") or []
        names = source.get("display_names") or []
        if not ciks or not names:
            continue
        name = str(names[0])
        if not _hit_matches(firm, name):
            continue
        found = _nport_from_submissions(str(ciks[0]))
        if found:
            return found
    return None


def _primary_xml(cik: str, accession: str) -> bytes | None:
    folder = accession.replace("-", "")
    index_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{folder}/index.json"
    index = sec_fetch_json(index_url)
    items = (index.get("directory") or {}).get("item") or []
    name = next((item.get("name") for item in items if (item.get("name") or "").lower() == "primary_doc.xml"), None)
    if name is None:
        name = next(
            (
                item.get("name")
                for item in items
                if (item.get("name") or "").lower().endswith(".xml") and "xsl" not in (item.get("name") or "").lower()
            ),
            None,
        )
    if not name:
        return None
    return sec_fetch_bytes(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{folder}/{name}")


def _write_outputs(stakes: list[dict], notes: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DASH.mkdir(parents=True, exist_ok=True)
    for stale in DASH.glob("*.json"):
        stale.unlink()
    by_ticker: dict[str, list[dict]] = {}
    for stake in stakes:
        by_ticker.setdefault(stake["ticker"], []).append(stake)
    for ticker, rows in by_ticker.items():
        rows.sort(key=lambda row: -(row.get("value_usd") or 0))
        payload = {
            "schema_version": 1,
            "in_base_irr": False,
            "source": "nport",
            "ticker": ticker,
            "threshold_basis": "fund portfolio weight",
            "context": "Form N-PORT holdings are context. They are not an input to the base return.",
            "holders": rows,
        }
        (DASH / f"{ticker}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    status = {
        "schema_version": 1,
        "in_base_irr": False,
        "source": "nport",
        "stake_count": len(stakes),
        "funds": notes,
    }
    STATUS.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")


def run(tracked_only: bool, limit: int) -> int:
    _tickers, names = portfolio_universe()
    portfolio = {ticker: names.get(ticker) or ticker for ticker in names}
    stakes: list[dict] = []
    notes: list[dict] = []
    for manager in _managers(tracked_only)[:limit]:
        firm = manager.get("display_name") or manager["manager_id"]
        try:
            found = _nport_from_submissions(manager["cik"])
            if found is None:
                for query in [firm, *FUND_FAMILY.get(manager["manager_id"], [])]:
                    found = _nport_from_search(query)
                    if found:
                        break
        except Exception as error:  # noqa: BLE001
            notes.append({"manager_id": manager["manager_id"], "error": str(error)})
            print(f"{manager['manager_id']}: FAILED {error}", flush=True)
            continue
        if not found:
            notes.append({"manager_id": manager["manager_id"], "nport": False})
            print(f"{manager['manager_id']}: no N-PORT", flush=True)
            continue
        try:
            xml = _primary_xml(found["cik"], found["accession"])
        except Exception as error:  # noqa: BLE001
            notes.append({"manager_id": manager["manager_id"], "error": str(error)})
            print(f"{manager['manager_id']}: FAILED {error}", flush=True)
            continue
        if not xml:
            notes.append({"manager_id": manager["manager_id"], "nport": False})
            print(f"{manager['manager_id']}: N-PORT document missing", flush=True)
            continue
        period, rows = parse_nport_holdings(xml)
        kept = 0
        for row in rows:
            ticker = match_portfolio_ticker(row, portfolio)
            if not ticker or not is_international(row, ticker):
                continue
            stakes.append(
                {
                    "ticker": ticker,
                    "issuer": row.get("name") or "",
                    "isin": row.get("isin") or "",
                    "manager_id": manager["manager_id"],
                    "manager_name": firm,
                    "shares": row.get("shares"),
                    "value_usd": row.get("value_usd"),
                    "pct_val": row.get("pct_val"),
                    "country": row.get("country") or "",
                    "period_end": found.get("period") or period or "",
                    "source": "nport",
                    "source_url": f"https://www.sec.gov/Archives/edgar/data/{int(found['cik'])}/{found['accession'].replace('-', '')}/",
                    "in_base_irr": False,
                }
            )
            kept += 1
        notes.append({"manager_id": manager["manager_id"], "nport_cik": found["cik"], "rows": len(rows), "matched": kept})
        print(f"{manager['manager_id']}: nport rows={len(rows)} matched={kept}", flush=True)
    _write_outputs(stakes, notes)
    print(f"N-PORT stakes {len(stakes)}", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracked-only", action="store_true")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    return run(args.tracked_only, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
