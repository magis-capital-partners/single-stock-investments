# CPRT — Lower bound fair value

**Date:** 2026-09-17  
**Status:** Research estimate. Not a production contract rewrite and not capital authority.  
**Method:** No-growth owner-cash capitalization plus net cash. Land is a cross-check, not an add-on.

## Headline

| | |
|---|---|
| **Lower bound fair value** | **$20 per share** |
| Price today | **$29.66** (Yahoo close 2026-09-17) |
| Price vs floor | 1.48 times the floor (price is **33% above**) |
| Proof-first model low | $24.29 (still assumes growth and an 18 times exit) |
| Economic book (land re-mark) | $14.81 |

The stock is **above** the floor. The floor answers "what is it worth if volumes and used-car prices stop compounding," not "what should we pay to earn 15%."

## What this business is

Copart runs a salvage-vehicle auction network. Insurers send wrecked cars; Copart stores them on owned yards and sells them to a global buyer base. FY2025 contract revenue was about **$4.0 billion**, operating income about **$1.70 billion**, and there is **no debt**.

## Floor method (why this, not the DCF low)

The production DCF low of **$24.29** still grows owner earnings at **5.6% per year** (35% reinvestment times 16% incremental return) and exits at **18 times** year-7 owner earnings. That is a conservative *growth* case. A **lower bound of fair value** should not need growth or multiple expansion.

Rule used here:

1. Take evidenced owner cash after capex.
2. Assume **zero growth**.
3. Capitalize at **12 times** (about an 8% cash yield), which is a trough multiple for a durable auction franchise, not a software fantasy multiple.
4. Add **net cash**. Do **not** also add land: the yards are what produce the owner cash. Adding both would count the same asset twice.
5. Set unproven options to zero.

## Arithmetic

| Input | Amount | Source |
|---|---:|---|
| Owner cash | **$1,230.76 million** | Locked proof fact: FY2025 operating cash flow net of capex. `CPRT/research/valuation.json` (tag `NetCashProvidedByUsedInOperatingActivities`, FY2025 10-K) |
| Diluted shares | **925.81 million** | 10-Q period ended 2026-04-30 |
| Cash | **$3,354.14 million** | Same 10-Q |
| Debt | **$0** | 10-K long-term debt tag |
| Net cash per share | **$3.62** | 3,354.14 / 925.81 |

**Step 1.** Twelve times owner cash = 1,230.76 × 12 = **$14,769 million**.  
**Step 2.** Per share = 14,769 / 925.81 = **$15.95**.  
**Step 3.** Add net cash = 15.95 + 3.62 = **$19.57**.  
**Published floor (rounded):** **$20**.

### Cross-checks (not averaged in)

| Check | Per share | What it is |
|---|---:|---|
| Gordon, 12% required return, zero growth, plus cash | $14.71 | Too harsh for this moat; treats Copart like a melting ice cube |
| Proof-first DCF low | $24.29 | Growth still inside the number |
| Filed GAAP book | $9.92 | Land at historical cost; not a fair-value floor (`option_treatment.md`) |
| Economic book (comp land + other equity at cost) | $14.81 | `CPRT/research/book_estimate.json`. Parallel asset check. **[HUMAN REVIEW]** on the land comps |

The economic book sits **below** the earnings floor. That is expected: the yards are worth more in use than as vacant land. The earnings floor is the binding lower bound of *fair value*. Book is the binding lower bound of *liquidation*.

## What would break the floor

- Trailing owner cash stays below about **$1.0 billion** for two fiscal years (volume or fee collapse).
- Copart takes on material net debt, or cash is no longer excess.
- A second national salvage network takes insurer assignments at scale.

## Classification (this estimate)

| Field | Value |
|---|---|
| Archetype | compounder |
| Moat | stable |
| Dhando | full on the *business*; **not** full at $29.66 vs a $20 floor |
| Stance | unchanged (watch / core per holdings). This note does not set stance. |

## Not in this number

International yard optionality, catastrophe volume spikes, and any re-rating above 12 times. Those belong in base or high cases, not the floor.
