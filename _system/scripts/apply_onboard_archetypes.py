#!/usr/bin/env python3
"""Set provisional Stahl archetypes for batch-onboard tickers (no valuation.json yet).

Does not create valuation.json — only classification.json + thesis sync.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from sync_classification import CLASS_PATH, update_thesis  # noqa: E402

# Provisional archetype from company type (deep dive still required).
ONBOARD_ARCHETYPE: dict[str, dict] = {
    "HE": {"archetype": "infrastructure", "payoff_lens": "operating", "lawrence_bucket": "low_cost"},
    "MIAX": {"archetype": "croupier", "payoff_lens": "operating", "lawrence_bucket": "multi_sided"},
    "CBOE": {"archetype": "croupier", "payoff_lens": "operating", "lawrence_bucket": "multi_sided"},
    "CME": {"archetype": "croupier", "payoff_lens": "operating", "lawrence_bucket": "multi_sided"},
    "FNV": {"archetype": "optionality", "payoff_lens": "asset", "lawrence_bucket": "other"},
    "WPM": {"archetype": "optionality", "payoff_lens": "asset", "lawrence_bucket": "other"},
    "PBT": {"archetype": "optionality", "payoff_lens": "asset", "lawrence_bucket": "other"},
    "OR": {"archetype": "optionality", "payoff_lens": "asset", "lawrence_bucket": "other"},
    "TRC": {"archetype": "optionality", "payoff_lens": "asset", "lawrence_bucket": "other"},
    "HKHC": {"archetype": "holding_co", "payoff_lens": "asset", "lawrence_bucket": "other"},
    "DMLP": {"archetype": "optionality", "payoff_lens": "asset", "lawrence_bucket": "other"},
    "GLXY": {"archetype": "optionality", "payoff_lens": "levered", "lawrence_bucket": "other"},
    "BKRB": {"archetype": "holding_co", "payoff_lens": "asset", "lawrence_bucket": "other"},
    "MSTR": {"archetype": "optionality", "payoff_lens": "levered", "lawrence_bucket": "other"},
    "RPRX": {"archetype": "optionality", "payoff_lens": "asset", "lawrence_bucket": "other"},
    "RGLD": {"archetype": "optionality", "payoff_lens": "asset", "lawrence_bucket": "other"},
    "SBR": {"archetype": "optionality", "payoff_lens": "asset", "lawrence_bucket": "other"},
    "PCYO": {"archetype": "optionality", "payoff_lens": "asset", "lawrence_bucket": "other"},
    "WRLC": {"archetype": "optionality", "payoff_lens": "asset", "lawrence_bucket": "other"},
    "PDER": {"archetype": "optionality", "payoff_lens": "asset", "lawrence_bucket": "other"},
    "BVERS": {"archetype": "optionality", "payoff_lens": "asset", "lawrence_bucket": "other"},
    "GCCO": {"archetype": "optionality", "payoff_lens": "asset", "lawrence_bucket": "other"},
    "CKX": {"archetype": "optionality", "payoff_lens": "asset", "lawrence_bucket": "other"},
    "BUR": {"archetype": "croupier", "payoff_lens": "event", "lawrence_bucket": "other"},
    "ALS.TO": {"archetype": "optionality", "payoff_lens": "asset", "lawrence_bucket": "other"},
    "PSK.TO": {"archetype": "optionality", "payoff_lens": "asset", "lawrence_bucket": "other"},
}


def main() -> int:
    portfolio = json.loads(CLASS_PATH.read_text(encoding="utf-8"))
    updated = 0
    for ticker, patch in ONBOARD_ARCHETYPE.items():
        row = portfolio.get(ticker)
        if not row or row.get("archetype") != "unknown":
            continue
        row.update(patch)
        row["moi_bucket"] = row.get("moi_bucket") or "pending"
        portfolio[ticker] = row
        if update_thesis(ticker, row):
            updated += 1
        print(f"OK {ticker}: archetype -> {patch['archetype']} (provisional)")
    CLASS_PATH.write_text(json.dumps(portfolio, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {updated} thesis.md file(s); wrote {CLASS_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
