"""CLI entrypoints for the reverse-split research database.

    python -m _system.scripts.reverse_splits.cli <command> [options]

Collectors (``seed``, ``clocks``, ``prices``, ``finra``, ``fundamentals``) write
the local SQLite database; ``databento-pull`` fetches licensed venue files into
``local/raw/databento`` and ``detect-splits`` reads them into a local report;
``export-ledger`` / ``import-ledger`` move rows
between it and the committed JSONL ledger; ``build-dashboard`` and ``check``
read the ledger alone. ``--since-days`` scopes the EDGAR and price collectors
to a recent window so the weekly job does not re-scan five years.

No command opens a broker connection. Borrow comes from ``borrow-csv``.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from .config import SCRIPTS_DIR, load_config


def _since(args) -> date | None:
    days = getattr(args, "since_days", None)
    if days is None:
        return None
    return date.today() - timedelta(days=int(days))


def _scripts_on_path() -> None:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reverse_splits", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=None, help="config.toml (default: _system/data/reverse_splits/config.toml)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="Create the local SQLite schema")

    p_seed = sub.add_parser("seed", help="Seed reverse splits from EDGAR full-text search + yfinance corporate actions")
    p_seed.add_argument("--max-tickers", type=int, default=None)
    p_seed.add_argument("--full-scan", action="store_true", help="Scan all SEC tickers via yfinance (slow)")
    p_seed.add_argument("--since-days", type=int, default=None, help="Search EDGAR only from N days ago (weekly job)")

    sub.add_parser("tag-repeats", help="Tag first/second/third_plus reverse splits")
    sub.add_parser("classify-exchanges", help="Classify listed vs OTC using the SEC exchange map")

    p_edgar = sub.add_parser("enrich-edgar", help="Enrich proxy/announce/vote/effective dates (full filing text)")
    p_edgar.add_argument("--limit", type=int, default=None)
    p_edgar.add_argument("--fast", action="store_true", help="Search-index only (no filing downloads)")

    p_clocks = sub.add_parser("clocks", help="Attach EDGAR accept times and parse announcement text")
    p_clocks.add_argument("--no-text", action="store_true")
    p_clocks.add_argument("--text-limit", type=int, default=None)
    p_clocks.add_argument("--since-days", type=int, default=None, help="Only filings filed in the last N days")

    p_px = sub.add_parser("prices", help="Download daily OHLCV around events (yfinance)")
    p_px.add_argument("--limit", type=int, default=None)
    p_px.add_argument("--since-days", type=int, default=None, help="Only events dated in the last N days")

    sub.add_parser("finra", help="Ingest FINRA short interest files from local/raw/finra")

    p_dbn = sub.add_parser("databento-pull", help="Fetch Databento venue daily bars, definitions and status into local/raw/databento (DATABENTO_API_KEY; refuses any request quoted above --max-cost)")
    p_dbn.add_argument("--start", type=date.fromisoformat, default=None, help="Default 2018-05-01, where the venue datasets begin")
    p_dbn.add_argument("--end", type=date.fromisoformat, default=None, help="Exclusive; default today")
    p_dbn.add_argument("--schemas", default="ohlcv-1d,definition,status")
    p_dbn.add_argument("--datasets", default="XNAS.ITCH,XNYS.PILLAR,XASE.PILLAR", help="Daily-bar venues")
    p_dbn.add_argument("--max-cost", type=float, default=0.0, help="Highest acceptable quote per request, USD")

    p_det = sub.add_parser("detect-splits", help="Detect reverse splits in the Databento bars and reconcile them with the ledger (local report)")
    p_det.add_argument("--datasets", default="XNAS.ITCH,XNYS.PILLAR,XASE.PILLAR")
    p_det.add_argument("--reuse-scan", action="store_true", help="Reuse the last bar scan; redo merge, classification and reconciliation")

    p_borrow = sub.add_parser("borrow-csv", help="Import a Client Portal Short-Securities Availability CSV")
    p_borrow.add_argument("csv", type=Path)

    sub.add_parser("book", help="Run strict and assumed-fee books; write the local snapshot and reports")
    sub.add_parser("backtest", help="Alias of book")

    p_fund = sub.add_parser("fundamentals", help="Cache SEC companyfacts using the SSI fundamentals method")
    p_fund.add_argument("--tickers", nargs="*", default=None)
    p_fund.add_argument("--limit", type=int, default=None)

    p_rerun = sub.add_parser("rerun", help="Replay the frozen 96-case fundamental/cost experiment; cached prices only")
    p_rerun.add_argument("--refresh-sources", action="store_true", help="Fill missing public SEC caches and freeze their hashes")

    p_serve = sub.add_parser("serve", help="Local research API (and optional static dashboard folder)")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.add_argument("--docs", type=Path, default=None, help="Static files to serve (the old repository's docs/)")

    p_controls = sub.add_parser("controls", help="Download a random listed sample for the control match")
    p_controls.add_argument("--sample-size", type=int, default=None)

    sub.add_parser("report", help="Write legacy timing CSVs and markdown report")

    p_all = sub.add_parser("pipeline", help="seed -> classify -> tag -> clocks -> prices -> finra -> controls -> book -> report")
    p_all.add_argument("--max-tickers", type=int, default=None)
    p_all.add_argument("--skip-edgar", action="store_true", help="Do not download filing text in the clocks step")
    p_all.add_argument("--edgar-limit", type=int, default=None)
    p_all.add_argument("--full-scan", action="store_true")
    p_all.add_argument("--since-days", type=int, default=None)

    p_exp = sub.add_parser("export-ledger", help="SQLite -> JSONL ledger")
    p_exp.add_argument("--db", type=Path, default=None)
    p_exp.add_argument("--out", type=Path, default=None)

    p_imp = sub.add_parser("import-ledger", help="JSONL ledger -> SQLite")
    p_imp.add_argument("--db", type=Path, default=None)
    p_imp.add_argument("--ledger-dir", type=Path, default=None)
    p_imp.add_argument("--replace", action="store_true")

    sub.add_parser("build-dashboard", help="Build dashboard/data/reverse_splits.json from the ledger")

    p_check = sub.add_parser("check", help="Structural and health checks on the ledger and dashboard feed")
    p_check.add_argument("--strict", action="store_true")
    p_check.add_argument("--warn-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(args.config)

    from .db import init_db

    if args.cmd == "init-db":
        init_db(cfg.db_path)
        print(f"Initialized {cfg.db_path}")
        return 0

    if args.cmd == "seed":
        from .ingest_splits import seed_from_edgar_and_yfinance, tag_repeat_splits

        stats = seed_from_edgar_and_yfinance(cfg, max_tickers=args.max_tickers, full_scan=args.full_scan, since=_since(args))
        print(stats)
        print("tagged", tag_repeat_splits(cfg))
        return 0

    if args.cmd == "tag-repeats":
        from .ingest_splits import tag_repeat_splits

        print("tagged", tag_repeat_splits(cfg))
        return 0

    if args.cmd == "classify-exchanges":
        from .classify_exchanges import main as classify_main

        classify_main(cfg)
        return 0

    if args.cmd == "enrich-edgar":
        if args.fast:
            from .enrich_edgar_fast import enrich_from_search

            print(enrich_from_search(cfg))
        else:
            from .enrich_edgar import enrich_events

            print(enrich_events(cfg, limit=args.limit))
        return 0

    if args.cmd == "clocks":
        from .enrich_edgar import enrich_clocks

        since = _since(args)
        print(enrich_clocks(cfg, download_text=not args.no_text, text_limit=args.text_limit, since=since.isoformat() if since else None))
        return 0

    if args.cmd == "prices":
        from .ingest_prices import ingest_prices

        since = _since(args)
        print(ingest_prices(cfg, limit=args.limit, since=since.isoformat() if since else None))
        return 0

    if args.cmd == "finra":
        from .ingest_finra import ingest_finra

        print(ingest_finra(cfg))
        return 0

    if args.cmd == "databento-pull":
        from .databento_bars import FIRST_DAY, pull

        print(pull(cfg, start=args.start or FIRST_DAY, end=args.end, schemas=tuple(args.schemas.split(",")),
                   datasets=tuple(args.datasets.split(",")), max_cost=args.max_cost))
        return 0

    if args.cmd == "detect-splits":
        import json

        from .split_detector import detect

        summary = detect(cfg, datasets=tuple(args.datasets.split(",")), reuse_scan=args.reuse_scan)
        print(json.dumps({k: v for k, v in summary.items() if k != "by_year"}, indent=1, default=str))
        return 0

    if args.cmd == "borrow-csv":
        from .borrow import import_ibkr_slb_csv

        n = import_ibkr_slb_csv(args.csv, cfg)
        print(f"imported {n} rows from {args.csv}")
        return 0

    if args.cmd in {"backtest", "book"}:
        from .snapshot_export import export_snapshot

        print(export_snapshot(cfg))
        return 0

    if args.cmd == "fundamentals":
        from .fundamentals import refresh_companyfacts

        print(refresh_companyfacts(cfg, tickers=args.tickers, limit=args.limit))
        return 0

    if args.cmd == "rerun":
        import sqlite3

        from .realism import verified_announcements
        from .rerun import freeze_inputs, run_rerun
        from .rerun_sources import ensure_sources
        from .run_book import load_events

        root = freeze_inputs(cfg)
        if args.refresh_sources or not (root / "source_refresh.json").exists():
            conn = sqlite3.connect(root / "input.sqlite")
            conn.row_factory = sqlite3.Row
            events, _ = verified_announcements(load_events(conn), [dict(r) for r in conn.execute("SELECT * FROM edgar_hits")])
            conn.close()
            if (root / "source_refresh.json").exists():
                print("Using the existing frozen SEC source ledger; create a new experiment version to change it.")
            else:
                ensure_sources(cfg, events, root / "source_refresh.json")
        result = run_rerun(cfg)
        print("Published", len(result["cases"]), "scenarios")
        return 1 if any(c["status"] == "failed" for c in result["cases"]) else 0

    if args.cmd == "serve":
        from .serve import serve

        serve(args.port, docs=args.docs, cfg=cfg)
        return 0

    if args.cmd == "controls":
        from .controls import download_control_universe

        print(download_control_universe(cfg, sample_size=args.sample_size))
        return 0

    if args.cmd == "report":
        from .report import event_coverage, write_reports

        print(event_coverage(cfg))
        print(write_reports(cfg))
        return 0

    if args.cmd == "pipeline":
        from .classify_exchanges import main as classify_main
        from .enrich_edgar import enrich_clocks, enrich_events
        from .ingest_finra import ingest_finra
        from .ingest_prices import ingest_prices
        from .ingest_splits import seed_from_edgar_and_yfinance, tag_repeat_splits
        from .report import write_reports
        from .snapshot_export import export_snapshot

        since = _since(args)
        since_text = since.isoformat() if since else None
        print("== seed ==")
        print(seed_from_edgar_and_yfinance(cfg, max_tickers=args.max_tickers, full_scan=args.full_scan, since=since))
        print("== classify ==")
        classify_main(cfg)
        print("== tag ==")
        print(tag_repeat_splits(cfg))
        if args.edgar_limit is not None:
            print("== edgar deep ==")
            print(enrich_events(cfg, limit=args.edgar_limit))
        print("== clocks ==")
        print(enrich_clocks(cfg, download_text=not args.skip_edgar, since=since_text))
        print("== prices ==")
        print(ingest_prices(cfg, since=since_text))
        print("== finra ==")
        print(ingest_finra(cfg))
        print("== controls ==")
        try:
            from .controls import download_control_universe

            print(download_control_universe(cfg))
        except Exception as exc:  # noqa: BLE001 - the control sample is optional
            print(f"control sample skipped: {exc}")
        print("== book ==")
        print(export_snapshot(cfg))
        print("== report ==")
        print(write_reports(cfg))
        return 0

    if args.cmd == "export-ledger":
        from .export_ledger import export_ledger

        db = args.db or cfg.db_path
        if not Path(db).exists():
            print(f"no database at {db}; run import-ledger or init-db first", file=sys.stderr)
            return 1
        manifest = export_ledger(db, args.out or cfg.ledger_dir, cfg.decisions_db_path)
        for name, info in manifest["files"].items():
            print(f"{name:24s} rows={info['rows']:>6} bytes={info['bytes']:>10,}")
        return 0 if manifest["decisions_chain_valid"] else 1

    if args.cmd == "import-ledger":
        from .import_ledger import import_ledger

        counts = import_ledger(args.ledger_dir or cfg.ledger_dir, args.db or cfg.db_path, cfg.decisions_db_path, replace=args.replace)
        print(" ".join(f"{k}={v}" for k, v in counts.items()))
        return 0

    if args.cmd == "build-dashboard":
        _scripts_on_path()
        import build_reverse_splits_dashboard as builder  # noqa: PLC0415

        return builder.main([])

    if args.cmd == "check":
        _scripts_on_path()
        import check_reverse_splits as checker  # noqa: PLC0415

        flags = []
        if args.strict:
            flags.append("--strict")
        if args.warn_only:
            flags.append("--warn-only")
        return checker.main(flags)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
