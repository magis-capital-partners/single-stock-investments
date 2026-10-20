# Patient short entry at $25k and $50k targets

Retrospective sensitivity, 2023-01-03 through 2026-10-13. All 96 declared variants retained. 551 primary events; 325 outside the old unrestricted cohort. No broker orders or paid data. H21 was declared before its replay, after extensive prior examination of the underlying event sample. H22 was declared after H21 results but before its additional participation replays.

Dollar trading profit below deducts sampled-price execution costs, case impact buffers, child-order commissions and current regulatory-rate sensitivities. Annualized profit divides total by elapsed calendar years; it is not a forecast of annual business revenue. Borrow approvals, locate fees, overhead, capital opportunity cost and tax are unverified or excluded. Same-day flatness is conditional on completing every cover.

Timing reconciliation: the legacy cohort has 325 restricted events at the instant of the open. Cached status shows nine more restrictions triggered within the first second, giving 334 by open+1 second. The new replay uses the status at each execution interval, including later intraday triggers; earlier published cohort labels are preserved for reproducibility.

## What changed and why

| Old assumption | Audit | New sensitivity |
|---|---|---|
| Exclude SSR-active names | A short-sale price restriction is not a blanket short-sale ban. | Include them with offers above the sampled bid and 25/50/75% assumed capture. Live Rule 201 compliance still requires current NBBO. |
| Entire target must fit one opening book | A snapshot cannot establish capacity available over several hours. | Keep partial fills and work orders over 30/60/120/240 minutes. |
| Never enter more than 3% below the opening midpoint | This is an absolute price anchor, not a measure of our own impact; it can reject a profitable trade after an unrelated market move. | Price against contemporaneous quotes, with a declared impact buffer. Delayed entry naturally loses any decline that occurred before the fill. |
| Listing venue volume represents opportunity flow | Understates recorded capacity when other exchanges also trade the stock. | Sum distinct Nasdaq/Arca/EDGX and listing feeds where available, without double-counting overlapping daily/monthly files. Other venues and off-exchange prints remain missing. |
| Forecast net return must exceed 0.5% | The cutoff and the small-sample forecast are not independently validated. | Remove the forecast filter for this experiment; losing names remain. |
| Old $500 depth proxy and fixed opening/closing half-spread charge | Not calibrated to patient $25k-$50k orders. | Use quotes along the execution path, no duplicate legacy spread/depth charge. Impact buffers are assumptions, not measured market impact. |
| Three-name cap | A portfolio policy, rather than per-stock execution capacity. | Show all opportunities, aggregate exposure and margin; do not change live risk policy. |
| Same-day cover completion beyond observed depth | Potentially optimistic rather than conservative. | Count unsupported covers, charge an explicit surcharge, and show failed-cover gap exposure. No closed-position profitability claim without validating those exits. |

## Flow-based estimates

Use 5% of observed one-second trading volume, starting one minute after the open. For restricted intervals, estimate the portion trading at or above a bid-plus-tick offer by spreading each one-second bar over its tick prices, then apply the case capture rate to that 5% allocation. This is a bar proxy, not observed signed flow, queue priority or executed short orders. The target is a dollar ceiling; partial fills reduce actual position size.

