"""Load mandate and training defaults."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANDATE_PATH = ROOT / "_system" / "portfolio" / "darwin_mandate.json"
DATA_DIR = ROOT / "dashboard" / "data"
FEATURES_PATH = DATA_DIR / "darwin_features.json"
PORTFOLIO_PATH = DATA_DIR / "darwin_portfolio.json"
MODEL_DIR = DATA_DIR / "darwin_models"
IRA_WEIGHTS_PATH = ROOT / "_system" / "portfolio" / "ira_target_weights.json"
BACKTEST_REPORT_PATH = DATA_DIR / "darwin_backtest_report.md"


def load_mandate() -> dict:
    return json.loads(MANDATE_PATH.read_text(encoding="utf-8"))
