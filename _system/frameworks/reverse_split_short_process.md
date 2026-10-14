# Reverse-split short process (RSI-1.0)

**Status:** operative process document for the reverse-split research lane; not a persona lens.
**Governance record:** `_system/proposals/one_hub_for_humans_and_bots_2026-10-11.md` (Phase 3) is the proposal that admitted this process into SSI. Changing a threshold below requires a new strategy version and a new proposal entry; this file describes, it does not authorise.
**Code:** `_system/scripts/reverse_splits/` (rules in `strategy.py`, lenses in `research_lens.py`, routes in `framework_plan.py`). **Data:** `_system/data/reverse_splits/` (README there). **Owner of decisions:** Michael (`decisions.jsonl`).

## One sentence

A reverse split is a discovery event. Fundamental impairment, valuation, catalyst timing and a feasible borrow are four further propositions, each of which has to be established separately before a paper short exists. A high score is a reason to read a filing; it is not a thesis, a fraud finding or an order.

## Five propositions, kept apart

| Proposition | What settles it | What it is not |
|---|---|---|
| Discovery event | A substantive 8-K/6-K reverse-split announcement with a parsed ratio, within seven calendar days, before any known effective date, with issuer, accession, ratio and schedule reconciled by the reviewer | A phrase hit; a proxy proposal; a historical reference in a later filing |
| Impairment | Raw point-in-time SEC fundamentals (filed strictly before the entry day) with a deterioration score of at least 60, three numeric signals, an operating-company profile and a latest period no older than 200 days; then the six lenses below | The score itself (it is deterioration, not conviction); the latest-revision SSI cache (a limited fallback, excluded from the historical screen) |
| Valuation | Bear/base/bull common-equity values after debt, preferreds, warrants, converts and dilution; at least 30% gross downside to a catalyst-reachable target, 20% after costs and seven-day carry | "Expensive"; a split-adjusted price level; recovery optionality ignored |
| Catalyst | A dated event within seven calendar days and before a known split that can expose the impairment, plus a measurable falsifier | A hope that the market notices |
| Tradability | Executable quote within 15 minutes, approved locate within four hours with fee, size and reference, an SSR execution check, and a shared-account squeeze budget | Availability on a screen; FINRA short interest (positioning, not inventory); an assumed fee |

## The RSI-1.0 rules

Adopted 2026-10-09 as an original paper proposal. The thresholds were chosen after inspecting the historical sample; that sample is exploratory, not a validation set. `strategy.RULES` is the machine copy and `policy()["rules_hash"]` fingerprints it.

| Rule | Value | Rule | Value |
|---|---:|---|---:|
| Fundamental score floor | 60 | Name loss budget (of equity, +200% shock) | 0.5% |
| Latest fundamental period, max age | 200 days | Sleeve loss budget (joint, of equity) | 2% |
| Announcement age for entry, max | 7 calendar days | Notional cap (of equity) | 2.5% |
| Maximum hold (including entry) | 5 sessions | Participation (of prior 20-session ADV) | 0.1% |
| Carry window for payoff and stress | 7 calendar days | Stress price increase | +200% |
| Maximum names | 3 | Margin buffer (of original equity) | 20% |
| Gross downside floor | 30% | Net downside floor (after costs, carry) | 20% |
| Carry ceiling (of notional) | 10% | Minimum notional | $100 |
| Locate age, max | 4 hours | Quote age, max | 15 minutes |

Sizing takes whole shares at the smallest of: the name loss budget under a +200% price shock with carry stressed at three times the entered fee on 102% collateral rounded up to a dollar at triple the entry price; the remaining joint sleeve budget; the notional cap; participation; the approved locate; and the stressed maintenance margin with the 20% buffer, after losses and margin from every other strategy under the same joint scenario. A hypothetical stress is not a maximum possible loss. Exit after five sessions, before a known split, when the catalyst resolves, the falsifier occurs, borrow is recalled, or a 50% adverse move triggers a cover instruction at the next executable opportunity. Never average into a losing short.

## Entry gates (all must pass for `paper_ready`)