| Target | Entry window | Flow rate | Case | Trades | SSR/prudent restricted trades | Mean position | Annual profit | Closing DD | Covers requiring assumed completion |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| $25,000 | 30 min | 5% | bear | 523 | 312 | $2,089 | $7,324 | $9,855 | 124 |
| $25,000 | 60 min | 5% | bear | 544 | 329 | $2,708 | $6,252 | $11,193 | 179 |
| $25,000 | 120 min | 5% | bear | 549 | 334 | $3,488 | $1,806 | $14,276 | 233 |
| $25,000 | 240 min | 5% | bear | 551 | 334 | $4,380 | -$4,833 | $26,461 | 301 |
| $50,000 | 30 min | 5% | bear | 523 | 312 | $2,902 | $13,468 | $14,926 | 125 |
| $50,000 | 60 min | 5% | bear | 544 | 329 | $3,680 | $13,594 | $16,320 | 182 |
| $50,000 | 120 min | 5% | bear | 549 | 334 | $4,676 | $8,841 | $19,035 | 238 |
| $50,000 | 240 min | 5% | bear | 551 | 334 | $5,983 | -$1,744 | $24,807 | 306 |
| $25,000 | 30 min | 5% | base | 531 | 320 | $2,458 | $11,383 | $9,726 | 152 |
| $25,000 | 60 min | 5% | base | 547 | 332 | $3,249 | $10,414 | $11,417 | 238 |
| $25,000 | 120 min | 5% | base | 549 | 334 | $4,278 | $7,029 | $15,426 | 323 |
| $25,000 | 240 min | 5% | base | 551 | 334 | $5,398 | $300 | $19,621 | 413 |
| $50,000 | 30 min | 5% | base | 531 | 320 | $3,400 | $19,334 | $17,784 | 154 |
| $50,000 | 60 min | 5% | base | 547 | 332 | $4,439 | $21,133 | $19,706 | 242 |
| $50,000 | 120 min | 5% | base | 549 | 334 | $5,730 | $17,204 | $23,038 | 328 |
| $50,000 | 240 min | 5% | base | 551 | 334 | $7,368 | $8,241 | $23,604 | 420 |
| $25,000 | 30 min | 5% | bull | 535 | 324 | $2,781 | $13,491 | $10,096 | 189 |
| $25,000 | 60 min | 5% | bull | 547 | 332 | $3,723 | $12,678 | $12,331 | 278 |
| $25,000 | 120 min | 5% | bull | 549 | 334 | $4,919 | $8,989 | $16,809 | 374 |
| $25,000 | 240 min | 5% | bull | 551 | 334 | $6,306 | $1,107 | $21,987 | 448 |
| $50,000 | 30 min | 5% | bull | 535 | 324 | $3,813 | $23,185 | $18,284 | 192 |
| $50,000 | 60 min | 5% | bull | 547 | 332 | $5,019 | $24,103 | $20,712 | 282 |
| $50,000 | 120 min | 5% | bull | 549 | 334 | $6,544 | $20,647 | $25,194 | 380 |
| $50,000 | 240 min | 5% | bull | 551 | 334 | $8,425 | $12,014 | $25,760 | 455 |
| $25,000 | 30 min | 10% | bear | 533 | 320 | $3,002 | $7,001 | $11,037 | 124 |
| $25,000 | 60 min | 10% | bear | 548 | 332 | $3,974 | $3,377 | $16,019 | 176 |
| $25,000 | 120 min | 10% | bear | 550 | 334 | $5,111 | -$2,470 | $29,367 | 228 |
| $25,000 | 240 min | 10% | bear | 551 | 334 | $6,399 | -$14,055 | $57,666 | 295 |
| $50,000 | 30 min | 10% | bear | 533 | 320 | $4,103 | $13,898 | $19,968 | 124 |
| $50,000 | 60 min | 10% | bear | 548 | 332 | $5,380 | $11,569 | $22,715 | 179 |
| $50,000 | 120 min | 10% | bear | 550 | 334 | $6,967 | $2,505 | $29,700 | 233 |
| $50,000 | 240 min | 10% | bear | 551 | 334 | $8,762 | -$10,934 | $56,232 | 302 |
| $25,000 | 30 min | 10% | base | 537 | 324 | $3,612 | $12,325 | $10,658 | 153 |
| $25,000 | 60 min | 10% | base | 549 | 333 | $4,839 | $9,475 | $14,953 | 234 |
| $25,000 | 120 min | 10% | base | 550 | 334 | $6,320 | $4,245 | $23,403 | 317 |
| $25,000 | 240 min | 10% | base | 551 | 334 | $8,025 | -$8,015 | $46,214 | 406 |
| $50,000 | 30 min | 10% | base | 537 | 324 | $4,863 | $22,717 | $19,433 | 153 |
| $50,000 | 60 min | 10% | base | 549 | 333 | $6,478 | $20,857 | $22,770 | 238 |
| $50,000 | 120 min | 10% | base | 550 | 334 | $8,543 | $14,223 | $30,809 | 323 |
| $50,000 | 240 min | 10% | base | 551 | 334 | $10,799 | $955 | $38,999 | 414 |
| $25,000 | 30 min | 10% | bull | 539 | 326 | $4,074 | $14,385 | $10,963 | 188 |
| $25,000 | 60 min | 10% | bull | 550 | 334 | $5,515 | $11,204 | $17,154 | 276 |
| $25,000 | 120 min | 10% | bull | 550 | 334 | $7,279 | $6,205 | $23,434 | 367 |
| $25,000 | 240 min | 10% | bull | 551 | 334 | $9,219 | -$5,921 | $44,853 | 440 |
| $50,000 | 30 min | 10% | bull | 539 | 326 | $5,523 | $27,223 | $20,121 | 189 |
| $50,000 | 60 min | 10% | bull | 550 | 334 | $7,409 | $25,780 | $24,450 | 280 |
| $50,000 | 120 min | 10% | bull | 550 | 334 | $9,823 | $18,659 | $33,345 | 374 |
| $50,000 | 240 min | 10% | bull | 551 | 334 | $12,614 | $3,230 | $43,102 | 449 |
| $25,000 | 30 min | 20% | bear | 537 | 324 | $4,403 | $5,949 | $16,102 | 120 |
| $25,000 | 60 min | 20% | bear | 549 | 333 | $5,771 | -$1,270 | $27,373 | 167 |
| $25,000 | 120 min | 20% | bear | 551 | 334 | $7,429 | -$11,644 | $62,531 | 213 |
| $25,000 | 240 min | 20% | bear | 551 | 334 | $9,265 | -$31,204 | $117,832 | 276 |
| $50,000 | 30 min | 20% | bear | 537 | 324 | $5,961 | $12,042 | $22,906 | 124 |
| $50,000 | 60 min | 20% | bear | 549 | 333 | $7,936 | $4,159 | $34,608 | 176 |
| $50,000 | 120 min | 20% | bear | 551 | 334 | $10,207 | -$8,165 | $67,339 | 228 |
| $50,000 | 240 min | 20% | bear | 551 | 334 | $12,800 | -$31,995 | $125,610 | 295 |
| $25,000 | 30 min | 20% | base | 540 | 327 | $5,261 | $12,635 | $14,118 | 145 |
| $25,000 | 60 min | 20% | base | 550 | 334 | $7,036 | $6,668 | $23,821 | 222 |
| $25,000 | 120 min | 20% | base | 551 | 334 | $9,186 | -$2,480 | $44,362 | 296 |
| $25,000 | 240 min | 20% | base | 551 | 334 | $11,441 | -$19,305 | $88,802 | 379 |
| $50,000 | 30 min | 20% | base | 540 | 327 | $7,186 | $24,017 | $21,414 | 153 |
| $50,000 | 60 min | 20% | base | 550 | 334 | $9,663 | $18,177 | $30,204 | 234 |
| $50,000 | 120 min | 20% | base | 551 | 334 | $12,619 | $7,617 | $47,813 | 317 |
| $50,000 | 240 min | 20% | base | 551 | 334 | $16,052 | -$16,973 | $94,826 | 406 |
| $25,000 | 30 min | 20% | bull | 542 | 329 | $5,978 | $14,894 | $17,780 | 178 |
| $25,000 | 60 min | 20% | bull | 550 | 334 | $8,079 | $9,315 | $23,581 | 262 |
| $25,000 | 120 min | 20% | bull | 551 | 334 | $10,530 | -$461 | $42,942 | 344 |
| $25,000 | 240 min | 20% | bull | 551 | 334 | $13,087 | -$16,249 | $86,286 | 414 |
| $50,000 | 30 min | 20% | bull | 542 | 329 | $8,106 | $28,687 | $21,933 | 188 |
| $50,000 | 60 min | 20% | bull | 550 | 334 | $11,033 | $22,376 | $34,319 | 276 |
| $50,000 | 120 min | 20% | bull | 551 | 334 | $14,533 | $12,497 | $46,890 | 367 |
| $50,000 | 240 min | 20% | bull | 551 | 334 | $18,440 | -$11,569 | $88,829 | 440 |

