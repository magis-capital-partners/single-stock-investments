#!/usr/bin/env python3
"""Fetch issuer operating KPIs into the normalized store.

    python _system/scripts/fetch_operating_kpis.py
    python _system/scripts/fetch_operating_kpis.py --tickers MIAX OCC
    python _system/scripts/fetch_operating_kpis.py --force

Writes ``_system/reference/market-data/operating_kpis/{TICKER}.json`` and
``_status.json``. A vendor block (HTTP 403) keeps the previous file and does
not fail the nightly job. A document that downloads and then does not match
the parser fails the run, so a layout change is visible.

After a successful write, operating series are merged into the ticker's agent
shard and into ``dashboard/data/kpi_summary.json`` ``operating_latest``. The
full ``kpi_trends.json`` rebuild picks the same series up on the nightly
intake job.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from atomic_io import attach_envelope, semantic_json_sha256  # noqa: E402
from operating_kpis.model import LayoutError, STORE_DIR, utc_now, write_ticker_store  # noqa: E402
from operating_kpis.registry import ADAPTERS  # noqa: E402
from operating_kpis.trends import (  # noqa: E402
    merge_operating_series,
    operating_latest_rows,
    select_shard_series,
)

SHARD_DIR = ROOT / "dashboard" / "data" / "agent_shards"
KPI_SUMMARY = ROOT / "dashboard" / "data" / "kpi_summary.json"


def publish_views() -> None:
    """Put operating levels on the shards and the L0 summary without a full rebuild."""
    # Parse the canonical stores once per publication, not once per shard.
    operating = merge_operating_series({})
    if SHARD_DIR.is_dir():
        for path in sorted(SHARD_DIR.glob("*.json")):
            shard = json.loads(path.read_text(encoding="utf-8"))
            ticker = str(shard.get("ticker") or path.stem).upper()
            issuer_rows = operating.get(ticker) or []
            names = {row["metric"] for row in issuer_rows}
            rows = issuer_rows + [row for row in shard.get("kpi_series") or [] if row.get("metric") not in names]
            if not any(row.get("tier") == "operating" for row in rows):
                continue
            selected = select_shard_series(rows)
            if selected == shard.get("kpi_series"):
                continue
            shard["kpi_series"] = selected
            truncation = shard.setdefault("truncation", {})
            truncation["kpi_series"] = {"shown": len(selected), "total": len(rows)}
            envelope = shard.get("_envelope") or {}
            digest = semantic_json_sha256(shard)
            if envelope:
                envelope["content_sha256"] = f"sha256:{digest}"
                envelope["row_count"] = len(selected) + len(shard.get("recent_news") or [])
            path.write_text(json.dumps(shard, indent=2) + "\n", encoding="utf-8")
            print(f"Shard {ticker}: {sum(1 for row in selected if row.get('tier') == 'operating')} operating series")

    if not KPI_SUMMARY.is_file():
        return
    summary = json.loads(KPI_SUMMARY.read_text(encoding="utf-8"))
    prior = dict(summary.get("_envelope") or {})
    latest = operating_latest_rows()
    summary.pop("_envelope", None)
    summary["operating_latest"] = latest
    summary["description"] = (
        "L0 KPI inflection summary extracted from dashboard/data/kpi_trends.json. "
        "Inflections are the accelerating and decelerating series. "
        "operating_latest carries issuer operating levels even when the series is steady."
    )
    attach_envelope(
        summary,
        feed_id=prior.get("feed_id") or "dashboard-kpi-summary",
        as_of=str(summary.get("as_of") or "")[:10] or None,
        row_count=prior.get("row_count") if prior.get("row_count") is not None else len(summary.get("inflections") or []),
        upstream_inputs=prior.get("upstream_inputs"),
    )
    KPI_SUMMARY.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"kpi_summary operating_latest: {len(latest)} rows")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch issuer operating KPIs.")
    parser.add_argument("--tickers", nargs="*", help="Limit to these tickers (OCC included)")
    parser.add_argument("--force", action="store_true", help="Ignored; the fetch always runs")
    parser.add_argument("--no-publish", action="store_true", help="Do not touch shards or kpi_summary")
    parser.add_argument("--import-mirror", type=Path, help="Import dated observations only; executes no mirror code or network fetch")
    args = parser.parse_args()
    wanted = {ticker.upper() for ticker in args.tickers} if args.tickers else None
    fetched_at = utc_now()
    if args.import_mirror:
        from operating_kpis.mirror import import_mirror, royalty_signals
        from buy_zones import load_config
        from atomic_io import write_json_if_changed
        config = load_config()
        report = import_mirror(args.import_mirror, tickers=wanted or set(config["tickers"]), root=ROOT)
        state_path = ROOT / "_system/data/core_compounder_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        state["royalty_signals"] = royalty_signals(args.import_mirror, set(config["tickers"]))
        write_json_if_changed(state_path, state)
        if not args.no_publish:
            publish_views()
        print(json.dumps(report))
        return 0
    status_rows = []
    hard_failure = False

    for ticker, fetch in ADAPTERS:
        if wanted and ticker not in wanted:
            continue
        try:
            points, sources = fetch(fetched_at)
        except LayoutError as exc:
            hard_failure = True
            status_rows.append({"ticker": ticker, "status": "layout_error", "note": str(exc)})
            print(f"{ticker}: LAYOUT {exc}", file=sys.stderr)
            continue
        except Exception as exc:  # noqa: BLE001 — one adapter must not hide the others
            hard_failure = True
            status_rows.append({"ticker": ticker, "status": "error", "note": str(exc)})
            traceback.print_exc()
            continue
        status_rows.extend(sources)
        ok = [row for row in sources if row.get("status") == "ok"]
        if points and ok:
            path = write_ticker_store(ticker, points, sources=sources, fetched_at=fetched_at)
            print(f"{ticker}: {len(points)} points -> {path.relative_to(ROOT)}")
        else:
            print(f"{ticker}: no new points ({sources[0].get('status') if sources else 'empty'})")

    STORE_DIR.mkdir(parents=True, exist_ok=True)
    from atomic_io import write_json_if_changed
    status_path = STORE_DIR / "_status.json"
    previous_status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    if wanted:
        status_rows = [r for r in previous_status.get("adapters") or [] if r.get("ticker") not in wanted] + status_rows
    write_json_if_changed(status_path, {"fetched_at": fetched_at, "adapters": status_rows})
    if not args.no_publish and not hard_failure:
        publish_views()
    elif not args.no_publish and any(
        (STORE_DIR / f"{ticker}.json").is_file()
        for ticker, _fetch in ADAPTERS
        if not wanted or ticker in wanted
    ):
        # A blocked adapter is not a hard failure. Publish whatever was written
        # this run or already on disk. A layout error still publishes the
        # tickers that parsed, then fails the process.
        publish_views()
    return 1 if hard_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