| Gate | Requires |
|---|---|
| Point-in-time fundamentals | Raw filing-availability-filtered score and freshness meet the rules above |
| Fresh verified announcement | Substantive parsed announcement within seven days, before any known effective split, identity reconciled |
| Six evidence lenses | All six reviewed with dated primary evidence, a locator, the mechanism, contrary evidence and a falsifier; at least two impairment lenses supported, one of them cash/financing or operating; valuation and catalyst supported; no lens contradicted |
| Net payoff and carry | 30% gross, 20% net downside; carry at most 10% of notional; target reachable in the hold window |
| Catalyst within hold window | Dated, within seven calendar days, before a known split |
| Fresh quote and locate | Quote within 15 minutes, approved locate within four hours with fee, size, reference; SSR checked |
| Shared-account survival | Notional at least $100; all-account stressed margin and existing sleeve losses reconciled |
| Prospective decision | Evidence date equals the current Eastern date; anything older is retrospective and excluded from forward validation |

A ready plan is a plan. It is not an order, a simulated fill or a position.

## The six lenses

Each review records the date the evidence was known, the primary source and locator, the mechanism, contradictory evidence, a falsifier and a status (`unreviewed`, `unresolved`, `supported`, `contradicted`). The documentation grade weights all six equally (contradicted 0, unresolved 1, supported 2) and is unscored until all six are complete. It is not calibrated to returns and is never a probability.

| Lens | Question | Short Alpha frameworks | What weakens it |
|---|---|---|---|
| Earnings and revenue quality | Are booked earnings supported by collectible revenue and cash? | accounting, revenue_recognition, earnings_vs_cash, working_capital | Collections catch up; a documented seasonal or contract explanation |
| Cash quality and financing pressure | How much usable cash remains after correcting presentation and meeting obligations? | cash_burn, leverage_refinancing, dilution_financing, off_balance_sheet, capitalization_reserves | Sustainable cash generation or committed financing without the expected damage to common equity |
| Operating impairment | What operating mechanism makes future equity economics worse than expected? | cycle_mean_reversion, supply_side, margin_contraction, secular_obsolescence, fad_single_product | Durable demand, pricing or unit economics improve enough to contradict the mechanism |
| Disclosures, incentives and control | What changed in the disclosures, and whose interests do the transactions serve? | reporting_integrity, governance_related_party, promotion_insider_selling, acquisition_nongaap_kpi | Primary documents show ordinary arm's-length terms or a required disclosure update |
| Valuation and common-equity payoff | Is there enough downside after all claims, dilution and the cost of waiting? | leverage_refinancing, dilution_financing | The impairment is priced in; financing improves per-share value; carry consumes the downside |
| Catalyst, falsifier and survivable path | What dated event exposes the impairment, and can the account survive until then? | regulatory, borrow_and_carry, crowding_squeeze, path_and_timing, issuer_retaliation | The catalyst slips past affordable carry; the falsifier occurs; borrow disappears; joint squeeze loss exceeds budget |

Eight framework routes (`framework_plan.PATHS`) turn a dated fundamental observation into a question for one of these lenses. Suggested routes are prompts: they add no support, do not raise the grade and do not change any threshold. Cash burn, refinancing and dilution often describe one funding problem; revenue and margins one demand shock; parent and child accounting labels share evidence. Count mechanisms, not labels. Fraud/bad-actor is a conclusion tag reserved for a regulator, a court, an admitted restatement or an evidence-backed analyst determination.

## What the historical result establishes

| Study | Result | Why it is not an edge |
|---|---|---|
| Original $50k completed-split comparator (`assumed_100_h5_effective`) | about -$14,286 on 124 trades | Selecting completed splits at announcement uses future outcomes; fills are half the prior-range spread, not quotes; no maintenance margin; the five-session horizon spans six observed bars |
| Predeclared daily-bar scenarios (`verified_daily_100`, `verified_daily_300`, `verified_small`, `verified_stop`, `verified_strict`, exploratory `fundamental_60`) | sensitivities, not strategies | Parsed filing evidence without a completion filter; whole shares, 1% ADV, 5% of equity, accrued collateral borrow, commissions, slippage, margin floors; `verified_strict` is empty because no historical locate exists; the persisted `fundamental_60` scenario (+$141 on four trades) predates the clause audit below, which removed three of its four leads |
| Frozen 96-account fundamental rerun (`fundamentals_v1`), after the 2026-10-11 filing and corporate-action audit | One primary candidate, EDBL, a shareholder-authorization event: about -$150 over five sessions, -$582 over ten; 0 of 12 ten-session brackets positive | The preliminary +$131 / +$1,123 on four trades was input error: ASTI's filing described a split already effected, PALI and IBO fell below the $1 printed-price floor once omitted split factors were restored. 216 parsed leads, 24 prepared, one passes the filter; Sharpe and intervals suppressed; the pre-audit results are archived as superseded |

