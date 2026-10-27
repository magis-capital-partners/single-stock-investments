# Trading reverse-split shorts under SSR: execution and proof plan

Proposal dated October 25, 2026 ET. Research design; no orders, live settings, data purchases or Gateway access are authorized or performed by this document. Numerical execution settings below are initial hypotheses, not an established optimum. The current backtests remain hypothetical sizing sensitivities.

## Recommended design

Treat an SSR flag as a route-and-price constraint. Attempt a small, compliant short order, retain actual partial fills, and stop when the remaining opportunity no longer pays for execution and covering. The objective is expected net dollars across every eligible decision, including rejections and no-fills. Completing $100,000 is not the objective by itself.

Keep the requested $10m reference NAV, $100k initial parent cap, three concurrent issuers, no old percentage reserve, no margin-capacity admission gate, no sleeve-wide admission cap and no minimum future-session requirement. Broker borrowing and live house-margin acceptance remain actual prerequisites. Removing a modeling gate does not grant broker credit or lendable stock.

The primary signal stays third-plus AND the saved single-day 50% rally veto AND common-share growth at least 25%. Preserve other signal arms as comparisons. Do not add a new fundamental optimization grid while changing execution.

The first continuous-session hypothesis is a 60-minute, partial-fill parent beginning at 09:31 ET on the original eligible entry date, provided all source clocks and market-data gates pass. It sells into actual buyer demand at permitted prices. It may trade less than the cap or nothing. The entry deadline remains 09:31 plus the declared window even if the first valid order starts later; halts or rejections do not reset it. The original signal-anchored 20-session exit date remains fixed; a delayed fill does not receive the profit from price declines before it filled or an automatically extended holding period.

## 1. Useful execution mechanisms

| Mechanism | Why it can help | What must be modeled or confirmed |
|---|---|---|
| Display a small offer at a permitted price above NBB | Buyer-initiated orders can fill the short without selling into the protected bid | Actual NBBO, dated price grid, route access, queue and borrow |
| Improve inside a wide spread | A better sell offer can attract buyers before a more expensive existing ask | A valid inside price must remain above NBB; a one-increment spread leaves no such inside price |
| Preserve a qualifying displayed order | Avoid repeatedly losing priority through cancel/replacement | Initial display, route eligibility and exact broker/venue order handling |
| Use a supported native SSR repricer | Exchange/broker handles fast price changes instead of a fragile client chase loop | Account/security support, limits, timestamps, rejection rules and broker logs |
| Enter during buying-flow bursts | More incoming buy demand may support a larger legal short fill | Estimate from past/current data; a bounce is not guaranteed to continue |
| Test an opening-auction route separately | A supported auction can concentrate demand | Venue-specific SSR handling, deadlines, imbalance information and counterfactual auction capacity |

Example: with a $5.00 bid and $5.04 offer, an ordinary permitted $5.01 displayed short offer could compete for incoming buyers. If the offer is $5.01 already, joining it entails a queue; a trade touching $5.01 does not establish our fill. This example assumes a one-cent permitted increment and actual broker approval. It is not a forecast of fill probability.

Rule 201 contains specific treatment for displayed orders initially above NBB. Nasdaq Rule 4763(f) implements that treatment. Consequently, the simulator must track initial display and the order's lifetime rather than automatically canceling every time the bid reaches the resting price. Broker/venue behavior determines what is executable. We submit ordinary short orders; any exempt marking requires the broker's documented basis, not a client-side assumption.

Nasdaq also documents native SSR repricing and distinct auction handling. These are route-specific features, not a general promise that a market or opening order fills. Initially use ordinary supported limit orders. IBKR documents passive-relative sell orders pegged to the offer, but that product description alone does not establish SSR support or fill quality for these names. Compare it only after route/account verification.

Do not use the last sale's color as the legal test. Incoming buying can fill a permitted short while the broader price is falling. Buying-flow and bounce features are execution predictors to test, not ways to bypass the rule. Off-hours trading is not assumed to remove SSR.

## 2. Live parent and child workflow

