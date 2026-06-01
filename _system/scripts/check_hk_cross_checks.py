#!/usr/bin/env python3
"""Verify HK-indexed tickers (delegates to check_cross_checks.py).

Usage:
  python _system/scripts/check_hk_cross_checks.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HK_INDEX = ROOT / "_system" / "reference" / "investment-wisdom" / "hk_ticker_index.json"
PY = sys.executable
SCRIPTS = Path(__file__).resolve().parent


def main() -> int:
    if not HK_INDEX.exists():
        print("WARN: no hk_ticker_index.json")
        return 0
    idx = json.loads(HK_INDEX.read_text(encoding="utf-8"))
    tickers = sorted(idx.get("tickers", {}).keys())
    if not tickers:
        return 0
    cmd = [PY, str(SCRIPTS / "check_cross_checks.py"), *tickers]
    if "--strict" in sys.argv:
        cmd.append("--strict")
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
