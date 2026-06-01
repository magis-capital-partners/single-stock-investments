#!/usr/bin/env python3
"""Build Marvin feature store for Darwin (Phase 1)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from darwin.config import DATA_DIR, FEATURES_PATH  # noqa: E402
from darwin.features import build_features  # noqa: E402


def main() -> None:
    payload = build_features()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FEATURES_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {FEATURES_PATH} ({payload['ticker_count']} tickers, dim={payload['feature_dim']})")


if __name__ == "__main__":
    main()
