# Autonomous stock-short executor, starting with one share

Updated 2026-10-28. The owner confirmed **one initial share per company**. The
destination is automatic entry, management and covering without per-trade human
approval. This is a design, not an order authorization or deployment. Existing
research has `production_authority: none`; no credentials, Gateway configuration,
registry allocation or SPX operating rules change here.

## IBKR connection and host

Use an independent execution VM with its own broker connection and dedicated
IBKR username. Prefer a separately funded stock account; have IBKR confirm
whether its margin and liquidation exposure are actually independent of SPX.
A separate machine isolates compute and operating failures. A separate username
isolates brokerage sessions. Neither alone proves separate capital or lending
capacity. Do not reuse the SPX username, credentials or NY4 Gateway.

The ordinary implementation is a dedicated IB Gateway on the new VM, with the
executor connecting to its local API over loopback. Bind the API locally, use a
dedicated OS user and secret store, and expose no broker listener publicly. A
separate execution project must define its own client-ID and ownership contract
before connecting. This repo's registry remains unchanged.

```text
SEC / issuer announcements + independent stock prices
                   |
Point-in-time signals -> automatic eligibility and account risk reservation
                   |
Independent execution VM -> local API -> own Gateway / IBKR username
                   |                              |
Durable private order ledger              Dedicated stock account
                   |
Own execution events + daily Flex HTTPS reconciliation
                   |
Redacted health and outcomes -> research dashboard

NY4 / SPX Gateway: no dependency from this path
```

IBKR permits one active brokerage session per username across its platforms.
Changing an API client ID does not create another username or login session.
Additional usernames may need their own data entitlements. Confirm account
eligibility, permissions, shorting and subscribed data before implementation.

| Arrangement | Advantages | Disadvantages / decision |
|---|---|---|
| Existing NY4 SPX Gateway | Lowest additional hosting cost | Current SSI contract forbids an unattended session. Shares session, lines, capacity and outages. Do not use. |
| NY4 with separate Gateway and username | Saves another VM; separates brokerage sessions | Shares a two-vCPU host, RAM, disk, OS maintenance and outages with SPX. Requires an approved independent arrangement and host resource contract. Inferior isolation. |
| New VM remotely using the SPX Gateway | Separates strategy compute | Retains the brokerage failure point and adds network dependency. Does not solve coexistence. |
| New VM with own Gateway and username | Independent deploys, restarts, resources and brokerage session; clear ownership | Extra hosting, monitoring and possibly data subscription. Recommended, preferably with separately isolated funding. |

Disclosure-driven trading with multi-session holdings does not require NY4
colocation for a one-share pilot. Use a reliable ordinary always-on VM near
IBKR connectivity, then measure latency before buying specialized hosting.
Research and backfills should run away from NY4.

## Automatic trading and authentication operations

Automatic trading can run without approval on each trade. Standard TWS / IB
Gateway still has an authentication limitation: IBKR documents weekly manual
reauthentication after the Sunday token reset. Unscheduled session revocation
is also possible. Daily auto-restart does not remove this requirement. IBKR
does not officially support a GUI-free headless Gateway. Do not promise
permanent unattended operation by scripting around security controls.

If zero routine human authentication is mandatory, obtain IBKR confirmation
of eligibility for an approved direct API arrangement first. OAuth 2.0
organizational access has eligibility requirements; an LLC name alone proves
neither eligibility nor perpetual unattended access. FIX has materially higher
integration and commercial requirements, disproportionate to a one-share pilot.

Detect expired sessions through the future executor's own authorized connection,
disable new entries and follow its position-risk procedure. Never restart or
borrow SPX's Gateway because of a stock-executor authentication outage.

## Signals and availability

| Signal | Live source | Availability rule |
|---|---|---|
| Definite reverse-split announcement | SEC submissions/filings plus licensed issuer/news distribution | After receipt and parsing establish a definite action; shareholder authorization/proposal is a different event. |
| Third or later split | Issuer identity and prior completed corporate-action ledger | Count only prior completed actions already known when the signal arrives. |
| Cash burn | SEC CompanyFacts and source 10-Q/10-K/20-F filings | Negative trailing-12-month operating cash flow from filings already public. Unknown stays unknown. |
| No 50% daily rally | Independent split-adjusted completed-session prices | No daily close-to-close gain of 50% or more in the previous five completed sessions. |
| Weak split-day close | Completed regular-session OHLC | Available only after the effective-day close and data receipt. Cannot gate an immediate announcement short. |
| Executable price / loan terms | Dedicated broker/data and stock-loan arrangement | Fresh references and actual permission to short at order time. Public lists are indications, not an approved loan. |

Cash burn uses annual CFO, or annual CFO plus current YTD minus matching
prior-year YTD. Preserve periods, accession, filing/retrieval clocks, units and
source bytes; reject inconsistent periods and reports older than the frozen
200-day freshness limit. Historical date-only filings use conservative next-day
availability. Production needs actual acceptance/retrieval clocks and latency.

Weak close means close below open and `(close-low)/(high-low) <= 0.25`, with
a positive range. An announcement policy must omit it or enter later. SEC-only
discovery can lag an earlier issuer/news release: retain the earliest observed
public source and receipt, resolve CIK/security/conId, deduplicate amendments
and retain cancellations and changed effective dates. The existing public
research monitor is not a latency-qualified production news feed.

## Announcement versus the existing backtest

The frozen post-effective policy enters 09:31–10:31 Eastern in the first
eligible regular session after the effective split day and covers in session
20. It can use the completed split-day weak close. It does **not** short
immediately when the original announcement is released.

