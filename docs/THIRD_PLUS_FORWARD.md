# Frozen 20-session forward comparison

This is the implementation of research steps 1–3: freeze a policy, expose its
candidate decisions, and collect prospective execution/cost/exit evidence. It
has no order authority. A completed historical test is not a completed forward
test: new entrants must actually pass through their future holding periods.

Open **Short Alpha → Backtest → Follow the frozen 20-session policy**, or
`#/ideas/short-alpha/forward`.

## The two fixed research books

`_system/data/reverse_splits/third_plus_forward_v1/policies.json` contains the
creation time and SHA-256 of each complete policy. `freeze` is idempotent and
rejects changed definitions. Any change requires a new policy version and a
separate comparison; existing decisions are retained.

| Rule | Treatment | Control |
|---|---|---|
| Third or later documented reverse split | Required | Required |
| No single adjusted daily closing-price gain ≥50% in five completed sessions | Required | Required |
| Negative reconciled trailing-12-month operating cash flow | Required | Required |
| Effective-session close below open and in bottom 25% of nonzero daily range | Required | Omitted |
| Requested position ceiling | $100,000 | $100,000 |
| Concurrent issuer slots | 3 in its own book | 3 in its own book |
| Gross / minimum +200% squeeze additional-loss budgets | $300,000 / $600,000 | Same |
| Holding period | 20 exchange sessions including entry | Same |

Financial extraction calls the **same** `third_plus_signal/features.cjs`
`financialSnapshot` used for the historical study, including conservative
filing availability, same-currency reconciliation and 200-day freshness.
Unknown borrowing remains assumed accessible; unknown required financial or
price signals remain unknown. A borrowing indication is never promoted to a
locate approval.

The first complete snapshot after the effective-session close is frozen before
the next eligible opening. If required inputs remain unknown, record an
abstention during the final five minutes before entry. If a scheduled runner
arrives late, record a missed entry; never recreate an earlier decision. Public
source discovery is bounded and incomplete, and the screen says so.

Entry is 09:31–10:31 Eastern, after the effective day and the public-source
availability delay. Use the actual exchange calendar, including daylight-saving
changes, holidays and shortened sessions. Cover from 90 minutes to 15 minutes
before the close of session 20. Two subsequent sessions are the retry window.
Unresolved positions remain open after that window; no estimated liquidation
turns them into completed forward trades.

The frozen execution reference is E2, 10% participation, $2,000 children,
500 ms acknowledgement delay, five-second minimum repricing, 50% eligible-flow
capture, 86 bp half-spread, 10 bp additional impact per side, 50% annual borrow,
and $0.01/share locate with a $5 minimum. These are comparison assumptions,
not observations or commands. Actual order attempts and fills need sourced
evidence; public daily bars do not simulate a queue or create fills.

## What runs automatically

The existing `reverse-split-borrow-history.yml` research workflow also runs:

```powershell
python -m _system.scripts.third_plus_forward monitor --max-requests 30
python -m _system.scripts.third_plus_forward check
```

It runs on GitHub-hosted infrastructure, using the existing disclosure ledger,
bounded public SEC companyfacts and public daily market references. It reuses
the existing checksum-verified public IBKR borrowing snapshot. The new monitor
does not open another stock-loan download, broker login or market-data session.
It never uses ThetaData or the shared Gateway. Public-source failures are
reported and do not become clean financials, zero costs or successful fills.

The workflow's existing schedule includes an after-close observation in either
Eastern time regime, allowing decisions to freeze before the following open.
GitHub schedules can run late; this is an observation workflow, not an execution
clock. Existing disclosure discovery may miss companies or deliver them late;
unresolved announcement leads and source coverage are visible separately.

Files committed by the workflow:

- `policies.json`: unchanged rules and hashes.
- `journal.jsonl`: append-only, hash-chained public research evidence.
- `status.json`: source receipts, coverage, errors and update time.
- `dashboard/data/third_plus_forward.json` and its manifest: allowlisted view.

Every enrollment binds the input snapshot, public-source hashes, issuer,
decision, exact entry/cover schedule and requested budget. The snapshot retains
the six public daily price observations and the selected financial snapshot,
including its cash anchor and operating-cash-flow components, so later provider
revisions cannot erase the evidence used for a decision. These are new public
research observations; licensed historical intraday inputs remain local.
Each book reserves
capacity independently. An unobserved entry remains unresolved until its order
outcome is supplied; a small partial fill consumes one issuer slot. A sourced
zero-fill terminal order releases its reservation after the entry window, never
retroactively. Covered shares release position capacity; outstanding financing
and loan-return reconciliation remain visible in the ledger.

## Record paper or broker observations

The importer accepts explicit evidence, not trading instructions. Its input is
an array of records. Each record carries:

