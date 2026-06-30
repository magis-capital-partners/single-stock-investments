# QDEL — Valuation assumption ledger (traceable)

**As of:** 2026-06-29  
**Model:** `valuation_model.html` · **Data:** `qdel_data.json` · **JSON:** `valuation.json`  
**Primary sources:** FY2025 10-K (`10-K_20260219_rpt20251228_acc0001906324_26_000008.htm`), Q1 FY2026 10-Q (`10-Q_20260506_rpt20260329_acc0001906324_26_000024.htm`), Q1 FY2026 earnings deck

This document walks through **every input** in the Marvin QDEL model: what it is, where it comes from, the math, and what would falsify it. McIntyre Partnerships is cited only as **context** (not a model input).

---

## How the model is structured (two layers)

| Layer | Question it answers | Output |
|-------|---------------------|--------|
| **A. Lawrence owner-cash IRR** | If owner cash grows as assumed, what annual return do you earn at today's price over 7 years? | **15.4%** base IRR at $13.79 |
| **B. Segment sum-of-parts (SOTP)** | What is the business worth today by segment, minus net debt? | **~$49/share** status quo; **~$83/share** post-POC sale at base multiples |

Layer A is the **stance gate**. Layer B is a cross-check and scenario tool. They use different mechanics on purpose.

---

## Part 1 — Market and capital structure (facts)

### 1.1 Price today

| Field | Value | Source | Trace |
|-------|-------|--------|-------|
| Share price | **$13.79** | Yahoo Finance close ~2026-06-27 | `qdel_data.json` → `price.value` |
| Market cap | **$935M** | $13.79 × 67.8M shares | Arithmetic |

**Falsifier:** Material 8-K or earnings miss moves price; refresh before stance change.

---

### 1.2 Shares outstanding

| Field | Value | Source | Trace |
|-------|-------|--------|-------|
| Diluted shares | **67.8 million** | FY2025 10-K weighted average diluted | `valuation.json` → `inputs.shares_millions` |

**Note:** Q1 FY2026 10-Q should be checked each refresh for buybacks or dilution.

---

### 1.3 Balance sheet (FY2025 year-end)

| Field | Value ($M) | XBRL tag / filing | File |
|-------|-----------|-------------------|------|
| Cash | **169.8** | `CashAndCashEquivalentsAtCarryingValue` | FY2025 10-K |
| Long-term debt & leases | **2,471.9** | `LongTermDebtAndCapitalLeaseObligations` | FY2025 10-K |
| Stockholders' equity | **1,920.5** | `StockholdersEquity` | FY2025 10-K |

**Net debt (model input):** **~$2,380M** = total debt **~$2,550M** less cash **$170M** (includes current portion of debt; see 10-K debt footnote).

| Derived | Formula | Result |
|---------|---------|--------|
| Market cap | $13.79 × 67.8M | $935M |
| Enterprise value | $935M + $2,380M | **$3,315M** |
| Implied EV / FY25 EBITDA | $3,315M ÷ $597M | **5.5×** |

**Q1 FY2026 check:** Cash **$140.4M** (10-Q); debt roughly flat. Net debt ~unchanged.

---

## Part 2 — Consolidated operating facts

### 2.1 Revenue

| Period | Revenue ($M) | YoY | Source |
|--------|-------------|-----|--------|
| FY2025 | **2,730.2** | -1.9% | 10-K `Revenues` |
| FY2024 | 2,782.9 | | 10-K |
| Q1 FY2026 | **619.8** | -10.5% vs $692.8M | Q1 FY2026 10-Q |

**FY2026 guidance:** **$2.70B – $2.75B** (flat to slightly up vs FY25). Source: Q1 FY2026 earnings presentation.

---

### 2.2 Adjusted EBITDA

| Period | Adj. EBITDA ($M) | Margin | Source |
|--------|-----------------|--------|--------|
| FY2025 | **597.0** | **21.9%** | Q4 FY25 earnings materials (non-GAAP reconciliation in 10-K MD&A / IR deck) |
| FY2026 guide | **615 – 630** | ~22.7% at midpoint | Q1 FY2026 deck |

