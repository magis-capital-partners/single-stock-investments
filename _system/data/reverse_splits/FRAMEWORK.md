# Shared short framework

Implemented on 23 October 2026. The new **Framework** tab in the Short Alpha
strategy lab uses the same decision engine as the private replay and order-review
commands. The framework is implemented locally; this does not deploy the hub or
enable live trading.

## What is reused and what is new

| Reused research | New implementation |
| --- | --- |
| Reverse-split, financing and deficiency discoveries; public availability clocks | A common opportunity and point-in-time snapshot contract |
| Existing as-filed fundamental scores and source facts | Exact signal-count/profile gates for verified inputs, separate from old lower bounds |
| Cached prices, split repairs and SSR status | Shared portfolio accounting, current-unit liquidity, persistent incomplete covers and loan returns |
| Existing operating limits and original dated fee schedule | One policy and decision function for replay, shadow and reviewed orders |
| 100 cached source-review packets | Append-only source reviews, independent-review checks and financing reconciliation |
| The authenticated order desk, client 91 and human approvals | Content-bound private handoffs, current ledger/reservation checks and revalidation before submission |

The existing 420-comparison study and older strategy versions remain unchanged.
The new comparison contains 180 settings: five opportunity families, three hold
lengths, three cost cases, two evidence modes and two SSR treatments. Every
setting is retained. The last nine entry sessions are excluded consistently for
all hold lengths. Chronological fresh-account diagnostics are exploratory;
previously examined history is not an untouched holdout. The designated sealed
execution files are not read.

## Current evidence

The published snapshot uses market history through **2026-10-12**. It has 100
cached source packets and 100 passing automated consistency checks. Those are
not completed primary or independent reviews. There are currently zero imported
reviews, approved borrows, observed entry/cover fills or prospective outcomes.
Verified-mode comparisons therefore admit zero trades. Funding statistics use
daily opening, entry and closing marks; actual intraday margin peaks and house
calls require additional evidence.

The old venue data is not consolidated volume or verified NBBO. Conditional
comparisons declare price, spread, borrow and fill assumptions. Restricted-short
passive sensitivities require the historical high to reach the limit, but do not
establish queue priority or executable fills. Fundamentals-only comparisons are
unavailable until a separately selected historical universe is imported; the
framework never substitutes eventual splitters for that universe. Financing
leads cannot enter without reconciled economic terms.

## Files and prerequisites

Use **Node 24** with built-in `node:sqlite`. No npm packages are needed for the
engine, replay, evidence journal or handoff verifier. The existing Python hub
remains responsible for its own dependencies and execution controls.

- `dashboard/short-framework-engine.js`: pure browser/Node policy, decisions,
  sizing, exits and cash/share/loan accounting.
- `_system/scripts/short_framework.cjs`: private CLI.
- `_system/scripts/short_framework/`: adapters, replay, evidence store, operating
  checks, execution context and bounded public SEC discovery.
- `_system/trading/portfolio_hub/short_framework.py`: local verifier used by the
  existing hub at ticket creation and again before submission.
- `framework/summary.json` and `dashboard/data/short_framework/summary.json`:
  identical, hash-checked aggregate publications. No broker identifiers or
  private tickets are published.

Default private state is
`_system/data/reverse_splits/local/short_framework/v1/`, already ignored by git.
Keep that directory private and backed up. Its SQLite evidence chain, immutable
decisions, forecasts and handoffs must be on the **same host as the hub**. The
Python verifier uses this default location. An alternate `--work` location is
useful for isolated research/tests, but is not automatically available to the
hub. Use a distinct private environment for paper and live evidence.

The replay reuses the existing local price SQLite and event caches. A fresh
checkout without those caches can inspect the committed aggregate dashboard
snapshot; rebuilding requires restoring the cached inputs or explicitly passing
`--prices PATH` and `--calendar PATH`. Calendar JSON needs `verified`,
`source_url`, `source_sha256` and `sessions` fields. Session dates must match the
supplied price history.

## Commands

Run from the repository root. Paths below are examples of private input files,
not supplied broker evidence.

```powershell
node _system/scripts/short_framework.cjs build
node _system/scripts/short_framework.cjs review-export
node _system/scripts/short_framework.cjs import --input PRIVATE/evidence.json
node _system/scripts/short_framework.cjs evaluate --input PRIVATE/decision.json
node _system/scripts/short_framework.cjs shadow --input PRIVATE/decision.json
node _system/scripts/short_framework.cjs reconcile --input PRIVATE/attributed-flex.json --equity 50000
node _system/scripts/short_framework.cjs status --equity 50000
```

`build` freezes a declaration, implementation hash and input hashes before
replay. Private runs are archived by timestamp and declaration hash; only
aggregate output is copied to the dashboard. Price/WAL, event, action-repair,
review, broker and evidence inputs are checked again before publication. A
changed input refuses publication instead of replacing the old published run.
`evaluate` is a replay review. `shadow` requires an actual current prospective
observation and freezes an estimate **or abstention before the scheduled entry**.
A replay cannot be relabeled as prospective, and a frozen event/policy forecast
cannot be replaced after seeing its result. Neither command submits an order.

