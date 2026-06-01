#!/usr/bin/env python3
"""Bottom-up holdco uplift from assumption_ledger.components.

Reads valuation.json → scenarios.base.sotp_build.assumption_ledger.*.components,
sums incremental_m and per_share, writes derived blended_uplift_pct (output only).

Usage:
  python _system/scripts/holdco_uplift_build.py FRMO
  python _system/scripts/holdco_uplift_build.py FRMO --write
  python _system/scripts/holdco_uplift_build.py FRMO --key investment_a_lookthrough
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def compute_component(c: dict, shares: float) -> dict:
    """Fill incremental_m / per_share from prices when missing."""
    out = dict(c)
    slice_m = out.get("filing_slice_m") or 0.0
    meas = out.get("price_at_measurement")
    y5 = out.get("year5_price")
    pct = out.get("residual_uplift_pct")

    if out.get("incremental_m") is None:
        if meas and y5 and slice_m:
            out["incremental_m"] = round(slice_m * (y5 / meas - 1), 2)
        elif pct is not None and slice_m:
            out["incremental_m"] = round(slice_m * pct / 100, 2)
        elif out.get("incremental_m_direct") is not None:
            out["incremental_m"] = out["incremental_m_direct"]
        else:
            out["incremental_m"] = 0.0

    inc_m = float(out["incremental_m"])
    if out.get("per_share") is None:
        out["per_share"] = round(inc_m * 1_000_000 / shares, 4) if shares else 0.0
    return out


def build_ledger_key(ledger: dict, key: str | None) -> tuple[str, dict] | None:
    if key:
        block = ledger.get(key)
        return (key, block) if block else None
    # Prefer opaque look-through sleeves (Investment A pattern)
    for k, v in ledger.items():
        if isinstance(v, dict) and v.get("components") and "lookthrough" in k:
            return k, v
    preferred = (
        "investment_a_lookthrough",
        "investment_b",
        "winland_cmsg",
        "mih_miax",
    )
    for k in preferred:
        v = ledger.get(k)
        if isinstance(v, dict) and v.get("components"):
            return k, v
    for k, v in ledger.items():
        if isinstance(v, dict) and v.get("components"):
            return k, v
    return None


def run(ticker: str, key: str | None, write: bool) -> int:
    val_path = ROOT / ticker / "research" / "valuation.json"
    if not val_path.exists():
        print(f"No valuation.json for {ticker}", file=sys.stderr)
        return 1

    val = json.loads(val_path.read_text(encoding="utf-8"))
    sotp = (val.get("scenarios") or {}).get("base", {}).get("sotp_build") or {}
    ledger = sotp.get("assumption_ledger") or {}
    shares = sotp.get("shares") or val.get("shares_outstanding") or 1.0

    found = build_ledger_key(ledger, key)
    if not found:
        print(f"No assumption_ledger block with components for {ticker}", file=sys.stderr)
        return 1

    block_key, block = found
    components = block.get("components") or []
    if not components:
        print(f"{block_key}: empty components[]", file=sys.stderr)
        return 1

    computed = [compute_component(c, shares) for c in components]
    bottom_up_m = round(sum(c["incremental_m"] for c in computed), 2)
    bottom_up_ps = round(sum(c["per_share"] for c in computed), 4)

    parent_m = block.get("parent_filing_value_m") or block.get("gaap_m") or 0.0
    blended_pct = round(100 * bottom_up_m / parent_m, 1) if parent_m else None

    model_ps = block.get("model_uplift_per_share")
    if model_ps is None:
        for line in sotp.get("lines") or []:
            if line.get("id") == "investment_a" or "investment_a" in (line.get("id") or ""):
                model_ps = line.get("uplift_per_share")
                break

    slack_ps = round(model_ps - bottom_up_ps, 4) if model_ps is not None else None

    block["components"] = computed
    block["bottom_up_incremental_m"] = bottom_up_m
    block["bottom_up_per_share"] = bottom_up_ps
    if blended_pct is not None:
        block["blended_uplift_pct_derived"] = blended_pct
    if slack_ps is not None:
        block["slack_per_share"] = slack_ps
    block["note"] = (
        "blended_uplift_pct_derived = bottom_up / parent GAAP; not an input. "
        "See holdco_uplift_explanation.md"
    )

    print(f"{ticker} {block_key}:")
    print(f"  bottom_up: ${bottom_up_m}M = ${bottom_up_ps}/sh")
    if blended_pct is not None:
        print(f"  derived blended uplift: {blended_pct}% (output)")
    if model_ps is not None:
        print(f"  model uplift: ${model_ps}/sh")
    if slack_ps is not None:
        print(f"  slack: ${slack_ps}/sh")

    if write:
        ledger[block_key] = block
        sotp["assumption_ledger"] = ledger
        val.setdefault("scenarios", {}).setdefault("base", {})["sotp_build"] = sotp
        val_path.write_text(json.dumps(val, indent=2) + "\n", encoding="utf-8")
        print(f"  wrote {val_path.relative_to(ROOT)}")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Bottom-up holdco uplift build")
    parser.add_argument("ticker", help="Ticker symbol")
    parser.add_argument("--write", action="store_true", help="Update valuation.json")
    parser.add_argument(
        "--key",
        default=None,
        help="assumption_ledger key (default: first block with components)",
    )
    args = parser.parse_args()
    sys.exit(run(args.ticker.upper(), args.key, args.write))


if __name__ == "__main__":
    main()
