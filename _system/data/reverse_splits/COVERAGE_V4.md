# RSI-4: recovered data and documented estimates

This is a separate version of the shorts research. The original RSI-3 results
and the explored Calmar parameter search are preserved. All new data requests
use free, unauthenticated public resources. No ThetaData, broker connection,
paid provider request, model API, subscription or trial is used.

## Verified coverage recovery, October 16, 2026

The original 7,069-record catalogue now yields 4,332 unique prepared actions
after verification and deduplication. Reported numerical scores rise from 847
to 972; 881 of the current scores use the existing issuer identity and 91 use
an explicitly assumed company-name match. Another 3,360 scores are estimates,
including 219 informed by the company's older filings. They are never counted
as recovered reported financial scores.

On the **original scored-event-record denominator**, real public prices
recover 44 of the 70 missing recent entries, leaving 26. Across the full
history, they recover 121 of 233, leaving 112. Duplicate baseline records
remain in this comparison to reconcile the original counts; the repaired
portfolio deduplicates them. Recovered daily opens do not establish fills.

Of the 2,526 remaining raw-financial gaps, 2,470 lack an issuer identity and
56 have an identified issuer but no usable raw financial file. This makes
historical issuer reconciliation the main remaining acquisition task.
The collection also supplements 1,821 price symbols, replaces 45,264 partial
venue-volume observations and retains 29,419 public borrowing observations
across 141 symbols. Those borrowing indications supply no account approvals.

The recent ten-session, 20% target / 20% stop scenario closes 77 trades from
73 companies using reported scores, versus 111 from 100 companies when
estimated scores are allowed. The respective modeled net gains are about
$415 and $481 on $50,000. In the estimate scenario, doubling slippage changes
the gain to a $129 loss; using sixfold borrowing costs produces a $790 loss.
The conservative net-edge variant admits zero trades for these settings.
These are conditional research results through October 13, 2026.

RSI-4 also changes conviction discounts, financing assumptions and cost
reserves, and requires at least one billed borrowing day. Its performance
change from the earlier 46-trade result therefore cannot be attributed to
data repair alone. No additional parameter optimization was performed.
Full underwriting, reconciled financing packages, actual locates and observed
fills remain incomplete. The strict evidence case still admits zero trades.

## Read the dashboard simply

Open **Short Alpha → Backtest → Open expanded backtest · RSI-4**.

1. Start with **After split · 10 sessions · 20% target / 20% stop** and the
   recent three-year period. These are the earlier research candidate's exit
   settings, not newly optimized settings.
2. Compare **Recovered data · reported scores** with **Documented estimates**.
   The first requires enough reported numerical financial signals. The second
   permits estimates and identifies the trades relying on them.
3. Compare the **$25 minimum** and **1% volume capacity** rows. These show how
   deliberate sizing restrictions affect the number of trades. Larger orders
   include an added impact cost; the aggregate modeled squeeze-loss budget
   remains 2% of the $50,000 account.
4. Inspect the higher-borrow, double-slippage and 50%-access scenarios. A
   profitable result that depends on cheap borrowing or universal access is
   weaker than a result that survives those assumptions.
5. Choose **Explain**. The counts reconcile the period's candidates, admitted
   positions and first failing rule. Search any ticker and select it to see
   its reported amounts, estimated signals, provisional conviction, financing
   scenarios, all 27 framework assessments and dated citations.
6. Compare **At announcement** with **At entry**. A plan uses information known
   before the trade. The entry decision can use the opening benchmark and
   remaining portfolio capacity. Neither is an observed brokerage fill.

Net P&L subtracts modeled commissions, slippage, borrowing and identified cash
dividends. Annual return includes idle capital. Calmar divides that annual
return by the maximum daily account drawdown. An unresolved admitted liability
or funding breach suppresses performance instead of removing the trade. A
dash therefore means unavailable, not zero or profitable.

## How gaps are handled

**Announcement timing and actions.** Cached issuer filings can recover a
dated schedule when its effective date and ratio match the candidate action.
Public availability waits until the next Eastern day. A separate sensitivity
assumes a structured action was observable by its effective-day close. That
proxy never becomes a recovered announcement timestamp. Duplicate issuer,
effective-date and ratio records cannot inflate the trade sample. Clearly
identified ETFs, ETNs, warrants and preferred stock fall outside this sleeve.

**Identity.** A unique normalized company-name match can connect a candidate
to a SEC issuer. This is a documented historical-identity assumption. A
current ticker alone cannot identify a recycled historical security. Unknown
identities remain unknown; no account approval follows from any match.

**Financials.** Reported scores retain the original as-filed methodology and
cutoff. Missing mechanism scores use the median of earlier observed other
issuers, with one latest observation per issuer. Same-time observations and
the same issuer are excluded. Before peers exist, the fallback is neutral
50/100. Missing cash, debt, shares or revenue are never filled with zero.
The modeled score and reported score are separate fields. Provisional sizing
conviction discounts missing signals and assumed identity. Only reported-score,
non-proxy-clock observations train historical payoff comparisons.

**All 27 frameworks.** Six numerical deterioration mechanisms can be assessed
from reported facts. Prior filing passages provide dated context for other
routes. Unknown mechanisms remain neutral and add no positive edge. A
recorded assessment is not a completed valuation, catalyst or underwriting
review. No fraud or bad-actor allegation is inferred from keywords.

