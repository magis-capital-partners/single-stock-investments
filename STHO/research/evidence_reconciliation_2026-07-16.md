# STHO evidence reconciliation — 2026-07-16

**Ticker:** STHO  
**Method profile:** catalyst_asset_value  
**Purpose:** Retrieve primary evidence for the three critical valuation blockers and correct the cash/debt arithmetic error in the prior NAV overlay.

## Sources

| Source | Path | Period |
|--------|------|--------|
| Form 10-Q | `STHO/investor-documents/sec-edgar/10-Q_20260508_rpt20260331_acc0001953366_26_000010.htm` | 2026-03-31 |
| Form 10-K | `STHO/investor-documents/sec-edgar/10-K_20260217_rpt20251231_acc0001953366_26_000003.htm` | 2025-12-31 |
| 8-K / Ex-99.1 Asbury pro forma | `STHO/investor-documents/sec-edgar/8-K_20260401_exhibit_stho-20260327xex99d1.htm_acc0001953366_26_000006.htm` | 2026-03-27 |
| 8-K / Ex-99.1 Q1 results | `STHO/investor-documents/sec-edgar/8-K_20260508_exhibit_stho-20260508xex99d1.htm_acc0001953366_26_000011.htm` | 2026-05-08 |
| Market | Yahoo SAFE close | 2026-07-16 |

Shares outstanding (FACT): **12,081,333** as of May 6, 2026 (10-Q cover).

---

## Gap 1 — `safe_stake_mark_and_margin_loan`

**Status:** `partially_met`

### Facts
- Owned **approximately 13.5 million** SAFE shares (18.8% of SAFE) at 2026-03-31 (10-Q Note 7).
- Q1 mark: **$183.0M** at SAFE **$13.53** → implied share count **13,525,499** (= 183.0 / 13.53).
- Current SAFE close **$16.93** (2026-07-16) → gross mark **$229.0M** = **$18.95/STHO share**.
- Margin Loan Facility (Note 9): principal **$92.777M**, SOFR + 3.50%, maturity **March 2028**, first-priority pledge of Safe Shares, PIK election (+25 bp next period), delayed-draw capacity about **$15.8M**, Morgan Stanley.
- Safe Credit Facility (related party Safe): **$115.0M** at **8.00%** (10% if incremental drawn), maturity **March 2028**.
- Total debt obligations, net: **$207.001M**.
- Sale of Safe Shares: net proceeds applied per Margin Loan terms; declines can require prepayment or additional collateral.
- Governance Agreement restricts transfers to Activists / Company Competitors.

### Calculations
| Step | Math | Result |
|------|------|--------|
| Implied SAFE shares | 183,000,000 / 13.53 | 13,525,499 |
| Gross mark now | 13,525,499 × 16.93 | $228,986,698 |
| Per STHO share | $228,986,698 / 12,081,333 | $18.95 |
| Margin LTV at Q1 mark | 92.777 / 183.0 | 50.7% |
| Margin LTV at now mark | 92.777 / 229.0 | 40.5% |
| SAFE net of margin only | (228,986,698 − 92,777,000) / shares | $11.27 |

### Remaining uncertainty
- Exact integer share count not stated (only “approximately 13.5 million”).
- Numeric LTV / collateral-posting trigger percentages not disclosed (amendment “eased” them).
- Make-whole on margin prepayment not quantified in the 10-Q narrative.

### Affected components
`safehold_equity_stake`, `senior_debt`

### Valuation consequence
Gross SAFE component refreshed to current market (~$18.95/sh before friction). Senior debt corrected to about **−$17.13/sh** (prior **−$1.19** was wrong).

### Falsifier
SAFE forced-sale / collateral path nets below the low SAFE component after facility friction.

---

## Gap 2 — `legacy_asset_sale_schedule`

**Status:** `partially_met`

### Facts — MD&A monetizing portfolio (Q1 2026)
| Bucket | Carrying ($M) | $/STHO sh |
|--------|---------------|-----------|
| One loan | 16.1 | 1.33 |
| Ten AFS debt securities | 38.2 | 3.16 |
| Land (monetizing) | 14.4 | 1.19 |
| Two other properties | 2.7 | 0.22 |
| **Total monetizing** | **71.4** | **5.91** |
| Zero-carry loans/equity | 0.0 | 0.00 (option only) |

### Facts — Magnolia / Asbury residual (not in $71.5M monetizing line)
| Item | Evidence |
|------|----------|
| Magnolia Green | ~1,900 acres; entitled 3,550 units + ~193 commercial acres; YE2025 carrying **$28.9M**; lot sales expected over next ~2 years (10-K) |
| Asbury Park Waterfront | YE2025 carrying **~$127.6M**; Surfhouse multifamily venture deconsolidated 3/27/2026 after **$10.6M** mezz repaid and guaranty released (8-K / Note 5) |
| Q1 L&D net | **$100.5M** |
| Q1 RE net | **$70.2M** (buildings cost −~$80M with deconsolidation) |
| Residual after removing monetizing land/other | **$153.6M** = **$12.72/sh** |
| Q1 land development revenue / COS | $11.0M / $9.3M |

### Remaining uncertainty
- No asset-by-asset bid sheet or contracted sale prices for Magnolia remaining lots / Asbury hotels & sites.
- Entitlement surplus above residual carrying is uncontracted.

### Affected components
`legacy_monetizing_portfolio`, `magnolia_asbury_development_ops`, `zero_carry_and_entitlement_option`

### Valuation consequence
Split the old single “legacy $71.5M” line so Magnolia/Asbury residual carrying is no longer invisible. Prior book identity (15.15+5.92−1.19=19.88) hid ~$12.72/sh of carrying behind a false cash/debt figure.

