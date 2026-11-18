# Reverse-split IBKR paper executor

This is a **standalone paper trading process**, built from the SPX/SPY operating
patterns. It is not a feature switch on the live SPX executor or Box R collector.
There is no live mode, live order switch, production client allocation or automatic
deployment. The owner authorized its implementation/testing/merge on 2026-11-18;
that does not authorize connecting to NY4, a live Gateway, or placing real orders.

## Boundaries

* Box R continues collecting SEC/news/financial/history data, EQUS.MINI research
  books and public borrow/Flex evidence. Its code, deployment and policies are
  untouched by this package. No broker client, credentials or session belongs on R.
* An **isolated paper host** runs this package beside an independently configured
  paper Gateway/TWS. Only `127.0.0.1:4002` or `127.0.0.1:7497`, an explicit `DU...`
  account and a distinct operator-selected paper client ID are accepted. IDs in
  the canonical production/reserved/retired registry are rejected. This is a
  separate paper endpoint namespace, not an allocation on the NY4 Gateway.
* Before any data or orders, all broker-advertised managed accounts must be paper
  accounts, and the actual socket client identity must match the configured ID.
  Box R's role/environment/file and known collector/NY4 hostnames are blocked.
* Nothing here modifies the shared live Gateway registry, credentials, settings,
  SPX/ETF code or services. No test opens a Gateway or vendor connection.
* A future live RS system requires a new reviewed implementation, formal client-ID
  allocation/mirrors and approved operating contract. Changing a JSON mode or port
  cannot enable live orders in this implementation.

## SPX framework reuse

Source reviewed at `magis-capital-partners/spx-0dte` commit
`b52710eebde22ae2eecba1ba69de640ac8b8dd6e` (2026-11-18). These are adaptations
of the safety architecture, not a runtime import of a dirty SPX checkout:

| SPX source | Paper counterpart |
| --- | --- |
| `live/product_profile.py`, client registry | `PaperEndpoint`: explicit profile, account/client/endpoint pin, immutable paper boundary |
| `live/ib_connection.py` | Account-scoped `positionMultiEnd` completeness proof, error/late-end rejection, cancellation/cleanup on every path |
| `live/order_ownership.py` | `RSPAPER|` references, account + client + contract checks, uncertain-submission latch, owned-order cancellation only |
| `live/order_journal.py`, session recovery | Durable pre-submit intent, order/perm/execution IDs, partial-fill replay, duplicate rejection and startup reconciliation |
| `live/account_guards.py` | Fresh NAV, AvailableFunds and ExcessLiquidity; SPX reserve, pending-order reservations and squeeze/maintenance stress |
| `live/deliverable_governor.py` | Explicit margin provenance and rejection of missing/NaN/IB sentinel values; **no** option/assignment percentage fallback |
| Heartbeat/pager patterns | Durable local events, read-only status, optional redacted Slack outbox and sticky safety latches |

The broker client is pinned to `ib_insync==0.9.86`, the source generation inspected
in SPX. The adapter also guards the session immediately before WhatIf, submission
and cancellation. It never binds or cancels another client's orders.

## What is implemented

* Read-only ingestion of Box R's existing `collector-dashboard/operations.json`;
  no publisher/collector changes or a second Databento feed.
* Reviewed, source-bound common-share/IB conid mapping and fresh eligibility/borrow
  inputs. A later repair does not reopen a 15-minute publication/receipt window.
* All-scoreable repeat splits, minimum three supported factors, 200-day period
  freshness, resolved selected terms and issuer/action/source deduplication.
* RTH-only entries using the existing frozen NYSE calendar (holidays/half days).
* Actual IBKR WhatIf preview for the exact paper stock short, quantity and account.
  Missing fields, sentinel numbers, warnings and stale account data block entry.
* $5k default target, hard $50k/name, $150k total, three names, 0.5%/1.5% NAV caps;
  10% of displayed bid-size participation, borrow quantity/rate and 100-bps spread
  limits can reduce capacity to zero. These are paper experiment settings.
* Positive owner-set SPX reserve, cash buffer and daily loss limit are required;
  templates deliberately leave them unset. Pending orders consume reservations.
