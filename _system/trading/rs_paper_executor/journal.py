"""Single-writer durable intents/outcomes, adapted from SPX operation recovery."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3

from .safety import PREFIX, SafetyError


class Journal:
    def __init__(self, path, policy_hash, prefix=PREFIX):
        if prefix not in ("RSPAPER|", "RSLIVE|"):
            raise SafetyError("unknown order reference prefix")
        self.prefix = prefix
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = path.with_suffix(path.suffix + ".lock").open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                self.lock.seek(0)
                if not self.lock.read(1):
                    self.lock.write(b"0")
                    self.lock.flush()
                self.lock.seek(0)
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            self.lock.close()
            raise SafetyError("another paper executor owns this journal") from exc
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
          CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS signals(id TEXT PRIMARY KEY,issuer TEXT,payload TEXT);
          CREATE TABLE IF NOT EXISTS orders(ref TEXT PRIMARY KEY,signal_id TEXT,issuer TEXT,
            conid INTEGER,side TEXT,shares INTEGER,limit_price REAL,state TEXT,order_id INTEGER,
            perm_id INTEGER,filled INTEGER DEFAULT 0,payload TEXT);
          CREATE TABLE IF NOT EXISTS fills(exec_id TEXT PRIMARY KEY,ref TEXT,shares INTEGER,
            price REAL,at TEXT,commission REAL);
          CREATE TABLE IF NOT EXISTS positions(signal_id TEXT PRIMARY KEY,issuer TEXT,
            conid INTEGER,shares INTEGER,entry_price REAL,entry_at TEXT,exit_at TEXT,payload TEXT);
          CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,at TEXT,kind TEXT,payload TEXT);
        """)
        old = self.get("policy_hash")
        if old and old != policy_hash:
            self.close()
            raise SafetyError("policy changed: use a separately registered journal")
        self.set("policy_hash", policy_hash)
        if self.get("order_prefix", prefix) != prefix:
            self.close()
            raise SafetyError("journal belongs to another order namespace")
        self.set("order_prefix", prefix)

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO meta VALUES(?,?)", (key, json.dumps(value))
            )

    def event(self, at, kind, payload):
        with self.db:
            self.db.execute(
                "INSERT INTO events(at,kind,payload)VALUES(?,?,?)",
                (at, kind, json.dumps(payload)),
            )

    def rows(self, table):
        if table not in ("orders", "positions", "signals", "fills", "events"):
            raise SafetyError("invalid journal table")
        return [dict(x) for x in self.db.execute("SELECT *FROM " + table)]

    def intent(self, signal, side, shares, limit_price, at):
        # One entry and at most one unresolved cover per signal. A new cover gets
        # an explicit sequence only after the prior one is proven terminal.
        previous = [
            x
            for x in self.rows("orders")
            if x["signal_id"] == signal["id"] and x["side"] == side
        ]
        if side == "SELL" and previous:
            raise SafetyError("entry already attempted")
        if any(x["state"] not in ("filled", "cancelled", "rejected") for x in previous):
            raise SafetyError("order outcome unresolved")
        ref = (
            self.prefix
            + hashlib.sha256(
                f"{signal['id']}:{side}:{len(previous)}".encode()
            ).hexdigest()[:20]
        )
        payload = {"at": at, "signal": signal, "paper_only": self.prefix == PREFIX}
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO signals VALUES(?,?,?)",
                (signal["id"], signal["cik"], json.dumps(signal)),
            )
            self.db.execute(
                "INSERT INTO orders(ref,signal_id,issuer,conid,side,shares,limit_price,state,payload)VALUES(?,?,?,?,?,?,?,'submitting',?)",
                (
                    ref,
                    signal["id"],
                    signal["cik"],
                    signal["conid"],
                    side,
                    shares,
                    limit_price,
                    json.dumps(payload),
                ),
            )
        return ref

    def acknowledge(self, ref, order_id, perm_id=0):
        with self.db:
            self.db.execute(
                "UPDATE orders SET state='working',order_id=?,perm_id=? WHERE ref=?",
                (order_id, perm_id, ref),
            )

    def uncertain(self, ref, at):
        with self.db:
            self.db.execute("UPDATE orders SET state='uncertain'WHERE ref=?", (ref,))
        self.event(at, "submission_uncertain", {"ref": ref})

    def fill(self, ref, exec_id, shares, price, at, commission):
        order = self.db.execute("SELECT *FROM orders WHERE ref=?", (ref,)).fetchone()
        if not order:
            raise SafetyError("foreign fill")
        duplicate = self.db.execute(
            "SELECT *FROM fills WHERE exec_id=?", (exec_id,)
        ).fetchone()
        if duplicate:
            if (duplicate["ref"], duplicate["shares"], duplicate["price"]) != (
                ref,
                shares,
                price,
            ):
                raise SafetyError("conflicting execution identity")
            return False
        if shares <= 0 or order["filled"] + shares > order["shares"]:
            raise SafetyError("execution exceeds order quantity")
        signal = json.loads(order["payload"])["signal"]
        pos = self.db.execute(
            "SELECT *FROM positions WHERE signal_id=?", (order["signal_id"],)
        ).fetchone()
        old_shares = pos["shares"] if pos else 0
        if order["side"] == "BUY" and shares > old_shares:
            raise SafetyError("cover would create a long position")
        remaining = (
            old_shares + shares if order["side"] == "SELL" else old_shares - shares
        )
        entry_price = (
            ((old_shares * pos["entry_price"] if pos else 0) + shares * price)
            / remaining
            if order["side"] == "SELL"
            else pos["entry_price"]
        )
        with self.db:
            self.db.execute(
                "INSERT INTO fills VALUES(?,?,?,?,?,?)",
                (exec_id, ref, shares, price, at, commission),
            )
            self.db.execute(
                "UPDATE orders SET filled=filled+?,state=CASE WHEN filled+?=shares THEN 'filled' ELSE 'working' END WHERE ref=?",
                (shares, shares, ref),
            )
            self.db.execute(
                "INSERT OR REPLACE INTO positions VALUES(?,?,?,?,?,?,?,?)",
                (
                    order["signal_id"],
                    signal["cik"],
                    signal["conid"],
                    remaining,
                    entry_price,
                    pos["entry_at"] if pos else at,
                    signal["planned_exit_at"],
                    json.dumps(signal),
                ),
            )
        return True

    def close(self):
        self.db.close()
        if os.name == "nt":
            import msvcrt

            self.lock.seek(0)
            msvcrt.locking(self.lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self.lock.fileno(), fcntl.LOCK_UN)
        self.lock.close()
