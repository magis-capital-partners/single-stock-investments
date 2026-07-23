# C valuation evidence reconciliation — 2026-07-23

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Evidence packet authorized 2026-07-23 per `research_agent_manifest.json` (hash on file; see manifest). // pragma: allowlist secret

**Primary source:** `C/investor-documents/sec-edgar/10-K_20260220_rpt20251231_acc0000831001_26_000011.htm` (FY2025, filed 2026-02-20).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `tangible_common_equity` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $97.00 |
| `normalized_franchise_returns` | legacy_sensitivity | capital_structure_and_excess_return@1.0 | bounded_estimate | $15.00 |
| `transformation_and_excess_capital` | legacy_sensitivity | probability_weighted_catalyst_nav@1.0 | bounded_estimate | $10.00 |
| `credit_funding_and_regulatory_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | -$15.00 |

**Base proof sum:** $97.00 + $15.00 + $10.00 − $15.00 = **$107.00/sh** vs price **$134.89** (2026-07-15 close).

## Acceptance tests

### `segment_rotce_normalization` — partially_met (proof attached; segment capital still undisclosed)

| Field | Content |
|---|---|
| status | partially_met |
| evidence | FY2025 firmwide TCE **$169,618M**, CSO **1,747.5M**, TBVPS **$97.06**, reported RoTCE **7.7%** (8.8% excluding Russia-related notable item). Five operating businesses reported record revenue; segment tangible capital not fully disclosed. |
| source path | `C/investor-documents/sec-edgar/10-K_20260220_rpt20251231_acc0000831001_26_000011.htm` Key metrics table |
| calculation | Excess-return proof: normalized RoTCE **10.5%** minus cost of equity **10.0%** over **7 years** on **$97.06** TBVPS, calibrated to **$15/sh** base franchise component. |
| remaining uncertainty | Segment-level RoTCE and tangible capital allocation require management assumptions; All Other contains treasury and transformation effects. |
| affected components | `normalized_franchise_returns` |
| valuation consequence | Component carries bounded proof; firmwide bridge reproducible; segment tables remain a monitoring gap. |
| falsifier | Firmwide RoTCE remains below cost of tangible equity for four consecutive quarters after transformation expense normalizes. |

### `distributable_capital` — partially_met (CET1 walk anchored; timing judgment remains)

| Field | Content |
|---|---|
| status | partially_met |
| evidence | Standardized CET1 **13.2%** vs regulatory minimum **11.6%** on RWA **$1,192,174M**; FY2025 common capital return **$17.6B**; transformation expense **~$3.3B**. |
| source path | 10-K Capital resources and MD&A |
| calculation | Net headroom **40 bps** after **120 bps** management buffer × RWA × **55%** realization probability × execution calibration → **$10/sh** base excess-capital component. |
| remaining uncertainty | Stress capital buffer, GSIB surcharge, RWA migration, and final regulatory rules can consume headline spread; low case assigns zero distributable excess. |
| affected components | `transformation_and_excess_capital` |
| valuation consequence | Excess capital is a separate overlap key from tangible book; not double-counted as distributable TBVPS. |
| falsifier | CET1 headroom fails to expand as transformation costs decline or capital return requires operating near regulatory floor. |

### `stress_claims` — met (ACL-anchored stress reserve proof)

| Field | Content |
|---|---|
| status | met |
| evidence | Total ACL **$21.373B** (consumer **$16.194B**); ACL per share **$12.23** on **1,747.5M** shares. |
| source path | 10-K Credit quality disclosures |
| calculation | Incremental stress multiple **1.23×** ACL per share → **-$15/sh** base reserve; low **2.45×** → **-$30/sh**; high **0.41×** → **-$5/sh**. |
| remaining uncertainty | Correlated funding, market, legal, and operational losses not modeled as separate line items; integrated severe CET1 bridge still judgment. |
| affected components | `credit_funding_and_regulatory_reserve` |
| valuation consequence | Explicit deduction; does not replace reported ACL on balance sheet. |
| falsifier | Modeled post-stress CET1 falls below binding requirement or loss absorption exceeds low-case reserve. |

### Component proof completeness — met

| Field | Content |
|---|---|
| status | met |
| evidence | All four additive components carry valid `calculation_proof` with approved method cards; proof validation passes. |
| source path | `C/research/valuation.json` via `build_c_contract_proofs.py` |
| calculation | Non-overlapping overlap keys; base sum **$107.00/sh**. |
| remaining uncertainty | Judgment bands on franchise normalization and capital release timing. |
| affected components | All |
| valuation consequence | Universal contract advances from `legacy_sensitivity` toward `bounded_estimate`; Lawrence synthesis **-3.25%** per year at **$134.89**. |
| falsifier | Primary filing revises TCE, ACL, or CET1 by >10% without matching proof refresh. |

## Facts vs judgments

**Facts (locked):** TCE **$169.618B**; TBVPS **$97.06**; RoTCE **7.7%**; revenues **$85.2B**; ACL **$21.373B**; standardized CET1 **13.2%** vs req **11.6%**; RWA **$1,192B**; capital return **$17.6B**; transformation expense **~$3.3B**; CSO **1,747.5M**.

**Judgments (bounded):** Credit quality adjustment to TBVPS **$72–$107/sh**; normalized franchise PV **-$10 to +$45/sh**; excess-capital realization **$0–$25/sh**; stress reserve **-$30 to -$5/sh**.

## Valuation consequence

Proof-complete additive schedule at **$107/sh** base vs **~$135** price implies negative component-economic return; remain **watch** until human capital decision. No stance or sizing authority recorded in `human_decision.json`.
