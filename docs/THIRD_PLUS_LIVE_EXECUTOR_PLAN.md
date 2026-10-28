# Live short executor: staged plan with SPX protected

Status: design only. The implemented 20-session forward comparison has
`production_authority: none`. This document does not authorize orders, change
the client registry, permit a Gateway connection, or change the standing
ThetaData and SPX rules.

## Decision: two execution paths, with different authority

**Initial path: a human-approved, bounded stock order ticket.** Research
prepares the candidate, frozen policy and proposed maximum quantity/price.
A human chooses the account and approves a specific entry ticket. Covering
20 sessions later needs a fresh specific human action. An approved parent
ticket may manage its bounded children only inside its expressly approved
quantity, price, time and resource limits; it cannot create another issuer's
order or a future cover authorization. The existing SSI bridge is the only
candidate transport, using registry client 91 and owned `MAGIS|` references.
No implementation or connection is added by this research change.

**Unattended path: a separately approved execution arrangement.** The standing
repo contract permits only human-initiated tickets and prohibits repeating
Gateway connections. Renaming a collector, moving it to a second machine,
making it a signal scheduler or using another shared client ID does not make
unattended execution permissible. A fully automatic executor needs an explicit
future governance decision and separate implementation review. Prefer an
independent stock-short account, broker connection/credentials, lending
arrangement and market-data entitlement on infrastructure away from NY4. Verify
actual isolation with the broker; a different machine or IBKR username alone
does not prove isolation of margin, sessions or market-data pools.

Until that decision exists, the actionable route is manually approved tickets
or manual broker entry. There is no unattended fallback through the SPX
Gateway, Web API session or credentials.

## Invariants taken from the current operating contract

- SPX is protected. No agent Gateway connect/probe/restart during market hours
  without the user's specific authorization for that action in chat and an
  explanation of why it cannot wait until after 16:15 Eastern.
- `_system/trading/ib_gateway_client_registry.v1.json`, version `2026-09-09.1`,
  hash `3d2ba10bda3a577696e8e85ae5a6efd1a934e33341ade782506b79f0bad82abd`,
  is the allocation authority. Do not invent an ID. Assert the SSI role
  immediately before any permitted connection. Client 81 stays disabled and
  client 82 never connects. Client 91 is the sole SSI transmitter.
- Idle SSI holds zero Gateway sessions. No scheduled or recurring Gateway
  session, position poll, quote poll, reconnect loop or startup probe.
- Never issue account-wide cancellation, bind other clients' orders, restart
  the Gateway or change its global Read-Only setting. Off-hours refusal is
  normal and does not authorize a repair.
- Existing SSI snapshots remain bounded, one concurrent line, with cleanup
  in `finally`. No streaming market-data subscription is added to the hub.
- Never start another ThetaTerminal, use a credentialed ThetaClient or the
  Theta API key. No Theta access 07:45–16:15 Eastern on market weekdays. The
  forward observer needs no Theta access at all.
- Research and public-source workloads stay on GitHub-hosted or independent
  infrastructure. If any future non-broker batch work genuinely must run on
  NY4, retain Nice ≥15, a CPU quota, idle I/O scheduling and bounded backoff.
  Do not deploy this observer to NY4 merely for convenience.

## Proposed component boundaries

```text
Public disclosures + approved independent market references
                     |
Frozen policy -> candidate/decision ledger -> read-only dashboard
                                             |
                                  Specific human approval
                                             |
                       Durable ticket and account risk reservation
                                             |
                      Bounded owned-order execution adapter
                                             |
                       Own acknowledgements / own executions
                                             |
                           Release the ticket's connection

IBKR Flex HTTPS -> private reconciliation ledger -> redacted outcome metrics
```

The dashboard is a research and approval surface, not a streaming terminal.
D1 HTTPS may carry a command inbox and published health. It must not become a
reason to open a Gateway socket periodically. Flex is reporting, not a
real-time emergency liquidation control. Active-ticket execution events,
broker-native/manual risk alerts and an independently approved monitoring
arrangement must cover intraday risk; a daily Flex report cannot do that job.

## Build sequence and acceptance gates

### A. Finish forward calibration

Use the implemented policy comparison and private evidence importer. Collect
fresh borrow terms, real executable price indications where available, actual
paper order lifecycle evidence, fill fractions, cost changes, cover failures,
corporate actions and loan returns. Preserve no-fills and missed discoveries.
Paper fills and public shortable lists cannot prove an actual loan or exchange
queue priority. Complete multiple independent issuers and holding periods.

Acceptance: the frozen research review criteria are inspectable; every
observation has source bytes and clocks; no modeled completion is counted as
an actual exit. Passing these checks permits a human review, never production.

### B. Specify the account and hard limits before writing a transmitter

