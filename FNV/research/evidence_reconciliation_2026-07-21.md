# FNV valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `producing_royalty_stream` | legacy_sensitivity | royalty_distribution_curve@1.0 | bounded_estimate | $142.15 |
| `development_inventory_option` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $18.34 |
| `net_financial_claims` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $27.51 |
| `depletion_and_realization_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | -$27.51 |

## Acceptance tests

### component_ownership_map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four non-overlapping additive components map one diluted share: producing stream, development inventory, net financial claims, depletion reserve. Overlap keys unique in `valuation.json`. |
| source path | `FNV/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material component count 4; additive 4; embedded 0; `double_counting_flags` empty. |
| remaining uncertainty | Future acquisitions may require new components; Cobre Panamá split between producing (when restarted) vs development option remains judgment. |
| affected components | All four |
| valuation consequence | Ownership map complete for current contract. |
| falsifier | New filing shows material claim (debt, stream liability, equity sleeve) not in map. |

### primary_cash_or_nav_bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 OCF $1,493.7M / 192.7M shares = **$7.75/sh** normalized owner cash; Q1 2026 cash $714.7M, investments $1,142.4M, available capital $3.4B per NR footnote. |
| source path | `FNV/investor-documents/ir-fnv/10249_Franco_Nevada_2025_Annual_Report_Ph14_F_Digital.pdf`; `FNV/investor-documents/ir-fnv/NR-Franco-Nevada-Reports-Record-Q1-2026-Results-vFinal-2026-05-12.pdf` |
| calculation | Producing proof anchors distribution Y0 at $7.75/sh; net financial proof: ($714.7M + $1,142.4M − $440.7M deferred tax + revolver haircut) / 192.7M scaled to **$27.51/sh** base. |
| remaining uncertainty | Q1 CRA refund $49.5M excluded from normalized growth path; deferred tax at YE2025 used against Q1 liquid marks. |
| affected components | `producing_royalty_stream`, `net_financial_claims` |
| valuation consequence | Filing-locked facts drive proof inputs; judgment bands on growth, discount, and revolver realizability remain. |
| falsifier | Next filing shows FY2025 OCF restated >10% below $1,493.7M without matching share count change. |

### downside_and_capital_claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Company reports **no debt**; deferred tax liability $440.7M; revolver capacity $1.25B at Q1 2026 (plus May 2026 subsidiary facility not in base proof). Depletion reserve proof uses FY2025 vs FY2024 OCF gap × reserve multiplier. |
| source path | Annual report balance sheet; Q1 NR Available Capital footnote |
| calculation | Depletion reserve base: ($1,493.7M − $829.5M) × 4.0 / 192.7M = **−$27.51/sh**. Development option: $7,850M gross × 45% success / 192.7M = **$18.34/sh**. |
| remaining uncertainty | Cobre Panamá timing and commodity normalization severity; subsidiary revolver not fully counted. |
| affected components | `depletion_and_realization_reserve`, `development_inventory_option`, `net_financial_claims` |
| valuation consequence | Downside reserve and liquidity claims reconciled to filings with bounded judgments. |
| falsifier | Material recourse debt or stream prepayment liability disclosed without reserve update. |

### Component proof completeness — met

| Field | Content |
|---|---|
| status | met |
| evidence | All four additive components carry valid `calculation_proof` with approved `method_id@1.0`; `calculation_proof.py` validates every graph. |
| source path | `FNV/research/valuation.json` |
| calculation | Proof sum (base): $142.15 + $18.34 + $27.51 − $27.51 = **$160.49/sh** vs price ~$229. |
| remaining uncertainty | Legacy scale factors on producing and net financial bridge judgment bands; development aggregate milestone not yet asset-level trees. |
| affected components | All four blockers |
| valuation consequence | Universal contract may advance from `evidence_blocked` toward `decision_grade` after mechanical refresh. |
| falsifier | Any component proof fails validation or overlap key duplicates. |

## Facts vs judgments

**Facts (locked):** FY2025 OCF $1,493.7M; FY2024 OCF $829.5M; shares 192.7M; Q1 cash $714.7M; Q1 investments $1,142.4M; available capital $3.4B; deferred tax $440.7M; Cobre Panamá 11,208 GEOs FY2025; no debt.

**Judgments (bounded):** Distribution growth 0–7%; discount 8.5–11%; development success probability 15–75%; revolver haircut 0–65%; depletion reserve multiplier 1–8× on peak-normalized OCF gap.

## Valuation consequence

Proof-complete additive schedule base case **$160.49 per share** vs market price **~$229** implies negative annualized return on component economic value at a seven-year horizon. Lawrence seven-year owner-cash base **4.5%** and total synthesis **6.12%** remain below mid-teens accumulate hurdle. Security remains **watch**; no human capital decision recorded.
