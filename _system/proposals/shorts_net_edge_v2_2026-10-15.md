# RSI-2.0: announcement-time evidence and net-edge sizing

Research version requested October 15, 2026. This adds a separate backtest to
SSI Shorts → Backtest. RSI-1.0 and its original results remain available in the
same view. No production thresholds, live positions or order permissions change.

## What the number means

Net edge is expected short P&L as a fraction of opening gross exposure:

`E[gross short return] − E[round-trip slippage/depth] − commissions − E[borrow]`.

It is not the fundamental score or a probability derived from that score.
The return distribution uses up to 60 distinct other issuers with the closest
announcement-time deterioration and split ratio, and reconciled dilution when
both observations have it. Each donor must have closed before the announcement;
at least 20 prior issuers are required. Repeated splits use one most recent
observation per issuer. Cost observations also require completed prior exits,
another issuer, and sufficient observed reference-order depth. There is no
fallback to future data during warmup.

Report gross and net expected return, expected positive/negative payoff ratio,
win frequency, standardized third moment (skewness), expected holding minutes,
expected billed calendar days and the last training observation. Skewness is
the skew of **short P&L**, so its sign is not the stock-return skew sign.

## Evidence frozen at announcement

The existing conservative primary-schedule availability clock is the cutoff.
Raw SEC companyfacts are filtered by filing date **before** quarterly extraction.
Date-only filings on the announcement day are excluded. The latest period must
be no more than 200 days old and at least three numeric signals must exist.
The historical screen floor remains 60.

Current SEC industry metadata does not decide a historical rating. The strict
case requires a separately documented historical operating-company profile.
The numeric screen is a **provisional rating**. Full conviction combines 60%
fundamental deterioration with 40% documented framework support, on a 0–100
scale. These chosen research weights are not calibrated probabilities. All
27 Short Alpha frameworks, including gates and conclusion-only tags, require
dated evidence or a documented not-applicable assessment. The six existing
evidence lenses organize the reviews. Unresolved, contradicted or missing
frameworks block the full-framework case. All-not-applicable reviews cannot
establish a thesis. At least two impairment lenses, including cash/financing or
operating impairment, plus valuation and catalyst/path, must have support.

Later evidence and today's candidate ledger cannot update an earlier rating.
A retrospective review may cite historical documents, but its `known_at` must
be the source's actual availability, not a fabricated earlier review date.

## Reverse splits and financing dilution

A reverse split alone has **zero mechanical ownership dilution**. Keep it as
a discovery/context variable, not a direct percentage of expected profit.
Actual issuance, ATM draws, warrants and converts need reconciled share counts,
claims and proceeds. Authorized capacity is not actual issuance. Share counts
must use the same split basis. Reconcile mutually exclusive conversions and
exercise proceeds before providing the incremental share count.

For a documented scenario:

`ownership dilution = new shares / (existing shares + new shares)`

`per-share value change = ((common equity + net proceeds to common) / total shares) / (common equity / existing shares) − 1`.

Fair-value issuance can dilute ownership while leaving per-share economic
value unchanged. The return model matches on **per-share economic change**,
not raw issuance alone. It does not add a second dilution return to an empirical
return that already includes financing effects. Unknown dilution remains null.
The full-framework case requires a reconciled package (including explicit zero
issuance if applicable).

## Carry and the exit policy

Borrow is accrued on collateral and **settled calendar days**, not trading
minutes or a blanket annual fee deduction. Per-opening-notional cost is:

`sum(ceil(1.02 × daily collateral price) × daily annual rate / 360) / opening price`.

Compute that sum for every predicted exit scenario, then average; do not use
the tested trade's realized exit to predict its cost. Daily prices and annual
rates may vary when supplied as explicit ex-ante scenarios. The current replay
holds forecast collateral at the announcement-price projection and assumes a
50% annual rate when a dated approved quotation is absent. These are assumptions,
not historical invoices.

Settlement uses the exchange calendar, T+2 before May 28, 2024 and T+1 thereafter.
Example: a Thursday short and Friday cover under T+1 settle Friday and Monday,
respectively: **three** billed calendar days. Same-day ordinary short and cover
settle together and have zero ordinary carry under matched settlement. A separate
minimum-one-day pre-borrow sensitivity applies a full day's fee. Do not multiply
that minimum by hours/24. Broker-specific minimums, recalls, rebates, dividends
owed and exceptional settlement terms require additional dated inputs.