| Field | Meaning |
|---|---|
| `kind` | `borrow`, `quote`, `reference`, `order`, `fill`, `cashflow`, `loan_return`, `action`, `closure`, or `exception` |
| `event_id`, `issuer_id` | Exactly the enrolled event and issuer |
| `policy_id`, `policy_sha256` | Exactly one frozen policy |
| `evidence_id` | Stable unique identifier; repeated identical imports are harmless |
| `observed_at`, `known_at` | Explicit timezone; observation ≤ availability ≤ import time |
| `source` | `url`, original-byte `sha256`, and row/page `locator` |
| `environment` | `paper` or `broker` for orders, fills and economic records |

Source references can be public HTTPS, the existing public IBKR file, or
`paper-export://<reference>` / `broker-export://<reference>`. Supply original
source documents to the importer; it checks their actual SHA-256 bytes.
Enrollment records cannot be imported or backdated.

Additional fields by record:

| Kind | Required economic fields |
|---|---|
| Borrow | `status`: indication/approval/unavailable; `apr` as fraction or null; available quantity if known. Approvals stay private. |
| Quote | Positive `bid`, `ask` ≥ bid. This remains a quote reference, not a fill. |
| Reference | Positive `price`, `day`, `basis`. Daily marks do not complete a trade. |
| Order | `phase`: entry/cover; `order_id`; `requested_shares`; `limit_price`; `status`: submitted/rejected/cancelled/expired/uncertain. |
| Fill | Matching `order_id`; globally unique `execution_id` per environment; entry/cover `phase`; positive `shares`, `price`; nonnegative `commission_usd`; `observed: true`. |
| Cash flow | Signed `amount_usd` (expenses negative); category borrow/dividend/locate/commission/credit/other. Include zero borrow/locate records when genuinely zero. |
| Loan return | Positive `shares` in the current adjusted share basis. |
| Action | Positive `new_shares_per_old`, effective `day`; e.g. 0.1 for a 1-for-10 reverse split. Does not rewrite cash proceeds. |
| Closure | `positions_zero`, `loans_zero`, `costs_reconciled` all true; quantities and loan returns must reconcile. |
| Exception | `issue`, `detail`, effective `day` when relevant. An early paper cover also needs `exception_reason`. |

Paper import:

```powershell
python -m _system.scripts.third_plus_forward import --file C:/research/paper-records.json --source-document C:/research/paper-export.csv
python -m _system.scripts.third_plus_forward publish
```

Broker imports **must** use an ignored or external private directory:

```powershell
python -m _system.scripts.third_plus_forward import --file C:/research/broker-records.json --source-document C:/research/flex-export.xml --private-work C:/research/third-plus-private
python -m _system.scripts.third_plus_forward private-report --private-work C:/research/third-plus-private
```

The private chain references public frozen enrollments without copying broker
records into the public journal. Its report stays in that private directory.
Broker account identifiers, execution IDs, orders, approvals and raw exports
never enter the public dashboard projection. The publisher rejects a broker
record if one is accidentally placed in the public journal. Importing already
observed broker records grants no authority to place a trade.

## Interpretation and review

Paper and actual-broker accounting are separate. Net marked P&L uses sourced
short proceeds minus sourced covers, commissions, signed cash flows and open
short liability. A missing mark stays unknown. Subsequent split notices block
marked P&L until a sourced quantity adjustment is supplied. Missing cover,
loan-return or cost reconciliation prevents a completed result. Later cost
adjustments require renewed closure reconciliation.

The screen measures actual entered size versus requested size, entry/cover
shortfall against quotes available at order submission, borrowing indications versus the
50% base, cover delays and concentration. Quotes must have been known by order
submission and no more than two minutes old to measure shortfall. Quotes imported
later can have an earlier documented availability; their import time remains
separate and auditable.

Review limits are fixed before new outcomes: at least 50 completed positions
and 30 completed issuers, positive after-cost closed profit, no overdue
unresolved positions, median entry and cover shortfalls ≤100 bp, 90th-percentile
cover delay ≤2 sessions, observed borrow indications ≤150% APR, explicit cost
evidence and strongest-five profit contribution ≤50% of net profit. These are
provisional research review criteria, not statistical proof, stop-loss orders,
an automatically approved live policy or a guarantee of liquidity. Missing
metrics do not pass review. A new policy version is needed to change them.

The first new position requires approximately four calendar weeks plus
settlement and cost reconciliation. No earlier historical trade counts toward
these prospective thresholds. See [the executor plan](THIRD_PLUS_LIVE_EXECUTOR_PLAN.md).

## Offline verification

```powershell
python -m unittest discover -s _system/scripts/third_plus_forward -p 'test_*.py'
node --test _system/scripts/third_plus_forward/dashboard.test.cjs
python -m _system.scripts.third_plus_forward check
```
