# Short entry capacity and an intraday execution proposal

Research proposal, 20 October 2026. The next execution test should allow partial positions and trade only while the remaining expected profit pays for entry, covering and uncertainty. More time can reveal replenishing liquidity, but it also allows the expected price decline to happen before entry. A $25k target should therefore be a ceiling rather than a requirement to complete.

The proposed algorithm below has not been backtested or used for orders. The numerical execution settings are research hypotheses. Current dashboard returns still come from the existing frozen protocols.

## What the entry price limit means

The adaptive sizing experiment decides one second after the scheduled open. It requires the *entire* requested target to fit in the cached bids at prices no lower than 97% of that snapshot's midpoint. It then sets an immediate-or-cancel limit at the last bid required and simulates the response book 100 milliseconds later. Partial response-book fills are possible; partial *admission* below the requested target is currently disallowed.

For a $10 midpoint, the admission floor is $9.70. A $25k target requires 2,500 shares. If the book has only 400 shares bid at $9.70 or better, the test refuses that target even if more shares appear later. “Completing $25k would breach the entry price limit” means there is enough total cached depth only at lower prices. A different exclusion identifies insufficient total cached depth even without this price floor.

The 3% is a declared modeling guard, **not a measured impact estimate**. It limits individual eligible prices rather than the average fill discount. It does not establish that our order would move the market down by 3%. It combines a static snapshot with a full-target admission rule, so it cannot answer how much could be accumulated patiently intraday.

## Reproducing the median cached bid capacity

For each of the 226 eligible events in the test calendar from 3 January 2023 through 13 October 2026 (actual event dates: 19 January 2023 through 9 October 2026):

```text
m = (best bid + best ask) / 2 at open + 1 second
L = 0.97 * m
Q = sum of cached bid shares at prices >= L
capacity = m * Q
actual cash from sweeping those shares = sum(price * shares)
```

The capacity calculation is uncapped. It values available *shares at the midpoint*, consistent with sizing a target as target dollars / midpoint. It is different from proceeds at actual bid prices. After sorting all 226 capacities, the median averages observations 113 and 114:

| Sorted observation | Midpoint value of eligible bid shares |
|---|---:|
| 113 | $2,499.7700 |
| 114 | $2,675.1875 |

`($2,499.77 + $2,675.1875) / 2 = $2,587.47875`, rounded to approximately $2,600. The median of actual sale cash across all 226 books is $2,542.83. The cached midpoint-valued capacity reaches $25k on 32 events, $50k on 17 and $100k on eight.

These are opening snapshots assembled from the available venue depth and sampled quotes. They are not a complete market-wide inventory of displayed, hidden and future liquidity. An unchanged quote cannot be counted as a fresh batch of shares every second. Replenishment, cancellations, latency and routing access can change what actually fills.

The calculation is reproduced by `_system/scripts/short_entry_capacity_audit.py`, which verifies the existing frozen input hashes. Its aggregate result is `entry_capacity_audit_2026-10-20.json`; named event rows and underlying quote values stay in `local/adaptive_sizing/20261020_v1/entry_capacity_audit.local.json`, sorted by capacity. Source strategy logic: `short_adaptive_sizing.py`, functions `candidate`, `take` and `load_rows`.

## What the research supports

Eight free full papers are saved under `local/literature/20261020_execution/papers/`. `intraday_execution_literature_2026-10-20.json` records source URLs, exact downloaded versions, page counts and SHA256 checksums. Full papers remain local; no paid data or paper access was purchased.

