# 7176.T valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blocker by supplying a complete economic ownership map with valid `calculation_proof` graphs on every additive component.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `core_fee_engine` | unmapped | owner_cash_or_dividend_discount@1.0 | bounded_estimate | ¥2,065 |
| `performance_fee_option` | unmapped | risk_adjusted_milestone_value@1.0 | bounded_estimate | ¥420 |
| `net_financial_claims` | unmapped | net_asset_value@1.0 | bounded_estimate | ¥125 |
| `fee_cycle_and_liquidity_reserve` | unmapped | net_asset_value@1.0 | bounded_estimate | −¥274 |

## Economic ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four non-overlapping additive components cover base-fee owner cash, cyclical success-fee option, surplus cash, and cycle/liquidity reserve. |
| source path | `7176.T/02_Quarterly/Earnings_Releases/20260528_2026年3_月期_決算短信_日本基準_連結__finfo2026.pdf`; `7176.T/02_Quarterly/Earnings_Variance_Notices/20260528_前年同期実績_連結_との差異に関するお知らせ__Pnotice2026-1.pdf` |
| calculation | Base component sum **¥2,335.58/sh** reconciles to Lawrence seven-year present value on FY2025 mid-cycle owner cash **¥137.14/sh**; bear sum **¥1,604.84/sh**; bull **¥3,588.36/sh**. |
| remaining uncertainty | Yuho (EDINET E31267) segment detail pending; live TSE quote not confirmed. |
| affected components | all four additive components |
| valuation consequence | Universal contract can price the security; Lawrence synthesis **53.33%** remains stance context only. |
| falsifier | Two consecutive years of success-fee mix at FY2026 levels without base-fee growth, or material segment restatement in yuho. |

## Overlap control — met

Unique overlap keys preserved; `double_counting_flags` empty. Base-fee DCF slice excludes success-fee increment and full cash balance; surplus cash uses explicit ratio on filing cash only.

## Facts vs judgments

**Facts (locked):** FY2025 parent EPS **¥137.14/sh**; FY2026 **¥317.33/sh**; base fees **¥7,869M** (+17.1% YoY); success fees **¥14,316M** (+53.6%); AUM **¥1,335.7B** (+2.9%); cash **¥23,610M**; equity **¥20,530M**; shares issued **27.12M** split-adjusted; price last print **¥464** (100 shares, Jan 2026).

**Judgments (bounded):** Base-fee attribution ratio on Lawrence DCF; success-fee conversion multiple on incremental EPS; surplus cash ratio **0–14%** of gross cash per share; cycle reserve **0.55–2.55×** mid-cycle owner cash.

## Valuation consequence

Proof-complete additive schedule base **~¥2,336/sh** vs last print **¥464** implies large mechanical upside on filing math; **watch** stance unchanged pending live quote and peak success-fee normalization. No human capital decision recorded.
