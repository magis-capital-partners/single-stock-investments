# AXTI valuation evidence reconciliation — 2026-07-24

**Scope:** Evidence gap closure (`evidence_gap_ready`) plus confirm contract backfill blockers remain closed. Evidence packet per `research_agent_manifest.json`. // pragma: allowlist secret

## What changed since 2026-07-21

| Artifact | Prior | Current |
|----------|-------|---------|
| `DOWNLOAD_MANIFEST.json` | 56 SEC docs indexed | Stable; all `ok: true` |
| Full-tier text extracts | `no_full_tier_text_extract` | Available: FY2025 10-K, Q1 2026 10-Q, 2026 DEF 14A in `research/evidence/_text/` |
| `filing_digest_2026-07-24.md` | — | 55 documents inventoried; full-tier keyword extracts populated |
| Universal contract | `decision_grade` (2026-07-21 backfill) | Unchanged; proofs validated |

## Blockers status (authorized_evidence)

All five prior additive blockers remain closed with valid `calculation_proof` graphs:

| Component | Method | Proof status | Base per share |
|-----------|--------|--------------|----------------|
| `midcycle_substrate_operations` | midcycle_capacity_value@1.0 | bounded_estimate | $1.40 |
| `cash_and_liquidity` | net_asset_value@1.0 | calculated | $0.89 |
| `tongmei_hk_listing_option` | risk_adjusted_milestone_value@1.0 | bounded_estimate | $0.50 |
| `pe_redemption_liability` | net_asset_value@1.0 | bounded_estimate | -$0.75 |
| `dilution_reserve` | net_asset_value@1.0 | bounded_estimate | -$0.30 |

Embedded `raw_materials_gallium` remains zero and embedded in substrate operations (no double count).

## Acceptance tests

### Component proof completeness — met

| Field | Content |
|---|---|
| status | met |
| evidence | All additive components in `valuation.json` carry `calculation_proof` with approved method_id@1.0; `valuation_contract.json` reports `calculation_graphs_valid: true`. |
| source path | `AXTI/research/valuation_contract.json` |
| calculation | Proof sum (base): $1.40 + $0.89 + $0.50 - $0.75 - $0.30 = **$1.74/sh** vs price **$45.86**. |
| remaining uncertainty | Tongmei success value and PE redemption timing remain judgment-heavy; substrate mid-cycle anchor is normalized, not spot GAAP. |
| falsifier | Two consecutive quarters of owner cash below low-case normalized path; full PE redemption funded from parent cash without HK listing offset. |

### Full-tier evidence — met

| Field | Content |
|---|---|
| status | met |
| evidence | `filing_facts_2026-07-24.json` sources `evidence/_text/10-K_20260317_*.txt`; filing digest lists full-tier extracts for 10-K, 10-Q, proxy. |
| source path | `AXTI/research/evidence/filing_digest_2026-07-24.md` |
| calculation | n/a |
| remaining uncertainty | Segment-level capacity/utilization still requires manual read of Item 1 and MD&A for precision. |
| falsifier | Evidence build reverts to `no_full_tier_text_extract`. |

### Overlap control — met

Unique overlap keys unchanged; `double_counting_flags` empty; gallium embedded in `midcycle_substrate_operations`.

## Facts vs judgments

**Facts (locked):** Cash $57.9M (Q1 2026); shares 65.423M; PE redemption ~$49M; FY2025 revenue $88.3M; Q1 2026 revenue $26.9M (+39% YoY).

**Judgments (bounded):** Mid-cycle owner cash $4.5M–$12.0M; Tongmei HK success probability 0–55%; PE redemption pct 0–133%; future dilution haircut 0–1.1% of price.

## Valuation consequence

Proof-complete additive schedule base **$1.74 per share** vs **$45.86** price. Lawrence synthesis **-9.92%** per year on normalized owner cash remains stance reference. Security **watch**; no human capital decision recorded.
