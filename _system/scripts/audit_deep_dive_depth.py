#!/usr/bin/env python3
"""Portfolio scorecard for deep dive depth rubric.

Usage:
  python _system/scripts/audit_deep_dive_depth.py --portfolio
  python _system/scripts/audit_deep_dive_depth.py --portfolio --date 2026-06-04
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from deep_dive_depth_common import PASS_SCORE, score_dive  # noqa: E402
from lint_deep_dive_depth import latest_dive  # noqa: E402

REVIEWS = ROOT / "_system" / "reviews" / "pending"
SKIP = {"_system", ".git", ".cursor", "dashboard", "node_modules"}


def portfolio_tickers() -> list[str]:
    reg = ROOT / "_system" / "portfolio" / "registry.json"
    tickers: list[str] = []
    if reg.exists():
        import json

        data = json.loads(reg.read_text(encoding="utf-8"))
        tickers.extend(sorted((data.get("holdings") or {}).keys()))
        tickers.extend(sorted((data.get("watchlist") or {}).keys()))
    if not tickers:
        for td in sorted(ROOT.iterdir()):
            if td.is_dir() and td.name not in SKIP and (td / "research").is_dir():
                tickers.append(td.name)
    return sorted(set(tickers))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio", action="store_true", required=True)
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    rows: list[dict] = []
    for ticker in portfolio_tickers():
        research = ROOT / ticker / "research"
        dive = latest_dive(research)
        if not dive:
            rows.append(
                {
                    "ticker": ticker,
                    "dive_file": "",
                    "score": "",
                    "grade": "no_dive",
                    "passed": "no",
                    "full_tier": "",
                    "gaps": "no deep_dive_*.md",
                }
            )
            continue
        r = score_dive(dive)
        gaps = "; ".join(
            f"{c.label}({c.score})" for c in r.criteria if c.score < 2
        )
        if r.archetype_errors:
            gaps = (gaps + "; " if gaps else "") + "ARCH:" + ",".join(r.archetype_errors)
        rows.append(
            {
                "ticker": ticker,
                "dive_file": dive.name,
                "score": r.total,
                "grade": r.grade,
                "passed": "yes" if r.passed() else "no",
                "full_tier": r.full_tier_count,
                "gaps": gaps[:500],
            }
        )

    REVIEWS.mkdir(parents=True, exist_ok=True)
    out = REVIEWS / f"deep_dive_depth_scorecard_{args.date}.csv"
    fieldnames = ["ticker", "dive_file", "score", "grade", "passed", "full_tier", "gaps"]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    passed = sum(1 for r in rows if r.get("passed") == "yes")
    with_dive = sum(1 for r in rows if r.get("dive_file"))
    print(f"Wrote {out}")
    print(f"Holdings scanned: {len(rows)} | with dive: {with_dive} | pass ≥{PASS_SCORE}: {passed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
