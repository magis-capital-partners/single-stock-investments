#!/usr/bin/env python3
"""Import the reverse-split research review queue into the Short Alpha ledger.

Source: the rsdb export ``docs/data/short_alpha_review_queue.json`` from
``reverse-split-short-research`` ("research review queue, not positions").
Each row becomes a ``candidates.json`` lead with ``origin:
reverse_split_research``, ``category: reverse-split``, its frameworks and six
dated lens reviews carried verbatim, and a hypothesis that says plainly that
impairment has not been reviewed. Nothing is invented: no thesis, no catalyst,
no falsifier.

Rules:
* a ticker already in the ledger is skipped (the ledger never overwrites a row);
* a ticker that fails the schema pattern is skipped and reported;
* a framework id the catalog does not know is dropped and reported;
* existing rows are re-serialised with the file's own indent, so they stay
  byte-identical in meaning and in text.

File in, file out. This never touches the IB Gateway, ThetaData, or the network.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_short_alpha_dashboard as ledger  # noqa: E402

DEFAULT_INPUT = Path(
    r"C:\Users\drewg\Projects\reverse-split-short-research\docs\data\short_alpha_review_queue.json"
)
REGISTRY = ROOT / "_system" / "portfolio" / "registry.json"
SOURCE_ID = "reverse-split-research"
ORIGIN = "reverse_split_research"
CATEGORY = "reverse-split"
HYPOTHESIS = "Reverse-split discovery lead; impairment not yet reviewed."
NEXT_STEP = (
    "Run the six lens reviews against primary filings before promoting this lead. "
    "A reverse split alone supplies no mechanism."
)


def company_names() -> dict[str, str]:
    if not REGISTRY.exists():
        return {}
    try:
        holdings = json.loads(REGISTRY.read_text(encoding="utf-8")).get("holdings") or {}
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(holdings, dict):
        return {}
    return {str(t): str((row or {}).get("company") or t) for t, row in holdings.items() if t}


def lead_from_queue_row(row: dict, as_of: str, known_frameworks: set[str], names: dict[str, str]) -> tuple[dict, list[str]]:
    """One ledger lead from one export row. Returns the row and the framework ids it had to drop."""
    ticker = str(row.get("ticker") or "").upper().strip()
    frameworks: list[str] = []
    dropped: list[str] = []
    for tag in row.get("frameworks") or []:
        tag = str(tag)
        if tag not in known_frameworks:
            dropped.append(tag)
        elif tag not in frameworks:
            frameworks.append(tag)
    reviews = [json.loads(json.dumps(r)) for r in row.get("lens_reviews") or [] if isinstance(r, dict)]
    recorded = sum(1 for r in reviews if r.get("status") != "unreviewed")
    score = row.get("fundamental_score")
    score_text = f"rsdb fundamental score {float(score):g}" if isinstance(score, (int, float)) else "unscored by rsdb"
    score_as_of = row.get("score_as_of") or as_of
    gates = dict(row.get("gates") or {})
    gates.setdefault("borrow_and_carry", "pending")
    gates.setdefault("path_and_timing", "unscored")
    gates.setdefault("issuer_retaliation", "unscored")
    lead = {
        "ticker": ticker,
        "security_name": names.get(ticker, ticker),
        "instrument_type": "operating_company",
        "stage": "lead",
        "origin": ORIGIN,
        "source": SOURCE_ID,
        "category": CATEGORY,
        "added_on": as_of,
        "updated_on": as_of,
        "tags": ["reverse-split"],
        "summary": (
            f"Reverse-split discovery lead from the rsdb engine; {recorded} of {len(reviews)} lens reviews "
            f"recorded; {score_text} as of {score_as_of}. Impairment not yet reviewed."
        ),
        "frameworks": frameworks,
        "primary_framework": frameworks[0] if frameworks else None,
        "hypothesis": HYPOTHESIS,
        "catalysts": [],
        "falsifiers": [],
        "research": {
            "status": str((row.get("research") or {}).get("status") or "requires_analyst_review"),
            "ic": "not_ready",
            "next_step": NEXT_STEP,
        },
        "sources": [
            {
                "type": "internal_analysis",
                "label": f"Reverse-split research queue export \u00b7 {as_of} \u00b7 {score_text}",
                "system": SOURCE_ID,
            }
        ],
        "lens_reviews": reviews,
        "fundamental_score": score,
        "score_as_of": score_as_of,
        "gates": gates,
    }
    return lead, dropped


def import_queue(queue: dict, doc: dict, catalog: dict) -> tuple[dict, dict]:
    """Merge the export into the ledger document. Returns the new document and a report."""
    as_of = str(queue.get("as_of") or "")
    if not ledger.YMD_RE.match(as_of):
        raise ledger.LedgerError(f"Queue export as_of must be YYYY-MM-DD, got {as_of!r}")
    known = set(ledger._framework_ids(catalog))
    names = company_names()
    existing = list(doc.get("candidates") or [])
    seen = {str(row.get("ticker") or "").upper() for row in existing}
    report = {
        "export_rows": 0,
        "imported": [],
        "skipped_existing": [],
        "skipped_ticker_pattern": [],
        "dropped_frameworks": {},
    }
    added: list[dict] = []
    for row in queue.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        report["export_rows"] += 1
        ticker = str(row.get("ticker") or "").upper().strip()
        if not ledger.TICKER_RE.match(ticker):
            report["skipped_ticker_pattern"].append(ticker or "<blank>")
            continue
        if ticker in seen or ticker in ledger.EXCLUDED_TICKERS:
            report["skipped_existing"].append(ticker)
            continue
        lead, dropped = lead_from_queue_row(row, as_of, known, names)
        if dropped:
            report["dropped_frameworks"][ticker] = dropped
        added.append(lead)
        seen.add(ticker)
        report["imported"].append(ticker)
    out = dict(doc)
    out["candidates"] = existing + added
    out["as_of"] = max(str(doc.get("as_of") or ""), as_of)
    return out, report


def _indent_of(text: str) -> int:
    for line in text.splitlines()[1:]:
        stripped = line.lstrip(" ")
        if stripped and stripped != line:
            return len(line) - len(stripped)
    return 2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="rsdb short_alpha_review_queue.json")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing candidates.json")
    args = parser.parse_args()
    queue = json.loads(args.input.read_text(encoding="utf-8"))
    raw = ledger.CANDIDATES.read_text(encoding="utf-8")
    doc = json.loads(raw)
    catalog = ledger._read_json(ledger.CATALOG)
    merged, report = import_queue(queue, doc, catalog)
    ledger._validate_bundle(list(ledger._read_json(ledger.POSITIONS).get("ideas") or []), merged["candidates"], catalog)
    summary = {
        "export_rows": report["export_rows"],
        "imported": len(report["imported"]),
        "skipped_existing": report["skipped_existing"],
        "skipped_ticker_pattern": report["skipped_ticker_pattern"],
        "dropped_frameworks": report["dropped_frameworks"],
        "candidates_before": len(doc.get("candidates") or []),
        "candidates_after": len(merged["candidates"]),
        "as_of": merged["as_of"],
    }
    print(json.dumps(summary, indent=2))
    if args.dry_run or not report["imported"]:
        return
    indent = _indent_of(raw)
    ledger.CANDIDATES.write_text(json.dumps(merged, indent=indent) + "\n", encoding="utf-8")
    print(f"Wrote {ledger.CANDIDATES.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
