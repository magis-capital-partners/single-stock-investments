#!/usr/bin/env python3
"""Stub clinical peer-momentum profiles + short-interest placeholders for biotech quant."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from ownership_common import CLINICAL_PATH, SIGNALS_PATH, load_json, now_iso, save_json  # noqa: E402


def main() -> int:
    signals = load_json(SIGNALS_PATH, {"by_ticker": {}})
    by_ticker = {}
    for ticker, row in (signals.get("by_ticker") or {}).items():
        by_ticker[ticker] = {
            "ticker": ticker,
            "peer_cluster_id": None,
            "peer_momentum_12m": None,
            "short_interest_pct": None,
            "short_candidate_score": None,
            "status": "stub",
            "notes": "Await ClinicalTrials.gov ingest and approved short-interest feed.",
            "company": row.get("company"),
        }
    payload = {
        "generated_at": now_iso(),
        "schema_version": 1,
        "status": "stub",
        "ticker_count": len(by_ticker),
        "by_ticker": by_ticker,
        "notes": "Peer momentum and short interest are stubs per FACTOR_SPEC.json.",
    }
    save_json(CLINICAL_PATH, payload)
    # ensure signal keys exist
    for ticker, row in (signals.get("by_ticker") or {}).items():
        row.setdefault("peer_momentum_12m", None)
        row.setdefault("short_interest_pct", None)
        # Diversified short candidate heuristic: low consensus + no convergence
        if (row.get("consensus_quintile") or 5) <= 2 and not row.get("convergence_flag"):
            row["short_candidate_score"] = 40
        else:
            row["short_candidate_score"] = row.get("short_candidate_score") or 0
    if signals.get("by_ticker"):
        save_json(SIGNALS_PATH, signals)
    print(f"Wrote clinical/short stubs for {len(by_ticker)} tickers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
