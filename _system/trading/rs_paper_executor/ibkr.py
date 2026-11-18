"""Opt-in IBKR PAPER adapter. Never imported by Box R or the live SPX process.

Account pinning, positionMultiEnd proof and request cleanup are adapted from
SPX live/ib_connection.py. No live endpoint or production registry ID is accepted.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from .safety import SafetyError, fresh, integer, number, owned_order


def utc_now():
    return datetime.now(timezone.utc).isoformat()


async def positions_for_account(ib, account, timeout=10):
    """A completed future alone is not proof: require this request's end marker."""
    req = ib.client.getReqId()
    wrapper = ib.wrapper
    future = wrapper.startReq(req)
    rows, ended = [], False
    old_row, old_end = wrapper.positionMulti, wrapper.positionMultiEnd

    def row(request_id, acct, model, contract, position, average):
        if request_id == req and request_id in wrapper._futures:
            if acct != account:
                raise SafetyError("position returned for another account")
            rows.append(SimpleNamespace(contract=contract, position=position))

    def end(request_id):
        nonlocal ended
        if request_id == req:
            ended = request_id in wrapper._futures
            if ended:
                wrapper._endReq(request_id)

    wrapper.positionMulti, wrapper.positionMultiEnd = row, end
    try:
        ib.client.reqPositionsMulti(req, account, "")
        await asyncio.wait_for(future, timeout)
        if not ended:
            raise SafetyError("position snapshot ended without broker completion proof")
        return {
            integer(x.contract.conId, minimum=1): integer(abs(x.position))
            * (1 if x.position >= 0 else -1)
            for x in rows
        }
    finally:
        try:
            ib.client.cancelPositionsMulti(req)
        finally:
            wrapper.positionMulti, wrapper.positionMultiEnd = old_row, old_end
            wrapper._futures.pop(req, None)
            wrapper._results.pop(req, None)


async def account_values(ib, account, timeout=10):
    req = ib.client.getReqId()
    future = ib.wrapper.startReq(req)
    values = {}
    old = ib.wrapper.accountSummary

    def receive(request_id, acct, tag, value, currency):
        if request_id == req and acct == account and currency == "USD":
            values[tag] = number(value, tag, minimum=0)
        old(request_id, acct, tag, value, currency)

    ib.wrapper.accountSummary = receive
    try:
        ib.client.reqAccountSummary(
            req, "All", "NetLiquidation,AvailableFunds,ExcessLiquidity"
        )
        await asyncio.wait_for(future, timeout)
        if set(values) != {"NetLiquidation", "AvailableFunds", "ExcessLiquidity"}:
            raise SafetyError("required account values missing")
        return values
    finally:
        try:
            ib.client.cancelAccountSummary(req)
        finally:
            ib.wrapper.accountSummary = old
            ib.wrapper._futures.pop(req, None)
            ib.wrapper._results.pop(req, None)


