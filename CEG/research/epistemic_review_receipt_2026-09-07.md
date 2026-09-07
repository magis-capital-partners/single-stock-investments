# CEG epistemic review receipt — 2026-09-07

**Work ID:** `27717603be708e095936d09b`  
**Task:** `review_forecast` for `operating_business_and_net_assets`  
**Draft:** `CEG/research/falsifier_drafts/f8685f88d1aff5b6b56d0eba.json`  
**Evidence hash:** `249f509e39c8a416c65e3200681e8cd5f62cae9d8125826e7f26207e1d1bc42d` <!-- pragma: allowlist secret -->  
**Input SHA:** `1547c5631614209e1f5e171e99d162dd18869542`

## Epistemic loop status

**COLLECTING** — 0 eligible scored outcomes; calibration **insufficient_outcomes** with `release_hash: null`. Diagnostic and legacy outcomes do not change stance, valuation, or sizing.

## Calibration receipt

| Field | Value |
|-------|-------|
| calibration_release_hash | null |
| route | quality_reinvestment\|owner_earnings_reinvestment_dcf |
| named_challenge | null |
| calibration_response | not_applicable |

## Review challenges

| Challenge | Result | Notes |
|-----------|--------|-------|
| Reviewer differs from author | passed | Author `marvin-cloud-agent` / `composer-2.5` (2026-09-02); reviewer `cursor-cloud-agent` (independent run, 2026-09-07) |
| Materiality | passed | Component is `entire_security`; low-case anchor drives -$3.23/sh vs $28.53/sh base (85% equity impact if fires) |
| Period semantics | passed_with_note | Resolves Q3 FY2026 TTM via `sec_companyfacts_ttm` and `normalized_owner_earnings_ttm_m_v2`; threshold is FY2025 annual low-case anchor (1,288M), not prior TTM — intentional bridge test for heavy-capex compounders |
| Look-ahead | passed | Information cutoff 2026-09-02; Q3 FY2026 not yet filed; Q2 FY2026 TTM (309M, filed 2026-08-06) used only as cutoff-visible context |
| Source replay | passed | Q3 FY2025 TTM replay -276.0M independently verified via `_resolve_owner_earnings_ttm`; matches author historical replay |
| Probability | passed_with_note | 0.35 fire probability is conservative: Q1 FY2026 TTM 1,137M and Q2 FY2026 TTM 309M are both below the 1,288M threshold at cutoff, so realized fire risk may exceed 35% unless Q3 alone lifts TTM materially |

## Disposition

**Approved** — spec `ceg-operating-owner-earnings-2026q3-v2` (v3, revision 1). Fires if Q3 FY2026 TTM normalized owner earnings resolve below 1,288 USD millions (FY2025 low-case proof anchor). Scheduled promoter may append after review gate.

## Facts

- FY2025 normalized owner earnings: **$1,288M** (OCF $4,237M minus capex $2,949M) — `CEG/research/valuation_fact_ledger.json`; `CEG/investor-documents/sec-edgar/10-K_20260224_rpt20251231_acc0001868275_26_000032.htm`
- Q3 FY2025 TTM normalized owner earnings: **-$276M** (adapter replay; heavy capex during integration/restart cycles)
- Q1 FY2026 TTM: **$1,137M**; Q2 FY2026 TTM: **$309M** — demonstrates Calpine-close and Crane-restart capex keep TTM structurally volatile versus the annual anchor

## Inferences

- A Q3 FY2026 TTM below 1,288M would compress the bounded per-share range toward the low case (-$3.23/sh) without requiring a change to reinvestment-rate or incremental-ROIC judgment inputs (those legs remain untyped)

## Routed memory verification

- Routed observation on dual-method extreme return and watch stance: **confirmed** against `CEG/research/valuation_contract.json` legacy audit (-27.85% base annualized return at price) and FY2025 owner cash $3.57/sh; context only, not promoted

## [HUMAN REVIEW]

- Stance and sizing remain in `human_decision.json` only
- Scheduled promoter appends approved draft to `falsifier_specs.json`; agents do not edit authoritative list in place
