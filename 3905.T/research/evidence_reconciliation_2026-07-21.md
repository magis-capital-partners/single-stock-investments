# 3905.T valuation evidence reconciliation — 2026-07-21

**Scope:** Close contract backfill blockers by attaching valid calculation proofs on every additive component. See `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `core_ai_datacenter_engine` | unpriced | owner_cash_or_dividend_discount@1.0 | bounded_estimate | ¥3,282 |
| `inzai_gpu_platform_option` | unpriced | risk_adjusted_milestone_value@1.0 | bounded_estimate | ¥400 |
| `net_financial_claims` | unpriced | net_asset_value@1.0 | bounded_estimate | −¥600 |
| `execution_and_financing_reserve` | unpriced | net_asset_value@1.0 | bounded_estimate | −¥129 |

## Acceptance test: component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four additive components with unique overlap keys: core AI DC engine, Inzai/B300 platform option, net financial claims, execution reserve. Legacy IT services embedded in normalized owner-cash bridge. |
| source path | `3905.T/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once; sum base **¥2,953/sh** = ¥3,282 + ¥400 − ¥600 − ¥129. |
| remaining uncertainty | PDF text extract failed for all 505 indexed files; metrics from English IR inventory tier pending OCR rerun. |
| affected components | All four additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

## Acceptance test: primary owner-cash bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2026 guided parent EPS **¥115.57** on parent net profit **¥2,804M**; normalized owner cash **¥90/sh** after ramp discount; implied shares **~24.26M**. |
| source path | `3905.T/IR/en_financial_report/en-ir-20260421001.pdf` (inventory tier) |
| calculation | Guided EPS bridge: ¥115.57 × ~78% execution haircut ≈ **¥90/sh** starting owner cash; core proof capitalizes seven-year path with Lawrence scenario growth and exit multiples. |
| remaining uncertainty | Inventory-tier citation until OCR/extract succeeds; diluted share count may shift with 23rd stock-acquisition rights. |
| affected components | `core_ai_datacenter_engine` |
| valuation consequence | Filing-guided bridge anchors core proof; legacy scenario IRR remains separate stance gate. |
| falsifier | FY2026 actual EPS falls below **¥60/sh** for two consecutive quarters without offsetting utilization proof. |

## Acceptance test: downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | May 2026 IR (inventory): customer advance **¥13.6B**, planned borrowings **¥30.6B**, 23rd rights **¥6.7B**; Giga B200 **577 units / USD 252M** unpaid overhang. |
| source path | `3905.T/IR/en_financial_report/en-ir-20260507001.pdf` |
| calculation | Net financial base **−¥600/sh** stresses debt draw before GPU deliveries; execution reserve base **−¥129/sh** for Giga and ramp risk separate from core capitalization. |
| remaining uncertainty | Exact balance-sheet marks and Giga resolution terms not extracted from PDFs. |
| affected components | `net_financial_claims`, `execution_and_financing_reserve`, `inzai_gpu_platform_option` |
| valuation consequence | Downside capital claims reconciled to disclosed financing bridge; Giga not double-counted in core engine. |
| falsifier | Planned borrowings exceed **¥40B** without proportional customer advance or energization milestone within one quarter. |

## Facts vs judgments

**Facts (inventory tier, prior IR review):** FY2026 revenue guide **¥33,601M**; operating profit guide **¥3,635M**; parent net profit **¥2,804M**; guided EPS **¥115.57**; **5,080** B300 GPUs via Compal (~USD **325M**); Inzai phased ops May–Jul 2026; customer advance **¥13.6B**; planned borrowings **¥30.6B**.

**Judgments (bounded):** Normalized owner cash **¥90/sh**; core capitalization scale factors; Inzai option **¥0–900/sh**; net financial **−¥1,200 to +¥200/sh**; execution reserve **−¥400 to ¥0/sh**.

## Valuation consequence

Proof-complete additive schedule base case **~¥2,953 per share** vs price **~¥4,490** implies component economic value below market; Lawrence seven-year base **3.6%** and total synthesis **4.56%** remain below mid-teens accumulate hurdle. Security remains **watch**; no human capital decision recorded.