## Conditional target-fill scenarios

A separate what-if assumes equal-dollar minute slices fill throughout the chosen entry window: 100% of unrestricted slices and 25/50/75% of restricted slices in bear/base/bull. Unfilled restricted slices are canceled. Missing valid quotes also cancel their slices. This assumes liquidity; the required percentage of recorded volume is a diagnostic, not proof. These rates are fractions of proposed shares, not probabilities that an entire parent order fills.

| Target | Entry window | Case | Trades | Mean position | Annual profit | Closing DD | Entries requiring >10% of flow or missing flow |
|---|---|---|---:|---:|---:|---:|---:|
| $25,000 | 30 min | bear | 551 | $12,242 | -$86,914 | $328,151 | 425 |
| $25,000 | 60 min | bear | 551 | $11,957 | -$88,776 | $335,179 | 366 |
| $25,000 | 120 min | bear | 551 | $11,623 | -$93,741 | $353,926 | 301 |
| $25,000 | 240 min | bear | 551 | $11,204 | -$100,261 | $378,542 | 233 |
| $50,000 | 30 min | bear | 551 | $24,488 | -$186,409 | $703,803 | 472 |
| $50,000 | 60 min | bear | 551 | $23,917 | -$189,610 | $715,886 | 431 |
| $50,000 | 120 min | bear | 551 | $23,249 | -$197,602 | $746,059 | 393 |
| $50,000 | 240 min | bear | 551 | $22,412 | -$206,513 | $779,705 | 336 |
| $25,000 | 30 min | base | 551 | $16,433 | -$55,936 | $212,570 | 468 |
| $25,000 | 60 min | base | 551 | $16,267 | -$61,533 | $233,000 | 422 |
| $25,000 | 120 min | base | 551 | $16,058 | -$70,329 | $266,160 | 386 |
| $25,000 | 240 min | base | 551 | $15,787 | -$80,778 | $305,127 | 324 |
| $50,000 | 30 min | base | 551 | $32,870 | -$117,938 | $447,844 | 499 |
| $50,000 | 60 min | base | 551 | $32,537 | -$128,855 | $487,683 | 481 |
| $50,000 | 120 min | base | 551 | $32,119 | -$145,020 | $548,778 | 438 |
| $50,000 | 240 min | base | 551 | $31,577 | -$161,699 | $610,818 | 403 |
| $25,000 | 30 min | bull | 551 | $20,624 | -$44,557 | $174,399 | 484 |
| $25,000 | 60 min | bull | 551 | $20,577 | -$52,819 | $203,720 | 457 |
| $25,000 | 120 min | bull | 551 | $20,493 | -$64,385 | $245,231 | 411 |
| $25,000 | 240 min | bull | 551 | $20,369 | -$77,129 | $291,612 | 374 |
| $50,000 | 30 min | bull | 551 | $41,252 | -$91,458 | $357,519 | 509 |
| $50,000 | 60 min | bull | 551 | $41,157 | -$107,724 | $415,202 | 493 |
| $50,000 | 120 min | bull | 551 | $40,988 | -$129,712 | $494,051 | 470 |
| $50,000 | 240 min | bull | 551 | $40,742 | -$151,054 | $571,158 | 436 |

