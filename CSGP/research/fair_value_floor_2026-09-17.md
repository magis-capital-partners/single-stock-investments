# CSGP — Lower bound fair value

**Date:** 2026-09-17  
**Status:** Research estimate. The production contract is still **evidence_blocked** and has no dollar value. This is a first present-value floor, not a committee-approved contract.  
**Method:** No-growth capitalization of **already-depressed** owner cash (after Homes.com spend), plus net cash. Residential option at zero.

## Headline

| | |
|---|---|
| **Lower bound fair value** | **$18 per share** |
| Price today | **$29.30** (Yahoo close 2026-09-17) |
| Price vs floor | 1.63 times the floor (price is **39% above**) |
| Legacy Lawrence bear terminal (old dive) | ~$25 in year 10, not a value today |
| GAAP book | ~$18.81 (Q1 2026 equity / shares). Includes Matterport and Domain goodwill. Not a dhando floor. |

The stock is **above** the floor. The floor is "CoStar Suite and LoopNet keep throwing off the cash they already throw off after Homes.com marketing, forever, with no growth and no residential win."

## What this business is

CoStar is the main U.S. commercial real estate data and marketplace platform (CoStar Suite, LoopNet) plus a costly residential push (Homes.com) and recent acquisitions (Matterport, Domain). FY2025 revenue was **$3.25 billion**. About **89%** of revenue is on contracts of one year or longer. GAAP net income was **$7 million** because of marketing and amortization. Adjusted EBITDA was **$480 million**.

## Floor method

The production contract has **no** low/base/high dollar value (`CSGP/research/valuation_contract.json`, evidence_blocked). The old Lawrence model is a 7-year return at a 25 times exit. That is not a present-value floor.

Rule used here:

1. Start from FY2025 adjusted EBITDA **$480 million**, subtract **$80 million** maintenance capex. That is the same **$400 million** / **$0.95 per share** owner-cash bridge already in `CSGP/research/valuation.json`. That figure is **after** Homes.com marketing. Using it as the perpetual run-rate is conservative: it assumes the land-grab spend never stops and never earns a return.
2. Assume **zero growth**.
3. Capitalize at **18 times** owner cash. That is the bear *exit* multiple from the existing model, applied **today** with no growth. It is about a 5.6% cash yield on a sticky subscription franchise.
4. Add net cash. Do not add book goodwill. Do not add Homes.com or Matterport as extra options.

## Arithmetic

| Input | Amount | Source |
|---|---:|---|
| FY2025 adjusted EBITDA | **$480 million** | Deep dive / IR reconciliation; GAAP operating income $5 million is not used |
| Maintenance capex | **$80 million** | **[Assumption]** from `CSGP/research/valuation.json` (about 17% of adj. EBITDA) |
| Owner cash | **$400 million** | 480 − 80 |
| Diluted shares | **420.7 million** | Same valuation file |
| Cash | **$1,215 million** | Q1 2026 10-Q (`filing_facts_2026-05-29.json`) |
| Long-term debt | **$1,000 million** | Same 10-Q |
| Net cash per share | **$0.51** | 215 / 420.7 |

**Step 1.** Eighteen times owner cash = 400 × 18 = **$7,200 million**.  
**Step 2.** Per share = 7,200 / 420.7 = **$17.11**.  
**Step 3.** Add net cash = 17.11 + 0.51 = **$17.62**.  
**Published floor (rounded):** **$18**.

### Cross-checks (not averaged in)

| Check | Per share | What it is |
|---|---:|---|
| 15× on the same $400 million, plus net cash | $14.77 | Extra haircut if you refuse any franchise premium |
| 15× on GAAP-ish cash ($430 million OCF − $80 million capex) | $12.99 | Uses FY2025 operating cash flow $430 million (10-K) |
| Q1 2026 adj. EBITDA annualized ~$644 million, 18×, no net cash | ~$27.50 | **Not a floor.** One quarter, still includes mix shift; can reverse |
| GAAP book | $18.81 | Goodwill from Matterport / Domain. Do not use as dhando (`option_treatment.md`) |

Eighteen times on **depressed** cash is the chosen floor. Fifteen times or GAAP cash would be a stress case, not the going-concern fair-value lower bound for a stable CRE subscription network.

## What would break the floor

- Adjusted EBITDA falls **below $400 million** for two consecutive trailing-twelve-month periods (Homes.com spend up, CRE logos down, or both).
- Net cash turns to material net debt.
- Evidence that CoStar Suite net retention has broken (the subscription moat, not the residential campaign).

## Classification (this estimate)

| Field | Value |
|---|---|
| Archetype | platform |
| Moat | stable in CRE; residential unproven |
| Dhando | **partial.** Subscription base bounds bankruptcy risk. $29 vs $18 is not "tails I don't lose much." |
| Stance | unchanged (watch). This note does not set stance. |

## Not in this number

Homes.com share gains, Matterport synergy, a return to pre-campaign margins, or any exit above 18 times. Q1 run-rate EBITDA is a **base-case** input, not a floor input.

## Open diligence

- Confirm Q2 2026 10-Q cash, debt, and adjusted EBITDA when the full-tier extract is on disk (latest full 10-Q in the digest is Q1 2026).
- Segment EBITDA for CoStar Suite / LoopNet vs Homes.com would let us raise the floor (core only) or cut it (if core is weaker than the consolidated $480 million). Until then, consolidated depressed cash is the honest lower bound.
