"""RS paper state machine: proposals are inputs, never order authority."""

from __future__ import annotations

from datetime import timedelta
import json
import math
from zoneinfo import ZoneInfo

from .policy import Calendar
from .safety import SafetyError, fresh, integer, number, owned_order, timestamp

TERMINAL = {"filled", "cancelled", "rejected"}


class Executor:
    def __init__(
        self,
        endpoint,
        policy,
        journal,
        broker,
        calendar=None,
        kill_switch=lambda: False,
    ):
        self.endpoint = endpoint.validate()
        self.policy = policy.validate()
        self.journal, self.broker = journal, broker
        self.calendar = calendar or Calendar()
        self.kill_switch = kill_switch
        identity = {
            "account": endpoint.account,
            "client_id": endpoint.client_id,
            "port": endpoint.port,
        }
        if journal.get("endpoint", identity) != identity:
            raise SafetyError("journal belongs to another paper endpoint")
        journal.set("endpoint", identity)

    def alert(self, now, kind, detail):
        self.journal.event(now, kind, detail)

    def halt(self, now, reason):
        if self.journal.get("entry_halt") != reason:
            self.journal.set("entry_halt", reason)
            self.alert(now, "entry_halt", {"reason": reason})

    def killed(self):
        if self.kill_switch():
            self.journal.set("kill", True)
        return self.journal.get("kill", False)

    async def reconcile(self, now):
        snap = await self.broker.snapshot()
        if (
            snap.get("account") != self.endpoint.account
            or snap.get("complete") is not True
        ):
            raise SafetyError("incomplete/wrong-account broker snapshot")
        fresh(snap.get("at"), now, self.policy.evidence_age_seconds)
        known = {o["ref"]: o for o in self.journal.rows("orders")}
        for fill in snap.get("executions", []):
            if not owned_order(fill, self.endpoint, known):
                continue
            row = known[fill["ref"]]
            if fill.get("conid") != row["conid"] or fill.get("side") != row["side"]:
                raise SafetyError("execution contract/side mismatch")
            if row["order_id"] and fill.get("order_id") != row["order_id"]:
                raise SafetyError("execution broker order identity conflict")
            fresh(fill.get("at"), now, 366 * 86400)
            self.journal.fill(
                fill["ref"],
                str(fill["exec_id"]),
                integer(fill["shares"], minimum=1),
                number(fill["price"], minimum=0.000001),
                fill["at"],
                number(fill["commission"], minimum=0),
            )
        for row in snap.get("orders", []):
            if not owned_order(row, self.endpoint, known):
                continue
            local = self.journal.db.execute(
                "SELECT *FROM orders WHERE ref=?", (row["ref"],)
            ).fetchone()
            if row.get("conid") != local["conid"] or row.get("side") != local["side"]:
                raise SafetyError("order identity conflict")
            if local["order_id"] and row.get("order_id") != local["order_id"]:
                raise SafetyError(
                    "duplicate broker orders share an operation reference"
                )
            if integer(row["shares"], minimum=1) != local["shares"]:
                raise SafetyError("broker/local order quantity conflict")
            if integer(row.get("filled", 0)) != local["filled"]:
                raise SafetyError("broker fill quantity not reconciled to executions")
            state = row["state"]
            if state not in TERMINAL | {"working"}:
                state = "uncertain"
            with self.journal.db:
                self.journal.db.execute(
                    "UPDATE orders SET state=?,order_id=?,perm_id=?WHERE ref=?",
                    (state, row["order_id"], row.get("perm_id", 0), row["ref"]),
                )
        # Absence from an open-orders response does not prove rejection or no fill.
        if any(
            o["state"] not in TERMINAL
            and not any(r.get("ref") == o["ref"] for r in snap.get("orders", []))
            for o in self.journal.rows("orders")
        ):
            raise SafetyError("previous order outcome remains uncertain")
        expected = {}
        for pos in self.journal.rows("positions"):
            if pos["shares"]:
                expected[pos["conid"]] = expected.get(pos["conid"], 0) - pos["shares"]
        for conid, qty in expected.items():
            if snap.get("positions", {}).get(conid, 0) != qty:
                raise SafetyError(
                    "paper position mismatch; automatic entries/covers suspended"
                )
        return snap

    def validate_signal(self, signal, now):
        p = self.policy
        if not self.calendar.session(now):
            raise SafetyError("outside regular trading session")
        for field in (
            "id",
            "action_id",
            "cik",
            "ticker",
            "source_sha256",
            "published_at",
            "first_seen_at",
        ):
            if not signal.get(field):
                raise SafetyError("signal field missing: " + field)
        import re

        if not re.fullmatch(r"[a-f0-9]{64}", signal["source_sha256"]):
            raise SafetyError("primary source hash required")
        if not re.fullmatch(r"[A-Z][A-Z0-9.]{0,11}", signal["ticker"]):
            raise SafetyError("invalid common-share symbol")
        if integer(signal["cik"], "CIK", minimum=1) <= 0:
            raise SafetyError("invalid CIK")
        if signal.get("status") != "scheduled" or signal.get("instrument_type") != "CS":
            raise SafetyError("selected common-share split required")
        if (
            signal.get("currency") != "USD"
            or signal.get("identity_verified") is not True
        ):
            raise SafetyError("verified USD common-share identity required")
        if signal.get("conditions_resolved") is not True:
            raise SafetyError("implementation conditions unresolved")
        integer(signal.get("ordinal_min"), "split ordinal", minimum=2)
        number(signal.get("ratio"), "split ratio", minimum=1.000001)
        score = number(signal.get("score"), "financial score", minimum=0)
        if score > 100:
            raise SafetyError("invalid financial score")
        integer(signal.get("signal_count"), "supported factors", minimum=3)
        period = timestamp(signal["period"] + "T00:00:00Z")
        age = (timestamp(now) - period).total_seconds() / 86400
        if not 0 <= age <= p.max_financial_age_days:
            raise SafetyError("financial period stale or future")
        fresh(signal["published_at"], now, p.entry_window_seconds)
        fresh(signal["first_seen_at"], now, p.entry_window_seconds)
        for field in (
            "identity_known_at",
            "financial_known_at",
            "terms_known_at",
            "history_known_at",
        ):
            if timestamp(signal[field]) > timestamp(now):
                raise SafetyError("future knowledge cannot authorize entry")
        if timestamp(signal["first_seen_at"]) < timestamp(
            signal["published_at"]
        ) - timedelta(seconds=2):
            raise SafetyError("receipt precedes publication")
        effective = signal.get("action_day")
        if (
            not effective
            or effective
            <= timestamp(now)
            .astimezone(ZoneInfo("America/New_York"))
            .date()
            .isoformat()
        ):
            raise SafetyError("research must precede split action day")
        for previous in self.journal.rows("signals"):
            if previous["issuer"] != signal["cik"]:
                continue
            old = json.loads(previous["payload"])
            same_terms = (
                old.get("ratio") == signal["ratio"]
                and old.get("action_day") == effective
            )
            same_day = (
                timestamp(old["first_seen_at"])
                .astimezone(ZoneInfo("America/New_York"))
                .date()
                == timestamp(signal["first_seen_at"])
                .astimezone(ZoneInfo("America/New_York"))
                .date()
            )
            if old.get("action_id") == signal["action_id"] or same_terms or same_day:
                raise SafetyError("issuer/action already attempted")

    def quote(self, q, now, conid):
        if (
            q.get("conid") != conid
            or q.get("market_data_type") != 1
            or q.get("size_units") != "shares"
        ):
            raise SafetyError("live identified share-size quote required")
        for field in ("bid_at", "ask_at", "bid_size_at", "ask_size_at"):
            fresh(q.get(field), now, self.policy.quote_age_seconds)
        bid, ask = (
            number(q.get("bid"), minimum=0.000001),
            number(q.get("ask"), minimum=0.000001),
        )
        if ask < bid:
            raise SafetyError("crossed quote")
        integer(q.get("bid_size"), minimum=1)
        integer(q.get("ask_size"), minimum=1)
        return bid, ask

    def eligibility(self, proof, now, conid, *, require_ssr_clear=True):
        if proof.get("conid") != conid:
            raise SafetyError("eligibility contract mismatch")
        if (
            proof.get("complete") is not True
            or proof.get("source_verified") is not True
        ):
            raise SafetyError("fresh eligibility source required")
        fresh(proof.get("at"), now, self.policy.evidence_age_seconds)
        if (
            proof.get("halted") is not False
            or require_ssr_clear
            and proof.get("ssr") is not False
        ):
            raise SafetyError("halt/SSR unknown or restricted")

    async def submit(self, signal, side, shares, price, now):
        count = sum(
            timestamp(json.loads(o["payload"])["at"])
            .astimezone(ZoneInfo("America/New_York"))
            .date()
            == timestamp(now).astimezone(ZoneInfo("America/New_York")).date()
            for o in self.journal.rows("orders")
        )
        if side == "SELL" and count >= self.policy.max_orders_per_session:
            raise SafetyError("session order budget exhausted")
        if (
            side == "BUY"
            and sum(
                x["side"] == "BUY" and x["signal_id"] == signal["id"]
                for x in self.journal.rows("orders")
            )
            >= self.policy.max_cover_attempts
        ):
            raise SafetyError(
                "bounded cover retries exhausted; operator action required"
            )
        ref = self.journal.intent(signal, side, shares, price, now)
        try:
            ack = await self.broker.submit(
                {
                    "ref": ref,
                    "conid": signal["conid"],
                    "ticker": signal["ticker"],
                    "side": side,
                    "shares": shares,
                    "limit": price,
                    "account": self.endpoint.account,
                }
            )
            self.journal.acknowledge(
                ref, integer(ack["order_id"], minimum=1), integer(ack.get("perm_id", 0))
            )
        except Exception:
            self.journal.uncertain(ref, now)
            self.halt(now, "submission_uncertain")
            raise
        self.alert(
            now, "paper_order_submitted", {"ref": ref, "side": side, "shares": shares}
        )
        return ref

    async def cancel_entries(self, now):
        refs = {x["ref"] for x in self.journal.rows("orders")}
        snap = await self.broker.snapshot()
        for row in snap.get("orders", []):
            if (
                row.get("side") == "SELL"
                and row.get("state") == "working"
                and owned_order(row, self.endpoint, refs)
            ):
                await self.request_cancel(row, now)

    async def request_cancel(self, row, now):
        key = "cancel_requested:" + row["ref"]
        previous = self.journal.get(key)
        if previous:
            if (timestamp(now) - timestamp(previous)).total_seconds() > 30:
                self.halt(now, "cancellation_unconfirmed")
            return
        # Persist BEFORE requesting cancellation; repeated ticks cannot storm it.
        self.journal.set(key, now)
        await self.broker.cancel(row)
        self.alert(now, "order_cancel_requested", {"ref": row["ref"]})

    async def expire_orders(self, snap, now):
        refs = {o["ref"]: o for o in self.journal.rows("orders")}
        for row in snap.get("orders", []):
            if row.get("state") != "working" or not owned_order(
                row, self.endpoint, refs
            ):
                continue
            order = refs[row["ref"]]
            created = timestamp(json.loads(order["payload"])["at"])
            ttl = (
                self.policy.entry_order_ttl_seconds
                if order["side"] == "SELL"
                else self.policy.cover_order_ttl_seconds
            )
            if timestamp(now) - created >= timedelta(seconds=ttl):
                await self.request_cancel(row, now)

    async def protect(self, snap, now):
        positions = [x for x in self.journal.rows("positions") if x["shares"]]
        cash = sum(
            (1 if o["side"] == "SELL" else -1) * f["shares"] * f["price"]
            - f["commission"]
            for f in self.journal.rows("fills")
            for o in self.journal.rows("orders")
            if o["ref"] == f["ref"]
        )
        details, mark_value, marks_complete = [], 0, True
        for pos in positions:
            signal = json.loads(pos["payload"])
            try:
                await self.broker.qualify(signal)
                q = await self.broker.quote(pos["conid"])
                _, ask = self.quote(q, now, pos["conid"])
                proof = await self.broker.eligibility(pos["conid"])
                self.eligibility(proof, now, pos["conid"], require_ssr_clear=False)
            except (SafetyError, KeyError) as exc:
                marks_complete = False
                self.halt(now, "position_not_currently_protectable:" + str(exc))
                continue  # a halted name must not prevent other names' exits
            mark_value += pos["shares"] * ask
            key = "borrow_bound:" + signal["id"]
            bound = self.journal.get(
                key, {"price": pos["entry_price"], "apr": signal["entry_borrow_apr"]}
            )
            bound["price"] = max(bound["price"], ask)
            reason = ""
            if timestamp(now) >= timestamp(pos["exit_at"]):
                reason = "time_exit"
            if ask >= pos["entry_price"] * (1 + self.policy.stop_fraction):
                reason = "stop_trigger"
            if proof.get("recall") is True:
                reason = "borrow_recall"
            try:
                loan = await self.broker.borrow(pos["conid"])
                fresh(loan.get("at"), now, self.policy.borrow_age_seconds)
                current_apr = number(loan.get("apr"), minimum=0)
                bound["apr"] = max(bound["apr"], current_apr)
                if current_apr > self.policy.max_borrow_apr:
                    reason = "borrow_rate_exit"
            except (SafetyError, KeyError):
                bound["apr"] = max(bound["apr"], self.policy.max_borrow_apr)
                self.halt(now, "current_borrow_rate_unknown")
            self.journal.set(key, bound)
            if self.killed():
                reason = "operator_flatten"
            details.append((pos, signal, ask, reason))
        # Upper-bound paper cost estimate, retained after a cover. It is not a
        # settled loan ledger, a broker rate guarantee or an actual charged fee.
        borrow_reserve = 0
        orders = {o["ref"]: o for o in self.journal.rows("orders")}
        fills = self.journal.rows("fills")
        for pos in self.journal.rows("positions"):
            signal = json.loads(pos["payload"])
            related = [
                f for f in fills if orders[f["ref"]]["signal_id"] == signal["id"]
            ]
            sold = sum(
                f["shares"] for f in related if orders[f["ref"]]["side"] == "SELL"
            )
            end = now if pos["shares"] else max(f["at"] for f in related)
            days = max(
                1, (timestamp(end).date() - timestamp(pos["entry_at"]).date()).days + 1
            )
            bound = self.journal.get(
                "borrow_bound:" + signal["id"],
                {"price": pos["entry_price"], "apr": signal["entry_borrow_apr"]},
            )
            price = max(bound["price"], *(f["price"] for f in related))
            borrow_reserve += sold * math.ceil(1.02 * price) * bound["apr"] * days / 360
        pnl = cash - mark_value - borrow_reserve
        day = timestamp(now).astimezone(ZoneInfo("America/New_York")).date().isoformat()
        if marks_complete and self.journal.get("risk_day") != day:
            self.journal.set("risk_day", day)
            self.journal.set("day_start_pnl", self.journal.get("last_pnl", 0))
        loss = self.journal.get("day_start_pnl", 0) - pnl
        if marks_complete:
            self.journal.set("last_pnl", pnl)
        if marks_complete and loss >= self.policy.daily_loss_limit:
            self.halt(now, "daily_loss_limit")
            details = [
                (pos, signal, ask, "daily_loss_limit")
                for pos, signal, ask, _ in details
            ]
        for pos, signal, ask, reason in details:
            if not reason:
                continue
            # An entry cancellation is not a cancellation confirmation.
            if any(
                x["conid"] == pos["conid"] and x["state"] not in TERMINAL
                for x in self.journal.rows("orders")
            ):
                await self.cancel_entries(now)
                continue
            if snap.get("positions", {}).get(pos["conid"], 0) != -pos["shares"]:
                raise SafetyError("cover position proof failed")
            self.alert(
                now, "cover_trigger", {"signal_id": signal["id"], "reason": reason}
            )
            # A marketable LIMIT protects against an unbounded market submission.
            await self.submit(signal, "BUY", pos["shares"], ask, now)

    async def enter(self, proposal, snap, now):
        if (
            snap.get("account") != self.endpoint.account
            or snap.get("complete") is not True
        ):
            raise SafetyError("fresh pinned account proof required")
        fresh(snap.get("at"), now, self.policy.evidence_age_seconds)
        if self.journal.get("entry_halt") or self.killed():
            raise SafetyError("entries halted")
        if any(
            o["state"] in ("submitting", "uncertain")
            for o in self.journal.rows("orders")
        ):
            raise SafetyError("unresolved submission blocks entries")
        signal = dict(proposal)
        self.validate_signal(signal, now)
        contract = await self.broker.qualify(signal)
        if (
            contract.get("ticker"),
            contract.get("sec_type"),
            contract.get("currency"),
        ) != (signal["ticker"], "STK", "USD"):
            raise SafetyError("qualified instrument mismatch")
        signal["conid"] = integer(contract.get("conid"), minimum=1)
        if signal["conid"] != integer(signal.get("expected_conid"), minimum=1):
            raise SafetyError("proposal/IB contract identity mismatch")
        if snap.get("positions", {}).get(signal["conid"], 0):
            raise SafetyError("existing broker stock position is not a new RS entry")
        proof = await self.broker.eligibility(signal["conid"])
        self.eligibility(proof, now, signal["conid"])
        borrow = await self.broker.borrow(signal["conid"])
        if borrow.get("conid") != signal["conid"]:
            raise SafetyError("borrow contract mismatch")
        fresh(borrow.get("at"), now, self.policy.borrow_age_seconds)
        apr = number(borrow.get("apr"), "borrow APR", minimum=0)
        if apr > self.policy.max_borrow_apr:
            raise SafetyError("borrow APR exceeds policy")
        quote = await self.broker.quote(signal["conid"])
        bid, ask = self.quote(quote, now, signal["conid"])
        if 10000 * (ask - bid) / ((ask + bid) / 2) > self.policy.max_spread_bps:
            raise SafetyError("spread exceeds policy")
        p = self.policy
        nav = number(snap.get("nav"), "NAV", minimum=1)
        active = [x for x in self.journal.rows("positions") if x["shares"]]
        pending = [
            x
            for x in self.journal.rows("orders")
            if x["side"] == "SELL" and x["state"] not in TERMINAL
        ]
        if any(x["issuer"] == signal["cik"] for x in active + pending):
            raise SafetyError("issuer already open or reserved")
        names = {x["issuer"] for x in active + pending}
        if len(names) >= p.max_names:
            raise SafetyError("name count limit")
        gross = 0
        for position in active:
            book = await self.broker.quote(position["conid"])
            _, marked_ask = self.quote(book, now, position["conid"])
            gross += position["shares"] * max(position["entry_price"], marked_ask)
        reserved = sum((x["shares"] - x["filled"]) * x["limit_price"] for x in pending)
        remaining = (
            min(p.max_gross_notional, nav * p.nav_gross_fraction) - gross - reserved
        )
        notional = min(
            p.target_notional, p.max_name_notional, nav * p.nav_name_fraction, remaining
        )
        shares = min(
            math.floor(notional / bid),
            math.floor(quote["bid_size"] * p.depth_fraction),
            integer(borrow.get("available_shares"), minimum=0),
            p.max_shares_per_order,
        )
        if shares < 1:
            raise SafetyError("no supported capacity")
        # This is a broker preview for the exact proposed stock short, not an
        # options multiplier or a guessed percentage of stock notional.
        margin = await self.broker.margin(signal["conid"], shares, bid)
        fresh(margin.get("at"), now, p.evidence_age_seconds)
        if (
            margin.get("account") != self.endpoint.account
            or margin.get("what_if") is not True
            or margin.get("warning")
        ):
            raise SafetyError("margin preview not verified")
        initial = max(0, number(margin.get("initial_change"), "initial margin"))
        maintenance = max(
            0, number(margin.get("maintenance_change"), "maintenance margin")
        )
        number(margin.get("initial_after"), "post-trade initial margin", minimum=0)
        number(
            margin.get("maintenance_after"), "post-trade maintenance margin", minimum=0
        )
        # Pending orders reserve the full notional plus the larger preview margin.
        # Conservative stock squeeze loss is separate from broker margin.
        pending_margin = sum(
            number(json.loads(x["payload"])["signal"].get("margin_reserve"), minimum=0)
            for x in pending
        )
        protected = p.spx_reserve + p.cash_buffer
        after_initial = (
            number(snap.get("available_funds"), minimum=0) - initial - pending_margin
        )
        stressed = (
            number(snap.get("excess_liquidity"), minimum=0)
            - p.margin_stress_multiple * maintenance
            - pending_margin
            - (p.margin_stress_multiple - 1)
            * sum(
                number(
                    json.loads(x["payload"]).get("entry_maintenance_margin"), minimum=0
                )
                for x in active
            )
            - p.squeeze_loss_multiple * (gross + reserved + shares * ask)
        )
        if min(after_initial, stressed) < protected:
            raise SafetyError("SPX reserve/stressed margin headroom insufficient")
        signal["margin_reserve"] = max(initial, maintenance) + shares * ask
        signal["entry_maintenance_margin"] = maintenance
        signal["entry_evidence"] = {
            "quote": quote,
            "borrow": borrow,
            "eligibility": proof,
            "margin": margin,
            "account": {
                k: snap[k]
                for k in ("account", "at", "nav", "available_funds", "excess_liquidity")
            },
        }
        signal["entry_borrow_apr"] = apr
        signal["planned_exit_at"] = self.calendar.exit_at(now, p.hold_sessions)
        if p.pre_action_exit:
            signal["planned_exit_at"] = min(
                signal["planned_exit_at"],
                self.calendar.before_action(signal["action_day"]),
            )
        if timestamp(signal["planned_exit_at"]) <= timestamp(now):
            raise SafetyError("pre-action exit already due")
        # Expiry is rechecked after all asynchronous data/margin work.
        current = self.broker.now()
        fresh(signal["published_at"], current, p.entry_window_seconds)
        fresh(margin["at"], current, p.evidence_age_seconds)
        fresh(snap["at"], current, p.evidence_age_seconds)
        fresh(borrow["at"], current, p.borrow_age_seconds)
        self.eligibility(proof, current, signal["conid"])
        self.quote(quote, current, signal["conid"])
        if self.killed() or self.journal.get("entry_halt"):
            raise SafetyError("entry stopped during pretrade checks")
        return await self.submit(signal, "SELL", shares, bid, current)

    async def tick(self, proposals, now):
        try:
            snap = await self.reconcile(now)
            await self.expire_orders(snap, now)
            await self.protect(snap, now)
        except Exception as exc:
            self.halt(now, type(exc).__name__ + ":" + str(exc))
            return
        if self.killed() or self.journal.get("entry_halt"):
            await self.cancel_entries(now)
            return
        for proposal in proposals:
            try:
                # Re-read broker state after each submitted proposal; pending
                # journal reservations protect against delayed acknowledgements.
                await self.enter(
                    proposal, await self.reconcile(self.broker.now()), self.broker.now()
                )
            except (SafetyError, KeyError, TypeError) as exc:
                key = "blocked:" + str(proposal.get("id"))
                if self.journal.get(key) != str(exc):
                    self.alert(
                        now,
                        "proposal_blocked",
                        {"id": proposal.get("id"), "reason": str(exc)},
                    )
                    self.journal.set(key, str(exc))
        self.journal.event(
            now, "heartbeat", {"paper_only": True, "live_orders_allowed": False}
        )
