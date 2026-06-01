# TPL — Cross-Check: Horizon Kinetics Hard-Asset Lens

**Date:** 2026-06-01  
**Agent:** Marvin  
**Cross-checks:** `TPL/research/deep_dive_2026-06-01.md` vs Horizon Kinetics commentaries + primary filings  
**Framework:** `_system/frameworks/hk_cross_reference.md`, `external_view_blend.md`

---

## Executive summary

The inaugural TPL deep dive correctly documents **filings** (FY2025 revenue **$798M**, water segment **$307M**, GAAP equity **~$21/sh** vs **~882k** off-balance-sheet acres) and applies a **segment NAV overlay** (**~$162/sh** segment PV vs **~$393** price). Horizon Kinetics frames TPL as a **Level 1 strategic hard asset** (land, water, pipeline optionality) that index investors **cannot access** at meaningful weight. Those views **agree on asset quality** but **diverge on return at today's price**: Marvin's falsifier-adjusted ten-year return is **-1.0%** at **~$393** on **$7.91/sh** owner cash; HK does not publish a dated price target but treats TPL as a multi-decade **own, not trade** holding.

**Synthesis (best estimate):** Keep **watch**. HK material supports **partial dhando on hidden asset value** and **water scarcity optionality**, not a base-case Lawrence IRR upgrade. NAV / optionality stays **outside base IRR** until human approves a blend. Post-Stahl governance remains **[HUMAN REVIEW]** (LCI 2026; not in base IRR).

---

## Mental models applied

| Model | Finding |
|-------|---------|
| **Predictive attributes (HK)** | No dated mispricing signal at spot; scarcity is **descriptive**, not a timed catalyst |
| **Hard-asset scarcity (HK Q1 2026)** | Land and water supply fixed; index cannot replicate exposure |
| **Index mis-weighting (HK Q1 2025)** | S&P weights land **0%**, water **~0.02%** vs TPL economics |
| **Market structure discount** | Yield screens ignore asset NAV; GAAP book misstates 1888 trust assets |
| **Inversion (Munger)** | Paying **~50×** run-rate cash flow with **-1%** base return if Permian activity normalizes |
| **Dhando (Pabrai)** | **Partial**: quality asset, weak payoff at price; floor is **not** GAAP book |

**Predictive attribute:** `hard_asset_scarcity` (descriptive) — not `equity_yield_curve` (no dated recovery event)

---

## HK thesis vs primary-source reality

### What Horizon Kinetics argued

**Q1 2025 Commentary** (`horizon-kinetics/HK-Q1-2025-Commentary-extract.txt`, pp. 15–16):

- S&P 500 weights **land 0%**, **water ~0.02%** (even if imputing TPL water revenue share).
- Regulated water utilities are **not** comparable; free-market subsurface water (TPL model) differs.
- TPL cited alongside Land Bridge / Aris as pure-market water exposure AI/data-center demand cannot index into.

**Q1 2026 Commentary** (`horizon-kinetics/HK-Q1-2026-Commentary-extract.txt`, pp. 21–22):

- TPL is flagship **Level 1 strategic** holding: hard assets "as close to permanent as practicably be."
- Pipeline / private opportunities (LandBridge, WaterBridge, Bolt Energy) grew from TPL-related engagement.
- Strategic assets compound for **decades**; exchanges and royalty trusts now public enable this portfolio shape.

**Worth-The-Time interview** (`Stahl-Worth-The-Time-Predictive-Attributes-extract.txt`):

- Murray Stahl on TPL board; HKAM **no trading authority** on TPL shares; conflict policies disclosed.

### What filings show (Marvin floor)

**Source:** `TPL/investor-documents/sec-edgar/10-K_20260218_rpt20251231_acc0001811074_26_000018.htm`

