"""One bounded live-only Mini session; stdin commands, sanitized JSON stdout.

No Historical/Reference API, replay, broker library, paid request or licensing API.
The parent owns the lease and must terminate this child when that lease ends.
"""
from __future__ import annotations

import json
import logging
import math
import os
import queue
import re
import signal
import sys
import threading
import time
import uuid
from datetime import datetime, timezone

DATASET = "EQUS.MINI"
MAX_SYMBOLS = 128


class BookCredits:
    """Count positive displayed additions before output throttling; not fills."""
    def __init__(self):
        self.epoch = uuid.uuid4().hex
        self.books = {}

    def update(self, row):
        result = {}
        for side, price_key, size_key in (("short", "bid", "bid_size"), ("cover", "ask", "ask_size")):
            key = (row["ticker"], side, row[price_key])
            if key not in self.books and len(self.books) >= 32768:
                return None  # bounded memory; unknown additions cannot support fills
            size = row[size_key]
            old = self.books.get(key)
            total = size if old is None else old[1] + max(0, size - old[0])
            self.books[key] = (size, total)
            result[side] = total
        return {**row, "book_epoch": self.epoch, "book_credit": result}


def stamp(ns=None):
    return datetime.fromtimestamp(ns / 1e9, timezone.utc).isoformat(timespec="milliseconds") if ns else datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def normalize_record(record, ticker, received_at):
    """Reject undefined prices, corrupt books and clocks; sizes are shares."""
    level = record.levels[0]
    values = [int(level.bid_px), int(level.ask_px)]
    flags = int(record.flags)
    if flags & (4 | 8) or any(v <= 0 or v >= 2**62 for v in values):
        return None
    bid, ask = [v / 1e9 for v in values]
    bid_size, ask_size = int(level.bid_sz), int(level.ask_sz)
    ns = int(record.ts_recv)
    if not 0 < bid <= ask < 1_000_000 or not 0 < bid_size < 2**32 - 1 or not 0 < ask_size < 2**32 - 1:
        return None
    if not math.isfinite(ns) or ns <= 0 or ns >= 2**63:
        return None
    return {"kind": "quote", "ticker": ticker, "dataset": DATASET,
            "schema": "mbp-1", "quote_at": stamp(ns), "observed_at": received_at,
            "bid": bid, "ask": ask, "bid_size": bid_size, "ask_size": ask_size,
            "ts_recv_ns": str(ns), "ts_event_ns": str(record.ts_event),
            "instrument_id": int(record.instrument_id), "flags": flags}


def main():
    logging.disable(logging.CRITICAL)  # SDK diagnostics must never expose credentials.
    import databento as db
    import databento_dbn as dbn

    lock, commands, stopping = threading.Lock(), queue.Queue(maxsize=256), threading.Event()
    wanted, mappings, emitted = set(), {}, {}
    credits = BookCredits()
    key = os.environ.get("DATABENTO_API_KEY", "")

    def emit(value):
        with lock:
            print(json.dumps(value, allow_nan=False), flush=True)

    def control():
        try:
            for line in sys.stdin:
                if len(line) > 2048:
                    continue
                try:
                    item = json.loads(line)
                    ticker = item.get("ticker", "")
                    if item.get("kind") == "stop":
                        break
                    if item.get("kind") == "replace_subscriptions":
                        names = item.get("tickers", [])
                        if isinstance(names, list) and 0 < len(names) <= MAX_SYMBOLS and all(isinstance(t, str) and re.fullmatch(r"[A-Z][A-Z0-9.]{0,11}", t) for t in names):
                            commands.put({"kind": "replace_subscriptions", "tickers": names}, timeout=1)
                        continue
                    if item.get("kind") == "subscribe" and re.fullmatch(r"[A-Z][A-Z0-9.]{0,11}", ticker):
                        commands.put(item, timeout=1)
                except (ValueError, queue.Full):
                    continue
        finally:
            stopping.set()

    def receive(record):
        received_at = stamp()
        if isinstance(record, dbn.SymbolMappingMsg):
            symbol = str(record.stype_in_symbol)
            if symbol in wanted:
                mappings[int(record.instrument_id)] = symbol
        elif isinstance(record, dbn.MBP1Msg):
            ticker = mappings.get(int(record.instrument_id))
            if not ticker:
                return
            value = normalize_record(record, ticker, received_at)
            if value is None:
                emit({"kind": "invalidate", "ticker": ticker})
                return
            value = credits.update(value)
            if value is None:
                emit({"kind": "invalidate", "ticker": ticker})
                return
            # Bounded IPC; this never fabricates a fresh timestamp for an old book.
            if time.monotonic() - emitted.get(ticker, 0) >= .25:
                emitted[ticker] = time.monotonic()
                emit(value)
        elif isinstance(record, dbn.SystemMsg):
            message = str(record.msg).lower()
            if "succeeded" in message:
                emit({"kind": "health", "status": "subscribed", "at": received_at})
            elif "heartbeat" in message:
                emit({"kind": "heartbeat", "at": received_at})
        elif isinstance(record, dbn.ErrorMsg):
            # Do not forward arbitrary server text into logs or the dashboard.
            emit({"kind": "health", "status": "subscription_error", "at": received_at})

    threading.Thread(target=control, daemon=True).start()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    attempts = 0
    while not stopping.is_set():
        client = None
        try:
            if not wanted:
                try:
                    initial = commands.get(timeout=1)
                    wanted.update(initial["tickers"] if initial.get("kind") == "replace_subscriptions" else [initial["ticker"]])
                except queue.Empty:
                    continue
            mappings.clear()
            emitted.clear()
            credits = BookCredits()
            emit({"kind": "health", "status": "connecting", "at": stamp()})
            client = db.Live(heartbeat_interval_s=5)
            client.add_callback(receive)
            client.subscribe(dataset=DATASET, schema="mbp-1", symbols=sorted(wanted), stype_in="raw_symbol")
            client.start()
            rotation = False
            while not stopping.is_set() and client.is_connected():
                try:
                    command = commands.get(timeout=1)
                    if command.get("kind") == "replace_subscriptions":
                        wanted.clear()
                        wanted.update(command["tickers"])
                        rotation = True
                        break
                    ticker = command["ticker"]
                except queue.Empty:
                    continue
                if ticker not in wanted and len(wanted) < MAX_SYMBOLS:
                    wanted.add(ticker)
                    client.subscribe(dataset=DATASET, schema="mbp-1", symbols=[ticker], stype_in="raw_symbol")
            if stopping.is_set():
                break
            if rotation:
                emit({"kind": "health", "status": "connecting", "at": stamp()})
                continue
            client.block_for_close(timeout=1)
            raise RuntimeError("Live session ended")
        except Exception as exc:
            text = str(exc).replace(key, "[REDACTED]") if key else ""
            permanent = bool(re.search(r"auth|license|not.entitled|permission|not.authorized|subscription.*required", text, re.I))
            attempts += 1
            emit({"kind": "health", "status": "not_entitled" if permanent else "disconnected",
                  "error_class": type(exc).__name__, "at": stamp()})
            if permanent or attempts >= 12:
                return 2 if permanent else 3
        finally:
            if client:
                client.terminate()
        if stopping.wait(min(300, 30 * 2 ** min(attempts - 1, 4))):
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
