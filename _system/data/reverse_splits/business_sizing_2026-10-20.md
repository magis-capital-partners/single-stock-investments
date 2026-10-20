# Short strategy dollar profit and smaller position sensitivity

Retrospective research on the existing reverse-split event family. No broker orders or data downloads.

Test calendar: 2023-01-03 through 2026-10-13 (3.776 calendar years); 226 eligible test events, 56 initial earlier training events. All 57 declared sizing/cost variants are retained. The patient execution proposal is not implemented in this replay.

Annual profit below is total modeled dollar P&L divided by elapsed calendar years. It is not compounded CAGR or a forecast of future income. Target sizes are dollars of short notional, independent of how portfolio returns are presented.

## Fixed targets in the base cost case

| Target per name | Trades | Trades per year | Annual trading profit | Win rate | Worst trade | Closing equity max drawdown | Covers with modeled residual |
|---|---:|---:|---:|---:|---:|---:|---:|
| $250 | 170 | 45.0 | $12 | 46.5% | -$72 | $450 | 0 |
| $500 | 159 | 42.1 | $141 | 47.8% | -$130 | $702 | 0 |
| $1,000 | 142 | 37.6 | $309 | 49.3% | -$258 | $1,303 | 0 |
| $2,500 | 113 | 29.9 | $795 | 48.7% | -$646 | $2,646 | 0 |
| $5,000 | 81 | 21.5 | $1,648 | 53.1% | -$1,292 | $4,095 | 0 |
| $10,000 | 53 | 14.0 | $4,482 | 62.3% | -$2,588 | $4,628 | 1 |
| $25,000 | 32 | 8.5 | $8,117 | 62.5% | -$2,004 | $2,728 | 4 |
| $50,000 | 17 | 4.5 | $7,256 | 58.8% | -$17,367 | $17,367 | 2 |
| $100,000 | 8 | 2.1 | -$5,699 | 50.0% | -$48,090 | $50,499 | 1 |

Smaller targets admit additional names, so the rows have different traded populations. They are not a controlled comparison of the same trades at different sizes. Smaller fixed targets do not demonstrate more consistent profitability: every fixed target below $25k has negative 2026 P&L through October 13. Fixed $25k earns more dollars with a smaller observed closing drawdown than several smaller targets, but four of its covers require hypothetical completion beyond observed depth.

## Fixed targets with the existing net edge filter

| Target per name | Trades | Annual trading profit | Win rate | Closing equity max drawdown |
|---|---:|---:|---:|---:|
| $250 | 45 | $96 | 62.2% | $104 |
| $500 | 56 | $178 | 55.4% | $384 |
| $1,000 | 52 | $368 | 57.7% | $902 |
| $2,500 | 40 | $842 | 60.0% | $1,168 |
| $5,000 | 23 | $1,218 | 65.2% | $1,420 |
| $10,000 | 11 | $1,850 | 72.7% | $2,588 |
| $25,000 | 5 | $3,534 | 100.0% | $0 |
| $50,000 | 0 | $0 | No trades | $0 |
| $100,000 | 0 | $0 | No trades | $0 |

## Adaptive choice across all target sizes

The existing forecast selects among $250, $500, $1k, $2.5k, $5k, $10k, $25k, $50k and $100k. It must pass the original 0.5% expected net buffer, forecast cover support and shared risk limits. No target is selected using its realized test return.

| Cost case | Trades | Mean position | Annual trading profit | Closing equity max drawdown |
|---|---:|---:|---:|---:|
| Bull | 66 | $5,610 | $4,676 | $3,907 |
| Base | 56 | $5,292 | $4,095 | $3,677 |
| Bear | 41 | $5,972 | $4,022 | $3,226 |

Base takes 56 trades, about 14.8 per year, averaging $5,292. Trading profit totals $15,462; annualized profit is $4,095. The win rate is 53.6%, with 26 losing trades. Removing the single best trade reduces annualized profit to $2,422. One cover has modeled residual shares. The similar bull/base/bear totals partly reflect different selections; they are not a confidence interval for business income.

| Calendar period | Base adaptive trading profit |
|---|---:|
| 2023 | $202 |
| 2024 | $2,046 |
| 2025 | $10,889 |
| 2026 through October 13 | $2,326 |

## Business profit after operating expenses

Base adaptive can absorb only about $4,095 of annual overhead before its historical average operating profit reaches zero. The following costs are illustrations, not estimates of the current infrastructure bill.

| Assumed annual operating overhead | Annual operating profit at the base historical run rate |
|---|---:|
| $2,000 | $2,095 |
| $5,000 | -$905 |
| $10,000 | -$5,905 |

Trading P&L deducts modeled spread/depth costs, the declared impact buffers, censored-cover surcharges, fixed commissions and regulatory fees. Modeled same-day flat positions incur zero borrow charges and zero short-proceeds interest. Actual locate charges, routing differences, settlement failures, delayed covers and account funding remain unverified. Data subscriptions, infrastructure, labor, capital opportunity cost and tax are not deducted because their actual incremental amounts are unknown. Margin collateral is a capital requirement, not an expense to subtract in full.

Fee assumptions use the [IBKR Pro Fixed schedule](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php) and [SEC Section 31 rate](https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2), applied as a forward cost sensitivity throughout history. The normal $0.000195/share FINRA TAF is included conservatively, despite the temporary October-December 2026 holiday. This does not claim historical invoices or a future sliced-order commission total.

## Interpretation and remaining risk

Current evidence supports investigating a low-overhead side strategy generating hundreds to a few thousand dollars a year at smaller tickets under these assumptions. It does not establish a six-figure annual business. At an illustrative 2% average net trading edge, $5k entries earn $100 each; $100k annual trading profit would require 1,000 completed trades per year, before overhead. Neither that trade count nor maintaining that edge at greater breadth is established.

The drawdown figures use completed same-day P&L and omit unobserved intraday losses. A $5k short whose price triples loses $10k before costs. More fills and smaller individual loss dollars do not guarantee steadier annual profits or bounded squeeze losses. All results depend on unverified historical borrow approvals and executable routing; no live profit has been demonstrated by this experiment.

The new intraday execution proposal and additional event families remain separate research opportunities. Their hoped-for improvement is not included in the dollar estimate. The designated execution-study holdout file was not read. H20 is a retrospective sizing sensitivity, not a newly untouched out-of-sample result.