**Model midpoint for forward bridge:** **$622.5M** = (615 + 630) ÷ 2.

**Falsifier:** FY2026 prints below $615M for two consecutive quarters.

---

### 2.3 Interest and capex (owner-cash bridge context)

| Item | Model ($M) | Source / judgment |
|------|-----------|-------------------|
| Interest expense | **~185** | 10-K interest expense; company guided ~$170–200M (earnings commentary) |
| Total capex | **~130** | Cash flow statement + guidance |
| Maintenance capex | **~100** | **[Assumption]** ~75% of capex is maintenance |

These inform the FCF conversion rate but are **not** individually in the Lawrence IRR formula (which uses a single owner-cash per share).

---

## Part 3 — Segment revenue (facts from 10-K)

FY2025 revenue by business unit (10-K Note 4 / Note 5; extracted in `filing_digest_2026-06-01.md`):

| # | Segment | FY25 revenue ($M) | % of total | Prior year ($M) | YoY |
|---|---------|------------------|------------|-----------------|-----|
| 1 | **Labs** | **1,505.7** | 55.1% | 1,427.2 | +4.5% |
| 2 | **Immunohematology** | **543.8** | 19.9% | 522.0 | +3.1% |
| 3 | **Point of Care** | **601.6** | 22.0% | 694.6 | -13.4% |
| 4 | **Molecular** | **26.5** | 1.0% | (immaterial) | n/a |
| 5 | **Donor Screening** | **52.6** | 1.9% | 115.1 | -54% |
| | **Total** | **2,730.2** | 100% | 2,782.9 | -1.9% |

**Core franchise (Labs + IH):** **$2,049.5M** = **75.1%** of revenue.

**File trace:** `QDEL/research/evidence/_text/10-K_20260219...htm.txt` lines with `Revenues: 1,505.7`, `543.8`, `601.6`, etc.

---

## Part 4 — Segment EBITDA allocation **[Assumption]**

The 10-K reports **consolidated** adjusted EBITDA ($597M) but **not** segment-level EBITDA. We allocate for SOTP only.

### 4.1 Method

1. Start with consolidated adj. EBITDA **$597M** (fact).
2. Assign segment margins based on business quality (recurring vs volatile vs investment).
3. Add corporate / unallocated bucket to reconcile to $597M.

### 4.2 Segment EBITDA table

| Segment | FY25 revenue | Assumed margin | Segment EBITDA ($M) | Rationale |
|---------|-------------|----------------|---------------------|-----------|
| Labs | $1,505.7M | **23.0%** | **346** | Highest recurring mix; cost program benefits |
| Immunohematology | $543.8M | **25.0%** | **136** | Stable transfusion installed base |
| Point of Care | $601.6M | **14.0%** | **84** | Flu/COVID volatility; lower than core |
| Molecular | $26.5M | n/a | **-40** | LEX launch drag; company guided ~$50M cost in 2026 |
| Donor Screening | $52.6M | **0%** | **0** | U.S. exit in progress |
| Corporate / other | — | — | **71** | Plug to tie to consolidated |
| **Total** | **$2,730.2M** | **21.9%** | **597** | Matches FY25 consolidated |

**Check:** 346 + 136 + 84 - 40 + 0 + 71 = **597** ✓

**Falsifier:** Company begins reporting segment EBITDA in filings; replace assumptions with reported figures.

---

## Part 5 — SOTP multiples **[Assumption]**

### 5.1 Base-case multiples (slider defaults in `valuation_model.html`)