* Native broker paper fills only: this process never invents fills from quotes.
* SQLite WAL + synchronous FULL, one OS-locked writer, immutable policy hash and
  account identity, durable intent before transmission, no retry of an uncertain
  entry, and execution-ID idempotence. The collector's `synchronous=OFF` is not
  used here. Do not delete a journal to clear an unresolved broker position.
* Scoped entry cancellation, partial-cover accounting and no over-cover. Entry
  order TTL is 30 seconds; cover TTL is 15 seconds. Repricing waits for broker
  cancellation confirmation and uses remaining shares, with ten cover attempts
  maximum before operator escalation. A timeout is never treated as a fill.
* 20% adverse-price stop trigger, five-session maximum and pre-action exit guard;
  kill/daily-loss/recall/rate exits. **Stops are not guaranteed prices.** No order
  is transmitted on a stale/unknown/halted book; unfillable liabilities remain.
* Regular-session DAY LIMIT orders only; no market-order or global-cancel path.
* Existing-position protection runs before research reads and still runs when the
  inbox is unavailable. An unprotectable/ halted name stops entries and records an
  alert, but does not prevent other names' supported exits.
* Per-day persistent limit of three paper connection attempts; a disconnected
  session retries after 30 seconds within that budget. Reconnect does not clear
  entry uncertainty. No supervisor restart storm.

The 20% stop and pre-action exit are **new paper guardrails**, not the historical
five-session backtest. Original 60-point/all-scoreable shadow policies, source
clocks, failed trial grades and original November 13 trial end are unchanged.

## Input contract and missing access

`evidence.example.json` is intentionally empty. Populate a private evidence file
from reviewed primary/reference data and an authorized fresh eligibility producer.
Never set `source_verified=true` merely because a producer is alive or a ticker is
absent from a daily SSR list. Missing fields block paper entries; examples are not
production evidence.

* `identities[TICKER]`: `cik`, numeric `conid`, `type: "CS"`, `currency: "USD"`,
  `verified: true`, UTC `at`/`valid_until`, `source_url`/`source_sha256`, canonical
  issuer `action_id`, reviewed `ratio` and earliest legal/trading `action_day`,
  `action_source_sha256` matching a candidate primary object, and
  `conditions_resolved: true`. Mapping is dated new evidence, not an old quote upgrade.
* `borrow[CONID]`: numeric `conid`, UTC original source `at`, fractional annual
  `apr` (0.50 = 50%) and integer `available_shares`. It is capped by a fresh IB
  paper shortable-shares tick. Neither is a real allocated locate or margin grant.
* `eligibility[CONID]`: numeric `conid`, UTC `at`, `complete: true`,
  `source_verified: true`, explicit boolean `halted`/`ssr`; optional `recall`.
  Complete fresh SSR clearance is still an external data gap under EQUS.MINI.

Paper broker acceptance does not prove a hard-to-borrow live allocation, impact
or charged fees. P&L guards include known/estimated paper commissions and a disclosed
conservative calendar-day borrow bound. The bound remains after a cover, may
overestimate partial/same-day positions and is **not** settled Flex accounting.
Do not label it actual net P&L. Real fee schedules, settlement/recall/dividend costs,
economic sizing and full corporate-action support require further validation.

## Safe startup (operator-run; not performed by this change)

Use a dedicated Python 3.12 virtual environment on the isolated paper execution
host. It needs no GitHub/Databento/Flex/NY4 credentials. Copy source through the
existing reviewed artifact process. Verify a separate paper Gateway is listening
locally; do not tunnel or redirect it to the live Gateway.

1. Copy `config.example.json` to a private file. Fill the actual **paper** account,
   an unused paper-endpoint client ID and the owner's SPX reserve/cash/loss limits.
   The example cannot connect or pass preflight until those decisions exist.
2. Install this package's pinned requirements into that private venv.
3. Populate the reviewed evidence file. Supply a periodically refreshed local copy
   of Box R's existing operations JSON, or use its exact private Cloudflare R2 HTTPS
   object URL with a narrow read credential in `RS_OPERATIONS_READ_TOKEN`.
4. Run the no-network preflight:

```text
python -m _system.trading.rs_paper_executor preflight --config /etc/rs-paper-config.json
```

5. Prove the paper session read-only before any `run`. One connection, no retry,
   no journal, no order transmission. It refuses unless the port's listening
   process is a local IB Gateway/TWS (`java`, `javaw`, `ibgateway`, `tws`); an
   `ssh`/`sshd`/`plink` listener means a forward that could carry the API
   handshake to a live Gateway, and is refused before any socket opens. `run`
   applies the same check before every connect.