| Stage | Action | Required record |
|---|---|---|
| Before entry | Resolve the actual security/share units; freeze source-available signals, parent share budget, exit date and issuer slot | Security ID, source hashes/clocks, policy version and decision ID |
| Borrow preparation | Obtain usable quantity and validity from the broker; evaluate pre-borrow when available and economical | Confirmation, expiry, reserved quantity, APR, locate/pre-borrow fees and return obligations |
| Market gate | Confirm current NBBO, restriction state, trading/auction state, permitted increments and feed continuity | Observed and received timestamps, sequence gaps and market-state source |
| Parent activation | Reserve one issuer slot and the full possible filled-plus-working quantity | One immutable parent ID; count pending-cancel children until acknowledgement |
| Child placement | Submit one small normal short limit at the chosen permitted price | Limit, quantity, route, initial display/acknowledgement and reserved borrow |
| Rest or revise | Preserve queue when worthwhile; improve price only when the extra fill value exceeds lost priority and adverse selection | Reason for hold/change, queue estimate and remaining edge |
| Fill | Update inventory only from execution reports; decrement borrow and parent budget immediately | Fill ID, timestamp, route, price, fees and partial quantity |
| Deadline / invalidation | Cancel the unfilled remainder; await acknowledgement and handle race fills | Cancellation status, final inventory and unused borrow release |
| Cover | Trade real held quantity at the fixed exit clock or an explicit operational exception | Actual partial covers, settlement/borrow return and remaining liability |

Borrow indications are not a substitute for usable broker approval. A pre-borrow can incur costs even if no entry fills; charge those costs to the no-fill decision. Snapshot inventory must not be reused across several pending parents. Do not exceed borrowed/authorized shares, issuer limits or the fixed parent share budget through parallel routes or cancel/replace races.

### Initial execution settings to test

| Setting | Initial hypothesis |
|---|---|
| Parent budget | Floor($100,000 / valid arrival midpoint); freeze maximum shares and journal actual fill proceeds separately |
| Child size | At most $2,000 at the sizing mark, further reduced by borrow, remaining budget and observed-flow allowance |
| Working children | One live child per issuer initially |
| Participation | Compare 5% and 10%; 10% is the hard research maximum requested |
| Windows | Compare 30 and 60 minutes; 60 is the first primary hypothesis |
| Rest/change | React to market events; discretionary repricing no faster than every five seconds; required handling is immediate |
| Data health | A one-second maximum age for validated market-state/feed continuity; an unchanged quote is not automatically stale |
| Kill conditions | Unknown restriction/identity, feed gap, halt, expired borrow, exhausted budget, rejected route, nonpositive remaining edge or deadline |
| Unfilled quantity | Cancel; no guaranteed completion and no automatic second-day retry |

One-second freshness and five-second discretionary spacing are design hypotheses. Broker-native handling can operate faster than the decision loop. They must be tested against real quote, acknowledgement and cancellation latency.

### Participation must be based on observed flow

Use a cumulative volume budget from the start of the parent, with a rolling flow limit as an additional brake. At each decision:

~~~text
available flow shares
  = max(0, floor(rate × external observed volume so far)
           − own filled shares − own working/reserved shares)

child shares
  = min(parent shares remaining,
        valid borrow quantity remaining,
        available flow shares,
        small child-size ceiling,
        declared rolling-flow ceiling)
~~~

External volume excludes our known executions and is deduplicated across sources. Reserve tokens for a working child before another child can use them. A cancel request releases no tokens until its result is known. Historical final-day volume cannot determine an earlier order. Repeated identical snapshots do not supply fresh shares. Ten percent of total tape volume is an upper budget, not ten percent guaranteed accessible buying flow at our price.

### Optimize the value of the next child

For each permitted action estimate:

~~~text
P(fill | current state, route, queue)
  × E[net profit of the actual filled quantity | that fill]
  − costs incurred without a fill
  − operational / inventory risk penalty
~~~