The replay compares close, 60-minute and 10% profit take / 20% adverse trigger /
close exits. Each exit has its own prior-only holding-time and payoff distribution.
Trigger prices use observed path marks and delayed marketable covers; gaps and
halts can overshoot. Unobserved exits stay in P&L with explicit estimates. The
carry engine supports multi-day exit scenarios; this release claims **intraday
backtest results only**.

Sources: [IBKR borrow-fee calculation](https://www.ibkrguides.com/reportingreference/reportguide/borrowfeedetails_default.htm),
[IBKR settled short positions](https://www.interactivebrokers.com/en/pricing/short-sale-cost.php),
[SEC settlement transition](https://www.sec.gov/newsroom/press-releases/2024-62),
[SEC reverse split definition](https://www.investor.gov/introduction-investing/investing-basics/glossary/reverse-stock-split).

## Sizing and exclusions

Nonpositive expected net edge receives zero shares. Positive edge uses quarter
mean/second-moment sizing multiplied by the evidence rating. Apply the smaller
of 2.5% opening notional and 0.5% account loss under a +200% correlated squeeze,
including costs and triple-rate carry on triple-price collateral, then the
remaining 2% sleeve stress budget, three names, 60% entry-margin budget,
0.1% verified prior venue ADV, displayed decision depth, approved entry inventory
where available, and whole shares. A $100 minimum and order-size commission
recheck can veto the trade. Stops do not replace the squeeze budget.

Announcement borrow evidence informs the forecast. A separate fresh entry
locate, known before the entry and no older than four hours, is required by the
full-framework case; an earlier announcement locate is not an execution approval.

Equal-size, fundamental-only and net-edge variants share the forecastable
cohort, exit, capital, risk and execution rules. The full-framework variant
additionally requires dated complete reviews, reconciled dilution, identity,
announcement borrow terms and fresh entry inventory. Its missing-evidence
exclusions remain visible.

## Initial replay and its limits

The frozen input contains **691 priced events**, of which **331** have numeric
announcement-time ratings. No complete historical framework packages,
reconciled financing packages or approved historical locates exist in this
input. The full-framework case therefore has no admitted trades.

The primary net-edge case also admits zero trades: costs consume most gross
edges; remaining names fail restrictions, funding/capacity, the fundamental
floor, or order-size commission checks. Zero trades is a filter result, not
profitable performance. Do not relax thresholds after inspecting this result.

This is an already explored, completed-and-priced split sample. It excludes
cancelled and unpriced announcements and cannot validate a strategy on all
announcements. Ticker/security-class aliases need historical reconciliation;
current industry metadata is excluded from the numeric ratings. Closing drawdown does not establish intraday
margin survival. No incremental benefit from the qualitative framework or
actual dilution is claimed without dated evidence. A prospective all-announcement
cohort is needed before testing any such claim.

## Import and reproduction

`_system/scripts/reverse_splits/net_edge.py` contains pure research calculations;
`net_edge_research.py` replays the existing frozen local prices/quotes. Neither
module starts a data session or contacts a provider or broker.

From `_system/scripts`, run:

```text
python -m reverse_splits.net_edge_research --publish
python build_reverse_splits_dashboard.py
```

CI embeds the committed derived summary, so deployment needs no quote cache or
raw companyfacts. Raw prices and order books remain local. The manifest binds
source input hashes, companyfacts, evidence snapshots, review import and code.

Optional append-only review import: `_system/data/reverse_splits/net_edge_reviews.jsonl`,
or `--reviews <path>`. Each JSONL row has `event_id`, timezone-aware `known_at`,
`identity_reconciled`, and `frameworks` entries. Every framework entry has
`framework`, `known_at`, `source_url`, `locator`, `mechanism`, `contrary_evidence`,
`falsifier`, and `status` (`supported`, `contradicted`, `unresolved`, or
`not_applicable`). Later revisions are filtered before selection.
The strict case also requires `operating_profile: "operating"`,
`operating_profile_source_url`, and `operating_profile_locator` in the dated row.

Optional `dilution` has `known_at`, `source_url`, `locator`, `shares_before`,
`incremental_shares`, `common_equity_value_before`, and `net_proceeds_to_common`.
Optional `borrow` has `known_at`, `approved`, `reference`, `issuer`, `shares`,
and `annual_rate` (fraction: 0.5 means 50%). A separate `entry_borrow` with the
same fields records executable inventory as of entry. Its wrapper row and its
own clock must both precede entry. Public availability is not approval.

Full per-case trade and decision ledgers and frozen evidence snapshots are in
`_system/data/reverse_splits/local/net_edge_v2/`. The dashboard exposes the primary
policy's per-name audit and all 24 account comparisons.
