"""Import, reconcile and publish realized history from private Flex reports.

No command in this module opens a Gateway socket. `fetch` uses only the HTTPS
report service. Daily `sync` reuses files already fetched by the EOD producer.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import gzip
import json
import os
import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from .classify_positions import expand_blacklist_symbols
from .config_loader import load_blacklist, load_etf_ls_universe, load_etf_to_under
from .ingest import post_ingest
from .realized import VERSION, canonical, digest, read_report
from .realized_flex import fetch_report, report_lock
from .realized_store import RealizedStore


def partition(records: list[dict]) -> list[list[dict]]:
    batches, current = [], []
    size = 2
    for row in records:
        length = len(canonical(row).encode()) + 1
        if current and (len(current) >= 80 or size + length > 250_000):
            batches.append(current); current = []; size = 2
        current.append(row); size += length
    if current:
        batches.append(current)
    return batches


def publication(history: dict) -> tuple[dict, list[list[dict]]]:
    rows = [r for r in history["records"] if r["owner"] != "excluded" and r["trade_date"]]
    batches = partition(rows)
    recon = history["reconciliation"]
    manifest = {k: history[k] for k in ("through", "coverage", "policy_version", "source_reports")}
    manifest["ownership_version"] = history.get("ownership_version")
    manifest.update({"row_count": len(rows), "batch_hashes": [digest(b) for b in batches],
                     "storage": history.get("storage_version", "row_v1"),
                     "source_generated": max((r["generated"] for r in history["source_reports"]), default=history["through"] + "T00:00:00"),
                     "owner_counts": dict(Counter(r["owner"] for r in rows)),
                     "excluded_count": sum(r["owner"] == "excluded" for r in history["records"]),
                     "reconciliation": {**{k:v for k,v in recon.items() if k not in {"exceptions", "differences"}},
                        "difference_count": len(recon["differences"]), "differences": recon["differences"][:30],
                        "exception_count": len(recon["exceptions"]),
                        "exception_reasons": dict(Counter(x["reason"] for x in recon["exceptions"])),
                        "examples": recon["exceptions"][:20]}})
    return manifest, batches


def publish(store: RealizedStore, history: dict, *, url: str, token: str) -> dict:
    manifest, batches = publication(history)
    generation = history["generation_id"]
    old = store.db.execute("SELECT published_at FROM realized_publications WHERE generation_id=?", (generation,)).fetchone()
    if old and old[0]:
        return {"duplicate": True, "generation_id": generation}
    base = {"schema_version": VERSION, "generation_id": generation, "account": history["account"]}
    archives = []
    sources = []
    for source in history["source_reports"]:
        record = store.db.execute("SELECT archive_path FROM realized_reports WHERE report_id=?", (source["report_id"],)).fetchone()
        sources.append({**source, "path": Path(record[0]), "format": "xml"})
    if history.get("ownership_version"):
        identity = history["ownership_version"]
        registry_path = store.root / f"ownership-{identity}.json"
        compressed = registry_path.with_suffix(".json.gz")
        if not compressed.exists():
            compressed.write_bytes(gzip.compress(registry_path.read_bytes(), mtime=0))
        sources.append({"report_id": identity, "path": compressed, "format": "strategy_ownership.json"})
    for source in sources:
        part_shas = []
        with source["path"].open("rb") as handle:
            while data := handle.read(180_000):
                part_shas.append(hashlib.sha256(data).hexdigest())
        archives.append({"report_id": source["report_id"], "part_shas": part_shas, "compression": "gzip", "format": source["format"]})
    manifest["archives"] = archives

    def send(body):
        for attempt in range(3):
            try:
                response = post_ingest(url, token, {**base, **body}, timeout=45)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
        kind = body["kind"]
        acknowledged = {
            "begin": response.get("staged") is True,
            "archive-status": isinstance(response.get("parts"), list),
            "archive": response.get("archived") is True and response.get("part") == body.get("part"),
            "batch": response.get("staged") is True or response.get("duplicate") is True,
            "complete": response.get("complete") is True,
        }.get(kind, False)
        if not acknowledged:
            raise RuntimeError(f"server did not acknowledge realized {kind}; verify the deployed endpoint before retrying")
        return response

    send({"kind": "begin", "manifest": manifest})
    # Immutable original XML is archived as bounded gzip parts in private R2.
    # Each part carries its own checksum; the manifest records reconstruction.
    for source in sources:
        known = send({"kind": "archive-status", "report_id": source["report_id"]}).get("parts", [])
        expected = next(a for a in archives if a["report_id"] == source["report_id"])["part_shas"]
        known_parts = {p["part"]: p["content_sha"] for p in known}
        with source["path"].open("rb") as handle:
            part = 0
            while data := handle.read(180_000):
                if known_parts.get(part) != expected[part]:
                    send({"kind": "archive", "report_id": source["report_id"], "part": part,
                          "content_sha": expected[part], "data": base64.b64encode(data).decode()})
                part += 1
    for index, batch in enumerate(batches):
        send({"kind": "batch", "batch_index": index, "records": batch})
    response = send({"kind": "complete"})
    with store.db:
        store.db.execute("INSERT OR REPLACE INTO realized_publications VALUES (?,?,?,CURRENT_TIMESTAMP)",
                         (generation, history["account"], canonical(manifest)))
    return {"generation_id": generation, "rows": manifest["row_count"], "batches": len(batches), "response": response}


def window_chunks(start: str, through: str):
    first, end = date.fromisoformat(start), date.fromisoformat(through)
    while first <= end:
        following = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        last = min(end, following - timedelta(days=1))
        yield first.isoformat(), last.isoformat()
        first = last + timedelta(days=1)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=Path(os.environ.get("SLEEVE_REALIZED_STATE", "_private/sleeve-realized")))
    parser.add_argument("--account", default=os.environ.get("IBKR_ACCOUNT_ID") or os.environ.get("IBKR_ACCOUNT_ALIAS") or "")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("import")
    ingest.add_argument("files", nargs="+", type=Path)
    sync = commands.add_parser("sync")
    sync.add_argument("--positions", type=Path, required=True)
    sync.add_argument("--trades", type=Path)
    sync.add_argument("--closed-lots", type=Path)
    sync.add_argument("--stale-hours", type=int, default=30)
    sync.add_argument("--publish", action="store_true")
    build = commands.add_parser("build")
    build.add_argument("--output", type=Path)
    commands.add_parser("publish")
    fetch = commands.add_parser("fetch")
    fetch.add_argument("--query-id", default=os.environ.get("SLEEVE_CLOSED_LOTS_QUERY_ID", ""))
    fetch.add_argument("--from", dest="start", required=True)
    fetch.add_argument("--through", required=True)
    fetch.add_argument("--role", choices=("executions", "closed_lots", "supplement"), default="closed_lots")
    fetch.add_argument("--refresh", action="store_true", help="Retrieve later broker restatements of cached periods")
    detail = commands.add_parser("refresh-detail", help="Bounded supplemental fetch after the primary EOD producer finishes")
    detail.add_argument("--positions", type=Path, required=True)
    detail.add_argument("--query-id", default=os.environ.get("SLEEVE_CLOSED_LOTS_QUERY_ID", ""))
    assign = commands.add_parser("assign")
    assign.add_argument("rule", type=Path, help="Private JSON evidence rule; requires author and reason")
    args = parser.parse_args(argv)
    if not args.account:
        parser.error("configured account is required")
    store = RealizedStore(args.state)
    try:
        with report_lock(args.state):
            if args.command == "assign":
                rule = json.loads(args.rule.read_text(encoding="utf-8"))
                if rule.get("account") != args.account:
                    raise ValueError("ownership rule account does not match configured account")
                print(canonical(store.assign(rule))); return 0
            if args.command in {"fetch", "refresh-detail"}:
                if not args.query_id:
                    raise ValueError("Closed Lots query ID is not configured; archived executions remain usable")
                if args.command == "refresh-detail":
                    period = read_report(args.positions, account=args.account)
                    args.through = period["through"]
                    last = date.fromisoformat(args.through)
                    args.start = (last - timedelta(days=35)).isoformat()
                    args.role, args.refresh = "closed_lots", True
                for start, through in window_chunks(args.start, args.through):
                    destination = args.state / "downloads" / f"{args.role}-{start}-{through}.xml"
                    if args.refresh or not destination.exists():
                        fetch_report(query_id=args.query_id, account=args.account, start=start,
                                     through=through, destination=destination)
                    print(canonical(store.ingest(destination, account=args.account, role=args.role)), flush=True)
                return 0
            if args.command == "import":
                for path in args.files:
                    print(canonical(store.ingest(path, account=args.account)), flush=True)
                return 0
            if args.command == "sync":
                trades = args.trades or args.positions.with_name("flex_trades.xml")
                if not trades.exists():
                    raise ValueError("trade report is missing; retaining last valid realized history")
                if (time.time() - trades.stat().st_mtime) / 3600 > args.stale_hours:
                    raise ValueError("trade file is stale; retaining last valid realized history")
                if (time.time() - args.positions.stat().st_mtime) / 3600 > args.stale_hours:
                    raise ValueError("position file is stale; retaining last valid ownership registry")
                trade_period = read_report(trades, account=args.account)
                position_period = read_report(args.positions, account=args.account)
                if trade_period["through"] != position_period["through"]:
                    raise ValueError("trade and position statements have different completed-session dates; publication deferred")
                for path in (trades, args.positions, args.closed_lots):
                    if path and path.exists():
                        print(canonical(store.ingest(path, account=args.account, role="closed_lots" if path == args.closed_lots else None)), flush=True)
            history = store.build(account=args.account, ls_symbols=load_etf_ls_universe(),
                                  blacklist=expand_blacklist_symbols(load_blacklist(), load_etf_to_under()))
            if args.command == "build" and args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(canonical(history), encoding="utf-8")
            should_publish = args.command == "publish" or (args.command == "sync" and args.publish)
            if should_publish:
                url = os.environ.get("SLEEVE_REALIZED_INGEST_URL") or os.environ.get("SLEEVE_INGEST_URL") or "https://single-stock-investments-2wt.pages.dev/api/v1/sleeves/ingest"
                token = os.environ.get("SLEEVE_INGEST_TOKEN", "")
                if not token:
                    raise ValueError("SLEEVE_INGEST_TOKEN is not configured")
                print(canonical(publish(store, history, url=url, token=token)))
            else:
                print(canonical({"generation_id": history["generation_id"], "through": history["through"],
                                 "coverage": history["coverage"], "counts": dict(Counter(r["owner"] for r in history["records"])),
                                 "reconciliation": publication(history)[0]["reconciliation"], "gateway_contacted": False}))
        return 0
    except Exception as exc:
        print(f"realized history: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
