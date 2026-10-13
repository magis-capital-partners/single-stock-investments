"""Run the book and write the local snapshot JSON plus the markdown reports.

Writes ``public_dir/backtest.json`` (the old repository's
``docs/data/backtest.json``) and persists the book runs into SQLite. The hosted
dashboard is built separately, from the JSONL ledger alone, by
``_system/scripts/build_reverse_splits_dashboard.py``; this snapshot is a local
research artifact under the ignored ``local/`` tree.
"""

from __future__ import annotations

import json

from .config import Config, load_config
from .run_book import persist_snapshot, run_snapshot, write_book_report


def export_snapshot(cfg: Config | None = None) -> dict:
    cfg = cfg or load_config()
    path = cfg.public_dir / "backtest.json"
    baseline = path.with_name("baseline_reference.json")
    if path.exists() and not baseline.exists():
        baseline.write_bytes(path.read_bytes())
    snapshot = run_snapshot(cfg)
    persist_snapshot(cfg, snapshot)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    report = write_book_report(cfg, snapshot)
    from .analysis import write_analysis_report

    audit = write_analysis_report(cfg, snapshot)
    for name in ("analysis_audit.md", "short_alpha_review_queue.json"):
        (path.parent / name).write_bytes((cfg.reports_dir / name).read_bytes())
    return {
        "json": str(path),
        "report": report,
        "audit": audit,
        "books": [
            {
                "id": book["id"],
                "taken": book["stats"]["taken"],
                "dollar_pnl": round(book["stats"]["dollar_pnl"], 2),
                "median_return": book["stats"]["median_return"],
            }
            for book in snapshot["books"]
        ],
    }
