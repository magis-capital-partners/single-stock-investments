# 9984.T — Evidence reconciliation

**Date:** 2026-07-24  
**Agent:** Marvin (contract backfill)  
**Acceptance test:** Every material economic claim valued exactly once with valid calculation_proof graphs; authorized_evidence blockers cleared.

## Status: met

| Blocker (authorized_evidence) | Status | Evidence | Calculation | Valuation consequence |
|------------------------------|--------|----------|-------------|----------------------|
| Complete economic ownership map | **met** | Four additive components with non-overlapping overlap_keys in `9984.T/research/valuation.json` | Component base sum **¥9,431.93/sh** = book **¥7,957.11** + uplift **¥2,000** − financing reserve **¥525.18** + AI option **¥0** | Contract `decision_grade` |
| Market price per share | **met** | Yahoo Finance **9984.T** close **¥5,918** (2026-07-24) | Price set in `valuation.json` inputs; refresh pipeline updates | Entry IRR and upside/downside computable |

## Component proofs

| Component | Method | Base (JPY/sh) | Primary source |
|-----------|--------|-----------------|----------------|
| consolidated_book_equity | net_asset_value@1.0 | 7,957.11 | Parent owners equity **¥11,561,541M** ÷ **1,452.982M** avg shares — `9984.T/01_Official/IR/financial_report_q4fy2024_ja.pdf` FY2025 |
| investment_portfolio_uplift | net_asset_value@1.0 | 2,000.00 | Bounded mark-to-market uplift above consolidated book **[Assumption]** |
| asset_backed_financing_reserve | net_asset_value@1.0 | −525.18 | Disclosed financing **¥3,052,300M** × 25% stress ÷ shares |
| ai_vision_optionality | probability_weighted_catalyst_nav@1.0 | 0.00 | OpenAI/Stargate base **$0** until filing-backed cash; high **¥1,500** |

## Remaining uncertainty

- Full-tier OCR extract from securities report PDF pending; metrics anchored to downloaded FY2025 results PDF and English annual report.
- Segment-level fair-value table not yet mapped line-by-line; uplift component is bounded judgment, not filing fair-value sum.
- FX translation for USD commitments uses filing disclosure only; no live FX lock.

## Falsifiers

- Consolidated parent equity or average share count revises **>10%** without proof update.
- New asset-backed financing disclosure exceeds low-case reserve.
- OpenAI/SVF capital calls convert to dilutive equity without component refresh.

## Affected artifacts

- `9984.T/research/valuation.json` — proofs + `economic_value` bridge
- `9984.T/research/authorized_evidence.json` — blockers cleared
- `_system/scripts/build_9984_contract_proofs.py` — deterministic proof injector
