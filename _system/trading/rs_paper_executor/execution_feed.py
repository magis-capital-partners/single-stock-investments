"""Publish a read-only view of the local paper journal, independently of trading."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_PATH = "/api/v2/portfolio/ingest"
DOMAIN = "rs_execution_paper"
ORDER_REF = re.compile(r"RSPAPER\|[a-f0-9]{20}")
CENT = Decimal("0.01")


def utc_text(now):
    return now.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def money(value):
    return float(value.quantize(CENT))


def as_decimal(value):
    return Decimal(str(value))


def paper_snapshot(path, session_id, now=None, *, ended=False):
    now = now or datetime.now(timezone.utc)
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        meta = {r["key"]: json.loads(r["value"]) for r in db.execute("SELECT * FROM meta")}
        identity = meta.get("endpoint") or {}
        if meta.get("order_prefix") != "RSPAPER|" or not re.fullmatch(r"DU\d+", identity.get("account", "")):
            raise ValueError("An identified DU-only paper journal is required.")
        orders, signals = {}, {}
        for row in db.execute("SELECT * FROM orders ORDER BY rowid"):
            if not ORDER_REF.fullmatch(row["ref"]):
                raise ValueError("Foreign order in paper journal.")
            payload = json.loads(row["payload"])
            signal = payload["signal"]
            ticker = signal["ticker"]
            if not re.fullmatch(r"[A-Z0-9][A-Z0-9. /-]{0,15}", ticker):
                raise ValueError("Unsupported paper ticker.")
            signals[row["signal_id"]] = ticker
            orders[row["ref"]] = {
                key: row[key] for key in ("ref", "signal_id", "side", "shares", "limit_price",
                                         "state", "order_id", "perm_id", "filled", "conid")
            } | {"ticker": ticker, "at": payload["at"]}

        fills = []
        lots = {}
        realized = fees = Decimal(0)
        fees_final = True
        for row in db.execute("SELECT * FROM fills ORDER BY rowid"):
            order = orders[row["ref"]]
            cost = as_decimal(row["price"])
            qty = row["shares"]
            key = order["signal_id"]
            held, basis = lots.get(key, (0, Decimal(0)))
            if order["side"] == "SELL":
                basis = (basis * held + cost * qty) / (held + qty)
                held += qty
            elif order["side"] == "BUY" and held >= qty:
                realized += (basis - cost) * qty
                held -= qty
            else:
                raise ValueError("Paper cover exceeds open shares.")
            lots[key] = (held, basis)
            source = row["commission_source"] if "commission_source" in row.keys() else "unknown"
            fees_final &= source == "broker"
            fees += as_decimal(row["commission"])
            fills.append({
                key: row[key] for key in ("ref", "exec_id", "shares", "price", "at", "commission")
            } | {"side": order["side"], "ticker": order["ticker"], "commission_source": source})

        positions = []
        unrealized = Decimal(0)
        marks_complete = True
        for signal_id, (shares, basis) in lots.items():
            if not shares:
                continue
            mark = meta.get("execution_mark:" + signal_id)
            valid_mark = False
            if mark:
                age = (now - datetime.fromisoformat(mark["at"])).total_seconds()
                valid_mark = 0 <= age <= (3 if mark["source"] == "live_ask" else 30)
            marked_pnl = (basis - as_decimal(mark["ask"])) * shares if valid_mark else None
            if marked_pnl is None:
                marks_complete = False
            else:
                unrealized += marked_pnl
            positions.append({
                "signal_id": signal_id, "ticker": signals[signal_id], "shares_short": shares,
                "entry_price": float(basis), "mark": mark, "mark_current": valid_mark,
                "unrealized_gross": money(marked_pnl) if marked_pnl is not None else None,
            })

        timeline = []
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='execution_order_states'").fetchone():
            timeline = [dict(row) for row in db.execute(
                "SELECT id, at, ref, state, filled FROM execution_order_states ORDER BY id"
            )]
        events = [
            row | {"id": "order:" + str(row["id"]), "ticker": orders[row["ref"]]["ticker"],
                   "kind": "order_" + row["state"]}
            for row in timeline
        ]
        for ref, order in orders.items():
            cancelled_at = meta.get("cancel_requested:" + ref)
            if cancelled_at:
                events.append({"id": "cancel:" + ref, "at": cancelled_at, "ref": ref,
                               "kind": "cancel_requested", "ticker": order["ticker"]})
        for fill in fills:
            events.append({"id": "fill:" + fill["exec_id"], "at": fill["at"], "ref": fill["ref"],
                           "kind": "cover_fill" if fill["side"] == "BUY" else "short_fill",
                           "ticker": fill["ticker"], "shares": fill["shares"], "price": fill["price"]})
        events.sort(key=lambda row: datetime.fromisoformat(row["at"]))
        return {
            "schema": "rs_execution.v1", "mode": "paper", "session_id": session_id,
            "observed_at": utc_text(now), "ended": ended,
            "orders": list(orders.values()), "fills": fills, "events": events, "positions": positions,
            "kill_latched": meta.get("kill") is True,
            "pnl": {
                "currency": "USD", "realized_gross": money(realized),
                "unrealized_gross": money(unrealized) if marks_complete else None,
                "commission": money(fees), "commission_final": fees_final,
                "marked_before_borrow": money(realized + unrealized - fees) if marks_complete else None,
            },
        }


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def publish(url, key, snapshot, *, opener=None):
    parts = urlsplit(url)
    if (parts.path != API_PATH or parts.query or parts.fragment or parts.username
            or not parts.hostname or (parts.scheme != "https"
            and (parts.scheme != "http" or parts.hostname not in {"127.0.0.1", "localhost"}))):
        raise ValueError("Use the SSI ingestion HTTPS URL or a local test endpoint.")
    payload = json.dumps(snapshot, separators=(",", ":"), allow_nan=False).encode()
    ts, nonce = str(int(time.time())), secrets.token_hex(16)
    message = f"{DOMAIN}\n{ts}\n{nonce}\n".encode() + payload
    signature = hmac.new(key.encode(), message, hashlib.sha256).hexdigest()
    request = Request(url, data=payload, headers={
        "content-type": "application/json", "x-ssi-ingest-purpose": DOMAIN,
        "user-agent": "Magis-RS-Paper/1.0",
        "x-portfolio-timestamp": ts, "x-portfolio-nonce": nonce, "x-portfolio-signature": signature,
    })
    with (opener or build_opener(NoRedirect())).open(request, timeout=2) as response:
        if response.status != 200 or "application/json" not in response.headers.get("content-type", ""):
            raise ValueError("The SSI endpoint did not acknowledge a paper snapshot.")
        result = json.load(response)
        if isinstance(result.get("stored"), bool) or result.get("available") is True:
            return result
        raise ValueError("The SSI endpoint did not acknowledge a paper snapshot.")


def start_publisher(journal_path):
    key = os.environ.get("RS_EXECUTION_PUBLISH_KEY", "").strip()
    url = os.environ.get("RS_EXECUTION_PUBLISH_URL", "https://single-stock-investments-2wt.pages.dev" + API_PATH)
    if len(key) < 32:
        raise ValueError("Set RS_EXECUTION_PUBLISH_KEY before enabling the paper dashboard.")
    path = Path(journal_path).resolve()
    if path.exists() or not path.name.endswith(".integration.sqlite"):
        raise ValueError("The dashboard requires a new paper integration journal.")
    try:
        if not publish(url, key, {"schema": "rs_execution_probe.v1"}).get("available"):
            raise ValueError("Paper dashboard authentication check failed.")
    except (URLError, TimeoutError) as error:
        raise ValueError("The paper dashboard endpoint could not be verified.") from error
    path.parent.mkdir(parents=True, exist_ok=True)
    session = secrets.token_hex(16)
    done = path.with_suffix(".execution-finished")
    with path.with_suffix(".execution-log").open("w", encoding="utf-8") as log:
        child = subprocess.Popen([
            sys.executable, "-m", __name__, "--journal", str(path), "--url", url,
            "--session-id", session, "--until-file", str(done),
        ], stdout=log, stderr=subprocess.STDOUT)
    return child, done, session


def finish_publisher(child, done):
    done.touch(exist_ok=True)
    try:
        return child.wait(timeout=8) == 0
    except subprocess.TimeoutExpired:
        child.terminate()
        child.wait()
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--session-id", required=True, help="Stable 32-hex identifier for this journal.")
    parser.add_argument("--until-file", type=Path, help="Publish a final snapshot after this file appears.")
    parser.add_argument("--max-seconds", type=int, default=5400)
    parser.add_argument("--health-file", type=Path, help="Local timestamp of the last acknowledged snapshot.")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-f0-9]{32}", args.session_id) or not 1 <= args.max_seconds <= 14400:
        parser.error("Use a 32-hex session ID and a bounded duration of 1–14,400 seconds.")
    key = os.environ.get("RS_EXECUTION_PUBLISH_KEY", "").strip()
    if len(key) < 32:
        parser.error("RS_EXECUTION_PUBLISH_KEY is required.")
    deadline = time.monotonic() + args.max_seconds
    last_sent = 0
    previous = None
    while time.monotonic() < deadline:
        ended = bool(args.until_file and args.until_file.is_file())
        if args.journal.is_file():
            try:
                snapshot = paper_snapshot(args.journal, args.session_id, ended=ended)
                content = {k: v for k, v in snapshot.items() if k != "observed_at"}
                if content != previous or time.monotonic() - last_sent >= 12:
                    publish(args.url, key, snapshot)
                    previous, last_sent = content, time.monotonic()
                    if args.health_file:
                        args.health_file.write_text(snapshot["observed_at"], encoding="ascii")
                    if ended:
                        return 0
            except (sqlite3.OperationalError, URLError, TimeoutError) as error:
                detail = f"HTTP {error.code}" if isinstance(error, HTTPError) else type(error).__name__
                print(f"Paper feed awaiting valid journal/upload ({detail}).", file=sys.stderr)
                if isinstance(error, HTTPError) and error.code in {400, 401, 403, 404, 413, 422}:
                    return 2
            except ValueError as error:
                if "identified DU-only" not in str(error) or ended or previous is not None:
                    print(str(error), file=sys.stderr)
                    return 2
        elif ended:
            print("The paper journal was never created.", file=sys.stderr)
            return 2
        time.sleep(1)
    return 2


if __name__ == "__main__":
    sys.exit(main())