```text
python -m _system.trading.rs_paper_executor probe --config /etc/rs-paper-config.json --connect-paper
python -m _system.trading.rs_paper_executor probe --config /etc/rs-paper-config.json --connect-paper --symbol <TICKER> --conid <REVIEWED_CONID> --shares 1 --report probe.json
```

   Checks: local IB listener, DU-only managed accounts under the configured
   client ID, complete `positionMultiEnd` snapshot, NAV/AvailableFunds/
   ExcessLiquidity and, with a symbol, contract identity, a real-time (type 1)
   two-sided share-size quote, the paper shortable tick, broker halt state and an
   exact-stock WhatIf (1-100 shares). Exit 0 = all passed, 3 = a check failed,
   2 = refused. Quote/halt checks need regular hours. A pass is paper evidence
   only: not live margin, not a locate, and it does not see SPX's live exposure.

   **IBKR login and data rules.** Log in with the account's dedicated **paper
   username**, never the live username SPX uses on NY4: IBKR runs one trading
   session per username, so a second login of that username can end NY4's. Per
   IBKR FAQ 1136176599 (read 2026-11-18), a paper user set to share a live user's subscriptions gets **no data** whenever that
   live user is logged in on a different device, and NY4's live user is always
   logged in. So on a separate host the paper session receives live data only by
   mirroring a **second live username** that holds its own stock subscriptions
   and never logs in anywhere; otherwise it gets delayed data, and every entry
   correctly blocks on `market_data_type != 1`. Changing which user the paper
   account mirrors is a Client Portal setting; it does not change SPX's
   subscriptions, but make it outside 07:45-16:15 ET.

6. The explicit opt-in for a **paper** connection is:

```text
python -m _system.trading.rs_paper_executor run --config /etc/rs-paper-config.json --state /var/lib/rs-paper/state.sqlite --operations-file /var/lib/rs-paper/operations.json --evidence /var/lib/rs-paper/evidence.json --kill-file /var/lib/rs-paper/FLATTEN --connect-paper
```

Use `--once` for one bounded paper cycle. The default journal is under the user's
private home state directory; keep configuration/state/evidence outside Git and
readable only by the service user. `rs-paper-executor.service` is an **uninstalled**
operator template. It requires `/etc/rs-paper-approved` and never auto-restarts.

Status is read-only and opens no broker connection:

```text
python -m _system.trading.rs_paper_executor status --config /etc/rs-paper-config.json --state /var/lib/rs-paper/state.sqlite
```

Create `FLATTEN` to latch a paper entry stop and request scoped covers. Removing
the file does not clear the latch. After safe recovery, `run --resume-entries`
requires fresh reconciliation and no unresolved orders; it cannot bypass a
kill latch or a daily-loss breach in the same Eastern session. After a daily-loss
halt, operator review and explicit resumption in a later session are required.
Never clear these guards by editing or deleting the journal.

Optional `RS_PAPER_SLACK_WEBHOOK` sends only event kind/time, no free-form broker
data. Failed alerts retain the cursor for a throttled retry; webhook failures do
not prevent position management. Independent off-host dead-process monitoring is
still needed before unattended operation is accepted.

## Verification

```text
python -m pytest -q _system/trading/tests/test_rs_paper_executor.py
python -m ruff check _system/trading/rs_paper_executor _system/trading/tests/test_rs_paper_executor.py --select F
```

Tests exercise the actual engine, durable journal, restart/partial-fill paths,
position-completion and cleanup handlers, and the IB adapter with synthetic broker
responses. All application socket connections are forbidden in these tests.
Windows asyncio's own stdlib wake-up socketpair is the sole internal exception.
No synthetic test is a real forward trade or a complete broker-paper acceptance
session. Actual paper endpoint/session validation is a separate operator step.

Primary API references:
* https://www.interactivebrokers.com/docs/tws-api/doc/orders/whatif
* https://interactivebrokers.github.io/tws-api/market_data_type.html
* https://interactivebrokers.github.io/tws-api/tick_types.html
* https://www.interactivebrokers.com/support/faq/content/pre-borrow-shares-paper-trading-54824557
