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
    args = parser.parse_args()
    if args.download:
        import subprocess

        script = ROOT / "_system" / "scripts" / "download_ira_research.py"
        subprocess.run([sys.executable, str(script), "--tier", "A"], check=False)
        subprocess.run([sys.executable, str(script), "--tier", "B"], check=False)
    out = run_pipeline(fast=args.fast)
    if out.get("error"):
        print(f"Darwin pipeline error: {out['error']}", file=sys.stderr)
        sys.exit(1)
    print(
        f"Darwin portfolio: policy={out.get('policy_id')} "
        f"regime={out.get('regime')} weights={len(out.get('weights') or [])}"
    )


if __name__ == "__main__":
    main()
