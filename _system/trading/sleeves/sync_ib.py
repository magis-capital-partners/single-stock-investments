"""Snapshot the configured IBKR account and classify its legacy Drew/Michael views."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from _system.trading.sleeves.book import build_book, export_static_books
from _system.trading.sleeves.classify_positions import classify_positions, expand_blacklist_symbols, norm_sym
from _system.trading.sleeves.config_loader import (
    load_blacklist,
    load_config,
    load_etf_ls_universe,
    load_etf_to_under,
)
from _system.trading.sleeves.flex_positions import parse_flex_positions
from _system.trading.sleeves.ingest import post_ingest
from _system.trading.sleeves.store import SleeveStore


# The edge refuses a sleeve ingest body over 512,000 bytes (MAX_BODY_BYTES in
# dashboard/functions/api/v1/sleeves/ingest.js). Build to well under that.
INGEST_BODY_BUDGET = 450_000

# Everything the edge ingest reads from a book position. The rest of build_book's
# row -- display name, thesis text, notes, cluster, conviction, P&L -- is for the
# static page; the edge never stores it, and shipping it once per Flex tax lot
# is what took Michael's post to 647,887 bytes and an HTTP 413.
_INGEST_POSITION_KEYS = (
    "ticker", "qty", "mark", "market_value", "secType", "classifier_reason", "conid",
    "local_symbol", "expiry", "strike", "right", "multiplier", "cost_usd", "entry_price",
)
_INGEST_AUDIT_KEYS = ("as_of", "ticker", "bucket", "reason", "owner")


class IngestTooLarge(ValueError):
    """A book that cannot be posted in one body without dropping positions."""


def _compact(payload: Any) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode()


def _position_key(pos: Mapping[str, Any]) -> str:
    """The edge's key (positionKey in _lib/sleeves.js): local_symbol, else ticker."""
    local = str(pos.get("local_symbol") or pos.get("localSymbol") or "").strip()
    return local or str(pos.get("ticker") or "").strip()


