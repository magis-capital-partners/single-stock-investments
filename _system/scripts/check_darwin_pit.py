#!/usr/bin/env python3
"""Lint Darwin PIT discipline (audit pass, tracking files)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from darwin.config import PIT_STATUS_PATH, load_mandate  # noqa: E402


def main() -> None:
    mandate = load_mandate()
    pit_cfg = mandate.get("pit") or {}
    strict = bool(pit_cfg.get("strict_audit", True))

    if not PIT_STATUS_PATH.exists():
        print("darwin_pit_status.json missing — run build_darwin_portfolio.py", file=sys.stderr)
        sys.exit(1)

    status = json.loads(PIT_STATUS_PATH.read_text(encoding="utf-8"))
    errors: list[str] = []

    if strict and not status.get("audit_pass"):
        errors.append(f"audit_pass=false leakage_count={status.get('leakage_count')}")

    pit_err = status.get("pit_error")
    if pit_err and pit_err != "insufficient_rebalances":
        errors.append(f"pit_error={pit_err}")

    synth = status.get("synthetic_tickers") or []
    if strict and synth and not pit_cfg.get("allow_synthetic_returns"):
        print(f"PIT WARN: synthetic_tickers={synth[:8]} (add returns CSVs)", file=sys.stderr)

    if errors:
        for e in errors:
            print(f"PIT CHECK FAIL: {e}", file=sys.stderr)
        sys.exit(1)

    print(
        f"OK: PIT audit_pass={status.get('audit_pass')} "
        f"oos_genetic_sharpe={status.get('oos_sharpe_genetic')} "
        f"ml_oos_eligible={status.get('ml_oos_eligible')}"
    )


if __name__ == "__main__":
    main()