The separate `announcement_full_v2` experiment starts from the first qualifying
captured definite scheduled-action disclosure. SEC acceptance is a publication
proxy, not proof of the earliest press release or when a trader received it.
It compares zero/five-minute delay and next-open entry, always in regular
hours. It tests 20 sessions from entry and 20 sessions after the effective
date stated in that announcement. Its source-covered disclosure cohort does
not require a later completed split. The legacy completed-event cohort remains
a separately labeled selected-universe control. Missing intraday prices and
borrowing terms remain explicit assumptions.

The announcement backtest uses the full **$100,000 per-company target**, with
actual modeled fills disclosed separately. It compares first, second and third
or later documented splits and rebuilds every fundamental screen at announcement.
**One initial share is solely the future live pilot size.** The pilot tests
operations and cost calibration; backtest profit cannot scale linearly down to
it. Freeze its live configuration separately; do not revise existing policies.

## Fully automatic behavior

Start with **one whole share at initial entry**, one position per company and
three concurrent company slots. Also configure dollar, margin, squeeze reserve,
per-order and daily-loss limits: one share is not constant risk. Pending orders
reserve slots and capital. Subsequent corporate actions change the owed quantity;
cover the reconciled liability rather than a hardcoded one share.

No per-trade approval appears in the target state machine:

`signal_ready -> eligible -> reserved -> submitting -> acknowledged -> partial/filled/cancelled/rejected`

Persist intent and idempotency key before transmission. Lost acknowledgements
go to `uncertain`: block new entries and reconcile owned orders through the
dedicated broker connection. Never blindly resubmit. Handle duplicate fills,
cancel/replace races and reconnects in-process with persistent backoff and caps.
Service restarts cannot become connection churn. Future independent recovery
must not be implemented as an SSI Gateway poller.

Bind contract identity, account, policy/input hashes, quantity, price collar,
time window, loan limits and ownership on every order. Reject stale quotes,
unknown identity, missing required signals, excessive loan costs, missing
permissions or insufficient reserves. Universal tradability is a research
assumption; it cannot make a broker accept an unavailable short.

Use owned-order events on the dedicated connection, bounded recovery and daily
Flex HTTPS reconciliation. Flex is reporting, not intraday emergency liquidation.
Covers become automatic under the independent policy, including retry/escalation.
Track halts, recalls, buy-ins, delisting, dividends/payments in lieu, mergers,
split fractions, fee changes and settled loan returns. Never substitute a
backtest closeout premium for a real fill. Exceptions can need operational
intervention even when ordinary trades need no approval. Prearrange alerts,
broker protections and owned-position recovery. Rollback disables new entries;
it never flattens a shared account or touches another strategy's orders.

## Current SSI contract and SPX protection

The existing SSI bridge stays human-triggered, bounded and idle with zero
Gateway sockets. Client 91 remains its sole transmitter; 81 stays disabled
and 82 cannot connect. Registry `2026-09-09.1`, SHA-256
`3d2ba10bda3a577696e8e85ae5a6efd1a934e33341ade782506b79f0bad82abd`,
remains authoritative. Do not repurpose these IDs for the future executor.

No SSI Gateway polling, scheduled session, startup probe, streaming subscription,
account-wide cancellation, foreign order binding, Gateway restart or global
Read-Only change. Market-hours contact still requires the existing specific
authorization. No new Theta login/terminal, and no Theta access 07:45–16:15
Eastern on market weekdays. This research uses none of those resources.

Autonomous execution needs a separate project/operating contract and independent
broker arrangement. Renaming an SSI collector or moving it to a new VM that
connects to NY4 does not meet that boundary. If approved non-broker work must
run on NY4, preserve Nice at least 15, CPU quota, idle I/O and real backoff.

## Implementation sequence

1. Confirm account, username, permissions and authentication route with IBKR,
   including actual margin isolation; select the independent VM. Document
   ownership and limits without changing NY4.
2. Freeze the announcement or post-effective one-share policy and cost limits.
   Use the announcement replay and prospective comparison without choosing
   solely by fitted historical profit.
3. Build production announcement ingestion, point-in-time fundamentals,
   price/loan adapters and private ledger independently. Measure discovery
   latency, missed events and stale inputs in signal-only mode.
4. Implement against a fake broker first. Fault-inject duplicate commands,
   lost acknowledgements, reconnect/restart, partial covers, rejected loans,
   recalls and fractional liabilities. Prove ownership and persistent limits.
5. Test a complete lifecycle in an independent paper account. Paper fills
   validate plumbing, not actual stock-loan access.
6. Deploy the automatically managed **one-share live pilot** under an explicitly
   configured account, policy and limits. Ordinary trades need no manual ticket.
   Reconcile real fills, costs, loan returns and session/source exceptions.
7. Scale only after reviewing completed real lifecycles, losses, cost/fill
   error, concentration and operational reliability.

The existing research sample of 50 completions across 30 companies concerns
that frozen study. It neither authorizes orders nor prevents designing a
separately approved operational pilot. A merge does not deploy an executor
or commit capital.

## Primary references

- [IBKR sessions and username permissions](https://www.interactivebrokers.com/docs/web-api/authentication/trading)
- [IBKR multiple applications, subscriptions and Gateway operation](https://www.interactivebrokers.com/docs/third-party-integrations/general-third-party-frequently-asked-questions)
- [IBKR auto-restart and weekly reauthentication](https://www.ibkrguides.com/traderworkstation/auto-restart-considerations.htm)
- [IBKR OAuth 2.0 eligibility](https://www.interactivebrokers.com/docs/web-api/authentication/oauth-2/introduction)
- [IBKR FIX requirements](https://ibkrcampus.com/docs/fix/requirements)
- [SEC submissions and CompanyFacts](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [IBKR securities financing indications](https://www.interactivebrokers.com/en/trading/securities-financing.php)
