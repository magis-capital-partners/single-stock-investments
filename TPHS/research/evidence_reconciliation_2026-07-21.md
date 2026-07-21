# TPHS valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `cash_and_working_capital` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $0.00 |
| `ip_licensing_stub` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $0.01 |
| `nol_shell_option` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $0.04 |
| `steel_note_and_deficit_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | −$0.01 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four additive components with unique overlap keys; TPHGreenwich Trust property excluded from common. |
| source path | `TPHS/research/valuation.json` → `component_valuation.components[]` |
| calculation | Sum base **$0.04/sh** = $0.00 + $0.01 + $0.04 − $0.01; aligns with $0.045 five-year dated payoff (~14.4%/yr). |
| remaining uncertainty | Steel Partners has disclosed no shell transaction plan; option can go to zero. |
| affected components | All four additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | Q1 2026 IR press release: cash **$54 thousand**; other income FY2025 **$239 thousand**; federal NOL **$329.9 million** (face, fully reserved); Steel note **$1.372 million**; stockholders' deficit **$1.534 million**; shares **64,947,266**. |
| source path | `TPHS/investor-documents/ir-tphs/3-31-26-TPHS-Financials-Press-Release-v5.14.26.pdf` |
| calculation | Each proof divides filing-locked or bounded dollar claims by **64.947266M** shares; face NOL enters only as context for the risked shell-utility judgment, not as additive NAV. |
| remaining uncertainty | Audited FY2025 10-K and 2026 10-Qs not yet on EDGAR in this folder; IR press releases used. |
| affected components | All additive blockers |
| valuation consequence | Filing-locked facts anchor proofs; legacy sensitivities excluded from decision-grade sum. |
| falsifier | Next balance sheet shows note balance above **$2.0M** with no offsetting shell event. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Steel Promissory Note **$1.372M** secured by all company assets; stockholders' deficit **$1.534M** (~**$0.024/sh**). |
| source path | Q1 2026 press release balance sheet |
| calculation | Senior claim reserve modeled as additive negative component; base **−$0.01/sh** is a partial haircut, not full note foreclosure. |
| remaining uncertainty | Note conversion, going-private, or Form 15 could extinguish common ahead of any shell payoff. |
| affected components | `steel_note_and_deficit_reserve` |
| valuation consequence | Downside claims reconciled to filings; no double-count with Trust assets (explicit zero). |
| falsifier | Foreclosure or note conversion leaves minority common with near-zero residual before any NOL event. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys unchanged; Greenwich Trust and face NOL excluded from additive stack. |
| source path | `TPHS/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** Cash **$54 thousand**; shares **64,947,266**; FY2025 other income **$239 thousand**; federal NOL **$329.9 million** face; Steel note **$1.372 million**; stockholders' deficit **$1.534 million**; Steel Partners **~39.8%** via Feb 2025 SPA.

**Judgments (bounded):** Immaterial cash realization **$0/sh** base; IP cap multiple **~2.7×** on FY2025 licensing; risked shell utility **~$2.6M** base (not face NOL); senior claim reserve **~$0.649M** base.

## Valuation consequence

Proof-complete additive schedule base case **$0.04 per share** vs price **~$0.023** implies modest upside to the risked component stack; Lawrence dated-payoff base **14.4%** annualized over five years remains the stance gate. Security stays **watch** (dhando none, no floor under secured note). No human capital decision recorded.
