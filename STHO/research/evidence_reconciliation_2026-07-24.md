# STHO evidence reconciliation — 2026-07-24

**Ticker:** STHO  
**Method profile:** catalyst_asset_value  
**Purpose:** Close universal contract blockers with filing-backed calculation_proof graphs on all seven additive components.

## Sources

| Source | Path | Period |
|--------|------|--------|
| Form 10-Q | `STHO/investor-documents/sec-edgar/10-Q_20260508_rpt20260331_acc0001953366_26_000010.htm` | 2026-03-31 |
| Form 10-K | `STHO/investor-documents/sec-edgar/10-K_20260217_rpt20251231_acc0001953366_26_000003.htm` | 2025-12-31 |
| 8-K Asbury deconsolidation | `STHO/investor-documents/sec-edgar/8-K_20260401_exhibit_stho-20260327xex99d1.htm_acc0001953366_26_000006.htm` | 2026-03-27 |
| Prior reconciliation | `STHO/research/evidence_reconciliation_2026-07-16.md` | 2026-07-16 |

Shares outstanding (FACT): **12,081,333** (10-Q cover, May 6, 2026).

---

## Gap 1 — `safe_stake_mark_and_margin_loan`

**Status:** `accepted`

### Proof linkage
- `safehold_equity_stake`: `net_asset_value@1.0` — implied 13,525,499 SAFE shares × scenario SAFE price ÷ STHO shares → base **$18.48/sh**
- `senior_debt`: `net_asset_value@1.0` — Note 9 debt obligations net **$207.001M** → base **−$17.10/sh**

### Remaining limitations (documented, not blocking)
- Exact integer SAFE share count not disclosed (derived from FV ÷ price).
- Numeric LTV / collateral-posting trigger percentages not in 10-Q.

### Falsifier
SAFE forced-sale or collateral path nets below low SAFE component after facility friction.

---

## Gap 2 — `legacy_asset_sale_schedule`

**Status:** `accepted`

### Proof linkage
- `legacy_monetizing_portfolio`: MD&A schedule **$71.4M** carrying × recovery fraction → base **$5.30/sh**
- `magnolia_asbury_development_ops`: residual **$153.6M** carrying × recovery fraction → base **$7.50/sh**
- `zero_carry_and_entitlement_option`: incremental option only (non-overlapping with Magnolia carrying cases) → base **$0.20/sh**

### Remaining limitations
- No asset-by-asset third-party bids for residual Magnolia lots or Asbury operating real estate.

### Falsifier
Sales proceed below low-case recovery on either bucket after costs.

---

## Gap 3 — `fee_tax_and_related_party_waterfall`

**Status:** `accepted`

### Proof linkage
- `wind_down_fee_and_friction_reserve`: contractual fee path + friction reserve → base **−$1.40/sh**
- Cash taxes de minimis (DTA allowance zero; $0.2M paid in 2025).

### Remaining limitations
- Post-2027 2% GBV fee path uses estimated gross book value ex-SAFE shrinkage.

### Falsifier
Fees, termination payment, or tax leakage exceed $2.50/sh present value.

---

## Component proof sum (base case)

| Component | Method | Base $/sh |
|-----------|--------|-----------|
| Safehold equity stake | net_asset_value@1.0 | 18.48 |
| Legacy monetizing portfolio | probability_weighted_catalyst_nav@1.0 | 5.30 |
| Magnolia / Asbury residual | probability_weighted_catalyst_nav@1.0 | 7.50 |
| Cash and restricted | net_asset_value@1.0 | 5.10 |
| Senior debt | net_asset_value@1.0 | −17.10 |
| Fee and friction reserve | net_asset_value@1.0 | −1.40 |
| Zero-carry / entitlement option | probability_weighted_catalyst_nav@1.0 | 0.20 |
| **Total** | component sum | **≈18.1** |

Cross-check: Q1 book **$19.88/sh**; gap reflects judgment haircuts on residual real estate and fee reserve vs GAAP equity.

---

## Acceptance summary

| Gap | Status | Closure basis |
|-----|--------|---------------|
| safe_stake_mark_and_margin_loan | accepted | Reproducible mark and debt arithmetic in calculation_proof graphs |
| legacy_asset_sale_schedule | accepted | Split monetizing vs residual carrying; overlap keys non-overlapping |
| fee_tax_and_related_party_waterfall | accepted | Fee schedule anchored reserve with explicit judgment bounds |

**Committee conclusion:** Contract blockers closed with proof-first component schedule. Residual uncertainties remain in `economic_value.limitations` and **[HUMAN REVIEW]**; do not promote stance without human decision authority.
