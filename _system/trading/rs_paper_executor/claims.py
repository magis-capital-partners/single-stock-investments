"""Account symbol claims: the shared contract that keeps systems off each other's names.

IBKR nets every contract per account, so two systems in one account must never
trade the same symbol. Each system that trades single names publishes one file,
``<claims_dir>/<system>.json``::

    {"schema": "ib_account_symbol_claims.v1", "system": "reverse-split",
     "account": "U...", "generated_at": "<UTC ISO>",
     "claims": {"ABC": {"conid": 123, "sec_type": "STK",
                        "claimed_at": "<UTC ISO>", "release_after": null}}}

Rules every reader follows (ls-algo mirrors them in its own reader):

* A claim is active until ``release_after`` is set AND has passed. Age never
  releases a claim: a dead writer must not hand its names back.
* An unreadable or malformed file is not "no claims": readers keep the last
  good copy and refuse the names in it, and page.
* Writers write atomically (temp file, fsync, replace) and claim BEFORE
  transmitting the first order in a name.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re

from .safety import SafetyError, timestamp

SCHEMA = "ib_account_symbol_claims.v1"
SYMBOL = re.compile(r"[A-Z][A-Z0-9.]{0,11}")


def _validate(data, system=None):
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise SafetyError("symbol claims schema mismatch")
    if system is not None and data.get("system") != system:
        raise SafetyError("symbol claims belong to another system")
    timestamp(data.get("generated_at"))
    claims = data.get("claims")
    if not isinstance(claims, dict):
        raise SafetyError("symbol claims must be an object")
    for symbol, row in claims.items():
        if not SYMBOL.fullmatch(symbol) or not isinstance(row, dict):
            raise SafetyError("invalid claimed symbol")
        timestamp(row.get("claimed_at"))
        if row.get("release_after") is not None:
            timestamp(row["release_after"])
    return data


def active(row, now):
    release = row.get("release_after")
    return release is None or timestamp(now) < timestamp(release)


class ClaimBook:
    """This system's own claims file. One writer: the executor holding the journal."""

    def __init__(self, directory, system, account):
        self.directory = Path(directory)
        self.path = self.directory / (system + ".json")
        self.system, self.account = system, account
        self._foreign_cache = {}

    def foreign(self, now):
        """Names other systems in this account hold (fails closed, see module doc)."""
        return foreign_claims(self.directory, self.system, now, self._foreign_cache)

    def load(self):
        if not self.path.exists():
            return {"schema": SCHEMA, "system": self.system, "account": self.account,
                    "generated_at": "1970-01-01T00:00:00+00:00", "claims": {}}
        data = _validate(json.loads(self.path.read_text(encoding="utf-8")), self.system)
        if data.get("account") != self.account:
            raise SafetyError("symbol claims belong to another account")
        return data

    def write(self, data, now):
        data = dict(data, generated_at=now)
        _validate(data, self.system)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, sort_keys=True, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    def claim(self, symbol, conid, now):
        data = self.load()
        row = data["claims"].get(symbol)
        if row and row.get("conid") != conid:
            raise SafetyError("claimed symbol maps to another contract")
        data["claims"][symbol] = {"conid": conid, "sec_type": "STK",
                                  "claimed_at": row["claimed_at"] if row else now,
                                  "release_after": None}
        self.write(data, now)

    def release(self, symbol, release_after, now):
        """Mark a flat name releasable after ``release_after`` (never immediately)."""
        data = self.load()
        row = data["claims"].get(symbol)
        if row and row.get("release_after") is None:
            row["release_after"] = release_after
            self.write(data, now)

    def held(self, now):
        return {s for s, row in self.load()["claims"].items() if active(row, now)}


def foreign_claims(directory, own_system, now, cache=None):
    """Names other systems hold. Unreadable files fall back to ``cache`` and raise
    only when no good copy of that file was ever read (the caller then refuses)."""
    cache = {} if cache is None else cache
    names = {}
    for path in sorted(Path(directory).glob("*.json")):
        if path.stem == own_system:
            continue
        try:
            data = _validate(json.loads(path.read_text(encoding="utf-8")))
            if data["system"] != path.stem:
                raise SafetyError("claims file name/system mismatch")
            cache[path.stem] = data
        except (OSError, ValueError, SafetyError):
            if path.stem not in cache:
                raise SafetyError("unreadable symbol claims: " + path.name)
            data = cache[path.stem]
        for symbol, row in data["claims"].items():
            if active(row, now):
                names[symbol] = data["system"]
    return names
