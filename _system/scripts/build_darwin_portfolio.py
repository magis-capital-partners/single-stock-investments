#!/usr/bin/env python3
"""Build Darwin portfolio JSON for the Roth IRA paper account (IRA-only).

  python3 _system/scripts/build_darwin_portfolio.py
  python3 _system/scripts/build_darwin_portfolio.py --fast
  python3 _system/scripts/build_darwin_portfolio.py --account roth
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from darwin.accounts import ACCOUNT_IDS  # noqa: E402
from darwin.pipeline import run_all_accounts, run_pipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast", action="store_true", help="Reduced training for CI")
    parser.add_argument(
        "--account",
        choices=list(ACCOUNT_IDS) + ["all"],
        default="all",
        help="Which paper account to build (default: all = Roth IRA only)",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Run Tier A/B market-data download before build",
    )
    parser.add_argument("--pit-audit", action="store_true", help="Leakage audit only")
    parser.add_argument("--pit-backtest", action="store_true", help="PIT walk-forward backtest only")
    parser.add_argument("--sync-events", action="store_true", help="Rebuild research_events.jsonl")
    parser.add_argument(
        "--sync-external",
        action="store_true",
        help="Sync etf-dashboard / ls-algo context into market-data/external",
    )
    args = parser.parse_args()
    if args.download:
        import subprocess

        script = ROOT / "_system" / "scripts" / "download_ira_research.py"
        subprocess.run([sys.executable, str(script), "--tier", "A"], check=False)
        subprocess.run([sys.executable, str(script), "--tier", "B"], check=False)

    if args.account == "all" and not any(
        [args.pit_audit, args.pit_backtest, args.sync_events, args.sync_external]
    ):
        bundle = run_all_accounts(fast=args.fast)
        s = bundle["serving"]
        print(json.dumps(
            {
                aid: {
                    "policy_id": (s.get("accounts") or {}).get(aid, {}).get("policy_id"),
                    "backtest_cumulative_pct": (s.get("accounts") or {}).get(aid, {}).get("backtest_cumulative_pct"),
                    "paper_cumulative_pct": ((s.get("accounts") or {}).get(aid, {}).get("paper") or {}).get(
                        "cumulative_return_pct"
                    ),
                    "paper_inception": (s.get("accounts") or {}).get(aid, {}).get("paper_inception"),
                }
                for aid in ACCOUNT_IDS
            },
            indent=2,
        ))
        for aid, row in (s.get("accounts") or {}).items():
            paper = row.get("paper") or {}
            print(
                f"{aid}: policy={row.get('policy_id')} "
                f"backtest_cum={row.get('backtest_cumulative_pct')}% "
                f"paper_cum={paper.get('cumulative_return_pct')}% (since {row.get('paper_inception')})"
            )
        return

    out = run_pipeline(
        account_id=args.account if args.account != "all" else "roth",
        fast=args.fast,
        pit_audit_only=args.pit_audit,
        pit_backtest_only=args.pit_backtest,
        sync_events=args.sync_events,
        sync_external_only=args.sync_external,
    )
    if out.get("external_sync") is not None and args.sync_external:
        rep = out["external_sync"]
        print(
            f"External sync: returns={len(rep.get('returns_written') or [])} "
            f"errors={len(rep.get('errors') or [])}"
        )
        return
    if out.get("sync_events") is not None:
        print(f"Synced {out['sync_events']} research events")
        return
    if out.get("pit_audit"):
        print(
            f"PIT audit: pass={out.get('pit_status', {}).get('audit_pass')} "
            f"leakage={out.get('pit_status', {}).get('leakage_count')}"
        )
        return
    if out.get("pit_backtest"):
        print(
            f"PIT backtest: oos_sharpe={out.get('pit_status', {}).get('oos_sharpe_genetic')} "
            f"ml_oos={out.get('pit_status', {}).get('ml_oos_eligible')}"
        )
        return
    if out.get("error"):
        print(f"Darwin pipeline error: {out['error']}", file=sys.stderr)
        sys.exit(1)
    paper = out.get("paper_portfolio") or {}
    champ = (out.get("benchmarks") or {}).get("champion") or {}
    print(
        f"Darwin [{out.get('account_id')}]: policy={out.get('policy_id')} "
        f"regime={out.get('regime', {}).get('label') if isinstance(out.get('regime'), dict) else out.get('regime')} "
        f"weights={len(out.get('weights') or [])} "
        f"backtest_cum={(champ.get('cumulative_return') or 0)*100:.1f}% "
        f"paper_nav={paper.get('last_mark', {}).get('nav_usd')} "
        f"paper_cum={paper.get('last_mark', {}).get('cumulative_return_pct')}%"
    )


if __name__ == "__main__":
    main()
