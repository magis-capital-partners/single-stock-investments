"""Read-only PAPER session diagnostic (stage 5 of operator acceptance).

One connection, no retries, no journal, and no order transmission: the only
order object it builds is an exact-stock ``whatIf`` preview, which IBKR never
routes. It proves, in this order:

1. the loopback port is served by a local IB Gateway/TWS process, not by an
   SSH/port forward that could carry the handshake to a live Gateway;
2. the session advertises only ``DU`` paper accounts, the configured one among
   them, under the configured client ID;
3. complete account-scoped positions and NAV/AvailableFunds/ExcessLiquidity;
4. optionally, for one reviewed symbol/conid: identity, a real-time two-sided
   share-size quote, the paper shortable-shares tick, broker halt state and an
   exact-stock WhatIf margin response.

A pass is paper evidence only. It does not establish live margin availability,
a live borrow allocation, or capture SPX's live exposure.
"""

from __future__ import annotations

import os
import re
import subprocess
from types import SimpleNamespace

from .engine import Executor
from .safety import SafetyError, fresh, number

IB_PROCESS = re.compile(r"^(java|javaw|ibgateway|tws)(\.exe)?$", re.I)


def listener_processes(port, *, run=subprocess.run, system=os.name):
    """Names of processes LISTENING on ``port``; an empty list means unknown."""
    if system == "nt":
        command = [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Get-NetTCPConnection -State Listen -LocalPort %d -ErrorAction "
            "SilentlyContinue | ForEach-Object { (Get-Process -Id "
            "$_.OwningProcess).ProcessName }" % int(port),
        ]
        out = run(command, capture_output=True, text=True, timeout=20).stdout
        return sorted({x.strip() for x in out.splitlines() if x.strip()})
    out = run(
        ["ss", "-Hltnp", "sport = :%d" % int(port)],
        capture_output=True,
        text=True,
        timeout=20,
    ).stdout
    return sorted(set(re.findall(r'users:\(\("([^"]+)"', out)))


def require_local_ib_listener(port, lookup=None):
    names = (lookup or listener_processes)(port)
    if not names:
        raise SafetyError("cannot prove which process serves the paper port")
    if not all(IB_PROCESS.match(x) for x in names):
        raise SafetyError(
            "paper port is not served only by a local IB Gateway/TWS: " + ",".join(names)
        )
    return names


async def probe(endpoint, policy, broker, *, symbol=None, conid=None, shares=1,
                lookup=None):
    report = {
        "schema": "rs_paper_probe.v1",
        "paper_only": True,
        "live_orders_allowed": False,
        "orders_transmitted": 0,
        "synthetic": False,
        "account": endpoint.account,
        "client_id": endpoint.client_id,
        "port": endpoint.port,
        "checks": {},
    }
    checks = report["checks"]

    def record(name, ok, **detail):
        checks[name] = {"pass": bool(ok), **detail}

    if shares is not None and not 1 <= int(shares) <= 100:
        raise SafetyError("probe WhatIf size must be 1-100 shares")
    if (symbol is None) != (conid is None):
        raise SafetyError("--symbol and --conid are reviewed together")
    endpoint.validate()
    endpoint.runtime_guard()
    record("listener_is_local_ib", True, processes=require_local_ib_listener(
        endpoint.port, lookup))
    try:
        await broker.connect()  # validates, then proves DU-only + client identity
        record("paper_session_identity", True,
               managed_accounts=len(broker.ib.managedAccounts()))
        snap = await broker.snapshot()
        record("positions_complete", snap.get("complete") is True,
               positions=len(snap.get("positions", {})))
        record("account_values", all(
            number(snap.get(k), k, minimum=0) >= 0
            for k in ("nav", "available_funds", "excess_liquidity")),
            nav=snap["nav"], available_funds=snap["available_funds"],
            excess_liquidity=snap["excess_liquidity"])
        if symbol is not None:
            await probe_stock(policy, broker, symbol, int(conid), int(shares), record)
    finally:
        broker.close()
    report["at"] = broker.now()
    report["pass"] = all(x["pass"] for x in checks.values())
    return report


async def probe_stock(policy, broker, symbol, conid, shares, record):
    signal = {"ticker": symbol, "expected_conid": conid}
    try:
        await broker.qualify(signal)
        record("contract_identity", True, conid=conid, ticker=symbol)
    except SafetyError as exc:
        record("contract_identity", False, reason=str(exc))
        return
    q = await broker.quote(conid)
    now = broker.now()
    bid = None
    try:
        bid, ask = Executor.quote(SimpleNamespace(policy=policy), q, now, conid)
        record("realtime_two_sided_quote", True, bid=bid, ask=ask,
               bid_size=q["bid_size"], ask_size=q["ask_size"])
    except SafetyError as exc:
        record("realtime_two_sided_quote", False, reason=str(exc),
               market_data_type=q.get("market_data_type"))
    ticker = broker.tickers[conid]
    try:
        fresh(broker.components.get(conid, {}).get("shortable_at"), now, 30)
        record("paper_shortable_tick", True,
               shortable_shares=number(ticker.shortableShares, minimum=0),
               note="paper tick only; not a live locate or allocation")
    except SafetyError as exc:
        record("paper_shortable_tick", False, reason=str(exc))
    halted = getattr(ticker, "halted", None)
    record("broker_halt_state", q.get("market_data_type") == 1 and halted in (0, 1, 2),
           halted=halted, note="broker halt state is not SSR clearance")
    if bid is None:
        record("whatif_margin", False, reason="no valid real-time bid to preview at")
        return
    margin = await broker.margin(conid, shares, bid)
    try:
        if margin.get("warning"):
            raise SafetyError("WhatIf warning: " + str(margin["warning"]))
        values = {k: number(margin.get(k), k) for k in (
            "initial_change", "maintenance_change", "initial_after",
            "maintenance_after")}
        record("whatif_margin", True, shares=shares, limit=bid, **values,
               note="paper margin; not live margin availability")
    except SafetyError as exc:
        record("whatif_margin", False, reason=str(exc))
