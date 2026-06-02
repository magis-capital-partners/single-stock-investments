"""Point-in-time feature snapshots for backtest discipline (Workstream B)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT
from .pit import PIT_DIR, load_registry_raw

PIT_STATUS_PATH = ROOT / "dashboard" / "data" / "darwin_pit_status.json"
PIT_STATUS_HISTORY = ROOT / "dashboard" / "data" / "darwin_pit_status_history.jsonl"
PIT_BACKTEST_PATH = ROOT / "dashboard" / "data" / "darwin_backtest_pit.json"


def save_snapshot(features: dict) -> Path:
    PIT_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = PIT_DIR / f"darwin_features_{day}.json"
    path.write_text(json.dumps(features, indent=2) + "\n", encoding="utf-8")
    latest = PIT_DIR / "darwin_features_latest.json"
    latest.write_text(json.dumps(features, indent=2) + "\n", encoding="utf-8")
    return path


def save_registry_snapshot() -> Path:
    PIT_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    reg = load_registry_raw()
    path = PIT_DIR / f"registry_{day}.json"
    path.write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")
    latest = PIT_DIR / "registry_latest.json"
    latest.write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")
    return path


def append_pit_status(status: dict) -> None:
    PIT_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PIT_STATUS_PATH.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    with PIT_STATUS_HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(status, sort_keys=True) + "\n")