`status` reports reconciliation as pending unless a reconciliation is supplied by
the relevant build/handoff operation. `build --broker PRIVATE/attributed-flex.json`
can publish updated aggregate reconciliation status. Historical run declarations
and source clocks remain separate from the current broker snapshot.

For explicitly requested, bounded public discovery:

```powershell
node _system/scripts/short_framework.cjs discover --since 2026-10-23 --maximum 20
```

Discovery uses the existing SEC research User-Agent, HTTPS allowlisted SEC hosts,
a request cap and pacing. It stops on access denial/rate limiting, preserves the
actual first-seen time and emits phrase leads requiring source review. It checks
recent submissions for selected issuers; it is not complete market coverage.
Without an imported independent universe, prior-research selection bias remains
explicit. No recurring job or Gateway connection is installed.

## Input contracts

Imports accept a JSON object, array, or JSONL. Every record requires immutable
`id`, `kind`, aware ISO `known_at`, HTTPS `source_url`, `source_sha256` and a
`locator`. If `receipt_path` is supplied, its bytes must match the hash. Reusing
an ID with different contents fails; a failed batch rolls back completely.
Source hashes without a supplied receipt are references for review, not proof
that the raw document has been independently checked.

| Kind | Required substantive content |
| --- | --- |
| `event` | Family, issuer/instrument identity, public clock, source clause; verified events require source reconciliation. A dated review can use `event_id` to qualify the original catalogue identity after its review clock |
| `security` | Dated instrument/issuer/ticker mapping, reviewer, validity interval; verified identity and nominal units for entry |
| `fundamentals` | As-filed facts with accession, tag and known clock; period, frozen score, exact numeric-signal count and applicable operating-company profile |
| `universe` | Independent dated instrument/issuer membership and selection basis; never selection by eventual split |
| `market` | Instrument, quote time, bid/ask, SSR status; verified NBBO and prior 20-session consolidated capacity for verified entry |
| `borrow` | Status, quoted time, shares and APR; approval additionally needs broker, reference and positive quantity |
| `terms` | Deal identity, economic state, before/after share basis, saleable supply, net proceeds, reviewer and reconciled cash/claims/split/saleability |
| `thesis` | Six dated lenses, mechanisms, contrary evidence, falsifiers, reconciled bear/base/bull values, target and dated catalyst |
| `costs` | Dated roundtrip execution fraction, locate charge, both entry and cover observation counts and calibration verification |
| `review` | Event, named reviewer, primary/second role, outcome blinding, five explicit pass/fail/unresolved checks |
| Ledger events | Observed broker reference, `at` occurrence time, instrument and quantities/cash as applicable |
| `outcome` | Frozen forecast, issuer/event/instrument/policy identity, all execution and cost IDs, reconciled dollars and completed share/loan obligations |

The six lens IDs are `earnings_quality`, `cash_and_financing`,
`operating_impairment`, `disclosures_and_control`, `valuation_and_payoff`, and
`catalyst_and_path`. Each needs source, locator, mechanism, contrary evidence and
falsifier. At least two substantive mechanisms must be supported, including cash
or operating impairment, alongside valuation and a catalyst within the carry
horizon. A warning score alone does not complete underwriting.

A decision file contains `{ "snapshot": ..., "account": ..., "policy": ... }`.
The snapshot includes `as_of`, `observation_mode`, `event`, `security`,
`fundamentals`, `market`, `borrow`, `costs`, `thesis` and applicable `terms`.
An event declares `entry_at` and `entry_until`; post-split entry follows the
effective clock. An announcement cohort cannot be selected from completed
actions. Outcome fields are rejected in decision inputs.

The account includes dated equity, positions, reservations, other strategies'
stress loss and stressed margin, `basis`, `reconciled`, `source_reference` and a
private `account_reference`. Observed accounts use `basis: "observed_account"`;
declared research ledgers use `"simulated_ledger"` and a simulated policy.
Positions identify issuer and instrument with shares, loan shares and nominal
mark. Reservations identify `order_id`, instrument, issuer, action, shares and
mark. The handoff path checks these against current private state, including
unimported fills and uncertain hub orders. Imported fills should include their
`hub_intent_uuid` so completed fills release the correct hub reservation.

The attributed Flex input must contain `source: "ibkr_flex"`,
`scope: "short_framework"`, `complete: true`, `as_of`, `known_at`,
`account_reference`, attributed `cash`, mapped `positions` with signed
`quantity`, and `other_stress_loss` / `other_stressed_margin`. A full-account
cash balance cannot substitute for the attributed sleeve. The snapshot must be
no more than 36 hours old. Keep the starting capital passed through `--equity`
consistent with the journal; cash deposits/withdrawals are external flows.

