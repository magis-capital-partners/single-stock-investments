#!/usr/bin/env python3
"""Backward-compatible entry point — delegates to refresh_optionality_valuation."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from refresh_optionality_valuation import refresh_ticker  # noqa: E402


def main() -> int:
    return 0 if refresh_ticker("KEWL") else 1


if __name__ == "__main__":
    raise SystemExit(main())
