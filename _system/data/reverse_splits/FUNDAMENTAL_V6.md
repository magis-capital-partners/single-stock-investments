# Fundamental participation and Calmar study

This research implements the coverage-first experiment. It compares a genuinely
unfiltered reverse-split strategy against three fundamental policies with the
same account, entries, exits, execution-cost proxy and sizing constraints.
It does not promote a historical winner into a trading policy.

## Policies and comparison contract

1. No fundamental filter. Missing financial scores and absent payoff donors
   cannot exclude an otherwise eligible action.
2. Reported deterioration score at least 60.
3. Reported deterioration score at least 50.
4. Score at least 60 **or** a narrow cash-distress route: dated operating-company
   classification, fresh reported cash, TTM and latest-quarter cash runways each
   at most one year, operating losses, and an explicitly reported debt maturity
   in the next twelve months exceeding cash. A financing passage or authorization
   alone cannot establish this route.

Every policy starts with $50,000; enters the session after the split; has a
ten-session maximum hold and 20% profit target/20% stop; retains the $100 minimum,
0.1% prior share-volume cap, 2.5% position cap and three-name maximum; and reserves
the original 2% name/sleeve loss budgets under a +200% squeeze. Missing historical
borrow rates use 50% annualized with modeled settlement dates and holding costs.

Order size does not use an alpha forecast or a fundamental rating. Reserve carry
over the full planned holding horizon and rank simultaneous eligible events by
prior dollar liquidity. These common assumptions are intentionally independent
of the financial filter. The execution-cost proxy still needs twenty prior other
issuers. The final nine entry sessions are excluded for **every** policy so the
maximum horizon can mature, regardless of whether a particular trade later hits
its bracket early. Missing subsequent bars still create an unresolved liability;
they never become an entry exclusion.

The frozen 49-recent/89-full-history clean-data replay remains a separate
reference. It uses a forecast-dependent holding reserve and admission order.
Changes against that reference cannot be attributed solely to the score floor.

## Financial and market evidence

- SEC acquisition resumes hash-checked caches and durable issuer checkpoints.
  Exact issuer/former-name matches to a separate SEC submissions response bind
  Company Facts responses that omit their own CIK. Raw responses remain intact.
- Whole-entity XBRL extraction retains filing, public-use clock, currency,
  fiscal periods, accession, tag and source hash. New fields include restricted
  cash, short-term investments, current/short-term borrowings and twelve-month
  debt maturities. Restricted cash is not automatically spendable cash.
- Latest-quarter CFO is reported directly or reconstructed by subtracting
  matching fiscal YTD amounts. Annualizing a YTD amount as a quarter is forbidden.
  The standard IFRS `CashFlowsFromUsedInOperatingActivities` concept is recovered
  separately, without changing the legacy extractor's frozen aliases.
- Economic deterioration and evidence coverage are separate. Correlated accrual
  and cash-conversion measures share one earnings-quality family. Unreported
  current debt cannot silently become a zero in the new score. The legacy score
  is retained for audit. Current and noncurrent debt must match the flow period,
  and dated bank/lender/REIT classifications disable inapplicable lenses.
- Older annual results are shown as diagnostics, without cash projection or
  admission, until intervening results and financing are reconciled. Unknown
  annual filing frequency is not permission to relax freshness.
- A custom-tag mapping must be bound to one issuer, exact filing hash, metric,
  tag and cited locator, with a dated, outcome-blinded semantic review. No fuzzy
  mapping or current company classification changes an old decision.
- Price collection prioritizes already-high-scoring and recent entry gaps, using
  no subsequent returns. Each supplemental split segment needs at least three
  original nominal-close overlaps, at most 2% median discrepancy and 5% at the
  90th percentile. Original nominal prices take priority. Public chart volume
  supplies **no** additional verified capacity.
- ADV uses the preceding twenty **exchange sessions**, including missing-volume
  sessions in its denominator. It cannot substitute twenty arbitrarily old bars.

Verified market imports live in ignored
`local/fundamental_v6/verified_market_data.jsonl`. Records identify provider,
ticker/date, cited HTTPS source, nominal units, dated availability, identity and
split-unit verification, and a local receipt path/hash containing the exact
values. Volume also requires `scope="US_consolidated"`. Partial venue counts,
unverified proxies, conflicting values and changed receipts are rejected.
No actual broker exports are available; none are manufactured.

Optional custom mappings live in ignored
`local/fundamental_v6/custom_fact_mappings.json`, an array of records with
`cik`, `source_sha256`, `tag`, `metric`, `review_mode`, `outcome_blinded`,
`reviewed_at`, `rationale` and `locator`. The only accepted review mode is
`blinded_historical_reconstruction`; the source filing's clock controls use.

