# Reverse-split execution on NY4

Owner direction, November 22, 2026. NY4, the existing SPX machine, is the live
host. This is a rollout plan. Deployment, broker access and live orders each
have their own approval and evidence.

| Location | Responsibility |
| --- | --- |
| Box R | Discover announcements, retain primary sources, calculate signals and publish dated research proposals. Use public borrow indications. |
| Drew's PC | Run the supervised IBKR paper test and compare SSI with the DU blotter. |
| NY4 | Observe the research feed without a broker socket. Eventually execute individually approved reverse-split tickets on the existing Gateway using the registered client 60 role. |
| SSI | Show paper and live execution in separate views. Read signed journal events and independent market marks. Use Flex for broker reconciliation. |

The live path uses the existing NY4 machine and Gateway. The protected SPX
executor keeps its connection, market-data capacity and risk priority.
Separate processes and client IDs still share account margin and positions.
The SPX and ls-algo registry files deployed on NY4 matched SSI's client-60
allocation in the November 22 file check. Confirm registry bytes, role pins and
claims compatibility again at rollout. [Account allocation registry](../ib_gateway_client_registry.v1.json)

## 1. Prove paper execution and the research feed

Run the scheduled supervised paper test on Drew's PC with its DU account.
Compare the broker blotter, the local journal and what the SSI browser
receives. Verify the short, acknowledgements, cancellation and confirmation,
cover, final flat position, reconnect recovery, execution-ID deduplication,
commission provenance and each captured P&L update. Report event-to-browser
latency by event type. If the paper account supplies delayed quotes, label
those marks and retain unavailable marks as unavailable. Exercise partial
fills on a deterministic replay and record any partials actually observed in
the paper session. The target for execution events on an active browser is
five seconds, measured during the test.

Observe Box R for a full market session with the merged freshness repair.
Record publication acknowledgement, receiver receipt, report and underlying
state clocks against the deployed release. Both producer clocks must be within
120 seconds. Keep Flex reporting credentials on a separately approved
broker-reporting surface. Rotate the previous token and verify the replacement
report before using it to reconcile live trades.

## 2. Run Gateway-free shadow on NY4

Reuse the receipt-checking observer already staged on NY4. Scheduled work can
read R2 via a scoped credential and read existing SPX risk files. It runs with
`Nice>=15`, a measured CPU quota, idle disk scheduling and bounded retry.
Deny access to Gateway loopback ports in those services and verify that the
observer package has no broker adapter. Keep elapsed-time and resource
measurements with each release.

