"""Point-in-time feature snapshots for backtest discipline (Workstream B)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT

PIT_DIR = ROOT / "_system" / "reference" / "market-data" / "pit"


def save_snapshot(features: dict) -> Path:
    PIT_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = PIT_DIR / f"darwin_features_{day}.json"
    path.write_text(json.dumps(features, indent=2) + "\n", encoding="utf-8")
    latest = PIT_DIR / "darwin_features_latest.json"
    latest.write_text(json.dumps(features, indent=2) + "\n", encoding="utf-8")
    return path
