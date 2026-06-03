"""Improvement scorecard — append-only tracking (Phase D)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR

SCORECARD_PATH = DATA_DIR / "darwin_improvement_scorecard.jsonl"


def append_scorecard(
    pit_status: dict,
    pit_audit: dict,
    pit_backtest: dict,
    bias: dict,
    policy_id: str,
    exploration: bool,
) -> dict:
    row = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "policy_id": policy_id,
        "exploration_mode": exploration,
        "audit_pass": pit_audit.get("pass"),
        "leakage_count": pit_audit.get("leakage_count"),
        "oos_sharpe_genetic": pit_backtest.get("oos_sharpe_genetic"),
        "oos_sharpe_ira": (pit_backtest.get("benchmarks") or {}).get("oos", {}).get("ira_marvin", {}).get("sharpe_annualized"),
        "ml_oos_eligible": pit_backtest.get("ml_oos_eligible"),
        "bias_flags": bias.get("flag_count"),
        "bias_pass": bias.get("pass"),
        "synthetic_count": (pit_backtest.get("price_panel") or {}).get("synthetic_count"),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with SCORECARD_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
    return row
