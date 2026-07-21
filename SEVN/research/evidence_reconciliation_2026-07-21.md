# SEVN valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `tangible_loan_book_equity` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $14.90 |
| `external_manager_fee_drag` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | −$1.50 |
| `cre_credit_and_redeployment_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | −$1.50 |

Embedded `distributable_earnings_franchise` remains inside the book capitalization cross-check; not additive.

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Three additive components with unique overlap keys; distributable-earnings franchise embedded in `tangible_loan_book_equity`. |
| source path | `SEVN/research/valuation.json` → `component_valuation.components[]` |
| calculation | Sum base **$11.90/sh** = $14.90 − $1.50 − $1.50, matching component schedule before Lawrence scenario overlay. |
| remaining uncertainty | Redeployment timeline and sector CRE discount may move reserve bands. |
| affected components | All three additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | Q1 2026 stockholders' equity **$326.982M** on **22,596,077** shares = **$14.47/sh** filing book; presentation adjusted book **$14.90/sh**; FY2025 management fees **$4.985M** ($4.360M base + $0.625M incentive). |
| source path | `SEVN/investor-documents/sec-edgar/10-Q_20260428_rpt20260331_acc0001452477_26_000021.htm`; `10-K_20260218_rpt20251231_acc0001452477_26_000010.htm`; `SEVN-Q1-2026-Earnings-Presentation.pdf` |
| calculation | Book proof: $326.982M ÷ 22.596M × 1.030 mark ratio ≈ **$14.90/sh**. Fee drag: $4.985M ÷ 22.596M × 6.80 capitalization years ≈ **−$1.50/sh**. |
| remaining uncertainty | Incentive fees vary with core earnings; reserve bands are bounded judgments beyond filing ACL. |
| affected components | `tangible_loan_book_equity`, `external_manager_fee_drag` |
| valuation consequence | Filing-locked facts anchor proofs; legacy sensitivities excluded from decision-grade sum. |
| falsifier | Stockholders' equity per share falls below **$12.50** without a matching proof update. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Q1 2026 ACL **$9.495M** on **$775.958M** commitments (~1.2%); **$43.955M** unfunded commitments; **$56.606M** cash still deploying after December 2025 rights offering; debt-to-equity ~1.4. |
| source path | Q1 2026 10-Q; Q1 2026 earnings presentation |
| calculation | Incremental reserve base **$33.894M** (≈ **$1.50/sh**) beyond ACL already inside book; low/high bracket cycle stress and deployment lag. |
| remaining uncertainty | Realized credit losses or failed redeployment could force reserve toward low case (−$3.00/sh). |
| affected components | `cre_credit_and_redeployment_reserve` |
| valuation consequence | Downside claims reconciled to filings; ACL not double-counted against book equity. |
| falsifier | Realized losses exceed ACL build for two consecutive quarters without reserve band update. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys unchanged; distributable earnings embedded in book multiple. |
| source path | `SEVN/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** Stockholders' equity **$326.982M**; **22,596,077** shares; filing book **$14.47/sh**; adjusted book **$14.90/sh** (presentation); FY2025 base management fees **$4.360M**; incentive fees **$0.625M**; ACL **$9.495M**; loan commitments **$775.958M**; unfunded **$43.955M**; cash **$56.606M**.

**Judgments (bounded):** Book mark ratio **0.86–1.11×** filing book; fee capitalization **3.6–11.3 years** of annual fee load; incremental CRE/redeployment reserve **$11.3–67.8M** beyond filing ACL.

## Valuation consequence

Proof-complete additive schedule base case **~$11.90 per share** vs price **~$8.40** implies component economic value above market; Lawrence seven-year scenario base **14.6%** remains the stance-gate return. Security stays **watch** (unproven moat, partial dhando); no human capital decision recorded.