## Cases, costs and cover risk

| Case | Assumed SSR capture | Extra impact per side | Assumed residual-cover surcharge |
|---|---:|---:|---:|
| bear | 25% | 25 bps | 5% |
| base | 50% | 10 bps | 2% |
| bull | 75% | 5 bps | 1% |

H22 adds 10% and 20% participation on recorded flow, for entry and cover, with impact buffers multiplied by sqrt(rate/5%). These are additional assumptions declared after observing H21, not independently calibrated rates. Missing venues mean participation in the full market can be lower than participation in the recorded subset. Higher participation can also move prices more than the assumed buffer. All 48 extra flow variants are retained alongside H21's original 48 results.

The impact buffer is deducted as a separate dollar cost, so it does not turn a modeled SSR offer into an illegal below-bid execution price. It is not calibrated from our own fills. Fees use one persistent child per occupied five-minute interval: actual broker treatment of replacements can add minimums. The first minute is excluded to avoid counting opening auction shares as continuous liquidity.

The cover schedule uses at most 5% of recorded volume from 90 to 15 minutes before the close. Every residual assumes completion at the last valid sampled ask plus the case surcharge and a separate child commission. P&L retains those costs and liabilities rather than dropping difficult trades. A missing valid final-15-minute quote is counted. No assumed closing completion is evidence of a completed cover.

