# GOOGL valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `primary_operating_segment` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $200.66 |
| `secondary_operating_segments` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $100.35 |
| `strategic_option` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $16.15 |
| `net_claims_and_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $30.88 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four non-overlapping overlap keys map one diluted share claim: Services owner cash, Cloud owner cash, Other Bets option, net cash plus AI-capital reserve. |
| source path | `GOOGL/research/valuation.json` → `component_valuation.components[]` |
| calculation | Each component `overlap_key` unique; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | Alphabet-level R&D drag ($16.8B FY2025) is embedded in segment growth judgments, not a fifth additive line. |
| affected components | All four |
| valuation consequence | Ownership map complete for universal contract. |
| falsifier | New filing shows material claim (e.g., separate chip revenue) without unique overlap_key. |

### Primary cash / owner-cash bridge — partially met

| Field | Content |
|---|---|
| status | partially_met |
| evidence | FY2025 10-K: OCF $125.3B, capex $52.5B, FCF ~$72.8B; segment OI Services $139.4B, Cloud $13.9B; Q1 2026 Cloud +63% revenue (`10-Q_20260430`, `8-K_20260429`). |
| source path | `GOOGL/investor-documents/sec-edgar/10-K_20260205_rpt20251231_acc0001652044_26_000018.htm` |
| calculation | Services proof: $139,400M OI × 0.79 after-tax × 22.68× / 12,447M shares = **$200.66/sh**. Cloud proof: $13,900M × 0.79 × 113.75× / 12,447M = **$100.35/sh**. |
| remaining uncertainty | Segment proofs use OI × multiple proxies, not full segment DCF trees; Lawrence consolidated path still uses FY2025 FCF/sh $5.85. |
| affected components | `primary_operating_segment`, `secondary_operating_segments` |
| valuation consequence | Filing-locked segment OI drives bounded proofs; full owner-cash bridge to consolidated FCF remains [HUMAN REVIEW]. |
| falsifier | FY2026 segment OI mix shifts >10pp without matching Cloud revenue growth in filings. |

### Downside and capital claims — partially met

| Field | Content |
|---|---|
| status | partially_met |
| evidence | Cash + STI $95.657B; long-term debt $10.883B; 2026 capex guide $180–190B cited in Q1 materials. |
| source path | `GOOGL/investor-documents/sec-edgar/10-K_20260205_rpt20251231_acc0001652044_26_000018.htm` |
| calculation | Net cash proof: ($95,657M − $10,883M + $299,588M capex normalization) / 12,447M = **$30.88/sh** base; low case reserve **−$805,452M** → **−$57.90/sh**. |
| remaining uncertainty | Capex normalization adjustment is explicit judgment pending post-peak FCF visibility. |
| affected components | `net_claims_and_reserve` |
| valuation consequence | Reported net cash locked; AI capex overhang sized as reserve/release band. |
| falsifier | 2026–2027 FCF per share flat or down vs FY2025 with no capex guide reduction. |

### Strategic option — partially met

| Field | Content |
|---|---|
| status | partially_met |
| evidence | FY2025 Other Bets operating loss $7.5B; Waymo and Other Bets disclosed in segment note. |
| source path | `GOOGL/investor-documents/sec-edgar/10-K_20260205_rpt20251231_acc0001652044_26_000018.htm` |
| calculation | Base: ($3,000,000M × 0.082 − $7,500M × 6 yr) / 12,447M = **$16.15/sh**. |
| remaining uncertainty | Success value and probability are bounded judgments; no filing-locked Waymo valuation. |
| affected components | `strategic_option` |
| valuation consequence | Milestone method approved; segment build still uses $0 Other Bets terminal in Lawrence base. |
| falsifier | Other Bets losses accelerate >20% YoY for two years with no monetization path disclosed. |

### Component proof completeness — met

| Field | Content |
|---|---|
| status | met |
| evidence | All four additive components carry valid `calculation_proof` with approved `method_id@1.0`; `calculation_proof.py` validates every graph. |
| source path | `GOOGL/research/valuation.json` → `component_valuation.components[]` |
| calculation | Proof sum (base): $200.66 + $100.35 + $16.15 + $30.88 = **$348.04/sh** vs price **~$386**. |
| remaining uncertainty | Judgment bands on Cloud multiple and capex normalization remain wide. |
| affected components | All four additive blockers |
| valuation consequence | Universal contract may advance toward `decision_grade` after mechanical refresh. |
| falsifier | Any component proof fails validation or overlap key duplicates. |

## Facts vs judgments

**Facts (locked):** FY2025 revenue $402.8B; Services OI $139.4B; Cloud OI $13.9B; Other Bets loss $7.5B; OCF $125.3B; capex $52.5B; cash + STI $95.657B; LT debt $10.883B; diluted shares ~12.45B; Q1 2026 Cloud revenue +63% YoY.

**Judgments (bounded):** Services/Cloud owner-cash multiples; Other Bets success probability and gross value; AI capex normalization reserve/release; consolidated Lawrence growth 11%/8%.

## Valuation consequence

Proof-complete additive schedule base case **~$348 per share** vs market price **~$386** implies roughly **−10%** gap on component economic value at a seven-year horizon. Lawrence consolidated base **−0.97%** per year remains the legacy stance gate reference. Security remains **watch** pending human capital decision; no stance promotion in this agent run.