Ledger kinds include entry/cover fills, marks, splits, loan returns, recalls,
orders, cashflows, external flows and fractional settlements. Short-sale
proceeds remain offset by a liability. Covers do not prove loan return. Splits
transform nominal shares and prices; fractional obligations stay open until
explicit verified broker settlement, including the actual cash amount. Missing
quotes and volume never create zero-price or guaranteed stop fills.

Outcome imports must include **every** known event execution and cash cost.
Fractional settlement cash is included without inventing a cover fill. Optional
`stress_basis: "double_observed_costs_v1"` requires matched verified pre-arrival
NBBO within five seconds for every fill. `stressed_net_dollars` must equal net
dollars minus another copy of observed fees, negative cash costs and adverse
arrival slippage. A positive stress result cannot be asserted without those
receipts. Paper/simulated fills must never be imported as observed broker fills.

## Reviewed order path

Once real evidence is available, create a short-lived handoff using the actual
private hub ledger and attributed Flex export:

```powershell
node _system/scripts/short_framework.cjs handoff --input PRIVATE/decision.json --broker PRIVATE/attributed-flex.json --hub-ledger PRIVATE/hub.sqlite --equity 50000 --mode dry_run
node _system/scripts/short_framework.cjs cover --input PRIVATE/cover-decision.json --broker PRIVATE/attributed-flex.json --hub-ledger PRIVATE/hub.sqlite --equity 50000 --mode dry_run
```

The default mode is `dry_run`. Even a dry-run entry handoff requires verified
underwriting, approved borrow, observed account state and a qualified USD stock
contract. Covers require an attributed short, fresh verified quote, an actual
exit reason (or explicit `operator_cover`) and unreserved whole-share quantity.
Reducing an existing short does not depend on approval for opening new shorts.

Load the resulting private `handoff.local.json` into the Framework workspace.
Its explicit preview button records an authenticated order intent. It does not
transmit. The existing desk/hub previews the exact contract and requires the
existing human approval and live interlocks. A deterministic request hash makes
repeated browser requests idempotent. The hub revalidates the private decision,
account, pending orders and expiry before submission. Changed size, account,
mode, price, evidence or engine closes the path and requires a fresh review.

The hub needs Node 24 on PATH, or an explicit `SHORT_FRAMEWORK_NODE` executable.
Its verifier reads local files and SQLite only. It adds no Gateway contact.
The existing bridge remains human-triggered, single-ticket, client 91, with its
snapshot cleanup, connection budget, ownership and cancellation controls intact.
Do not add a scheduled broker session or restart the shared Gateway.

Live **entry** additionally requires the existing user-owned policy approval at
`_system/reviews/approved/short_framework_v1.json`, bound to the exact policy
hash, plus the completed evidence review. This implementation does not create
that approval. The existing review milestone is 100 completed prospective events
across 60 issuers **for the same frozen policy**, with positive observed cost
stress, independent reviews, calibrated entries/covers, reconciliation and
completed obligations. Meeting the count is a review trigger, not proof of an
edge or automatic production authority.

Merge and host deployment are separate: the known hub host uses a copied repo.
Install the code/runtime/private state there only through its existing deployment
process. No deployment, live order or Gateway probe was performed here.

## Validation

```powershell
node --test _system/scripts/tests/test_short_framework.cjs
node --test dashboard/cloudflare/test-short-framework.mjs dashboard/cloudflare/test-command-channel.mjs dashboard/cloudflare/test-command-peek.mjs dashboard/cloudflare/test-order-expiry.mjs _system/scripts/tests/test_short_profit_program.cjs
node _system/scripts/tests/test_short_framework_browser.cjs
python -m pytest _system/trading/portfolio_hub/tests/test_orders.py _system/trading/portfolio_hub/tests/test_short_framework.py -q
```

The Node suites cover browser/Node decision equivalence, unavailable evidence,
future clocks, independent cohorts, sizing, partial/fractional liabilities,
immutable forecasts, source receipts, outcome reconciliation, current hub
reservations and the actual authenticated HTTP order route. The optional browser
check uses an isolated Chromium/Edge profile, desktop/mobile screenshots and
filter assertions. Set `SHORT_FRAMEWORK_BROWSER` for a different executable.
The CI workflow installs Node 24/Python 3.12 and runs the non-browser checks.

Local validation passed the Node suites and real desktop/mobile Edge checks,
including the actual Framework tab inside the existing strategy lab. The Python
hub tests were added to CI but could not be run locally because this workspace
has no Python runtime. A one-request live SEC discovery attempt failed at the
network connection and added no evidence; bounded discovery behavior is also
covered with deterministic HTTP fixtures.

Real source review, independent review, purchased/missing market evidence, actual
borrow approvals, broker fills and future observations remain external work.
The software exposes those gaps instead of generating substitute evidence.