The conditional profit includes remaining expected price decline, entry/cover costs, borrow, fees and adverse selection. Compare resting, improving, repricing and canceling, with waiting valued explicitly. A rising price can fill our offer just before a squeeze; a lower entry after waiting can lose much of the original expected decline. Neither high fill rate nor a better entry price alone establishes better trading.

Use simple observable features first: spread, depth/queue, recent buyer-initiated flow, near-term price pressure, time since decision, borrow terms and remaining forecast edge. Fit from prior data; no future low, end-of-day volume or eventual winner labels at the decision. Arrival-price implementation shortfall and missed opportunity are diagnostics; do not subtract them a second time from cash P&L.

## 3. A backtest that can represent this faithfully

Use one deterministic execution state machine in both environments. Historical replay delivers market events and simulated exchange responses; live delivers market events and broker acknowledgements/fills. Signals, quantity reservations, deadlines, state transitions and position accounting are shared. The historical simulator is an execution hypothesis that must be calibrated, not broker truth.

Required historical inputs:

- Exact security identity, split units, dated trading calendar and source clocks.
- Timestamped consolidated NBBO and restriction changes, plus halts/auction/LULD state.
- Chosen-venue trades and depth; order-level data when available for better queue reconstruction. Consolidated quotes do not by themselves reveal venue queue priority.
- Dated tick, price-test and order-type handling, including order replacements and initially displayed eligibility.
- Archived borrow evidence where it exists. Keep a conditional-on-borrow replay separate from the borrow-verified replay; never substitute today's inventory for historical availability.
- Enough exit-session data to simulate partial covers and continued liabilities, not just entry fills.

Replay the observable order of events with receipt-time/latency delays. Do not credit a fill from the same event used to decide the order. Model submission, routing, acknowledgement, rejection, replacements, pending cancellation, partial fills and loan returns. Compare 100ms, 500ms and 2s response latency, with measured values replacing assumptions later.

A passive fill requires defensible eligible traded flow after arrival and queue ahead. A touched bar or the entire volume of a one-second bar is insufficient. Market-by-price data give an estimated queue, with hidden-liquidity and cancellation uncertainty; report conservative and calibrated alternatives. An improved inside offer changes the counterfactual book, so its access to historical incoming flow is modeled, not directly observed.

The existing reference simulator unconditionally slides an SSR offer when the bid reaches it. Audit and revise that behavior before reuse: it is stricter than the initially displayed-order provision and can erase queue priority. The venue best bid is also not necessarily NBB. Broker/native route handling and exact order lifetimes must be represented separately.

Charge commissions, venue fees, locate/pre-borrow expense, variable borrow and buyback costs once. Per-child minimum commissions can make many tiny slices expensive; cancellations and modifications must follow the actual broker's fee treatment. Include market-impact stress instead of assuming a fixed percentage remains accurate at $100k. Buying to cover is a different execution problem from opening an SSR short and still needs liquidity evidence.

For partial entries, retain actual quantity and time-weighted inventory. Apply splits, fees, per-fill settlement and loan return. Keep the original planned exit anchor in the primary comparison. Recent incomplete horizons remain marked; a missing delisting/identity/fractional resolution remains an obligation. Do not complete residual covers at an invented final print.

### Small declared comparison set

| Policy | SSR handling |
|---|---|
| E0 | Matched skip control: same clear-status execution and other rules; no SSR attempt |
| E1 | Rest at the displayed offer with queue preservation |
| E2 | Compete at a permitted inside price when available; otherwise join the offer |
| E3 | Verified broker/venue-native SSR repricer |

Compare E1-E3 across 30/60-minute windows and 5%/10% participation: 12 primary comparisons. Use the appropriate E0 at each window/rate so the result isolates SSR execution. Freeze the clear-status execution rule, financial signal, exit anchor, three slots and all other assumptions. Retain the older opening-price sizing result as a separate diagnostic; it is not the matched intraday control. Report every variant and correct selection claims across them.

Keep auction participation, midpoint/dark routes, delayed next-session entry, new signal ranking and longer entry windows as separately declared follow-ups. Do not silently fold the best alternative into the primary result.

## 4. What we can reuse and what is missing