The spread assumption alone can change the apparent edge substantially. Peer and random-listed controls are conditional descriptive comparisons on a present-day universe. Current SEC exchange maps and Yahoo history are not a contemporaneous security master; nominal-price reconstruction from split gaps is a heuristic; delisted names and failed exit paths are censored observations, not zero returns. FINRA short interest is positioning context, never a locate.

## Validation before any deployment

### Intraday research overlay adopted October 13, 2026

The separate `reverse_split_intraday.v1` protocol in
`_system/data/reverse_splits/forward_protocol.json` begins new-event validation
October 14. Its primary hold is next-session open to same-session close, with
the existing historical fundamental screen fixed. Compare zero and one
overnight descriptively; do not select a winning holding period after seeing
the validation returns. A prospective trade requires a fresh approved locate,
annual rate <=50%, expected total cost <=1%, dated quotes, security identity,
margin and thesis. A current public rate archive supports sensitivities only.

Every attempted entry, failed gate, partial cover, fee change and loan return
must remain in the record. A split-adjusted quantity is not proof of broker
cash-in-lieu settlement. An absent OTC price is not a zero-price liquidation.
The first intraday research review is at 100 completed events / 60 issuers;
this is a separate evidence review and does not approve live deployment.

1. Freeze this version before collecting future outcomes; log every lead, pass and review, including missing data and unavailable borrow.
2. Repair event-to-filing links and complete the publication-time lead ledger, including abandoned proposals and unscored names; keep a security master and terminal outcomes.
3. Import genuine historical borrow evidence with as-of timestamps, fee units and execution permission; a current availability export cannot prove borrow existed five years ago.
4. Run chronological walk-forward portfolios with issuer-separated evaluation, an embargo at least as long as the maximum hold and a contemporaneous control universe; compare fundamentals-only, split-only and combined baselines under identical universe and capital rules.
5. Measure account return, drawdown, expected shortfall, worst issuer, carry drag, fill and locate rejection, concentration and turnover. Never substitute median trade return or unconstrained overlapping P&L for an account result.
6. At 30 closed paper trades across at least 20 issuers and six months, review the evidence rather than approve deployment; keep a later untouched cohort and version every rule change.

No Sharpe, time-weighted return or closed-trade result exists until actual paper fills, costs, daily marked equity and external flows are collected. Review and pass decisions alone generate none of them.

## Data and the Gateway rule

| Source | Role | Rule |
|---|---|---|
| SEC EDGAR full-text search, submissions, filing text | Discovery, accept clocks, announcement parsing | Descriptive User-Agent with contact; 0.2 s between requests; weekly job scopes with `--since-days` |
| SEC companyfacts through SSI's `build_fundamental_series` / `build_short_quant_screen` | Point-in-time fundamentals and thresholds | Same functions as the rest of SSI; raw facts filtered by filing date before extraction |
| Yahoo daily OHLCV (`yfinance`) | Nominal price paths; split prints classified raw / continuous / ambiguous | Local only; never blindly scale by the ratio without jump detection |
| FINRA consolidated short interest | Positioning context; synthetic ADV rows when files are absent | Not a locate; never sets a share count |
| IBKR Client Portal Short-Securities Availability CSV | The only borrow evidence | Imported with `borrow-csv`; keeps the export's own timestamp; percent quotes divided by 100 |
| IB Gateway | **None.** | The original tool's live snapshot path (client id 17, the SPX executor's id) was deleted in the migration. No module in `_system/scripts/reverse_splits/` imports a broker client or opens a socket; `check_ib_gateway_registry.py` stays green. Borrow is CSV only. |

## Reading list

The playbook (`research_lens.BOOKS`) catalogues twenty titles on Drive. Selected sections of three were reviewed and ground the lenses above: *Financial Shenanigans* (third edition), *Financial Fine Print*, and *Fooling Some of the People All of the Time*. The others are references until reviewed; *Quality of Earnings* returned no readable text. No book text is stored in this repository; the catalogue belongs with `_system/reference/short-selling-library/`.

## Sources

[FINRA 4210 margin floors](https://www.finra.org/rules-guidance/rulebooks/finra-rules/4210) · [SEC Rule 201 price test](https://www.sec.gov/files/rules/final/2010/34-61595-secg.htm) · [IBKR collateral convention](https://www.interactivebrokers.com/campus/glossary-terms/collateral-short-sale/) · [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
