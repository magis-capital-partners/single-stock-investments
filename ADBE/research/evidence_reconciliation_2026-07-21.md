# ADBE valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `digital_media_document_engine` | unpriced | owner_earnings_reinvestment_dcf@1.0 | bounded_estimate | $493.00 |
| `digital_experience_engine` | unpriced | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $133.00 |
| `firefly_ai_monetization_option` | unpriced | risk_adjusted_milestone_value@1.0 | bounded_estimate | $50.00 |
| `net_financial_claims` | unpriced | net_asset_value@1.0 | bounded_estimate | −$2.00 |
| `ai_competition_and_sbc_reserve` | unpriced | net_asset_value@1.0 | bounded_estimate | −$18.00 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Five additive components with unique overlap keys: Digital Media engine, Digital Experience engine, Firefly AI option, net financial claims, AI competition reserve. Publishing segment cash embedded in revenue-weighted allocation. |
| source path | `ADBE/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **$656.00/sh** = $493 + $133 + $50 − $2 − $18. |
| remaining uncertainty | Firefly milestone band ($0–$120/sh) and AI reserve remain widest judgment bands. |
| affected components | All five additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 operating cash flow **$10,031M**; capital spending **$179M**; free cash flow **$9,852M**; diluted **427M** shares; free cash flow per share **$23.07**. |
| source path | `ADBE/investor-documents/sec-edgar/10-K_20260115_rpt20251128_acc0000796343_26_000003.htm` |
| calculation | Digital Media receives **$17.14/sh** (74% revenue weight) × 28.8× capitalization ≈ **$493/sh**; Digital Experience **$5.69/sh** × 23.4× ≈ **$133/sh**. |
| remaining uncertainty | Revenue-weighted FCF split is approximation; segment-level cash not disclosed separately in filings. |
| affected components | `digital_media_document_engine`, `digital_experience_engine` |
| valuation consequence | Filing-locked consolidated FCF anchors segment proofs; price stub replaced by component schedule. |
| falsifier | Trailing four-quarter free cash flow per share falls below **$18.00** for four quarters without offsetting RPO growth. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 cash **$5,431M**; long-term debt **$6,210M**; stock-based compensation **$1,942M**; share repurchases **$11,280M**. |
| source path | `10-K_20260115_rpt20251128` balance sheet and cash-flow extracts |
| calculation | Net cash less debt filing-locked at **−$779M** (~**−$1.82/sh**); net financial judgment base **−$2.00/sh**; AI competition reserve base **−$18.00/sh** separate from segment multiples. |
| remaining uncertainty | January 2025 **$2.0B** note offering and buyback pace affect net claim band; generative-AI seat churn severity is judgment. |
| affected components | `net_financial_claims`, `ai_competition_and_sbc_reserve` |
| valuation consequence | Downside claims reconciled to filings; reserve separate from operating engines. |
| falsifier | Long-term debt rises above **$8B** while buybacks fall below **$5B** annually for two consecutive fiscal years. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys; RPO and subscription growth embedded in segment engines; Firefly milestone is non-overlapping incremental band. |
| source path | `ADBE/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$23,769M**; Digital Media **$17,650M**; Digital Experience **$5,860M**; operating cash flow **$10,031M**; capital spending **$179M**; free cash flow **$9,852M**; RPO **$22,520M**; cash **$5,431M**; long-term debt **$6,210M**; stock-based compensation **$1,942M**; share repurchases **$11,280M**; diluted shares **427M**.

**Judgments (bounded):** Digital Media capitalization 18.7–39.7× on revenue-weighted owner cash; Experience capitalization 15–34×; Firefly milestone **$0–$120/sh**; net financial claim **−$10 to +$6/sh**; AI competition reserve **−$45 to −$5/sh**.

## Valuation consequence

Proof-complete additive schedule base case **$656.00 per share** vs price **~$222.65** implies substantial headroom if segment assumptions hold. Lawrence seven-year base and synthesis IRR are computed mechanically in Phase 3. Security stance remains **watch** pending human capital authority; no human decision recorded.
