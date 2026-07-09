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
    clinical = load_json(CLINICAL_PATH, {"by_ticker": {}})
    # Gate: if real SI or clinical builders already populated keys, do not overwrite
    has_si = any(
        (r.get("short_interest_pct") is not None) or (r.get("short_interest_quintile") is not None)
        for r in (signals.get("by_ticker") or {}).values()
    )
    has_peer = any(
        (r.get("peer_momentum_12m") is not None) or (r.get("peer_cluster_id") is not None)
        for r in (signals.get("by_ticker") or {}).values()
    ) or any(
        (r.get("peer_momentum_12m") is not None) or (r.get("trial_count") or 0) > 0
        for r in (clinical.get("by_ticker") or {}).values()
    )
    if has_si and has_peer:
        print("Skip peer/short stub — FINRA SI and clinical peer builders already live")
        return 0

    by_ticker = {}
    for ticker, row in (signals.get("by_ticker") or {}).items():
        by_ticker[ticker] = {
            "ticker": ticker,
            "peer_cluster_id": row.get("peer_cluster_id"),
            "peer_momentum_12m": row.get("peer_momentum_12m"),
            "short_interest_pct": row.get("short_interest_pct"),
            "short_candidate_score": row.get("short_candidate_score"),
            "status": "stub",
            "notes": "Await ClinicalTrials.gov ingest and FINRA short-interest feed.",
            "company": row.get("company"),
        }
    if not has_peer:
        payload = {
            "generated_at": now_iso(),
            "schema_version": 1,
            "status": "stub",
            "ticker_count": len(by_ticker),
            "by_ticker": by_ticker,
            "notes": "Peer momentum stub — run build_biotech_clinical_profiles.py",
        }
        save_json(CLINICAL_PATH, payload)
    for ticker, row in (signals.get("by_ticker") or {}).items():
        if not has_peer:
            row.setdefault("peer_momentum_12m", None)
        if not has_si:
            row.setdefault("short_interest_pct", None)
            if (row.get("consensus_quintile") or 5) <= 2 and not row.get("convergence_flag"):
                row["short_candidate_score"] = max(row.get("short_candidate_score") or 0, 40)
            else:
                row["short_candidate_score"] = row.get("short_candidate_score") or 0
    if signals.get("by_ticker"):
        save_json(SIGNALS_PATH, signals)
    print(f"Wrote clinical/short stubs for {len(by_ticker)} tickers (si_live={has_si}, peer_live={has_peer})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