For each fresh candidate, build a time-stamped evidence packet before the
original 15-minute window closes. Bind the original source and its hash to
the selected split terms, effective dates, issuer and approved stock conid.
Verify the frozen repeat-split and financial eligibility rules, independently
licensed consolidated NBBO and share depth, and fresh exchange halt and
short-sale restriction status. An unknown restriction, delayed or incomplete
quote, repaired timestamp, or unsettled security mapping blocks the entry.
Public borrow indications support screening. At review, obtain current
account-specific borrow and the broker's exact-stock margin preview, and
record the observed share limit, fee indication, warning and margin effect.
[IBKR short-stock information](https://www.interactivebrokers.com/support/faq/content/information-interactive-brokers-provide-about-707427431)
and [IBKR margin preview](https://www.interactivebrokers.com/support/faq/content/691853055).

For supervised shadow, the operator can supply a time-stamped margin preview
and other broker evidence from an existing, authorized IBKR interface that
can coexist with SPX. Use the current account, instrument, quantity and price
from the proposed ticket. Bind the preview and broker evidence to the exact
candidate and do not transmit an order during shadow. An additional login
using the protected username can take over its broker session. If the needed
evidence cannot be collected safely or within the original window, record the
refusal and exclude the opportunity. [IBKR brokerage-session limits](https://www.interactivebrokers.com/docs/web-api/authentication/multiple-sessions)

Keep the existing acceptance bar. Qualifying shadow requires five complete
regular sessions with an observer gap of at most 120 seconds and at least
95% measured fresh coverage, plus three fully gated opportunities from
three issuers across at least two sessions and a verified paper pass.
Deduplicate issuer and corporate action. Conditional, late and incomplete
records are excluded. The broker-free feed test measures uptime and
delivery only. Before grading this new protocol, implement and review an
offline import for source-, time- and ticket-bound broker evidence. The
existing shadow grader needs that proof before it can count these sessions.

## 3. Prepare the NY4 ticket runner

The current timer-based live implementation needs a one-ticket entry point
before rollout. Keep the scheduled research observer independent. The
eligible trigger for a Gateway session is a human approval of a specific
order action. Require an explicit owner approval for each proposed Gateway
action during the protected regular-hours window, including why it cannot wait
until after 16:15 ET. An approval for installation or a prior ticket grants no
permission for a subsequent Gateway action. [Gateway coexistence rules](../../../CLAUDE.md)

Before installation, confirm the deployed SPX and ls-algo registry hash and
read access to the shared symbol-claims file, even after an atomic file
replacement. Confirm the read-only SPX book-margin input is fresh and
budgeted. Stage a checksum-pinned release outside market hours under a
separate restricted service account and low resource limits. Keep release
activation, Gateway connection and any live-order approval as separate
steps.

For each approved ticket:

1. Bind the authorized account, client 60, `RSLIVE|` reference, conid, side,
   size, limit price, expiry, observed source clocks and frozen policy to
   a durable intent. Recheck that another strategy or human book holds no
   position or working order in the same name. Publish the symbol claim
   and keep it until the broker position and all orders reconcile. Follow the
   existing claim release window after flatness.
2. Validate the registry at the connection boundary. Recheck current
   shortability, locate or broker acceptance, fees, quote size, halt and
   eligibility, exact-order WhatIf, SPX reserve, cash buffer and stressed
   portfolio margin. Yield margin to SPX. Missing, stale or contradictory
   evidence blocks an entry.
3. Submit only the approved limit order. Use broker callbacks while handling
   that ticket, preserve every acknowledgement, execution, rejection and
   cancel, and release the connection at the terminal outcome. An ambiguous
   submission blocks further tickets until the operator reconciles it.
   Enforce the daily connection budget, real backoff and a persistent circuit
   breaker. Each new entry, cancel or cover is another separately approved action.
   A stopped worker leaves any broker-held order or position visible as
   unresolved and must not infer a successful cancel or cover.

Set the first pilot to one concurrent position. Record the reference size
and set a ceiling of one-tenth of it, with explicit per-name, gross and
loss caps. For a $25,000 reference the proposed ceiling is $2,500. The
approval also fixes the hold and pre-split exit policy, stop and recall
response, and who owns overnight cover decisions. Displayed depth, borrow
and stressed margin can reduce size further. Review a reconciled first
round trip before considering an increase.

## 4. Prove complete visibility before the first live short

Publish the ticket's durable broker events from NY4 to an owner-only SSI
execution feed. Use a live-only credential, namespace and storage partition.
The existing paper endpoint remains isolated. Attribute live positions and
P&L to reverse splits in SSI's portfolio, and reconcile execution IDs,
positions, commissions and actual borrow charges with Flex when available.

During a hold, use authorized independent quotes for marked P&L. Display the
mark source, age and distinction between estimated and posted fees. Prove a
broker-supported or already-authorized operator notification path for
broker-side changes between tickets, including recalls, buy-ins and external
fills or cancels. Confirm which events it actually delivers, measure receipt
latency and bind each event to the journal. Flex provides the reconciliation
after the fact. A broker event that only arrives later through Flex leaves
an intraday visibility gap. Keep the multi-session live pilot gated until
the notifications and quote coverage pass. A shorter, fully supervised
pilot would need an explicitly approved change to the hold policy.

Rehearse the end-to-end dashboard and emergency procedure using paper plus
recorded failure scenarios. Confirm the audit stays complete through a
reconnect and that stale feeds, lost ownership proof and ambiguous broker
state visibly block new entries. Stop accepting tickets on any failed
precondition. Use the operator's approved broker process to resolve outstanding
orders or positions and retain the journal and claims until reconciliation.
Keep SPX services and Gateway settings outside the rollback procedure.
