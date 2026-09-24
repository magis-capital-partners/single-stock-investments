# AMZN epistemic review receipt — 2026-09-24

**Work ID:** `b6366760af62fc74e361554d`  
**Task:** `review_forecast` for `core_engine`  
**Draft:** `AMZN/research/falsifier_drafts/bfb8c41c4edab4687e691df6.json`  
**Evidence hash:** `6a23452822378e3509a31623894c31630da7605912cbe63bb45fc806f5e8090a` <!-- pragma: allowlist secret -->  
**Input SHA:** `bcd068dd9613ef819a2c0433b3fcca83c18c427a`

## Epistemic loop status

**COLLECTING** — 0 eligible scored outcomes; calibration **insufficient_outcomes** with `release_hash: null`. Diagnostic and legacy outcomes do not change stance, valuation, or sizing.

## Calibration receipt

| Field | Value |
|-------|-------|
| calibration_release_hash | null |
| route | quality_reinvestment\|owner_cash_or_dividend_discount |
| named_challenge | null |
| calibration_response | not_applicable |

## Review challenges

| Challenge | Result | Notes |
|-----------|--------|-------|
| Reviewer differs from author | passed | Author `codex-gpt-5.6-sol` / `gpt-5.6-sol` (2026-09-02); reviewer `cursor-cloud-agent` (independent run, 2026-09-24) |
| Materiality | passed | `core_engine` base **$165.03/sh** vs low **$83.16/sh**; a fire moves ~50% of component value and ~44% of total equity in the registered impact table |
| Period semantics | passed_with_note | Resolves **Q3 FY2026 TTM** reported owner earnings (OCF minus `PaymentsToAcquireProductiveAssets` capex) via `sec_companyfacts_ttm` / `normalized_owner_earnings_ttm_m_v2`; contract normalized **$5.35/sh** uses a sustainable-capex judgment bridge, so this test is intentionally on **reported** cash, not the normalized input |
| Look-ahead | passed | Information cutoff 2026-09-02; Q3 FY2026 not filed; Q1 FY2026 TTM **-$2.472B** (filed 2026-04-30) used only as cutoff-visible context |
| Source replay | passed | Q3 FY2025 TTM replay **$10.560B** and Q1 FY2026 TTM **-$2.472B** independently verified via `_system/scripts/falsifier_evidence_adapters.resolve_spec` |
| Nested thresholds | passed | Same correlation group as runway (0) and cycle_reserve (-10B); fire probabilities **0.55 > 0.35 > 0.20** preserve monotonic severity |
| Probability | passed_with_note | 20% for **-$25B** is a conservative tail given Q1 2026 already below zero; threshold is a distinct stress state versus the zero and -$10B bands |

## Disposition

**Approved** — spec `amzn-core-engine-owner-earnings-2026q3-v1` (v3, revision 1). Fires if Q3 FY2026 TTM normalized owner earnings resolve below **-$25,000 USD millions**. Scheduled promoter may append after review gate.

## Facts

- Q3 FY2025 TTM owner earnings: **$10.560B** — adapter replay on `AMZN/research/evidence/sec_companyfacts.json` (10-Q accession `0001018724-25-000123`, filed 2025-10-31)
- Q1 FY2026 TTM owner earnings: **-$2.472B** — same adapter at 2026-03-31 (10-Q accession `0001018724-26-000014`, filed 2026-04-30)
- Contract `core_engine` range: low **$83.16/sh**, base **$165.03/sh**, high **$268.61/sh** — `AMZN/research/valuation_contract.json`
- Normalized owner cash input in proof: **$5.35/sh** — judgment bridge cited in contract trace (distinct from reported TTM)

## Inferences

- Breaching **-$25B** TTM would force a fresh normalization of owner cash for the predictable-cash discount leg without automatically changing growth or exit-multiple judgments
- Shared correlation group means one Q3 filing outcome updates runway, cycle_reserve, and core_engine tests together for calibration counting

## Routed memory verification

- Q1 2026 TTM OCF **$148.5B** vs capex **$151.0B** yielding negative reported owner earnings: **confirmed** against adapter formula inputs at 2026-03-31; context only, not promoted
- Legacy **$45B** runway threshold observation (`0679c1f233147debec1dbf64.json`): **superseded** by v2/v3 drafts using zero threshold and corrected capex concept; not cited as evidence

## [HUMAN REVIEW]

- Stance and sizing remain in `human_decision.json` only
- Scheduled promoter appends approved draft to `falsifier_specs.json`; agents do not edit authoritative list in place
- Universal contract remains **evidence_blocked** until remaining prospective falsifier reviews complete
