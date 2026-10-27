# CLAUDE.md — single-stock-investments

## IB Gateway coexistence (three systems, one Gateway) — DO NOT VIOLATE

The NY4 Gateway is shared by **spx-0dte**, **ls-algo**, this repo, and
**etf-0dte** (SPY/QQQ 0DTE; yields to SPX). SPX 0DTE
is the protected party. The allocation source of truth is
`_system/trading/ib_gateway_client_registry.v1.json`, registry version
`2026-09-09.1`, canonical SHA-256
`3d2ba10bda3a577696e8e85ae5a6efd1a934e33341ade782506b79f0bad82abd`.
The same version/hash is mirrored in the other two repos. Prose is explanatory,
not an allocation authority.

| System | IDs |
|---|---|
| spx-0dte | 17 live executor; 18 ibc_guard probe; 19 off-hours line probe; 87 basis sampler; 88 off-hours what-if; 97 emergency watchdog |
| ls-algo | 0 disabled-reserved; 83 read-only stale-order interlock; 41 rebalance; 77 flow; 90 screener; 198 contract probe; leased pool 100–129 |
| single-stock-investments | 71 Drew legacy sleeve; 72 Michael legacy sleeve; 73 legacy read-only sync; 81 disabled/reserved collector; 82 reserved/no-connect observer; **91 event-driven hub bridge and sole hub transmitter** |
| etf-0dte | 50 SPY 0DTE live executor; 51 QQQ 0DTE live executor; 130 SPY dead-executor watchdog; 131 QQQ dead-executor watchdog |

**Rule 0 — the one that governs the rest. During market hours on a market day
(09:30–16:00 ET, Mon–Fri, US holidays excluded) no agent initiates anything that
touches the Gateway.** Not a connect, not a probe, not a "quick read-only check",
not a unit restart. Diagnose from logs, the local ledger, D1 and the committed
payload — none of which need a socket. If a task truly requires the Gateway
during RTH, stop and ask the user in chat and say why it cannot wait until after
16:15 ET; approval for one such action never carries to the next. Off-hours, and
after 16:15 ET on a weekday, is the normal window. This is mirrored for Cursor in
`.cursor/rules/ib-gateway-safety.mdc` (`alwaysApply: true`); the two must agree.

Rules that keep SPX safe (test-enforced where noted):

1. **Never `reqGlobalCancel`** — cancels every working order account-wide,
   including SPX's. No call site may exist (`test_ib_bridge.py` enforces).
   Cancellation requires a `MAGIS|` orderRef, the configured account, and
   `clientId == 91`.
2. **Never take another system's client ID** — the hazard is grabbing an ID
   while its owner is mid-reconnect. Every SSI socket path must call
   `_system.trading.ib_gateway_registry.assert_ssi_client_id` immediately
   before connecting. The CI scanner rejects unguarded connects and foreign,
   retired, disabled, or role-mismatched defaults.
3. **Connection slots:** the Gateway accepts ~32 API connections total; the
   idle hub holds **zero** sessions. Client 91 opens only for a specific human
   ticket, is released at the end of that work, and is rate-limited by the
   persistent budget/circuit breaker. Client 81 stays disabled; client 82 may
   not connect. Scheduled or recurring Gateway sessions are prohibited.
4. **Market-data lines are one account-wide pool** shared with SPX's option
   NBBO stream. The bridge uses `snapshot=True` only, cancels in `finally`,
   and is leak-tested (50 quotes → 0 open lines, ≤1 concurrent). Keep it
   that way; never add a streaming subscription to the hub.
5. **`reqAutoOpenOrders` must never appear in this repo** (test-enforced) —
   binding TWS orders is how a hub session could end up owning SPX orders.
6. **Never stop/restart the Gateway process** or flip its global Read-Only
   API toggle. A failed client-18 handshake alone does **not** prove all clients
   are disconnected. spx-0dte's `ibc_guard` restart carve-out requires
   independent evidence that the protected executor is dead, in addition to
   its handshake checks and restart cap. SSI never invokes that carve-out.
7. **Background jobs deployed to NY4** (Whisper backfill and other non-Gateway
   batch work) run
   `Nice≥15` + `CPUQuota` + `IOSchedulingClass=idle` so the SPX executor never
   waits on CPU. The host has **2 vCPUs**. Enforced with systemd drop-ins at
   `~/.config/systemd/user/<unit>.service.d/10-spx-coexistence.conf`. Retry loops
   need a real backoff: at the stock `RestartSec=5` the collector produced
   **6,785 restarts and ~315k journal lines in one day** against a Gateway that
   was intentionally down.
