"""Retain full-market price-jump discoveries without treating them as actions.

Only event metadata is exported. Prices and the raw detector report stay local.
The detector's context window bounds the sample; unmatched and weak evidence
remain visible candidates and cannot enter the verified trading cohorts.
"""

import csv
from .ledger import read_json


def candidates(cfg, start, cutoff, *, report=None, coverage=None):
    report = report or cfg.reports_dir / "split_detections.csv"
    coverage = coverage or cfg.reports_dir / "split_detection_reconciliation.json"
    if not report.exists() or not coverage.exists():
        return []
    window = read_json(coverage, {}).get("window", [start, cutoff])
    lower, upper = max(start, window[0]), min(cutoff, window[1])
    rows = []
    with report.open(encoding="utf-8", newline="") as stream:
        for item in csv.DictReader(stream):
            if item["listed_equity"] != "True" or not lower <= item["day"] <= upper:
                continue
            # Existing matched ledger events already retain their primary identity.
            if item.get("status") == "matched":
                continue
            ratio = float(item["ratio_inferred"])
            if ratio <= 1:
                continue
            rows.append({
                "ticker": item["symbol"],
                "cik": None,
                "security_id": "unresolved/" + item["symbol"],
                "ex_date": item["day"],
                "ratio": 1 / ratio,
                "ratio_basis": "price_inferred_requires_primary_confirmation",
                "verification": "candidate_requires_verification",
                "available_at": None,
                "source": "full_market_price_jump_candidate",
                "source_url": None,
                "exchange_class": "listed",
                "security_type": item.get("security_type") or "unknown",
                "listing_venue": item.get("listing_venue"),
                "price_jump_corroborated": item.get("corroborated") == "True",
                "historical_identity": "dated_venue_symbol_requires_issuer_review",
            })
    return rows