| Research and downloaded version | Relevant result | Implication for this experiment |
|---|---|---|
| [Cont, Kukanov and Stoikov, 2011 preprint, The Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402) | In 50 US stocks, short-interval price changes relate to order-flow imbalance, with greater sensitivity when depth is thin. | Observe additions, removals and executed flow as well as spread. One-second quotes are an incomplete proxy for the underlying events. |
| [Zarinelli, Treccani, Farmer and Lillo, 2014 preprint, Beyond the Square Root](https://arxiv.org/abs/1412.2152) | Institutional US metaorder impact varies with participation and duration; a single square-root curve does not capture their full sample. | Fit a cost surface by liquidity and trading rate. Do not import a universal coefficient or assume waiting removes all impact. |
| [Cartea and Jaimungal, February 2016 preprint, Incorporating Order-Flow into Optimal Execution](https://ora.ox.ac.uk/objects/uuid%3A88a23aea-ceb6-4bb0-8b59-fd594d8db92c/files/mcc6dd20ff20d6845755544cc66405abe) | Their model adjusts the execution schedule for expected future net order flow under linear impact assumptions. | Test selling into buying flow and adapting urgency. The paper's calibrated Nasdaq examples do not calibrate these reverse-split names. |
| [Lehalle and Neuman, June 2018 preprint, Incorporating Signals into Optimal Trading](https://arxiv.org/abs/1704.00847) | Their framework combines a price signal with transient impact; their empirical illustration uses 13 European stocks. | Compare the cost of waiting with the cost of trading now. Transfer the modeling structure, not the fitted parameters. |
| [Cont and Kukanov, November 2014 preprint, Optimal Order Placement in Limit Order Markets](https://arxiv.org/abs/1210.1625) | Queue position, order-flow distributions, fees and execution risk jointly affect the split between passive and aggressive orders. | Score passive and marketable children separately; touching an offer does not prove a passive fill. |
| [Hong, Li, Ni, Scheinkman and Yan, May 2015 working paper, Days to Cover and Stock Returns](https://www.nber.org/papers/w21166) | Scaling short interest by turnover captures a trading-cost dimension missed by short interest alone. | Constrain the position by the ability to cover as well as the ability to enter. Their historical return estimate is not an input to our expected alpha. |
| [Asquith, Pathak and Ritter, April 2004 working paper, Short Interest and Stock Returns](https://www.nber.org/papers/w10434) | Several short-interest return patterns depend on weighting and sample period. | Retain chronological validation, small-stock concentration checks and opportunity-level denominators. |
| [Frazzini, Israel and Moskowitz, December 2012 draft, Trading Costs of Asset Pricing Anomalies](https://pages.stern.nyu.edu/~afrazzin/pdf/Trading%20Cost%20of%20Asset%20Pricing%20Anomalies%20-%20Frazzini%2C%20Israel%20and%20Moskowitz.pdf) | Live institutional trades show the value of optimizing net returns, including intended trades that are delayed or unfilled. | Measure missed opportunity and actual implementation shortfall. Their wider equity sample cannot establish cheap fills in distressed microcaps. |

Two further relevant references were located but full papers were not obtained: [D'Avolio, The Market for Borrowing Stock](https://www.aqr.com/Insights/Research/Journal-Article/The-Market-for-Borrowing-Stock), whose public summary emphasizes loan supply and fees, and [Blau and Whitby, How Does Short Selling Affect Liquidity in Financial Markets](https://www.sciencedirect.com/science/article/pii/S1544612317303562), whose publisher abstract reports a small-cap spread relationship. The latter is observational portfolio evidence, not an estimate of the causal impact of our orders. These two are recorded as abstract-only; neither is counted among the eight downloaded full papers.

## Existing execution tests constrain the proposal

The earlier workstream A validation sample covers 2023-2024. In its bar-based passive model, a $25k offer fills completely within 15 minutes on only 4% of restricted sessions. For a $1,250 offer, full fill is 22.1%; unfilled names fall 2.44% while waiting, on average. This is evidence against an unchanged passive offer as the sole execution method, subject to that model's approximate queue and within-bar price assumptions.

The first-hour participation model produces median validation positions of $190 at 1% participation and $952 at 5%. At 1%, its estimated entry shortfall is 1.79%; estimated round-trip cost is 4.45%, including 2.73% in cached spread terms. Its realized short return after the modeled spread term is -0.21% before commissions and other unmeasured costs. These figures are not measured own-order impact: the model follows listing-venue bars, uses endpoint spread proxies and assumes some residual covers at the closing print. See the H18/H19 sections in `README.md` and `execution_realism.json`.

The new design must improve the decision about *when and how much* to trade. Simply extending the first-hour schedule would not address these weaknesses. The designated workstream A 2025+ holdout remains sealed and is not used to design this proposal.

## Proposed execution algorithm

### Allocate to incremental net profit

Treat $25k, $50k and $100k as maximum parent positions on a $10m portfolio. Permit smaller partial positions when they pay minimum commissions and meet the net-edge test. Reconsider opportunities across names using expected *incremental net dollars*, with the existing issuer, margin and squeeze limits shared by all open positions and outstanding orders.

For each candidate child order estimate, using only information available at the decision:

```text
Expected incremental profit if filled
  = shares * (expected entry price - expected cover price)
    - entry and cover fees
    - borrow charges + attributable proceeds interest
    - incremental own-impact allowance
    - model-uncertainty reserve
```

Cover price includes expected exit spread and slippage. Entry price already includes the quoted spread/depth paid or earned; do not subtract them twice. Borrow and proceeds interest follow the actual modeled holding/settlement path, including failures to finish covering; a delay cannot automatically retain the same-day zero-financing assumption. A passive order's score must use its fill probability and cover-price distribution *conditional on filling*, including adverse selection. Unfilled opportunity remains in the parent-level evaluation.

### Choose between waiting and a small child order

At short review intervals, compare three actions: wait, post a genuine small sell limit at a permitted offer, or send a tightly bounded marketable sell limit. Prefer passive selling when actual buy-initiated flow is arriving. Consider paying the bid only when the forecast value of getting filled before the edge decays exceeds the extra spread and impact, and all price/risk limits pass. A falling market alone is not permission to chase with bigger children.

Use an evidence-based forecast of the remaining gross move at each elapsed entry time. Estimate this on earlier sessions, shrink thin groups and propagate uncertainty. The current opening-only ridge forecast cannot simply be reused at noon. Initially compare a small declared set of 15-, 30-, 60- and 120-minute maximum entry windows; reserve a separate cover window. The algorithm may finish earlier, finish smaller or skip.

### Size children to observed replenishment

For a marketable child, cap shares by the minimum of remaining target, approved borrow, shared risk headroom, observed participation allowance, a fraction of fresh eligible bid depth, and conservative forecast cover headroom. Reserve all outstanding child shares against these budgets before another order can be released; release reservations only after acknowledged cancellations or executions.

Start research with a 1% participation ceiling, with 2% and 5% as declared sensitivity variants. Bound both trailing-one-minute and cumulative-session participation. Use only already observed eligible continuous-trading volume, with prints deduplicated across feeds and opening/closing auctions excluded from the continuous-flow budget. Do not bank unused volume from earlier hours into a sudden sweep. Participation is a maximum, not a fill entitlement.

Test taking at most 5%, 10% or 20% of fresh eligible displayed depth per child. Credit replenishment from new book events after subtracting our own active/filled orders; do not reset capacity on every one-second snapshot. Without event-level evidence, report a conservative no-replenishment bound and a clearly labeled optimistic proxy bound. Do not claim historical passive fills from bar highs alone.

These percentages are proposed test settings, not findings that those rates have low impact. For approximately stable prices, a $25k entry requires $2.5m of eligible volume at 1%, $1.25m at 2%, or $500k at 5%. A $100k entry requires four times those amounts. Entry flow and subsequent cover flow must support their respective legs; they cannot both spend the same volume allocation.

### Guard price and covering capacity

Replace the single whole-target admission gate with child-level limits. The minimum sale price is the stricter of the local sweep/slippage limit and the price needed to preserve the net-edge buffer after forecast covering costs. A better quoted price does not override an already exhausted impact or risk budget.

Monitor spread, depth removal, bid replenishment and post-fill markouts at 10, 60 and 300 seconds. If bids vanish or sale prices deteriorate, pause and reduce the allowed rate. Do not identify every subsequent price fall as our own impact: the strategy itself predicts declines. Separate natural alpha from impact using matched controls and, if later authorized, randomized timing of genuinely intended small executions.

Stop adding when the uncertainty-adjusted net edge disappears, borrow or data quality fails, risk headroom is exhausted, or the cover deadline approaches. Fit a conservative distribution of coverable volume from earlier sessions and allow less inventory than its mean prediction would permit. A halt or failed cover retains the share liability and overnight costs; never force an unsupported closing-print fill to make the backtest flat. Covering has a separate urgency policy because incomplete liquidation is a different risk from incomplete entry.

Broker-approved locates and short-sale eligibility gate every child. When Rule 201 is active, ordinary short orders must respect its price restriction above the national best bid, subject to applicable exceptions; the research design assumes no exemption. Cached venue BBO is insufficient to enforce this live. See [SEC Rule 201 guidance](https://www.sec.gov/rules-regulations/staff-guidance/trading-markets-frequently-asked-questions-7).

### Use broker execution where it fits

[IBKR Accumulate/Distribute](https://www.interactivebrokers.com/en/software/pdfhighlights/PDF-accumulateDistribute.php) already provides order slicing, timing and price conditions. It is a candidate execution mechanism beneath the strategy's net-edge, participation and inventory controls. Randomizing order size/time alone does not create liquidity or calibrate impact. Verify supported order types, short eligibility and cancel/fill behavior in simulation before selecting a broker implementation.

## The next comparison and its acceptance criteria

Freeze the entry-time alpha model and the small parameter set before replay. Compare the current full-target IOC rule, the same IOC rule allowing economical partial positions, unchanged passive orders, fixed participation, and the proposed conditional hybrid. Use the same universe, information timing, broker eligibility, price limits, fees, financing and risk budget. Attribute improvement separately to admitting partial positions and to changing execution.

Use pre-2023 data for development, then earlier-session-only refits through the already studied 2023-2024 validation period. This remains retrospective research. A new prospective window provides the untouched test; do not quietly repurpose the sealed holdout after seeing other overlapping samples.

Report all parent opportunities: no fills, partial fills, completion times, entry VWAP, delay shortfall, spread, fees, assumed/estimated impact, adverse markouts, cover residuals, dollar net P&L, daily marked equity, drawdown and margin. Publish results by name, liquidity group and entry window, with issuer/day dependence retained in uncertainty estimates. Rank incremental net dollars and total portfolio contribution, not merely the average return of a handful of selected winners.

Existing one-second venue bars and quote paths can test time/volume availability and alpha decay for $0. They cannot establish queue position, hidden liquidity, signed trade flow or the causal impact of our orders. Event-level trades/books and prospective broker acknowledgments/fills are required for those claims. Free observation can improve the model without authorizing paid downloads or live executions.

Advance only if the hybrid improves total net dollars over the partial-IOC and fixed-participation controls after adverse fill/cover assumptions, preserves the shared risk limits, and works across more than a few names and sessions. If profitability exists only on an optimistic replenishment or passive-fill assumption, retain the result as an execution hypothesis.