def fold_ingest_positions(positions: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One slim row per contract, folded exactly as the edge's foldPositions folds.

    Flex reports open LOTS, so one contract arrives as several rows. The edge
    already folds them on the same key -- quantity, market value and cost add;
    everything else is the first lot's -- so folding here stores the identical
    result while sending one row per contract instead of one per lot.
    """
    folded: dict[str, dict[str, Any]] = {}
    for pos in positions:
        key = _position_key(pos)
        seen = folded.get(key)
        if seen is None:
            folded[key] = {name: pos[name] for name in _INGEST_POSITION_KEYS if pos.get(name) is not None}
            continue
        seen["qty"] = float(seen.get("qty") or 0) + float(pos.get("qty") or 0)
        seen["market_value"] = float(seen.get("market_value") or 0) + float(pos.get("market_value") or 0)
        if seen.get("cost_usd") is not None or pos.get("cost_usd") is not None:
            seen["cost_usd"] = float(seen.get("cost_usd") or 0) + float(pos.get("cost_usd") or 0)
    return list(folded.values())


def ingest_payloads(owner: str, book: Mapping[str, Any], audit: list[Mapping[str, Any]], *,
                    budget: int = INGEST_BODY_BUDGET) -> list[dict[str, Any]]:
    """The sync for one owner as a list of POST bodies, each under `budget` bytes.

    The first body carries the (slim, folded) book -- it must travel whole,
    because the edge replaces the owner's positions with whatever one post
    carries. Classifier audit rows, deduplicated, fill it; any that do not fit
    follow in audit-only bodies, which the edge stores without touching the book.
    """
    slim_book = {
        "owner": book.get("owner") or owner,
        "as_of": book.get("as_of"),
        "header": dict(book.get("header") or {}),
        "positions": fold_ingest_positions(list(book.get("positions") or [])),
    }
    first: dict[str, Any] = {"kind": "sync", "book": slim_book, "audit": []}
    base = len(_compact(first))
    if base > budget:
        raise IngestTooLarge(
            f"{owner} book is {base} bytes with {len(slim_book['positions'])} contracts, over the "
            f"{budget}-byte budget; positions cannot be split across posts without being deleted"
        )

    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for row in audit:
        slim = {name: row[name] for name in _INGEST_AUDIT_KEYS if row.get(name) is not None}
        identity = json.dumps(slim, sort_keys=True)
        if identity not in seen:
            seen.add(identity)
            rows.append(slim)

    payloads = [first]
    size = base
    for row in rows:
        row_bytes = len(_compact(row))
        target = payloads[-1]
        added = row_bytes + (1 if target["audit"] else 0)
        if size + added > budget:
            target = {"kind": "sync_audit", "audit": []}
            payloads.append(target)
            size = len(_compact(target))
            added = row_bytes
        target["audit"].append(row)
        size += added
    return payloads


def _maybe_ingest(payload: Mapping[str, Any], cfg: Mapping[str, Any]) -> dict[str, Any] | None:
    url = str((cfg.get("ingest") or {}).get("url") or os.environ.get("SLEEVE_INGEST_URL") or "").strip()
    token = os.environ.get(str((cfg.get("ingest") or {}).get("token_env") or "SLEEVE_INGEST_TOKEN") or "")
    if not url or not token:
        return None
    return post_ingest(url, token, dict(payload))


def merge_flex_marks(rows: list[dict[str, Any]], flex_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """When TWS has no last for a foreign name, avgCost masquerades as the mark. Prefer Flex."""
    by_con = {int(row.get("conId") or 0): row for row in flex_rows if row.get("conId")}
    out = []
    for row in rows:
        flex = by_con.get(int(row.get("conId") or 0))
        if not flex:
            out.append(row)
            continue
        mark = float(row.get("mark") or 0)
        avg = float(row.get("avgCost") or 0)
        if avg and abs(mark - avg) < 1e-4:
            updated = dict(row)
            updated["mark"] = flex.get("mark")
            updated["marketValue"] = flex.get("marketValue")
            if flex.get("costUsd") is not None:
                updated["costUsd"] = flex.get("costUsd")
            if flex.get("name"):
                updated["name"] = flex.get("name")
            out.append(updated)
        else:
            out.append(row)
    return out


def load_positions(
    cfg: Mapping[str, Any],
    *,
    supplied: list[Mapping[str, Any]] | None = None,
    flex_path: Path | None = None,
    flex_marks: Path | None = None,
) -> tuple[list[dict[str, Any]], str]:
    if supplied is not None:
        return [dict(row) for row in supplied], "supplied"
    account = str((cfg.get("ibkr") or {}).get("account_id") or "").strip()
    if flex_path is not None:
        return parse_flex_positions(flex_path, account_id=account), f"flex:{flex_path.name}"
    live_error: Exception | None = None
    try:
        from _system.trading.sleeves.ib_client import connect_ib, fetch_positions

        ib = connect_ib("sync", cfg, readonly=True)
        try:
            rows = fetch_positions(ib, account)
        finally:
            ib.disconnect()
        marks_path = flex_marks
        if marks_path is None:
            env_marks = os.environ.get("IBKR_FLEX_POSITIONS_XML") or os.environ.get("SLEEVE_FLEX_XML")
            marks_path = Path(env_marks) if env_marks else None
        if marks_path and marks_path.is_file():
            rows = merge_flex_marks(rows, parse_flex_positions(marks_path, account_id=account))
            return rows, "ib_live+flex_marks"
        return rows, "ib_live"
    except Exception as exc:
        live_error = exc
    env_path = os.environ.get("IBKR_FLEX_POSITIONS_XML") or os.environ.get("SLEEVE_FLEX_XML")
    path = Path(env_path) if env_path else None
    if path and path.is_file():
        return parse_flex_positions(path, account_id=account), f"flex:{path.name}"
    raise RuntimeError(
        "Could not read the configured IBKR account from TWS/Gateway. Start local TWS on port 7496 "
        "(NY4 Gateway must be logged out), or pass --flex path/to/flex_positions.xml. "
        f"Live error: {live_error}"
    ) from live_error


def sync_holdings(
    store: SleeveStore,
    cfg: Mapping[str, Any] | None = None,
    *,
    positions: list[Mapping[str, Any]] | None = None,
    flex_path: Path | None = None,
    flex_marks: Path | None = None,
    ingest: bool = True,
    write_dashboard: bool = True,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    rows, source = load_positions(cfg, supplied=positions, flex_path=flex_path, flex_marks=flex_marks)
    family = expand_blacklist_symbols(load_blacklist(cfg), load_etf_to_under(cfg))
    letf = load_etf_ls_universe(cfg)
    drew_symbols = [
        norm_sym(symbol)
        for symbol in ((cfg.get("operators") or {}).get("drew") or {}).get("symbols") or []
    ]
    classified = classify_positions(
        rows,
        blacklist_family=family,
        etf_ls_symbols=letf,
        drew_symbols=drew_symbols,
    )
    tags = {int(t["con_id"]): t for t in store.sleeve_tags() if t.get("con_id")}
    tags_by_ticker = {(t.get("owner"), str(t.get("ticker") or "").upper()): t for t in store.sleeve_tags()}
    for row in classified:
        cls = row.get("classification") or {}
        if cls.get("bucket") in {"spx_0dte", "etf_ls", "index_put_hedge"}:
            continue
        con_id = int(row.get("conId") or 0)
        tag = tags.get(con_id)
        if tag and tag.get("owner") in {"drew", "michael"}:
            row["classification"] = {
                "ticker": cls.get("ticker") or row.get("symbol"),
                "bucket": tag["owner"],
                "reason": "sleeve_tag",
                "owner": tag["owner"],
            }
            continue
        # Drew fills without a matching conId still win on ticker if tagged.
        symbol = str(row.get("symbol") or "").upper()
        drew_tag = tags_by_ticker.get(("drew", symbol))
        if drew_tag:
            row["classification"] = {
                "ticker": cls.get("ticker") or row.get("symbol"),
                "bucket": "drew",
                "reason": "sleeve_tag",
                "owner": "drew",
            }
    store.replace_positions(classified)
    store.append_audit([row["classification"] for row in classified])
    if write_dashboard:
        export_static_books(store, cfg, source=source)
    buckets = Counter((row.get("classification") or {}).get("bucket") for row in classified)
    michael = build_book("michael", store, cfg)
    drew = build_book("drew", store, cfg)
    michael["source"] = source
    drew["source"] = source
    ingest_result: dict[str, Any] = {}
    if ingest:
        # Every owner is attempted even when an earlier one fails; main() turns
        # any recorded error into a non-zero exit.
        for owner, book in (("michael", michael), ("drew", drew)):
            try:
                audit = [row["classification"] for row in classified if (row.get("classification") or {}).get("owner") == owner]
                bodies = ingest_payloads(owner, book, audit)
                responses = []
                for body in bodies:
                    response = _maybe_ingest(body, cfg)
                    if response is None:  # no URL or token configured: nothing is sent
                        break
                    responses.append(response)
                ingest_result[owner] = None if not responses else {
                    "ok": True, "posts": len(responses),
                    "bytes": [len(_compact(body)) for body in bodies[: len(responses)]],
                }
            except Exception as exc:
                ingest_result[owner] = {"error": str(exc)}
    return {
        "source": source,
        "count": len(classified),
        "buckets": dict(buckets),
        "michael": michael,
        "drew": drew,
        "ingest": ingest_result,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync the configured IBKR account into Michael / Drew sleeves")
    parser.add_argument("--flex", type=Path, help="IBKR Flex OpenPositions XML if TWS is down")
    parser.add_argument("--flex-marks", type=Path, help="Overlay Flex marks onto a live TWS snapshot")
    parser.add_argument("--no-ingest", action="store_true", help="Write local JSON only")
    args = parser.parse_args(argv)
    result = sync_holdings(
        SleeveStore(),
        flex_path=args.flex,
        flex_marks=args.flex_marks,
        ingest=not args.no_ingest,
    )
    michael = result["michael"]["header"]
    drew = result["drew"]["header"]
    print(
        f"source={result['source']} rows={result['count']} buckets={result['buckets']}\n"
        f"Michael names={michael.get('open_names')} nav={michael.get('nav_usd')}\n"
        f"Drew names={drew.get('open_names')} nav={drew.get('nav_usd')}\n"
        f"ingest={result['ingest']}"
    )
    # A failed POST used to print and exit 0, so the unit reported success while
    # an owner's book never reached the dashboard. Every owner has been attempted
    # by now; fail the run if any of them failed.
    failed = sorted(owner for owner, outcome in (result.get("ingest") or {}).items()
                    if isinstance(outcome, dict) and outcome.get("error"))
    if failed:
        print(f"sleeve ingest failed for: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