class PaperIBKR:
    def __init__(self, endpoint, evidence, *, ib=None, clock=utc_now, max_data_lines=8):
        self.endpoint = endpoint.validate()
        self.evidence = evidence
        self.ib = ib
        self.clock = clock
        self.max_data_lines = integer(max_data_lines, minimum=1)
        if self.max_data_lines > 8:
            raise SafetyError("paper data-line budget exceeds eight")
        self.contracts, self.tickers, self.components = {}, {}, {}
        self.known_refs = set()
        self.position_cache = None
        self.listening = False

    def now(self):
        return self.clock()

    async def connect(self):
        self.endpoint.validate()  # before any socket, even a supposed paper port
        self.endpoint.runtime_guard()
        if self.ib is None:
            from ib_insync import IB

            self.ib = IB()
        if self.listening:
            self.ib.pendingTickersEvent -= self.receive_ticks
            self.listening = False
        # Handles/mappings from a previous connection are never a live book.
        self.contracts.clear()
        self.tickers.clear()
        self.components.clear()
        self.ib.MaxSyncedSubAccounts = 0
        self.ib.RaiseRequestErrors = True

        async def empty_positions():
            return []

        self.ib.reqPositionsAsync = empty_positions
        try:
            await self.ib.connectAsync(
                self.endpoint.host,
                self.endpoint.port,
                clientId=self.endpoint.client_id,
                account=self.endpoint.account,
                timeout=10,
            )
            self.prove()
            self.ib.pendingTickersEvent += self.receive_ticks
            self.listening = True
            self.ib.reqMarketDataType(1)
        except Exception:
            self.ib.disconnect()
            raise

    def prove(self):
        if self.ib is None or not self.ib.isConnected():
            raise SafetyError("paper session disconnected")
        self.endpoint.prove_session(self.ib.managedAccounts(), self.ib.client.clientId)

    def receive_ticks(self, tickers):
        names = {
            0: "bid_size_at",
            1: "bid_at",
            2: "ask_at",
            3: "ask_size_at",
            89: "shortable_at",
        }
        for ticker in tickers:
            conid = ticker.contract.conId
            clocks = self.components.setdefault(conid, {})
            for tick in ticker.ticks:
                if tick.tickType in names:
                    clocks[names[tick.tickType]] = tick.time.isoformat()

    async def qualify(self, signal):
        self.prove()
        from ib_insync import Stock

        expected = integer(signal["expected_conid"], minimum=1)
        if expected not in self.contracts:
            contracts = await asyncio.wait_for(
                self.ib.qualifyContractsAsync(
                    Stock(
                        signal["ticker"],
                        "SMART",
                        "USD",
                        primaryExchange=signal.get("primary_exchange", ""),
                    )
                ),
                10,
            )
            if len(contracts) != 1 or contracts[0].conId != expected:
                raise SafetyError("qualified stock does not match reviewed contract ID")
            c = contracts[0]
            if (
                c.secType != "STK"
                or c.currency != "USD"
                or c.symbol != signal["ticker"]
            ):
                raise SafetyError("IB contract mismatch")
            self.contracts[expected] = c
        return {
            "conid": expected,
            "ticker": signal["ticker"],
            "sec_type": "STK",
            "currency": "USD",
        }

    async def quote(self, conid):
        self.prove()
        if conid not in self.contracts:
            raise SafetyError("reviewed contract missing; qualify before subscribing")
        if conid not in self.tickers:
            if len(self.tickers) >= self.max_data_lines:
                raise SafetyError("paper quote budget exhausted")
            self.tickers[conid] = self.ib.reqMktData(
                self.contracts[conid], "236", False, False
            )
        ticker = self.tickers[conid]
        for _ in range(20):
            if {
                "bid_at",
                "ask_at",
                "bid_size_at",
                "ask_size_at",
            } <= self.components.get(conid, {}).keys():
                break
            await asyncio.sleep(0.1)
        return {
            "conid": conid,
            "bid": ticker.bid,
            "ask": ticker.ask,
            "bid_size": ticker.bidSize,
            "ask_size": ticker.askSize,
            "market_data_type": ticker.marketDataType,
            "size_units": "shares",
            **self.components.get(conid, {}),
        }

    async def borrow(self, conid):
        await self.quote(conid)
        source = dict(self.evidence()["borrow"][str(conid)])
        if source.get("conid") != conid:
            raise SafetyError("borrow evidence contract mismatch")
        fresh(self.components.get(conid, {}).get("shortable_at"), self.now(), 30)
        quantity = number(
            self.tickers[conid].shortableShares, "paper shortable shares", minimum=0
        )
        source["available_shares"] = min(
            integer(source.get("available_shares")), int(quantity)
        )
        source["paper_only_not_live_allocation"] = True
        return source

    async def eligibility(self, conid):
        row = dict(self.evidence()["eligibility"][str(conid)])
        if row.get("conid") != conid:
            raise SafetyError("eligibility evidence contract mismatch")
        ticker = self.tickers.get(conid)
        if ticker is not None and getattr(ticker, "halted", None) in (1, 2):
            row["halted"] = True
        return row

    async def exit_eligibility(self, conid):
        """A BUY cover does not require SSR clearance from the research host."""
        self.prove()
        ticker = self.tickers.get(conid)
        if (
            ticker is not None
            and ticker.marketDataType == 1
            and ticker.halted in (0, 1, 2)
        ):
            return {
                "conid": conid,
                "at": self.now(),
                "complete": True,
                "source_verified": True,
                "halted": ticker.halted != 0,
                "ssr": None,
                "source": "current_paper_broker_halt_state",
            }
        return await self.eligibility(conid)

    async def margin(self, conid, shares, price):
        self.prove()
        from ib_insync import LimitOrder

        order = LimitOrder(
            "SELL",
            shares,
            price,
            account=self.endpoint.account,
            tif="DAY",
            whatIf=True,
            outsideRth=False,
        )
        state = await asyncio.wait_for(
            self.ib.whatIfOrderAsync(self.contracts[conid], order), 10
        )
        self.prove()
        return {
            "at": self.now(),
            "account": self.endpoint.account,
            "what_if": True,
            "initial_change": state.initMarginChange,
            "maintenance_change": state.maintMarginChange,
            "initial_after": state.initMarginAfter,
            "maintenance_after": state.maintMarginAfter,
            "warning": state.warningText,
        }

    @staticmethod
    def order_row(trade):
        order, status = trade.order, trade.orderStatus
        states = {
            "Filled": "filled",
            "Cancelled": "cancelled",
            "ApiCancelled": "cancelled",
            "Inactive": "uncertain",
            "PendingSubmit": "working",
            "PreSubmitted": "working",
            "Submitted": "working",
        }
        return {
            "ref": order.orderRef,
            "account": order.account,
            "client_id": order.clientId,
            "conid": trade.contract.conId,
            "side": order.action,
            "shares": integer(order.totalQuantity),
            "filled": integer(status.filled),
            "state": states.get(status.status, "uncertain"),
            "order_id": order.orderId,
            "perm_id": status.permId or order.permId,
        }

    async def snapshot(self):
        self.prove()
        from ib_insync import ExecutionFilter

        # Snapshot requests use the one existing PAPER connection. Every
        # subscription created by a bounded request is cancelled in finally.
        positions = await positions_for_account(self.ib, self.endpoint.account)
        values = await account_values(self.ib, self.endpoint.account)
        opened = await asyncio.wait_for(self.ib.reqAllOpenOrdersAsync(), 10)
        completed = await asyncio.wait_for(self.ib.reqCompletedOrdersAsync(False), 10)
        fills = await asyncio.wait_for(
            self.ib.reqExecutionsAsync(ExecutionFilter(acctCode=self.endpoint.account)),
            10,
        )
        trades = {
            (
                x.order.clientId,
                x.order.orderId,
                x.orderStatus.permId or x.order.permId,
            ): x
            for x in [*self.ib.trades(), *opened, *completed]
            if x.order.orderRef in self.known_refs
        }
        executions = []
        for fill in fills:
            e = fill.execution
            if e.orderRef not in self.known_refs:
                continue
            fee = fill.commissionReport.commission
            # Pending commission is a disclosed conservative estimate, not an
            # actually charged paper-position fee.
            if not math_is_set(fee):
                fee = max(1, 0.005 * float(e.shares))
            executions.append(
                {
                    "ref": e.orderRef,
                    "account": e.acctNumber,
                    "client_id": e.clientId,
                    "conid": fill.contract.conId,
                    "side": {"SLD": "SELL", "BOT": "BUY"}.get(e.side, e.side),
                    "exec_id": e.execId,
                    "shares": e.shares,
                    "price": e.price,
                    "at": e.time.isoformat(),
                    "commission": fee,
                }
            )
        self.prove()
        return {
            "at": self.now(),
            "account": self.endpoint.account,
            "complete": True,
            "nav": values["NetLiquidation"],
            "available_funds": values["AvailableFunds"],
            "excess_liquidity": values["ExcessLiquidity"],
            "positions": positions,
            "orders": [self.order_row(t) for t in trades.values()],
            "executions": executions,
        }

    async def submit(self, intent):
        self.prove()
        if (
            intent["account"] != self.endpoint.account
            or intent["conid"] not in self.contracts
        ):
            raise SafetyError("unverified submission identity")
        self.known_refs.add(intent["ref"])  # also retained if placeOrder raises
        from ib_insync import LimitOrder

        order = LimitOrder(
            intent["side"],
            intent["shares"],
            intent["limit"],
            account=self.endpoint.account,
            tif="DAY",
            outsideRth=False,
            orderRef=intent["ref"],
        )
        trade = self.ib.placeOrder(self.contracts[intent["conid"]], order)
        return {"order_id": trade.order.orderId, "perm_id": trade.order.permId}

    async def cancel(self, row):
        self.prove()
        if not owned_order(row, self.endpoint, self.known_refs):
            raise SafetyError("foreign cancellation forbidden")
        trade = next(
            (
                x
                for x in self.ib.trades()
                if x.order.orderId == row["order_id"] and x.order.orderRef == row["ref"]
            ),
            None,
        )
        if trade is None or not owned_order(
            self.order_row(trade), self.endpoint, self.known_refs
        ):
            raise SafetyError("no current owned order handle")
        self.ib.cancelOrder(trade.order)

    def close(self):
        if self.ib:
            try:
                if self.ib.isConnected():
                    self.retain_quotes(set())
            finally:
                if self.listening:
                    self.ib.pendingTickersEvent -= self.receive_ticks
                    self.listening = False
                self.ib.disconnect()

    def retain_quotes(self, wanted):
        for conid in list(self.tickers):
            if conid not in wanted:
                self.ib.cancelMktData(self.contracts[conid])
                self.tickers.pop(conid, None)
                self.components.pop(conid, None)


def math_is_set(value):
    try:
        number(value, minimum=0)
        return True
    except SafetyError:
        return False
