#!/usr/bin/env python3
"""Write biotech_overlay composite onto valuation.json for quant-universe names."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from memory_claim_sources import load_biotech_factor_spec  # noqa: E402
from ownership_common import SIGNALS_PATH, load_json, now_iso, save_json  # noqa: E402


def main() -> int:
    signals = load_json(SIGNALS_PATH, {"by_ticker": {}})
    spec = load_biotech_factor_spec()
    updated = 0
    for ticker, row in (signals.get("by_ticker") or {}).items():
        if not row.get("in_biotech_quant_universe"):
            continue
        val_path = ROOT / ticker / "research" / "valuation.json"
        if not val_path.exists():
            # still record overlay in signals only
            continue
        try:
            val = json.loads(val_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        overlay = {
            "as_of": now_iso()[:10],
            "source": "biotech_quant",
            "factor_spec_version": spec.get("schema_version"),
            "composite_score": row.get("composite_score"),
            "consensus_score": row.get("consensus_score"),
            "consensus_quintile": row.get("consensus_quintile"),
            "spend_value_quintile": row.get("spend_value_quintile"),
            "insider_score": row.get("insider_score"),
            "convergence_flag": row.get("convergence_flag"),
            "short_candidate_score": row.get("short_candidate_score"),
            "notes": "Context overlay only — does not replace Lawrence IRR.",
        }
        val["biotech_overlay"] = overlay
        val_path.write_text(json.dumps(val, indent=2) + "\n", encoding="utf-8")
        updated += 1
    # refresh composite on signals from weights
    weights = {f["id"]: f for f in (spec.get("factors") or [])}
    for ticker, row in (signals.get("by_ticker") or {}).items():
        parts = []
        wsum = 0.0
        if row.get("consensus_quintile") and "specialist_consensus" in weights:
            w = float(weights["specialist_consensus"].get("weight_long") or 0.35)
            parts.append(w * (row["consensus_quintile"] / 5) * 100)
            wsum += w
        if row.get("spend_value_quintile") and "spend_value" in weights:
            w = float(weights["spend_value"].get("weight_long") or 0.30)
            parts.append(w * (row["spend_value_quintile"] / 5) * 100)
            wsum += w
        if row.get("insider_score") is not None and "insider_non_ceo" in weights:
            w = float(weights["insider_non_ceo"].get("weight_long") or 0.10)
            parts.append(w * max(0, min(100, float(row["insider_score"]))))
            wsum += w
        if parts and wsum:
            row["composite_score"] = round(sum(parts) / wsum, 1)
    save_json(SIGNALS_PATH, signals)
    print(f"Wrote biotech_overlay on {updated} valuation.json file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
