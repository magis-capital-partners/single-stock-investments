"""Shared paths for the technical-signal study.

Large intermediates (full-history bars, per-stock replays, panels, event rows;
about 2.5 GB) live under DATA, which defaults to ./data (git-ignored) and can be
pointed elsewhere with the TECH_STUDY_DATA environment variable. Small,
reviewable outputs go to ./results and are committed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCRIPTS = REPO / "_system" / "scripts"
DATA = Path(os.environ.get("TECH_STUDY_DATA") or (HERE / "data"))
RESULTS = HERE / "results"

BARS = DATA / "bars"
INDEX_SIGNALS = DATA / "index_signals"
STOCK_SIGNALS = DATA / "stock_signals"
MANIFEST_PATH = DATA / "manifest.json"
THIN_PANEL = DATA / "thin_panel.parquet"
EVENTS = DATA / "events.parquet"
CROSS_SECTION_DAILY = DATA / "cross_section_daily.parquet"


def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())