Choose the actual account, owner, strategy identifier, borrowing route and
pilot capital. Research's $100,000 target and $10 million reference NAV are
not a live allocation. Rerun the backtest at the exact pilot ceiling because
minimum fees and partial fills do not scale linearly.

Specify per-issuer shares/notional, gross exposure, margin headroom, squeeze
reserve, maximum accepted loan APR and locate fee, price collars, order count,
message and connection budgets, maximum ticket lifetime, stale-data age,
daily-loss review levels, overnight responsibility and recall/buy-in handling.
Reserve shared-account risk before submission; release only on terminal proof.
If the account is shared, available margin must include SPX and other systems'
commitments. Separate account-level funding is the stronger isolation option.

Acceptance: versioned account/risk configuration with an owner; no ambiguous
"trade everything" fallback. Universal tradability remains a research
assumption, while actual orders require operationally valid stock-loan access.

### C. Implement a durable ticket state machine

Suggested states:

`proposed -> human_approved -> reserved -> submitting -> acknowledged -> partial/filled/cancelled/rejected`

`submitting -> uncertain -> human reconciliation` is a separate path.
Persist intent and the idempotency key before transmission. A lost response
must never trigger blind resubmission. Bind the exact contract identity,
account alias, side, policy/input hashes, quantity, price collar, start/end,
approval identity, expiry and nonce. A stale browser tab cannot approve a
different security under the same ticker.

Execution budgets and circuit state survive process restarts. A connection
failure is handled in-process; it cannot crash into a service restart loop.
After uncertainty, stop new entries and require owned-order reconciliation in
an authorized bounded action. Never infer rejection from silence. Cancellations
require the exact owned order reference, configured account and client 91.

Acceptance: offline fault injection covers duplicate commands, repeated fills,
partial fills, cancel/replace races, lost acknowledgements, disconnection and
restart. Every scenario produces at most one intended parent position and no
action against another system's order.

### D. Protect SPX resources without probing SPX

Consume only a health/lease signal already published by SPX's owner over an
approved non-Gateway channel. Missing/stale health, a lease denial, resource
budget exhaustion, stale prices or uncertain account state disables **new
entries**. Do not diagnose by opening a SPX client, touching the Gateway or
restarting a service. Set entry pacing materially below the shared broker
ceiling; exact limits require account-wide coordination, not an assumption
that the API's advertised maximum belongs to SSI.

There must be a prearranged manual/broker route for reducing SSI risk while
entries are disabled. A research kill switch cannot promise that a halted
stock is executable. It must not cancel SPX orders or flatten the account.
An emergency does not create an exception to the current Gateway rules.

Acceptance: failure tests demonstrate zero idle sessions, zero leaked data
lines, no churn, persistent connection/message caps, no startup probes and
no effect on protected order ownership. Use synthetic broker adapters first;
any broker-connected test requires its own specific authorized window.

### E. Make holding-period exceptions first-class

Track actual adjusted share quantity, settled loans, locate expiration, fee
changes, dividends/payments in lieu, ticker/conId changes, mergers, delisting,
halts, recalls and forced buy-ins. Use exchange sessions and early closes for
entry and cover deadlines. The session-20 cover is a new human ticket under
the current shared-Gateway policy.

At the retry deadline, escalate residual shares to the named operator. Keep
them open until broker confirmation; never replace them with the backtest's
2% or missing/OTC closeout premium. Maintain both execution completion and
settled-loan/cost reconciliation states. Use Flex HTTPS for broker truth and
the private outcome ledger for audit.

Acceptance: test an entire 20-session lifecycle, including a subsequent split,
partial covers, a halt through the cover deadline, a recall, delayed fees and
loan-return settlement. Broker evidence must reconcile to zero quantity and
settled obligations before final profit is labeled complete.

### F. Pilot, review, then scale

Start with a small separately chosen budget and specific human approvals.
Record actual fills and costs against the frozen pre-entry plans. Review
deviations, missed fills, concentration, overnight operations and SPX resource
behavior after complete holding periods. Rollback disables new SSI entries,
retains the private ledger and follows the prearranged owned-position cover
procedure; it never restarts or reconfigures the shared Gateway.

Any later unattended system is a new approved project with its own execution
authority, isolation proof and operating contract. Merging this research work
does not deploy a process to NY4 or authorize live capital.

## Primary references

- [IBKR Flex report generation](https://www.interactivebrokers.com/docs/web-api/flex-web-service/using-flex-web-service/generate-the-report)
- [IBKR securities financing and availability indications](https://www.interactivebrokers.com/en/trading/securities-financing.php)
- [SEC Regulation SHO overview](https://www.sec.gov/investor/pubs/regsho.htm)
- The current local `AGENTS.md` / committed `CLAUDE.md` and client registry take
  precedence over older bridge deployment prose or generic broker examples.