### Falsifier
Sales proceed below low-case recovery on either legacy bucket after costs.

---

## Gap 3 — `fee_tax_and_related_party_waterfall`

**Status:** `partially_met`

### Facts — Management Agreement (Note 1)
| Annual term ended | Fee |
|-------------------|-----|
| 2024-03-31 | $25.0M |
| 2025-03-31 | $15.0M |
| 2026-03-31 | $10.0M |
| Current term (to 2027-03-31) | **$7.5M** |
| Thereafter | **2.0% of GBV excluding Safe Shares** |
| Q1 2026 recorded | **$2.5M** |
| Termination without cause before 2027-03-31 | **$55M − fees paid to date** (~$5M overhang after $50M paid through 2026-03-31) |
| Manager | Safehold Management Services Inc. (Safe subsidiary) |

### Facts — Tax
- YE2025: deferred tax benefit $17.4M offset by valuation allowance → **DTA net realizable value zero**.
- Cash taxes paid 2025: **$0.2M**.

### Calculation (illustrative fee path, estimate)
Assume $7.5M for current term then 2% of GBV ex-SAFE starting from Q1 assets − SAFE mark (~$297M), shrinking 25%/year for four years:

Sum undiscounted ≈ **$19.7M** ≈ **$1.63/STHO share** (before discounting / sale friction).

### Remaining uncertainty
- Exact GBV definition for the 2% fee after year four.
- Transaction costs and cash tax on gains not scheduled asset-by-asset.
- Whether termination fee is a realistic path (judgment).

### Affected components
`wind_down_fee_and_friction_reserve`

### Valuation consequence
Fee reserve anchored to contractual schedule (~$1.0 to $2.5/sh) rather than a placeholder.

### Falsifier
Fees, termination payment, or tax leakage exceed $2.50/sh present value.

---

## Acceptance summary

| Gap | Status | Why not fully accepted |
|-----|--------|------------------------|
| safe_stake_mark_and_margin_loan | partially_met | Mark + debt arithmetic done; exact share count and LTV trigger % still undisclosed |
| legacy_asset_sale_schedule | partially_met | Carrying schedule rebuilt; no primary sale-price bids for residual Magnolia/Asbury |
| fee_tax_and_related_party_waterfall | partially_met | Fee schedule contractual; multi-year GBV fee path and sale-tax friction still estimated |

**Committee conclusion:** Evidence deepened and a material NAV arithmetic error corrected. Security remains **evidence-blocked** until residual sale evidence and LTV triggers are closed or explicitly marked unavailable.

---

## Thesis evaluation (human prompts, 2026-07-16)

### 1) “SAFE deal marked assets at ~$25”

| Class | Point |
|-------|-------|
| **FACT** | On merger/spin day **2023-03-31**, SAFE closed **$25.80** (Yahoo), with a **0.16** stock split that day. Round **$25** is the right mental anchor. |
| **CALC** | 13,525,499 implied shares × $25 = **$338.1M** = **$27.99/STHO share**. |
| **FACT** | Current SAFE **$16.93** → **$18.95/STHO share** (~**32%** below the deal mark). |
| **JUDGMENT** | The ~$25 level is a **cross-check / high-case anchor**, not a floor or contractual put. Valuation high case now uses a path back toward that mark. |

### 2) “Long-duration ground leases — rates down, value up”

| Class | Point |
|-------|-------|
| **FACT** | SAFE’s business is long-term **ground leases** (STHO 10-Q Note 7 description). |
| **FACT (SAFE IR, context)** | Typical ~**99-year** leases; decks cite ~**91–92 year** weighted-average extended lease term. |
| **INFERENCE** | Equity duration is long; SAFE’s mark has been rate-sensitive since the 2023 deal. Lower rates are a plausible path from $16.93 back toward ~$25. |
| **JUDGMENT** | Credit rate relief in the **high** SAFE component only; do not bake a rate cut into base. |

### 3) “Real estate book understated — depreciated, actively selling”

| Class | Point |
|-------|-------|
| **FACT** | Land/lot sales clear **above** cost of sales: 2025 +$17.6M, 2024 +$11.3M, 2023 +$9.7M, Q1 2026 +$1.7M (revenue − COS). |
| **FACT** | Q1 accum. depreciation RE+L&D ≈ **$39.3M** (~**$3.26/sh**) — a ceiling on depreciation add-back, not automatic equity. |
| **FACT** | Operating **buildings** were **not** sold in 2025 or 2023 (10-K Note 4) — Asbury hotel/ops premium unproven. |
| **JUDGMENT** | Raise Magnolia/Asbury and monetizing **base/high** for lot-sale evidence; do **not** add full accum. dep. to base. |

### 4) “Multiple parties can bid on management later this year”

| Class | Point |
|-------|-------|
| **FACT** | Without-cause termination: **180 days** notice + **2/3** independent trustees (Note 1). |
| **FACT** | Termination-fee formula ($55M − fees paid) applies if termination is **before 2027-03-31**. After that date, the disclosed fee trigger falls away. |
| **FACT** | Current overhang ≈ **$5M** after $50M fees paid through 2026-03-31. |
| **JUDGMENT** | The real contestability cliff is **2027-03-31**, not a 2026 free option. **H2 2026** is the practical RFP window so a new manager can be effective at/after that date. High case trims fee drag; base still assumes Safehold manages most of the wind-down. |

### Valuation consequence of this pass

Component ranges updated: SAFE high → deal-mark path; Magnolia/Asbury base/high up on sale margins; fee high less punitive on post-2027 contestability. Still **evidence-blocked** (LTV triggers, asset bids, exact share count).
