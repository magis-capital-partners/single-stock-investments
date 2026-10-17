"""Archive each written valuation.json under <TICKER>/research/valuation_history/."""
from __future__ import annotations

import json
from pathlib import Path

VAL_HISTORY_DIR = "valuation_history"


def valuation_history_dir(ticker_dir: Path) -> Path:
    return ticker_dir / "research" / VAL_HISTORY_DIR


def archive_valuation_on_write(ticker_dir: Path, valuation: dict) -> Path | None:
    """Copy valuation.json into valuation_history/valuation_{as_of}.json."""
    as_of = valuation.get("as_of")
    if not as_of:
        return None
    hist = valuation_history_dir(ticker_dir)
    hist.mkdir(parents=True, exist_ok=True)
    dest = hist / f"valuation_{str(as_of)[:10]}.json"
    if not dest.exists():
        dest.write_text(json.dumps(valuation, indent=2) + "\n", encoding="utf-8")
    return dest
