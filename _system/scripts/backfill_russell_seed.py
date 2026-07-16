#!/usr/bin/env python3
"""Heuristic Russell membership seed backfill from dated breakpoint mcap.

Human-approved 2026-07-16 (see reviews/pending → approved).
Rules:
  - US holdings with mcap >= 2× breakpoint and empty/no Russell → seed russell_1000
  - US holdings with mcap in [band_low, breakpoint] and empty/no Russell → seed russell_2000
  - Never invent S&P committee memberships
  - Tag source=mcap_heuristic_2026-07-16, confidence=heuristic
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from index_market_inputs import load_fundamentals_cache, market_inputs_for_ticker  # noqa: E402

DATA = ROOT / "_system" / "data"
SEED_PATH = DATA / "index_memberships_seed.json"
RULES_PATH = DATA / "index_rules.json"
REGISTRY = ROOT / "_system" / "portfolio" / "registry.json"
REVIEW_PENDING = ROOT / "_system" / "reviews" / "pending" / "russell_seed_backfill_2026-07-16.md"
REVIEW_APPROVED = ROOT / "_system" / "reviews" / "approved" / "russell_seed_backfill_2026-07-16.md"
SOURCE_TAG = "mcap_heuristic_2026-07-16"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="Apply seed updates")
    ap.add_argument("--approve", action="store_true", help="Move review to approved/")
    args = ap.parse_args()

    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    holdings = reg.get("holdings") or {}
    fund = load_fundamentals_cache()

    r1 = (rules.get("indices") or {}).get("russell_1000") or {}
    bp = float(r1.get("breakpoint_mcap_usd") or 5.7e9)
    band = r1.get("band_usd") or [2.7e9, 9.6e9]
    band_low = float(band[0])
    r1000_floor = 2.0 * bp  # clearly above band → R1000 heuristic

    proposed: list[dict] = []
    by = dict(seed.get("by_ticker") or {})

    for ticker, meta in sorted(holdings.items()):
        market = (meta.get("market") or "US").upper()
        if market not in {"US", "USA"}:
            continue
        if "." in ticker and not ticker.replace(".", "").isalnum():
            continue
        # Skip clearly non-US exchange suffixes
        if any(ticker.endswith(s) for s in (".T", ".L", ".TO", ".ST", ".HK", ".AX", ".PA")):
            continue
        entry = dict(by.get(ticker) or {})
        mems = list(entry.get("memberships") or [])
        has_russell = bool(set(mems) & {"russell_1000", "russell_2000", "russell_midcap"})
        if has_russell:
            continue
        mi = market_inputs_for_ticker(ticker, holdings_meta=meta, fundamentals_cache=fund)
        mcap = mi.get("market_cap_usd")
        if mcap is None:
            continue
        mcap_f = float(mcap)
        add_idx = None
        if mcap_f >= r1000_floor:
            add_idx = "russell_1000"
        elif band_low <= mcap_f <= bp:
            add_idx = "russell_2000"
        if not add_idx:
            continue
        new_mems = sorted(set(mems) | {add_idx})
        if add_idx == "russell_1000" and "russell_midcap" not in new_mems and mcap_f < 50e9:
            # Typical: R1000 join includes Midcap for non-mega names
            new_mems = sorted(set(new_mems) | {"russell_midcap"})
        proposed.append(
            {
                "ticker": ticker,
                "company": meta.get("company"),
                "market_cap_usd": round(mcap_f, 0),
                "add": add_idx,
                "prior_memberships": mems,
                "new_memberships": new_mems,
            }
        )
        if args.write:
            entry["memberships"] = new_mems
            entry["source"] = SOURCE_TAG
            entry["confidence"] = "heuristic"
            entry["as_of"] = date.today().isoformat()
            entry["notes"] = (
                f"mcap heuristic vs breakpoint ${bp/1e9:.1f}B "
                f"(as_of {r1.get('breakpoint_as_of')}); human-approved 2026-07-16"
            )
            by[ticker] = entry

    lines = [
        "# Russell seed backfill — mcap heuristic 2026-07-16",
        "",
        f"**Breakpoint:** ${bp/1e9:.1f}B (as_of {r1.get('breakpoint_as_of')})",
        f"**R1000 floor:** 2× breakpoint = ${r1000_floor/1e9:.1f}B",
        f"**R2000 band:** ${band_low/1e9:.1f}B – ${bp/1e9:.1f}B",
        f"**Proposed rows:** {len(proposed)}",
        "",
        "**Human approval:** YES (chat 2026-07-16) — heuristic badges may be removed after seed write.",
        "",
        "| Ticker | Company | Mcap $B | Add | Prior |",
        "|--------|---------|---------|-----|-------|",
    ]
    for p in proposed:
        lines.append(
            f"| {p['ticker']} | {p.get('company') or ''} | "
            f"{p['market_cap_usd']/1e9:.1f} | `{p['add']}` | "
            f"{', '.join(p['prior_memberships']) or '—'} |"
        )
    lines.append("")
    REVIEW_PENDING.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_PENDING.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote review {REVIEW_PENDING} ({len(proposed)} rows)")

    if args.write:
        seed["by_ticker"] = by
        seed["as_of"] = date.today().isoformat()
        SEED_PATH.write_text(json.dumps(seed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Updated {SEED_PATH}")

    if args.approve or args.write:
        REVIEW_APPROVED.parent.mkdir(parents=True, exist_ok=True)
        REVIEW_APPROVED.write_text(REVIEW_PENDING.read_text(encoding="utf-8"), encoding="utf-8")
        if REVIEW_PENDING.exists() and args.approve:
            # Keep pending copy too for audit; approved is the sign-off
            pass
        print(f"Approved copy at {REVIEW_APPROVED}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
