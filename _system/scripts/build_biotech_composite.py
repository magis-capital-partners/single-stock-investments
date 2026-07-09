#!/usr/bin/env python3
"""Write biotech_overlay composite onto valuation.json and ownership/overlays/."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from memory_claim_sources import load_biotech_factor_spec  # noqa: E402
from ownership_common import (  # noqa: E402
    OVERLAYS_DIR,
    SIGNALS_PATH,
    load_json,
    now_iso,
    save_json,
)


def overlay_payload(row: dict, spec: dict) -> dict:
    return {
        "as_of": now_iso()[:10],
        "source": "biotech_quant",
        "factor_spec_version": spec.get("schema_version"),
        "ticker": row.get("ticker"),
        "composite_score": row.get("composite_score"),
        "consensus_score": row.get("consensus_score"),
        "consensus_quintile": row.get("consensus_quintile"),
        "spend_value_quintile": row.get("spend_value_quintile"),
        "insider_score": row.get("insider_score"),
        "insider_quintile": row.get("insider_quintile"),
        "peer_momentum_12m": row.get("peer_momentum_12m"),
        "short_interest_pct": row.get("short_interest_pct"),
        "short_candidate_score": row.get("short_candidate_score"),
        "convergence_flag": row.get("convergence_flag"),
        "issuer_size_bucket": row.get("issuer_size_bucket"),
        "position_size_bucket": row.get("position_size_bucket") or row.get("size_bucket"),
        "notes": "Context overlay only — does not replace Lawrence IRR.",
    }


def recompute_composite(row: dict, weights: dict) -> float | None:
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
    if row.get("peer_momentum_12m") is not None and "peer_momentum" in weights:
        w = float(weights["peer_momentum"].get("weight_long") or 0.15)
        momo = max(-50.0, min(50.0, float(row["peer_momentum_12m"])))
        parts.append(w * ((momo + 50.0) / 100.0) * 100)
        wsum += w
    if parts and wsum:
        score = sum(parts) / wsum
        # Short interest as dampener on long composite (not a long weight)
        if row.get("short_interest_quintile") and "short_interest" in weights:
            w_short = float(weights["short_interest"].get("weight_short") or 0.20)
            # High SI quintile reduces long score
            damp = 1.0 - (w_short * ((row["short_interest_quintile"] - 1) / 4) * 0.35)
            score *= max(0.7, damp)
        return round(score, 1)
    return row.get("composite_score") or row.get("consensus_score")


def main() -> int:
    signals = load_json(SIGNALS_PATH, {"by_ticker": {}})
    spec = load_biotech_factor_spec()
    weights = {f["id"]: f for f in (spec.get("factors") or [])}
    OVERLAYS_DIR.mkdir(parents=True, exist_ok=True)
    updated_val = 0
    updated_overlay = 0

    for ticker, row in (signals.get("by_ticker") or {}).items():
        if not row.get("in_biotech_quant_universe"):
            continue
        score = recompute_composite(row, weights)
        if score is not None:
            row["composite_score"] = score
        overlay = overlay_payload(row, spec)
        save_json(OVERLAYS_DIR / f"{ticker}.json", overlay)
        updated_overlay += 1

        val_path = ROOT / ticker / "research" / "valuation.json"
        if val_path.exists():
            try:
                val = json.loads(val_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            val["biotech_overlay"] = overlay
            val_path.write_text(json.dumps(val, indent=2) + "\n", encoding="utf-8")
            updated_val += 1
        elif row.get("in_book"):
            # Minimal stub so book quant names can carry overlay without a full dive
            val_path.parent.mkdir(parents=True, exist_ok=True)
            stub = {
                "ticker": ticker,
                "as_of": now_iso()[:10],
                "notes": "Minimal stub for biotech_overlay only — not a Lawrence valuation.",
                "biotech_overlay": overlay,
            }
            val_path.write_text(json.dumps(stub, indent=2) + "\n", encoding="utf-8")
            updated_val += 1

    save_json(SIGNALS_PATH, signals)
    print(
        f"Wrote biotech_overlay on {updated_val} valuation.json file(s); "
        f"{updated_overlay} ownership/overlays/"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
