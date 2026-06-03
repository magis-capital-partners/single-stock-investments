"""Load mandate and training defaults."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PORTFOLIO_DIR = ROOT / "_system" / "portfolio"
MANDATE_PATH = PORTFOLIO_DIR / "darwin_mandate.json"
DATA_DIR = ROOT / "dashboard" / "data"
FEATURES_PATH = DATA_DIR / "darwin_features.json"
PORTFOLIO_PATH = DATA_DIR / "darwin_portfolio.json"
MODEL_DIR = DATA_DIR / "darwin_models"
IRA_WEIGHTS_PATH = ROOT / "_system" / "portfolio" / "ira_target_weights.json"
BACKTEST_REPORT_PATH = DATA_DIR / "darwin_backtest_report.md"
PIT_STATUS_PATH = DATA_DIR / "darwin_pit_status.json"
PIT_BACKTEST_PATH = DATA_DIR / "darwin_backtest_pit.json"


def load_mandate() -> dict:
    """Legacy default: Roth mandate."""
    path = MANDATE_PATH
    if not path.exists():
        path = PORTFOLIO_DIR / "darwin_mandate_roth.json"
    return json.loads(path.read_text(encoding="utf-8"))