Reuse the 210-event cohort, reconciled as-of fundamentals, the saved rally screen, dated split/security work, 100 current SSR exclusions, verified opening-status audit, original portfolio accounting and baseline replications. Reuse the earlier passive and patient-execution code as inspected building blocks, not as validated fill truth.

Our metadata join found 67 exact ticker/intended-date matches between the 209 scheduled current events and each of the two older execution indexes. It found 57 matches among 170 primary signal-pass events and 31 among the 100 SSR exclusions. These are index overlaps only, not proof of complete valid paths; other caches may add coverage. The companion inventory records source hashes and these limits.

Earlier H18/H19 work had one-second listing-venue bars and opening/closing quote books, with no continuous NBBO. The patient study added more venue flow and sampled quote paths, still without a certified market-wide queue replay. In an earlier, different 2023-24 validation sample, the bar-based $25k passive-offer model fully filled within 15 minutes on only about 4% of restricted sessions; the $1,250 version reached about 22.1%. Those results are model-dependent warnings about unchanged offers, not live fill probabilities for our 210-event strategy.

New work is exact date/security/schema coverage for the actual cohort; market-wide quote and venue-flow reconstruction; corrected route-specific queue handling; parent/child accounting; broker capability confirmation; and own-order calibration. One-second data can screen ideas and produce bounds. It cannot establish that all 100 SSR names would fill, or that the fixed 50% capture proxy is realistic.

Prepare a gap manifest with needed symbols, dates, schemas, time windows and estimated data cost. Reuse valid local files first. Existing old data quotes do not establish today's price or coverage. No purchase or download with a positive cost is authorized by this proposal. Do not open the separate sealed execution holdout; all current third-plus history is already explored development data.

## 5. Practical live rollout

1. Confirm the broker can lend these securities and supports the intended routes/order types for the actual account. Verify native repricing, initially displayed treatment, modify/cancel priority, fees, borrow validity and recall handling. These are questions to resolve; no message to the broker is sent by this plan.
2. Build the event replay and shared order state machine. Require accounting/quantity invariants, as-of clocks, no duplicate fills, no over-allocation and deterministic replays. Log every rejection and no-fill.
3. Run shadow decisions with live external data and no orders. Reconstruct eligible prices, virtual queue paths and missing-source rates. Broker paper trading checks integration; IBKR explicitly notes top-of-book fill simulation, so paper fills do not prove $100k queue capacity.
4. With separate authorization, use small real parent limits to measure borrow, route acknowledgements, fills, race conditions, slippage and covers. The research maximum stays $100k; the pilot is deliberately smaller. Log partial/no-fill/failed-locate decisions, not only successful trades.
5. Review a minimum checkpoint of 200 child attempts over 30 SSR parent decisions and 20 issuers, with sufficient actual fills in each intended spread/liquidity regime. This is a calibration checkpoint, not a statistical profitability pass. Multiple children of one parent are dependent.
6. For strategy evidence, retain the existing future checkpoint of 50 eligible parent decisions across 30 issuers, plus uncertainty, concentration, cost and resolved-exit tests. Current history is already explored. At approximately two SSR exclusions per month in this selected historical cohort, a meaningful issuer sample can take many months; more children do not create more independent issuers.
7. Increase authorized parent size only when observed capacity and covering at the next size support it. Evaluate $5k, $25k, $50k and the $100k ceiling as capacity steps, not guaranteed assignments. Do not scale by multiplying tiny-position returns.

### What should appear on the dashboard

Track eligible parents, borrow-approved parents, attempted parents, partial/full fills, executed dollars, remaining borrowed/working quantity, rejection/no-fill reasons, time to fill, total child fees, entry shortfall, 1/5/30-minute short-side markouts, borrow/recalls, cover completion and open liabilities. Report issuer-clustered and calendar uncertainty, concentration and net P&L per eligible decision, including paid no-fills and idle periods.

Display conditional historical fills, calibrated simulation, broker paper fills and real fills as distinct evidence. Do not rank an execution policy solely by completed-trade P&L: it can look good by avoiding difficult losing fills or leaving bad covers unresolved. Realized marks and outstanding exposure must reconcile.

