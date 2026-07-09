#!/usr/bin/env python3
"""Diff biotech quant knowledge vs prior signals snapshot for Memory tab."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from ownership_common import (  # noqa: E402
    OWNERSHIP_DIR,
    PAPER_BOOK_PATH,
    SIGNALS_PATH,
    load_json,
    now_iso,
    save_json,
)

DELTA_PATH = OWNERSHIP_DIR / "knowledge_delta_latest.json"
PRIOR_SIGNALS = OWNERSHIP_DIR / "signals_prior.json"


def main() -> int:
    current = load_json(SIGNALS_PATH, {"by_ticker": {}})
    prior = load_json(PRIOR_SIGNALS, {"by_ticker": {}})
    paper = load_json(PAPER_BOOK_PATH, {})
    cur = current.get("by_ticker") or {}
    prev = prior.get("by_ticker") or {}

    new_convergences = sorted(
        t
        for t, r in cur.items()
        if r.get("convergence_flag") and not (prev.get(t) or {}).get("convergence_flag")
    )
    lost_convergences = sorted(
        t
        for t, r in prev.items()
        if r.get("convergence_flag") and not (cur.get(t) or {}).get("convergence_flag")
    )
    spend_q_up = sorted(
        t
        for t, r in cur.items()
        if (r.get("spend_value_quintile") or 0) > ((prev.get(t) or {}).get("spend_value_quintile") or 0)
        and (r.get("spend_value_quintile") or 0) >= 4
    )
    initiations = sorted(t for t, r in cur.items() if r.get("initiation_signal"))
    exits = sorted(t for t, r in cur.items() if r.get("exit_signal"))

    delta = {
        "generated_at": now_iso(),
        "quarter": current.get("quarter"),
        "new_convergences": new_convergences[:40],
        "lost_convergences": lost_convergences[:40],
        "spend_q_up": spend_q_up[:40],
        "initiations": initiations[:40],
        "exits": exits[:40],
        "paper_book_added": (paper.get("membership_delta") or {}).get("long_added")
        or (paper.get("membership_delta") or {}).get("short_added")
        or [],
        "paper_book_removed": (paper.get("membership_delta") or {}).get("long_removed")
        or (paper.get("membership_delta") or {}).get("short_removed")
        or [],
        "paper_long_added": (paper.get("membership_delta") or {}).get("long_added") or [],
        "paper_long_removed": (paper.get("membership_delta") or {}).get("long_removed") or [],
        "universe_count": len(cur),
        "prior_universe_count": len(prev),
    }
    # Prefer explicit long membership for UI
    if paper.get("membership_delta"):
        delta["paper_book_added"] = (paper["membership_delta"].get("long_added") or [])[:20]
        delta["paper_book_removed"] = (paper["membership_delta"].get("long_removed") or [])[:20]

    save_json(DELTA_PATH, delta)
    # Snapshot current as prior for next run
    save_json(PRIOR_SIGNALS, current)
    print(
        f"Knowledge delta: +{len(new_convergences)} convergence, "
        f"{len(spend_q_up)} spend Q up, paper +/-{len(delta['paper_book_added'])}/{len(delta['paper_book_removed'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