If a cover fails, the marked short remains open. The published aggregate includes additional +20% and +100% residual-price stresses across all affected historical trades; these are total-period dollar sensitivities, not simultaneous portfolio losses or assigned probabilities. Overnight borrow, proceeds credit and gap paths must then be modeled explicitly; zero same-day financing would no longer apply.

## Risk, source quality and interpretation

CAGR/Sharpe/Sortino/Calmar use a hypothetical flat-core $10m NAV and daily closing conditional P&L. They are denominator-dependent; dollar profit and drawdown are the business metrics. Daily closing drawdown omits intraday adverse paths and unseen squeezes. No stop, profit take, forecast filter or hindsight selection is added. Holding longer to enter changes the price captured, so the opening gross return is not preserved for delayed fills.

Capital estimates sum individual intraday peaks by date, which can overstate coincident peaks. Margin uses a 100% house assumption plus low-price short floors; borrow collateral is shares times the dollar-rounded 102% quote mark. Collateral is restricted proceeds, not a second trading expense. Actual account margin and broker concentration requirements can differ. Historical borrow is assumed available: additional names may still be unavailable to short.

Coverage: {'venues': {'ARCX.PILLAR': 551, 'XASE.PILLAR': 34, 'XNAS.ITCH': 550, 'XNYS.PILLAR': 51, 'EDGX.PITCH': 549}, 'requests': {'have': 594, 'error': 3}, 'quality_audited': True, 'provider_flagged_events': 9, 'download_cost': 0, 'source_manifest_sha256': 'fa33191311894f99a49e590eda4cf6ec09f5bcd379783fdb07c455caf71534e1'}. The source manifest is private and hash-bound. Provider day-quality flags are counted against event sessions and retained rather than selecting events by data quality after seeing results. Data is partial multi-venue coverage, not consolidated US volume or verified NBBO. A zero-quote gate preceded every new download. Monthly files only batch transport; replay selects each event's exact session and never combines overlapping copies from the same venue.

Rule 201 basis: [SEC staff FAQ](https://www.sec.gov/rules-regulations/staff-guidance/trading-markets-frequently-asked-questions-7). Fees: [IBKR US stock commissions](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php), [SEC 2026 rate advisory](https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2). Normal TAF is retained as a forward sensitivity rather than extrapolating the temporary 2026Q4 holiday.

The original execution-study designated holdout file remains unread. This newer sample overlaps previously examined adaptive/portfolio research and cannot be presented as an untouched holdout. New event families, validated fills, account borrows and incremental live impact remain the steps that can establish production profitability.
