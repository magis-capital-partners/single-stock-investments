#!/usr/bin/env python3
"""Patch valuation.json with lens_consensus summary (derived from lenses.json)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def apply_lens_consensus_to_valuation(ticker: str, lenses_payload: dict | None = None) -> bool:
    research = ROOT / ticker / "research"
    val_path = research / "valuation.json"
    lenses_path = research / "lenses.json"
    if lenses_payload is None:
        if not lenses_path.exists():
            return False
        lenses_payload = json.loads(lenses_path.read_text(encoding="utf-8"))
    if not val_path.exists():
        return False

    val = json.loads(val_path.read_text(encoding="utf-8"))
    blend = lenses_payload.get("valuation_blend") or {}
    consensus = lenses_payload.get("consensus") or {}

    val["lens_consensus"] = {
        "as_of": lenses_payload.get("as_of"),
        "shared_inputs_ref": lenses_payload.get("shared_inputs_ref"),
        "valuation_richness": lenses_payload.get("valuation_richness"),
        "blended_return_pct": blend.get("blended_return_pct"),
        "band_pct": blend.get("band_pct"),
        "weighted_median_pct": blend.get("weighted_median_pct"),
        "median_mean_flag": blend.get("median_mean_flag"),
        "stance": consensus.get("stance"),
        "agreement_pct": consensus.get("agreement_pct"),
        "dissent_count": len(consensus.get("dissents") or []),
        "lawrence_divergence": consensus.get("lawrence_divergence"),
        "top_dissents": (consensus.get("dissents") or [])[:3],
        "contributor_count": len(blend.get("contributors") or []),
        "in_base_irr": False,
        "disclaimer": "Advisory lens blend only. Does not replace Lawrence total-synthesis stance gate without [HUMAN REVIEW].",
    }
    val_path.write_text(json.dumps(val, indent=2) + "\n", encoding="utf-8")
    return True


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    args = parser.parse_args()
    ok = apply_lens_consensus_to_valuation(args.ticker.upper())
    print("OK" if ok else "SKIP")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