| Item | Fact |
|------|------|
| FY2025 revenue | **$798.2M** (+81% YoY) |
| Water segment revenue | **$307.5M** (~39% of total) |
| FY2025 operating cash flow | **$545.9M** (~**$7.91/sh** owner cash basis in dive) |
| GAAP stockholders' equity | **$1.46B** (~**$21/sh**) |
| Assigned 1888 trust land/royalty | **No balance-sheet value** (fair value never determined at formation) |
| Q1 2026 revenue | **$236.8M** (+21% YoY); OCF **$162.0M** |

**Inference:** HK's **water index-weight** argument is **directionally correct** and **understated** in public indices. Marvin's segment build (**~$162/sh** PV on explicit producing paths) is a filing-grounded attempt to quantify what HK describes qualitatively; both show **price >> explicit cash-flow PV** at **~$393**.

---

## Agreements, divergences, synthesis

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | **$7.91/sh** start; segment PV **~$162/sh** | **-1.0%** per year (10yr base) | watch |
| HK strategic (Q1 2026) | Hard asset + pipeline optionality not in GAAP | Multi-decade own; no spot IRR cited | long-term strategic |
| **Blended best estimate** | **Filing cash + NAV overlay separate** | **-1.0%** base; optionality not in IRR | **watch** |

**Weights:** Marvin **65%** on return math at **~$393** (filings, explicit assumptions); HK **35%** on asset scarcity and strategic context (supports **partial dhando**, not accumulate at spot).

**Returns statement (blended):** At **~$393**, we expect about **-1.0%** per year on current owner cash in the base case; HK hard-asset framing validates **quality and hidden NAV** but does **not** clear the **15%** bar or justify sizing without a lower entry or approved NAV blend.

---

## What the deep dive got right / wrong

| Deep dive claim | Assessment |
|-----------------|------------|
| No HK predictive attribute at spot | Correct — scarcity is not a dated payoff |
| GAAP book misleading | Correct; aligns with HK index-weight argument |
| Water segment material (~39% rev) | Correct; supports HK water scarcity thesis |
| Falsifier-adjusted **-1.0%** at **~$393** | Correct filing-based math |
| NAV overlay required | Correct; matches HK "land not on balance sheet" logic |
| HK governance transition cited (LCI) | Correct; **[HUMAN REVIEW]** appropriate |

---

## Classification

| Field | Value |
|-------|-------|
| **Archetype** (Stahl) | infrastructure / land |
| **Moat** (Munger) | partial (scarcity; not pricing power at any price) |
| **Dhando** (Pabrai) | partial |
| **Stance** | watch |
| **Cycle** | mid (Permian activity elevated) |
| **Predictive attribute** | hard_asset_scarcity (descriptive) |

---

## [HUMAN REVIEW]

- [ ] Approve any **NAV blend** into `valuation.json` → `estimates.external[]` (HK strategic case not in base IRR today).
- [ ] Confirm post-Stahl board / incentive changes (LCI 2026) affect stance.
- [ ] Track Q2 2026 water volume and Permian rig count vs segment growth assumptions.

---

## [PROPOSED MEMORY]

- [PROPOSED HK] TPL: HK Q1 2025 index-weight argument (land 0%, water ~0.02%) matches filing reality that GAAP and indices understate TPL economics; does not by itself justify positive ten-year IRR at **~$393**.
- [PROPOSED COMPANY] TPL: cross-check 2026-06-01 — watch stance; HK context tier only until NAV blend approved.

---

## Primary sources cited

1. `TPL/investor-documents/sec-edgar/10-K_20260218_rpt20251231_acc0001811074_26_000018.htm`
2. `TPL/investor-documents/sec-edgar/10-Q_20260506_rpt20260331_acc0001811074_26_000035.htm`
3. `_system/reference/investment-wisdom/horizon-kinetics/HK-Q1-2025-Commentary-extract.txt`
4. `_system/reference/investment-wisdom/horizon-kinetics/HK-Q1-2026-Commentary-extract.txt`
5. `_system/reference/investment-wisdom/horizon-kinetics/Stahl-Worth-The-Time-Predictive-Attributes-extract.txt`
6. `TPL/research/deep_dive_2026-06-01.md`
7. `TPL/third-party-analyses/hk_scan_2026-06-01.md`
