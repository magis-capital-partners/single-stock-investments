#!/usr/bin/env python3
"""Create Darwin's compact research contract from a full repository checkout."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))
from darwin.accounts import load_mandate_for  # noqa: E402
from darwin.features import RESEARCH_SNAPSHOT_PATH, build_features  # noqa: E402

features = build_features(load_mandate_for("roth"), use_snapshot=False)
features["schema_version"] = 1
features["contract"] = "full-checkout research features for sparse Darwin allocation"
RESEARCH_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
RESEARCH_SNAPSHOT_PATH.write_text(json.dumps(features, indent=2) + "\n", encoding="utf-8")
print(f"wrote {RESEARCH_SNAPSHOT_PATH} ({len(features.get('tickers') or [])} tickers)")