## 6. SPX coexistence and operational boundary

The current SSI repository permits only human-initiated bounded Gateway actions, prohibits recurring Gateway connections and polling, and reserves client 91 for its event-driven hub bridge. It also protects shared market-data lines and SPX-owned orders. This proposal changes none of those rules.

Keep SSI as research, intent display and Flex-over-HTTPS reconciliation. An autonomous slicer needs a separately reviewed execution service and a broker connection/session that does not share the protected SPX Gateway. Prefer operational and capital separation; confirm account/session and market-data entitlements with the broker. Do not assign a client ID, reuse SPX IDs, move a task onto NY4, add recurring connections or deploy live code as part of this plan.

The isolated executor owns its orders and execution stream, persists an idempotent journal and reconciles late/duplicate events. It may cancel only its own identified orders, never account-wide global cancellation. A restart must reconcile before submitting replacement orders. Broker-native orders may remain working if our process fails; shutdown and disconnect behavior must be tested explicitly.

The user-requested removal of modeled margin and sleeve limits is preserved. Live broker acceptance and truthful account reconciliation are unavoidable. Three initial $100k shorts would lose about $600k before costs if all rose 200%, equal to 6% of the $10m reference account; this is a stress illustration, not a loss ceiling. Decide any further discretionary exit or loss policy as a separate strategy change and test it accordingly.

## 7. Next implementation deliverables

| Order | Deliverable | Completion evidence |
|---|---|---|
| 1 | Actual-cohort data/borrow/route gap manifest | Every event has coverage and known/unknown states; explicit priced request list |
| 2 | Broker capability specification | Exact supported short-order attributes, venue handling, fees and borrow terms |
| 3 | Shared parent/child state machine | Deterministic unit fixtures for partials, race fills, SSR changes, halts and source gaps |
| 4 | Conservative event-level exchange simulator | No touched-bar fills, no reused liquidity, explicit queue/latency alternatives |
| 5 | Matched E0-E3 portfolio study | All 12 comparisons, costs, no-fills, immature positions and unresolved exits reported |
| 6 | Forward shadow journal and isolated execution design | Data-health evidence and SPX separation review; no implicit live authority |
| 7 | Small authorized execution calibration | Actual borrow/fill/cover evidence; measured model errors before size increases |

## Sources and prior work

- [Rule 201, including initially displayed orders](https://www.ecfr.gov/current/title-17/chapter-II/part-242/subject-group-ECFR1607681c7b4f78d/section-242.201).
- [Nasdaq Equity 4, Rules 4763(e)-(f), 4756 and auction provisions](https://listingcenter.nasdaq.com/rulebook/nasdaq/rules/nasdaq-equity-4).
- [IBKR passive-relative order description](https://www.interactivebrokers.com/campus/glossary-terms/passive-relative-order/).
- [IBKR securities financing and pre-borrow tools](https://www.interactivebrokers.com/en/trading/securities-financing.php).
- [IBKR paper-trading limitations](https://www.interactivebrokers.com/campus/glossary-terms/paper-trading-account/).
- [SEC June 2026 pricing-increment compliance relief](https://www.sec.gov/files/rules/exorders/2026/34-105656.pdf). Use dated broker/venue price rules rather than an unconditional penny increment in every year/security.
- [Cont and Kukanov, Optimal Order Placement](https://arxiv.org/abs/1210.1625): a framework for queue, fees and execution risk; no calibration to these names is imported.
- [Lehalle and Neuman, Incorporating Signals into Optimal Trading](https://arxiv.org/abs/1704.00847): motivates balancing signal decay and impact; it does not establish our best schedule.
- Existing repository reports: execution_realism.json; patient_execution_2026-10-20.md; intraday_execution_research_2026-10-20.md; the frozen third-plus and requested-sizing studies.

The companion ssr_execution_proposal.v1.json is a machine-readable proposed specification. ssr_execution_inventory.v1.json binds the limited cache-overlap audit to its sources. No new strategy performance or live fill result is claimed.
