#!/usr/bin/env python3
"""Build Darwin portfolio JSON (phases 0–3).

  python _system/scripts/build_darwin_portfolio.py
  python _system/scripts/build_darwin_portfolio.py --fast
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from darwin.pipeline import run_pipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast", action="store_true", help="Reduced training for CI")
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
    out = run_pipeline(
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
        print(f"PIT audit: pass={out.get('pit_status', {}).get('audit_pass')} leakage={out.get('pit_status', {}).get('leakage_count')}")
        return
    if out.get("pit_backtest"):
        print(f"PIT backtest: oos_sharpe={out.get('pit_status', {}).get('oos_sharpe_genetic')} ml_oos={out.get('pit_status', {}).get('ml_oos_eligible')}")
        return
    if out.get("error"):
        print(f"Darwin pipeline error: {out['error']}", file=sys.stderr)
        sys.exit(1)
    print(
        f"Darwin portfolio: policy={out.get('policy_id')} "
        f"regime={out.get('regime', {}).get('label') if isinstance(out.get('regime'), dict) else out.get('regime')} "
        f"weights={len(out.get('weights') or [])} pit_audit={out.get('pit', {}).get('audit_pass')}"
    )


if __name__ == "__main__":
    main()