## Performance and validation

Publish full and recent account/trade/risk/cost/exclusion/yearly statistics and
source-cited financial packets. Unresolved admitted liabilities or margin
breaches suppress funded-account returns, drawdown and Calmar. Closed-trade
statistics in such a case are explicitly an incomplete subset.

Separate fresh-account chronological diagnostics cover 2018–2021, 2022–2024 and
2025 through the cutoff, with the same matured-entry rule at each boundary.
Stress borrowing and slippage at twice the base assumptions and impose at least
one billed borrow day. Replay after removing each policy's largest positive
issuer, as a retrospective concentration sensitivity rather than a tradable
filter. Daily-high drawdown is a conservative joint-mark bound, not evidence of
simultaneous prices or a successful forced liquidation.

Before calculating outcomes the plan declares minimum participation of thirty
trades, twenty companies and three active years; at least five trades in each
chronological period; positive median chronological Calmar; positive funded
profits in every cost stress and after removing the largest contributing issuer.
Among qualifying policies, show the participation/median-Calmar frontier and a
historical paper candidate. If none qualifies, publish that result explicitly.
These minimum counts do not establish statistical reliability.

All historical periods have been explored. Resampling and chronological replays
remain diagnostics. A hash-bound protocol is recorded for future paper
observations, with zero completed forward trades at implementation. No future
performance or completed underwriting is asserted.

## Completed replay · 2026-10-18

The expanded source pass confirmed 1,629 issuer identities and retained 7,625
filing documents. After action verification and deduplication, the comparison
contains 4,699 dated events; 1,201 have a numerical score. Another 815 have fewer
than three usable signals and 2,683 have stale or missing financial periods.
These are coverage counts, not executable trades. Supplemental price validation
accepted 630 bars across 25 symbols and zero volume observations. Of 500 new
public-price requests, 496 returned no history for the requested ticker.

The recent window is 2023-10-14 through 2026-10-13; full history starts
2018-05-01. Counts below use the common matured-entry rule and fixed account
contract above. All eight accounts reconcile with zero unresolved positions or
funding breaches. Drawdowns are daily closing account drawdowns.

| Policy | Recent trades / companies | Recent net profit | Recent drawdown | Recent Calmar | Full trades / companies | Full net profit | Full drawdown | Full Calmar |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| No fundamental filter | 192 / 178 | -$1,512.74 | 6.047% | -0.169 | 339 / 297 | -$3,457.38 | 8.471% | -0.100 |
| Score at least 60 | 45 / 42 | $764.99 | 0.333% | 1.523 | 88 / 80 | $309.77 | 1.300% | 0.056 |
| Score at least 50 | 58 / 55 | $971.43 | 0.339% | 1.899 | 114 / 104 | $256.23 | 1.779% | 0.034 |
| Score at least 60 or cash distress | 45 / 42 | $764.99 | 0.333% | 1.523 | 88 / 80 | $309.77 | 1.300% | 0.056 |

The lower floor adds 13 recent trades (28.9%) and 26 full-history trades (29.5%)
against the matched score-60 case. Its better recent Calmar does not persist
over full history or the median chronological period. All three fundamental
policies fail the doubled-slippage stress: full-history profits become -$256.71
at score 60 and -$445.21 at score 50. No policy qualifies as the historical paper
candidate. Four events meet the independent cash-distress route, but it admits
no additional trades under the common execution and capacity rules.

Complete underwriting, reconciled financing packages, actual locate approvals,
observed fills and imported verified full-market volume remain zero. The next
clean-data bottlenecks are dated financial contexts, delisted security identity
and price histories, and verified consolidated volume; collecting more filings
alone cannot remove the capacity policy. Future paper validation has zero
completed trades. No production or capital policy changed.

## Reproduce

Use the original frozen input root for `SOURCE`, without moving or altering its
licensed cache. Collection has a $0 data budget and stops on denied access.
No ThetaData, terminal, broker connection, live order or subscription is used.

```powershell
python -m _system.scripts.reverse_splits.clean_data_sources --source-root SOURCE --fetch --maximum 5000 --snapshot-name sources-v6.json --resume
python -m _system.scripts.reverse_splits.fundamental_study --source-root SOURCE --sources-snapshot sources-v6.json --fetch-financials --fetch-prices --publish
python _system/scripts/build_reverse_splits_dashboard.py
python -m pytest -q _system/scripts/tests/reverse_splits
```

The dashboard entry is **Short Alpha → Backtest → Compare no fundamentals
versus fundamental policies · all statistics**. Data files are
`fundamental_research.json` and `fundamental_packets/`. Individual licensed
price outcomes and full account paths remain in ignored `local/fundamental_v6/`.
