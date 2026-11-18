"""Stage-6 paper integration test: order handling and recovery on a real paper session.

SYNTHETIC CONTROLS ONLY, KEPT APART FROM FORWARD OBSERVATIONS:

* The signal is a labelled control (``synthetic-control:`` id, ``synthetic_control``
  flag). It is not a news signal and never enters the production journal,
  evidence file or any research ledger.
* Halt/SSR eligibility and the borrow rate are synthetic controls too (the
  borrow quantity is still capped by the real paper shortable tick).
* Quotes, WhatIf margin, orders, fills, cancels and reconnects are REAL paper
  broker behaviour. That is what this test exists to prove.
* The journal must be a NEW file named ``*.integration.sqlite``.

Paper acceptance does not prove live borrow, capacity or fees.

Steps, each recorded pass/fail with evidence:
 1. stale_quote_rejected      a real quote aged past the limit is refused
 2. margin_rejection          an entry that would breach the reserve is refused
                              after a real WhatIf (separate journal)
 3. entry_fill                bounded marketable SELL; fills (partials counted)
 4. duplicate_prevented       the same control signal cannot enter twice
 5. reconnect_recovery        disconnect, reconnect, reconcile: no duplicate
                              fills, positions still proven
 6. cancel_confirmed          a non-marketable 1-share order expires (TTL),
                              cancellation is requested and broker-confirmed
 7. kill_flatten             kill latch -> scoped cover -> flat; alerts recorded
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import uuid

from .engine import TERMINAL, Executor
from .journal import Journal
from .safety import SafetyError

SCHEMA = "rs_paper_integration.v1"


class SyntheticEvidence:
    """Real paper broker, with labelled synthetic halt/SSR and borrow-rate inputs."""

    def __init__(self, broker, apr=0.05):
        self.inner, self.apr = broker, apr

    def __getattr__(self, name):
        return getattr(self.inner, name)

    async def eligibility(self, conid):
        return {"conid": conid, "at": self.inner.now(), "complete": True,
                "source_verified": True, "halted": False, "ssr": False,
                "synthetic_control": True}

    async def exit_eligibility(self, conid):
        return await self.eligibility(conid)

    async def borrow(self, conid):
        await self.inner.quote(conid)
        shortable = int(getattr(self.inner.tickers.get(conid), "shortableShares", 0) or 0)
        return {"conid": conid, "at": self.inner.now(), "apr": self.apr,
                "available_shares": shortable, "synthetic_control": True,
                "paper_only_not_live_allocation": True}


def control_signal(symbol, conid, now, *, cik="999999999"):
    at = datetime.fromisoformat(now.replace("Z", "+00:00")).astimezone(timezone.utc)
    period = (at - timedelta(days=60)).date().isoformat()
    action = (at + timedelta(days=14)).date().isoformat()
    return {
        "id": "synthetic-control:" + uuid.uuid4().hex, "synthetic_control": True,
        "action_id": "synthetic-control:" + cik, "cik": cik, "ticker": symbol,
        "expected_conid": conid, "status": "scheduled", "ratio": 10,
        "action_day": action, "instrument_type": "CS", "currency": "USD",
        "identity_verified": True, "conditions_resolved": True,
        "source_sha256": "0" * 64, "published_at": now, "first_seen_at": now,
        "identity_known_at": now, "terms_known_at": now, "financial_known_at": now,
        "history_known_at": now, "ordinal_min": 2, "score": 50, "signal_count": 3,
        "period": period,
    }


async def run_integration(endpoint, policy, broker, journal_path, *, symbol, conid,
                          timeout=60, sleep=asyncio.sleep, reconnect=True):
    if endpoint.live:
        raise SafetyError("integration test is paper only")
    journal_path = Path(journal_path)
    if not journal_path.name.endswith(".integration.sqlite") or journal_path.exists():
        raise SafetyError("integration journal must be a NEW *.integration.sqlite file")
    steps = {}
    report = {"schema": SCHEMA, "synthetic_control": True, "paper_only": True,
              "symbol": symbol, "conid": conid, "steps": steps}

    def record(name, ok, **detail):
        steps[name] = {"pass": bool(ok), **detail}

    broker = SyntheticEvidence(broker)
    journal = Journal(journal_path, policy.digest)
    killed = {"on": False}
    executor = Executor(endpoint, policy, journal, broker, kill_switch=lambda: killed["on"])

    async def until(predicate):
        for _ in range(int(timeout)):
            await executor.tick([], broker.now())
            if predicate():
                return True
            await sleep(1)
        return False

    def orders(side=None):
        return [o for o in journal.rows("orders") if side is None or o["side"] == side]

    try:
        await broker.qualify({"ticker": symbol, "expected_conid": conid})
        # 1. stale quote
        q = await broker.quote(conid)
        old = (datetime.fromisoformat(broker.now()) - timedelta(seconds=10)).isoformat()
        try:
            executor.quote({**q, **{k: old for k in ("bid_at", "ask_at", "bid_size_at",
                                                     "ask_size_at")}}, broker.now(), conid)
            record("stale_quote_rejected", False, reason="aged quote accepted")
        except SafetyError as exc:
            record("stale_quote_rejected", True, reason=str(exc))

        # 2. margin rejection: same broker, a reserve larger than the account.
        snap = await executor.reconcile(broker.now())
        tight = type(policy)(**{**policy.__dict__, "spx_reserve": snap["available_funds"] * 10})
        side_journal = Journal(journal_path.with_name(journal_path.stem + ".margin.sqlite"),
                               tight.digest)
        try:
            probe = Executor(endpoint, tight, side_journal, broker)
            try:
                await probe.enter(control_signal(symbol, conid, broker.now(), cik="999999998"),
                                  snap, broker.now())
                record("margin_rejection", False, reason="entry was not refused")
            except SafetyError as exc:
                record("margin_rejection", "headroom" in str(exc), reason=str(exc),
                       orders_sent=len(side_journal.rows("orders")))
        finally:
            side_journal.close()

        # 3. entry and fill
        sig = control_signal(symbol, conid, broker.now())
        ref = await executor.enter(sig, await executor.reconcile(broker.now()), broker.now())
        filled = await until(lambda: any(o["state"] == "filled" for o in orders("SELL")))
        fills = [f for f in journal.rows("fills") if f["ref"] == ref]
        pos = sum(p["shares"] for p in journal.rows("positions"))
        record("entry_fill", filled and pos > 0, ref=ref, fills=len(fills),
               partial_fills=max(0, len(fills) - 1), shares=pos,
               state=[o["state"] for o in orders("SELL")])

        # 4. duplicate prevention
        try:
            await executor.enter(dict(sig, id="synthetic-control:" + uuid.uuid4().hex),
                                 await executor.reconcile(broker.now()), broker.now())
            record("duplicate_prevented", False, reason="second entry accepted")
        except SafetyError as exc:
            record("duplicate_prevented", True, reason=str(exc))

        # 5. reconnect recovery
        if reconnect:
            before = len(journal.rows("fills"))
            broker.ib.disconnect()
            await broker.connect()
            await broker.qualify({"ticker": symbol, "expected_conid": conid})
            snap = await executor.reconcile(broker.now())
            record("reconnect_recovery", len(journal.rows("fills")) == before
                   and snap["positions"].get(conid, 0) == -pos,
                   fills_before=before, fills_after=len(journal.rows("fills")),
                   broker_position=snap["positions"].get(conid, 0))

        # 6. cancel confirmation: 1 share far from the market, left to expire.
        q = await broker.quote(conid)
        far = round(float(q["ask"]) * 1.5, 2)
        cancel_sig = control_signal(symbol, conid, broker.now(), cik="999999997")
        cancel_sig["conid"], cancel_sig["planned_exit_at"] = conid, broker.now()
        cref = await executor.submit(cancel_sig, "SELL", 1, far, broker.now())
        await sleep(policy.entry_order_ttl_seconds + 1)
        done = await until(lambda: any(o["ref"] == cref and o["state"] == "cancelled"
                                       for o in orders()))
        record("cancel_confirmed", done, ref=cref, limit=far,
               cancel_requested=journal.get("cancel_requested:" + cref) is not None)

        # 7. kill -> scoped flatten
        killed["on"] = True
        flat = await until(lambda: not any(p["shares"] for p in journal.rows("positions"))
                           and all(o["state"] in TERMINAL for o in orders()))
        kinds = {e["kind"] for e in journal.rows("events")}
        record("kill_flatten", flat and "cover_trigger" in kinds, alerts=sorted(kinds))
    finally:
        journal.close()
    report["pass"] = bool(steps) and all(s["pass"] for s in steps.values())
    report["journal"] = str(journal_path)
    return report


def reference_price(quote, ticker, operator_price=None):
    """A price to work orders around when the paper session has no live quotes.

    Delayed bid/ask mid first, then delayed last/close, then the operator's
    ``--reference-price``. Mechanics mode only: never an entry decision input."""
    import math

    def ok(x):
        try:
            return x is not None and math.isfinite(float(x)) and float(x) > 0
        except (TypeError, ValueError):
            return False

    bid, ask = quote.get("bid"), quote.get("ask")
    if ok(bid) and ok(ask) and float(ask) >= float(bid):
        return (float(bid) + float(ask)) / 2, "delayed_mid"
    for name in ("last", "close"):
        value = getattr(ticker, name, None)
        if ok(value):
            return float(value), "delayed_" + name
    if ok(operator_price):
        return float(operator_price), "operator"
    raise SafetyError("no delayed quote and no --reference-price: cannot price mechanics orders")


async def run_mechanics(endpoint, policy, broker, journal_path, *, symbol, conid,
                        shares=10, reference=None, timeout=60, sleep=asyncio.sleep,
                        reconnect=True):
    """Order mechanics on a paper session WITHOUT live quotes (route A, step P).

    With no separate paper host and no second IBKR username, a paper session
    off NY4 gets delayed data or none, so the engine correctly refuses to
    enter or to protect. This mode therefore drives the real adapter and the
    real journal directly, and proves on IBKR's simulated paper market:

     1. delayed_quote_refused   the engine refuses a non-live quote
     2. whatif_preview          a real exact-stock WhatIf returns finite fields
     3. entry_fill              a bounded SELL priced through the market fills
                                (partials counted), imported by execution ID
     4. duplicate_prevented     the journal refuses a second entry for it
     5. reconnect_recovery      disconnect, reconnect, reconcile: no duplicates
     6. cancel_confirmed        a resting 1-share order expires (TTL) and the
                                cancellation is broker-confirmed
     7. scoped_cover            a BUY priced through the market flattens it
     8. kill_latch_holds        a set kill latch refuses resume_entries

    Entry decisions, live-quote protection, stops and margin refusal are NOT
    proven here: live shadow (stage S) and the unit tests cover those.
    """
    if endpoint.live:
        raise SafetyError("mechanics test is paper only")
    if not 1 <= int(shares) <= 100:
        raise SafetyError("mechanics size must be 1-100 shares")
    journal_path = Path(journal_path)
    if not journal_path.name.endswith(".integration.sqlite") or journal_path.exists():
        raise SafetyError("integration journal must be a NEW *.integration.sqlite file")
    steps = {}
    report = {"schema": SCHEMA, "mode": "mechanics_only", "synthetic_control": True,
              "paper_only": True, "symbol": symbol, "conid": conid, "steps": steps,
              "not_proven_here": ["entry decision gates on live quotes",
                                  "live-quote protection and stops",
                                  "margin refusal inside enter()"]}

    def record(name, ok, **detail):
        steps[name] = {"pass": bool(ok), **detail}

    journal = Journal(journal_path, policy.digest)
    executor = Executor(endpoint, policy, journal, broker)

    def orders(side=None):
        return [o for o in journal.rows("orders") if side is None or o["side"] == side]

    async def until(predicate):
        # Reconcile and TTL expiry only: protect() would (correctly) halt on
        # a position it cannot quote live.
        for _ in range(int(timeout)):
            snap = await executor.reconcile(broker.now())
            await executor.expire_orders(snap, broker.now())
            if predicate():
                return True
            await sleep(1)
        return False

    def tick_round(price):
        return round(price, 2)

    try:
        if getattr(broker, "ib", None) is not None and hasattr(broker.ib, "reqMarketDataType"):
            broker.ib.reqMarketDataType(3)  # delayed where available
        await broker.qualify({"ticker": symbol, "expected_conid": conid})
        q = await broker.quote(conid)
        ref, source = reference_price(q, broker.tickers.get(conid), reference)
        if ref < 1:
            raise SafetyError("mechanics test needs a stock priced at $1 or more")
        report["reference"] = {"price": ref, "source": source,
                               "market_data_type": q.get("market_data_type")}

        try:
            executor.quote(q, broker.now(), conid)
            record("delayed_quote_refused", q.get("market_data_type") == 1,
                   reason="quote accepted (live data present: full mode is available)")
        except SafetyError as exc:
            record("delayed_quote_refused", True, reason=str(exc))

        preview = await broker.margin(conid, int(shares), tick_round(ref))
        fields = ("initial_change", "maintenance_change", "initial_after", "maintenance_after")
        try:
            values = {k: float(preview.get(k)) for k in fields}
            finite = all(abs(v) < 1e100 for v in values.values())
        except (TypeError, ValueError):
            values, finite = {}, False
        record("whatif_preview", finite and not preview.get("warning"), **values,
               warning=preview.get("warning"))

        sig = control_signal(symbol, conid, broker.now())
        sig["conid"] = conid
        sig["planned_exit_at"] = broker.now()
        sell = tick_round(ref * 0.97)
        ref_entry = await executor.submit(sig, "SELL", int(shares), sell, broker.now())
        filled = await until(lambda: any(o["ref"] == ref_entry and o["state"] == "filled"
                                         for o in orders()))
        fills = [f for f in journal.rows("fills") if f["ref"] == ref_entry]
        held = sum(p["shares"] for p in journal.rows("positions"))
        record("entry_fill", filled and held == int(shares), ref=ref_entry, limit=sell,
               fills=len(fills), partial_fills=max(0, len(fills) - 1), shares=held)

        try:
            await executor.submit(sig, "SELL", int(shares), sell, broker.now())
            record("duplicate_prevented", False, reason="second entry accepted")
        except SafetyError as exc:
            record("duplicate_prevented", True, reason=str(exc))

        if reconnect:
            before = len(journal.rows("fills"))
            broker.ib.disconnect()
            await broker.connect()
            if hasattr(broker.ib, "reqMarketDataType"):
                broker.ib.reqMarketDataType(3)
            await broker.qualify({"ticker": symbol, "expected_conid": conid})
            snap = await executor.reconcile(broker.now())
            record("reconnect_recovery", len(journal.rows("fills")) == before
                   and snap["positions"].get(conid, 0) == -held,
                   fills_before=before, fills_after=len(journal.rows("fills")),
                   broker_position=snap["positions"].get(conid, 0))

        far = tick_round(ref * 1.5)
        cancel_sig = control_signal(symbol, conid, broker.now(), cik="999999997")
        cancel_sig["conid"], cancel_sig["planned_exit_at"] = conid, broker.now()
        cref = await executor.submit(cancel_sig, "SELL", 1, far, broker.now())
        await sleep(policy.entry_order_ttl_seconds + 1)
        done = await until(lambda: any(o["ref"] == cref and o["state"] == "cancelled"
                                       for o in orders()))
        record("cancel_confirmed", done, ref=cref, limit=far,
               cancel_requested=journal.get("cancel_requested:" + cref) is not None)

        buy = tick_round(ref * 1.03)
        cover = await executor.submit(sig, "BUY", held, buy, broker.now()) if held else None
        flat = await until(lambda: not any(p["shares"] for p in journal.rows("positions"))
                           and all(o["state"] in TERMINAL for o in orders()))
        snap = await executor.reconcile(broker.now())
        record("scoped_cover", flat and snap["positions"].get(conid, 0) == 0,
               ref=cover, limit=buy, broker_position=snap["positions"].get(conid, 0))

        journal.set("kill", True)
        try:
            await executor.resume_entries(broker.now())
            record("kill_latch_holds", False, reason="resume accepted after kill")
        except SafetyError as exc:
            record("kill_latch_holds", True, reason=str(exc))
    finally:
        journal.close()
    report["pass"] = bool(steps) and all(s["pass"] for s in steps.values())
    report["journal"] = str(journal_path)
    return report


def dumps(report):
    return json.dumps(report, indent=1, sort_keys=True)