**Financing.** A reverse split changes the share units and creates **zero
economic dilution by itself**. The model considers no issuance and issuance
at 15% and 30% discounts. When cash burn and dollar capitalization are known,
the six-month financing need informs the assumed number of shares. Otherwise
a clearly labeled 25% issuance-size scenario is used. Scenario weights depend
on reported runway; absent runway uses a stated prior. Proceeds are included:

`per-share value change = (1 + new/old shares × (1 − discount)) / (1 + new/old shares) − 1`

These scenarios do not establish actual warrants, conversions, ATM utilization
or issuance dates. They guide comparable matching and risk interpretation;
their expected effect is never added again to historical price returns.

**Prices.** Real free daily charts supplement unavailable nominal observations.
Later split adjustments are inverted. Each split segment is checked against
overlapping original nominal prices; an already-nominal public segment is
handled separately. Conflicting units are rejected. Segments lacking overlap
retain an explicit conversion assumption. Existing provenance-bound nominal
observations take priority. No missing entry, exit or delisting price is
invented. A public daily open is not proof of an official auction or fill.
Yahoo data can contain split and other errors, as its open-source client
[documents](https://ranaroussi.github.io/yfinance/advanced/price_repair.html).

**Slippage and capacity.** Earlier other-issuer measured depth is preferred.
When missing, an assumed spread floor of the greater of 0.5% or one cent divided
by share price is combined with `2 × prior daily volatility × sqrt(order dollar
size / prior daily dollar volume)`. The uncertainty reserve rises when facts
are missing. Increasing the volume limit adds impact rather than preserving
the small-order cost. Whole shares, commission minima, margin, concurrent names
and aggregate stress limits still apply.

**Borrowing.** The free one-year public rate collector is expanded to the
prepared cohort. A completed daily record becomes usable on the following
Eastern day and must be within 24 hours of the decision. Historical symbol
continuity remains assumed. A public inventory indication can be zero and
still does not establish an account locate. Missing rates use a 50% annualized
fallback; double and sixfold fee scenarios scale both public proxies and the
fallback. The fee remains modeled, rather than an actual loan charge.

For each earlier comparable holding-duration scenario, the model projects the
new trade's settlement calendar and then calculates daily borrowing:

`daily fee = nominal shares × ceil(1.02 × nominal reference price) × annual rate / 360`

It averages those possible costs before entry. It does not use the tested
trade's later exit to estimate its own holding period. Settlement lags, weekend
days, known split units and at least one billed day are included. Future
rate/recall paths remain unknown. The [broker's collateral
description](https://www.interactivebrokers.co.uk/en/software/tws.bak/usersguidebook/specializedorderentry/about_stock_borrow_loan.htm)
explains why low-price names can cost much more than notional × APR.

For example, a $500 short at $0.25 involves 2,000 shares. Rounded collateral is
$1 per share, or $2,000. At 50% annualized for seven billed days, modeled
borrowing is about **$19.44**. The same notional at $5 involves 100 shares and
$6 collateral per share, giving about **$5.83**. These examples exclude other
fees and illustrate the holding-period calculation.

**Access and tails.** Borrowing/execution access is conditional. A fixed,
identity-seeded 50%-access scenario is replayed without selecting its seed
for results. A separate $1,000 loss deduction illustrates one additional 2%
account loss; it is not an observed event, a maximum loss, or a recalculated
Calmar. A stop cannot guarantee an execution price or prevent a gap.

**Cash adjustments.** Available public dividends become modeled payment-in-lieu
costs when the position was open before the ex-date. They are charged on the
ex-date as a conservative payment-timing assumption. Missing dividends,
fractional settlements, mergers and other cash adjustments remain gaps.

## Reproduce using only free inputs

Run from the repository root. `SOURCE` is the original SSI reverse-split data
directory containing the frozen October 13 run and cached SEC files.

```powershell
python -m _system.scripts.reverse_splits.coverage_research --source-root SOURCE --collect --fetch --publish
python _system/scripts/build_reverse_splits_dashboard.py
python -m pytest -q _system/scripts/tests/reverse_splits
```

The expanded public-borrow collector is separately available as
`coverage_data.collect_expanded_borrow(source, destination, fetch=True)`.
It reads only the free one-year public ticker responses and has no credentials.
For the full acquisition sequence, including exact gaps and partial-venue
volume completion, use the dedicated command before the replay:

```powershell
python -m _system.scripts.reverse_splits.coverage_data --source-root SOURCE --fetch
python -m _system.scripts.reverse_splits.coverage_research --source-root SOURCE --publish
python _system/scripts/build_reverse_splits_dashboard.py
```

Omit `--fetch` to use only cached responses. The three acquisition phases have
separate maximum request counts of 3,000, 1,000 and 1,500; all have a $0 price.
`coverage_data.refresh_cached_inputs(source, destination)` reruns nominal-unit
and identity checks on already fetched responses without network access.

Acquisition uses bounded requests, cached URL/content hashes, SEC pacing of
at most two requests per second and public borrow pacing of one per second.
The [SEC provides free public financial data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).
Raw price observations and source caches remain ignored/local. Derived
summaries, name packets and case audits are published with hashes and checked
for reconciliation, future-data leakage, scope and cost claims.

The strict case still requires dated complete underwriting, actual entry
locates and execution evidence. Those requirements cannot be turned into
historical facts by making an assumption. Existing prospective collection
continues to build public disclosure and borrow vintages; it does not rewrite
older predictions.