9. **NEVER POLL THE GATEWAY FROM THIS REPO. This rule has no exceptions.**
   Broker truth arrives via **IBKR Flex**, which is an HTTPS report service and
   touches no Gateway, no TWS API socket and no client ID. There is no
   `collect` command in this repo and there must never be one again.

   Why this is a rule and not a preference: the hub collector (client 81) held
   a *single* connection at a time and so passed rule 3 for months, while
   opening and closing that connection **every 30 seconds** -- about 780
   connects per session. On Monday 2026-08-24, an ordinary day with no outage,
   systemd logged **213 restarts of it during RTH alone**; on 2026-08-25 it
   logged 1,057 start/stop events before the SPX side masked it. It was a
   standing denial-of-service against the Gateway carrying the live SPX 0DTE
   executor, and it read as healthy the entire time because the thing being
   counted (concurrent sockets) was not the thing doing the harm.

   The three failures that combined, all of which any future design must avoid:
   * **Churn.** A session opened and closed per poll. A human-triggered bounded
     session is allowed; a timer-driven or repeating connection is not.
   * **Crash-to-restart.** A failed connect escaped and killed the process, so
     an upstream outage became a restart loop. Connection failure must be
     caught in-process with real backoff and a daily cap.
   * **Polling at all.** Nothing on this dashboard needs sub-daily broker
     truth. It is a research and allocation surface, not an execution screen.
     Intraday state belongs to the systems that own it.

   Applies to any future component, in any language, under any name. If a
   design needs a repeating Gateway connection to work, the design is wrong.
   The only Gateway contact this repo may ever make is a **human-initiated,
   single-shot** order action (see rule 10).

10. **Order placement, if it exists, is event-driven and never scheduled.**
    No standing Gateway session, no poll loop against IB. A connection may be
    opened only in response to a specific human action on a specific ticket,
    must be released when that ticket reaches a terminal state, and must be
    rate-limited with a circuit breaker that fails closed. The command channel
    is polled against **D1 over HTTPS**, never against the Gateway.

11. **`ibc.service` is a session service.** It starts, runs a few hours, and exits
   `0/SUCCESS` after the close; weekends it is down entirely. A
   `ConnectionRefusedError` on 127.0.0.1:**7496** is therefore normal off-hours,
   **not a fault**. Never "fix" it by restarting anything, and never by touching
   `ibc.service` (see rule 6).

**Deployment layout.** The `/opt` + system-systemd runbook under
`portfolio_hub/deploy/README.md` is deprecated and must not be used. The known
NY4 layout is `/home/spx` under `spx` user systemd; its repo is an unversioned
file copy, so a merge does not deploy it. Client 81's collector is disabled and
must not be restored. Broker truth is Flex over HTTPS. The command process may
poll D1, but an idle process holds no Gateway socket.

Local checks that do not touch the Gateway:

```bash
python _system/scripts/check_ib_gateway_registry.py --skip-mirrors --scan-ssi
python _system/scripts/check_ib_gateway_registry.py  # manual cross-repo mirror check
```

## ThetaData seat (one key, one terminal) — DO NOT VIOLATE

The ThetaData key is **shared with spx-0dte, and spx-0dte is the protected
party** — the same standing as the Gateway contract above. Mirrored
machine-wide in `~/.claude/CLAUDE.md`, in spx-0dte's `AGENTS.md` (Rule 0T) and
in ls-algo's `CLAUDE.md`; they must agree.

**One key holds ONE terminal session and the NEWEST login wins.** A second
login invalidates the first one's session: the loser keeps answering
`/v3/terminal/mdds/status` with `CONNECTED` while every data endpoint returns
**HTTP 478**. That is not a crash, so `Restart=always` never fires and the
terminal serves nothing for hours behind green health checks (2026-09-08
twice, 2026-09-10). During the session NY4's terminal is the **live SPX
executor's market-data source**; taking it blinds live trading, and running SPX
on its IB fallback flips its skew gate on ~12.8% of minutes.

**RULE: during the seat window — 07:45–16:15 ET, Mon–Fri, US holidays
excluded — nothing in this repo touches ThetaData**, and **never start a local
ThetaTerminal, at any hour**. The window is wider than RTH on purpose: it runs
from 07:45 (the owner moved it from 08:40 on 2026-09-29, because spx-0dte's
early-ORB pre-open job reads NY4's terminal from 07:55) through spx-0dte's
16:15 pull. If a pull genuinely cannot wait, stop and ask the user in chat and
say why it cannot wait until after 16:15 ET; approval for one such action never
carries to the next.

**What takes or shares the seat here:**

- `_system/research/systematic_flows_volatility/`: `scripts/check_data_access.py`
  and `scripts/collect_and_analyze_event.py` (both `from thetadata import
  ThetaClient` with `THETADATA_API_KEY`: running either is a login, and a login
  takes the seat), and the vendored
  `internal_ls_algo/code_and_config/bucket5_theta.py` (same hazard). Research
  scripts with no schedule, which is exactly why they are easy to run without
  thinking.
- `_external/single_stock_options/pull_greeks_eod.py` (+ `run_overnight.py`,
  `pull_entry_snapshots.py`, `speed_test*.py`; git-ignored): BORROWS NY4's seat
  through spx-0dte's `theta_seat.borrowed_seat()`, never a local terminal, and
  stands aside for the seat window, 16:00–19:00, and while spx-0dte's nightly is
  still running. Halt it with a `STOP` file in that folder.