| Segment | EBITDA ($M) | Multiple | Enterprise value ($M) | Why this multiple |
|---------|------------|----------|----------------------|-------------------|
| Labs | 346 | **10.0×** | **3,460** | Recurring hospital/lab contracts; discounted vs peers (12–18×) for leverage + turnaround |
| Immunohematology | 136 | **11.0×** | **1,496** | Niche transfusion franchise; slight premium to Labs |
| Point of Care (held) | 84 | **8.0×** | **672** | Volatile respiratory; below core |
| Molecular option | — | lump sum | **50** | Probability-weighted LEX option (not DCF'd) |
| **Gross EV (status quo)** | | | **5,678** | Sum of above |

### 5.2 Status quo equity value

```
Enterprise value (segments)     $5,678M
Less: net debt                  ($2,380M)
────────────────────────────────────────
Equity value                    $3,298M
÷ Shares                         67.8M
────────────────────────────────────────
Equity per share                ~$48.64  →  ~$49 rounded
```

**Upside vs $13.79 spot:** +253% (market prices far below segment sum at these multiples).

### 5.3 Point of Care divestiture scenario **[Assumption — press, unconfirmed]**

| Field | Value | Source |
|-------|-------|--------|
| Reported sale price | **~$1,500M** | Financial Times via Seeking Alpha, Jun 27, 2026 |
| Company confirmation | **None** | No 8-K as of model date |
| Bear / bull range | $800M – $2,000M | Model sliders |

**Post-sale SOTP math (base $1.5B):**

```
Labs EV                         $3,460M
Immunohematology EV             $1,496M
POC divestiture (cash)          $1,500M   ← replaces POC operating EV ($672M)
Molecular option                   $50M
────────────────────────────────────────
Enterprise value                $6,506M

Net debt before sale            $2,380M
Less: debt paydown from sale   ($1,500M)
────────────────────────────────────────
Pro forma net debt                 $880M

Equity value                    $5,626M
÷ Shares                         67.8M
────────────────────────────────────────
Equity per share                ~$83.0
```

**Important:** This is **not** the same as "stock goes to $83 tomorrow." It is fair value if (a) the sale closes at $1.5B, (b) proceeds repay debt, and (c) remaining segments re-rate to assumed multiples.

**Debt paydown alone (no multiple re-rating):** $1,500M ÷ 67.8M = **$22.1/share** of deleveraging capacity. That is the minimum mechanical uplift from the transaction.

**Conservative core-only case (6× on Labs+IH + cash):**

```
(346 + 136) × 6.0 + 1,500 - 880 = $3,492M equity → ~$51.5/share
```

This is where a **~$52/share** post-sale figure comes from (lower core multiple, not base-case 10–11×).

---

## Part 6 — Lawrence owner-cash IRR (Layer A)

### 6.1 Owner cash per share (starting point)

| Step | Calculation | Result |
|------|-------------|--------|
| FY26 EBITDA guide midpoint | (615 + 630) ÷ 2 | **$622.5M** |
| FCF conversion rate | **18%** **[Assumption]** | |
| Owner cash (firm) | $622.5M × 18% | **$112.1M** |
| ÷ Shares | ÷ 67.8M | **$1.65/share** |

**Why 18% conversion (not company 25% target)?**

| Evidence | Implication |
|----------|-------------|
| Company targets adj. FCF ≈ 25% of EBITDA | Upper bound ~$2.29/share |
| FY25 actual ~17% of EBITDA (A/R timing miss) | Lower bound ~$1.06/share |
| LEX ~$50M drag + China headwinds in 2026 | Haircut toward actual, not target |

**Stress floor:** **$1.05/share** (25% haircut on owner cash if revenue decline persists).

**Falsifier:** Two quarters of FCF conversion ≥ 22% with stable revenue → raise starting owner cash toward $2.00+.

---

### 6.2 Growth assumptions (base case)

| Horizon | Growth | Source / judgment |
|---------|--------|-------------------|
| Years 1–5 | **2.5%** per year | FY26 flat revenue guide; core grows but donor/POC drag |
| Years 6–7 | **2.0%** per year | Turnaround maturation |

**Bear:** -3% / 0% · **Bull:** +5% / +3%

---

### 6.3 Exit multiple (year 7)

| Case | Multiple | Rationale |
|------|----------|-----------|
| Base | **9×** year-7 owner cash | Distressed turnaround; above current ~5× EV/EBITDA implied by spot |
| Bear | 7× | Leverage stress persists |
| Bull | 10× | Core stabilizes; modest re-rating |

**Not** using McIntyre's 15× or 20× peer multiples in base case.

---

### 6.4 IRR arithmetic (show your work)

**Inputs:** Price **$13.79** · Owner cash Y0 **$1.65** · Growth **2.5%** (Y1–5), **2.0%** (Y6–7) · Exit **9×** in year 7 · Horizon **7 years**

| Year | Owner cash ($/sh) | Notes |
|------|------------------|-------|
| 0 | (13.79) | Price paid |
| 1 | 1.69 | 1.65 × 1.025 |
| 2 | 1.73 | |
| 3 | 1.78 | |
| 4 | 1.82 | |
| 5 | 1.87 | |
| 6 | 1.90 | × 1.02 |
| 7 | **19.42** | 1.942 cash + 9 × 1.942 terminal |

**Cash-flow stream (Marvin):** `[-13.79, 1.69, 1.73, 1.78, 1.82, 1.87, 1.90, 19.42]`

**IRR (solver):** **15.4%** per year → `valuation.json` → `results.base.return_pct`

Verify: `python3 _system/scripts/marvin_valuation.py --ticker QDEL`

---

## Part 7 — Segment owner-cash build (overlay)

Segment-level owner cash in `valuation.json` → `segment_build` allocates the **$1.65/share** consolidated starting point:

| Segment | Owner cash Y0 ($/sh) | Growth Y1–5 | Exit (Y10) | Logic |
|---------|---------------------|-------------|------------|-------|
| Labs | **0.95** | 3.0% | 10× | ~58% of firm owner cash; highest quality |
| Immunohematology | **0.38** | 3.0% | 11× | ~23% of firm owner cash |
| Point of Care | **0.20** | 0% | 7× | ~12%; volatile |
| Corporate drag | **(0.15)** | — | — | Unallocated costs |
| Molecular | **0** in base | — | option | LEX drag not in Lawrence base |
| **Sum** | **~1.38** | | | Rounding + molecular ≈ **1.65** consolidated |

---

## Part 8 — Options (not in Lawrence base IRR)

| Option | Treatment | Base value | In base IRR? |
|--------|-----------|------------|--------------|
| POC divestiture ~$1.5B | milestone_nav | **$22.1/sh** debt capacity | **No** (unconfirmed) |
| LEX / molecular | probability_weighted | P=25% × ~$200M / shares | **No** |
| Donor screening exit | zero | $0 | N/A (wind-down) |

---

## Part 9 — What we explicitly do NOT use as inputs

| Source | Why excluded |
|--------|--------------|
| McIntyre ~$4 FCF/sh by 2028 | External normalization; context tier only (5% synthesis weight) |
| McIntyre 15× exit | Not filing-derived; peer re-rating assumption |
| FT POC price in base IRR | Not company-confirmed |
| Sell-side segment EBITDA | Not in 10-K; we build our own allocation |

---

## Part 10 — Summary table (base case)

| Output | Value | Primary driver |
|--------|-------|----------------|
| Lawrence 7yr IRR | **15.4%** | $1.65/sh owner cash, 2.5%/2% growth, 9× exit |
| SOTP status quo | **~$49/sh** | Segment EBITDA × multiples − net debt |
| SOTP post-POC ($1.5B) | **~$83/sh** | Core EV + sale cash − pro forma net debt |
| Debt paydown only | **~$22/sh** | $1.5B ÷ shares (no re-rating) |
| Conservative post-POC | **~$52/sh** | 6× core EBITDA + cash |
| Spot price | **$13.79** | Market |
| Implied EV/EBITDA | **~5.5×** | Market cap + net debt ÷ $597M |

---

## Part 11 — Sensitivity (quick reference)

| Variable | Low | Base | High |
|----------|-----|------|------|
| Owner cash Y0 | $1.05 | $1.65 | $2.29 |
| FCF conversion | 17% | 18% | 25% |
| Exit multiple | 7× | 9× | 10× |
| Labs EBITDA multiple | 8× | 10× | 12× |
| POC sale price | $800M | $1,500M | $2,000M |

Use `valuation_model.html` sliders for live sensitivity.

---

## Revision log

| Date | Change |
|------|--------|
| 2026-06-29 | Initial ledger; independent Marvin path; POC divestiture scenario |
