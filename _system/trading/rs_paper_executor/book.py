"""RS inside the account-wide book margin limit, as the LOWEST-priority claimant.

spx-0dte's limit (``live/book_margin_limit.py``, #596) has each product of its
fixed ``PROFILES`` list publish ``data/live/<ET date>/book_margin_<product>.json``
and fit its entries in a pro-rata share of ``nav x book_wide_margin_pct`` minus
the others' claims. SPX reads ONLY its known products, so an RS file there would
be ignored, and SPX's executor is deliberately not changed. RS therefore yields
on its own side. It reads the products' files read-only and fits only in what is
left after the larger of SPX's claim and an owner-set SPX reserve:

    others + max(spx_claim, spx_reserve x nav) + rs_claim + new  <=  limit x nav

It YIELDS (flattens its own names) whenever that stops holding with new = 0.
``nav`` is SPX's published ``account_nav`` (the configured compounding anchor
SPX's limit uses), never a number RS invents; without a valid SPX file RS takes
no entry.

RS's claim is priced on squeeze stress, not defined risk (a short stock has
none): ``squeeze_loss_multiple x shares x max(entry, highest ask seen)`` plus the
WhatIf maintenance margin recorded at entry, plus pending-entry reservations.

RS publishes its own claim, in the same schema, under its OWN state directory,
never inside spx-0dte's tree (the nightly syncs and commits that tree).
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from .safety import SafetyError, number, timestamp

OWN_PRODUCT = "rs"
SPX_PRODUCT = "spx"
SCHEMA = 1  # spx-0dte live/book_margin_limit.py SCHEMA
PREFIX = "book_margin_"


def et_day(now):
    return timestamp(now).astimezone(ZoneInfo("America/New_York")).date().isoformat()


def parse_claim(data, product, today):
    """(claim dollars, account_nav) from one spx-0dte claim file, or raise.

    Mirrors spx-0dte ``_claim_from``: schema 1, today's date, the file's own
    product, and a finite non-negative claim."""
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise SafetyError("book margin schema mismatch")
    if data.get("today") != today or data.get("product") != product:
        raise SafetyError("book margin file is for another day or product")
    claim = number(data.get("claim"), "claim", minimum=0)
    nav = data.get("account_nav")
    return claim, (number(nav, "account_nav", minimum=1) if nav is not None else None)


class BookMargin:
    def __init__(self, read_root, publish_root, policy, spx_reserve_fraction, *,
                 limit_fraction=1.0):
        self.read_root, self.publish_root = Path(read_root), Path(publish_root)
        if self.publish_root.resolve() == self.read_root.resolve():
            raise SafetyError("RS must not publish inside spx-0dte's live tree")
        self.policy = policy
        self.spx_reserve = number(spx_reserve_fraction, "spx_book_reserve_fraction", minimum=0)
        self.limit = number(limit_fraction, "book_margin_limit_fraction", minimum=0)
        if not 0 < self.limit <= 1 or not 0 < self.spx_reserve < self.limit:
            raise SafetyError("need 0 < spx reserve < book limit <= 1")
        self._last_good = {}

    def others(self, now, *, for_entry):
        """({product: claim $}, spx account_nav). Absent file = that product
        holds nothing today (spx-0dte's rule). Unreadable: an entry check
        refuses; a yield check uses the last good value, so a file glitch
        alone never flattens RS."""
        today = et_day(now)
        directory = self.read_root / today
        found, nav = {}, None
        try:
            paths = sorted(directory.glob(PREFIX + "*.json")) if directory.is_dir() else []
        except OSError as exc:
            # spx-0dte's tree lives in the spx user's home; without the install's
            # read grant this is EACCES, not "no file". Name it as what it is.
            if for_entry:
                raise SafetyError(
                    "SPX book margin directory unreadable: " + type(exc).__name__)
            last = {k[1]: v for k, v in self._last_good.items() if k[0] == today}
            return {k: v[0] for k, v in last.items()}, last.get(SPX_PRODUCT, (0, None))[1]
        for path in paths:
            product = path.stem[len(PREFIX):]
            if product == OWN_PRODUCT:
                continue
            try:
                claim, file_nav = parse_claim(
                    json.loads(path.read_text(encoding="utf-8")), product, today)
                self._last_good[(today, product)] = (claim, file_nav)
            except (OSError, ValueError, SafetyError):
                if for_entry:
                    raise SafetyError("unreadable book margin claim: " + product)
                if (today, product) not in self._last_good:
                    continue
                claim, file_nav = self._last_good[(today, product)]
            found[product] = claim
            if product == SPX_PRODUCT:
                nav = file_nav
        if nav is None and for_entry:
            raise SafetyError("SPX book margin file absent: no NAV for the limit")
        if nav is None:
            nav = next((v[1] for k, v in self._last_good.items()
                        if k == (today, SPX_PRODUCT) and v[1]), None)
        return found, nav

    def rs_claim_dollars(self, executor):
        p, journal = self.policy, executor.journal
        total = 0.0
        for pos in journal.rows("positions"):
            if not pos["shares"]:
                continue
            signal = json.loads(pos["payload"])
            bound = journal.get("borrow_bound:" + signal["id"], {}) or {}
            price = max(pos["entry_price"], bound.get("price", 0) or 0)
            total += p.squeeze_loss_multiple * pos["shares"] * price
            total += number(signal.get("entry_maintenance_margin", 0), minimum=0)
        for order in journal.rows("orders"):
            if order["side"] == "SELL" and order["state"] not in ("filled", "cancelled", "rejected"):
                signal = json.loads(order["payload"])["signal"]
                total += number(signal.get("margin_reserve", 0), minimum=0)
        return total

    def _committed(self, now, *, for_entry):
        found, nav = self.others(now, for_entry=for_entry)
        if nav is None:
            return None, None
        spx = max(found.pop(SPX_PRODUCT, 0.0), self.spx_reserve * nav)
        return nav, spx + sum(found.values())

    def require_fit(self, snap, now, executor, new_claim_dollars):
        nav, committed = self._committed(now, for_entry=True)
        rs = self.rs_claim_dollars(executor) + number(new_claim_dollars, minimum=0)
        if committed + rs > self.limit * nav:
            raise SafetyError("book margin: no room after SPX reserve and other products")

    def must_yield(self, snap, now, executor):
        nav, committed = self._committed(now, for_entry=False)
        if nav is None:
            return False  # no SPX file today and none seen: nothing to yield to
        return committed + self.rs_claim_dollars(executor) > self.limit * nav

    def publish(self, executor, snap, now):
        today = et_day(now)
        claim = self.rs_claim_dollars(executor)
        if not math.isfinite(claim):
            raise SafetyError("RS claim is not finite")
        directory = self.publish_root / today
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (PREFIX + OWN_PRODUCT + ".json")
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump({"schema": SCHEMA, "product": OWN_PRODUCT, "today": today,
                       "ts": now, "claim": claim, "measure": "squeeze_stress",
                       "priority": "lowest", "broker_nav": snap.get("nav")}, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
