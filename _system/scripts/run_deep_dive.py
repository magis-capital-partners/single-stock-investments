#!/usr/bin/env python3
"""Dispatch Marvin deep dive via Cursor Cloud Agent (used by onboard workflow and CLI)."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    args = parser.parse_args()
    ticker = args.ticker.strip()

    if not os.environ.get("CURSOR_API_KEY"):
        print("CURSOR_API_KEY not set — skipping cloud deep dive", file=sys.stderr)
        return 1

    repo = os.environ.get("GITHUB_REPOSITORY", "GoldmanDrew/single-stock-investments")
    env = {**os.environ, "TICKER": ticker, "GITHUB_REPOSITORY": repo}

    scripts_dir = ROOT / "_system" / "scripts"
    subprocess.run(["npm", "install", "--no-save", "@cursor/sdk"], cwd=scripts_dir, check=False)
    result = subprocess.run(["node", str(scripts_dir / "marvin_deep_dive.mjs")], cwd=ROOT, env=env)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
