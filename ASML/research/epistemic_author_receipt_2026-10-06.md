# Epistemic author receipt — ASML — 2026-10-06

**Work ID:** `290e1242482eb2878775b1a4`  
**Task:** `author_forecast` / `operating_business_and_net_assets`  
**Route:** `quality_reinvestment` / `owner_earnings_reinvestment_dcf`

## Outcome

**Success.** v3 falsifier draft `asml-opbiz-oe-2026fy-v4` (spec revision 7) at `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json`, status **`awaiting_review`**.

## Remediation (rejection of draft `2750cd7278c04903d8dacb51`)

| Review reason | Author response |
|---|---|
| `source_recipe_incompatible` (sec_companyfacts_ttm vs 20-F-only filer) | Observation plan `source_adapter`: **`fact_ledger`**; `source_hint`: `normalized_owner_earnings_m`; accepted forms `20-F` / `20-F/A`; FY duration. |
| `unit_mismatch` (USD plan vs EUR companyfacts) | `source_unit` / `canonical_unit`: **USD millions** via locked ledger field with evidenced EUR/USD conversion (FY2025 20-F). |
| `historical_replay_not_adapter_verified` | Independent `resolve_spec` on FY2025 reproduces **13,024.816 USD millions** (`fact_ledger`, blocker none). |

## Spec summary

- **Metric:** normalized owner earnings, comparator `lt`, threshold **13,024.816 USD millions** (low-case `owner_earnings_reinvestment_dcf` proof trace, contract hash `25c42a2a…`).
- **Measurement period end:** 2026-12-31; observable after ~2027-02-28 (annual 20-F cadence).
- **Probability fires:** 0.22 (unchanged; reconciled to cutoff evidence).

## Calibration / loop (analysis receipt)

- **Epistemic loop:** `health_state=COLLECTING` (not BOOTSTRAP_BLOCKED, DEGRADED, or HALTED).
- **Calibration:** `calibration_status=insufficient_outcomes`; `release_hash=null`; route `quality_reinvestment`; **named_challenge:** null; **calibration_response:** `not_applicable`.

## Provenance

- **Evidence hash:** `4bb18b6aca2d16d89cd2a2895b91df37cc0af7d1115e4531d343fb2bdb36337e` <!-- pragma: allowlist secret -->
- **Input SHA:** `13c05dda78bff23f5c93e41c4aede18ae3fbd80e`
- **Manifest:** `ASML/research/research_agent_manifest.json` <!-- pragma: allowlist secret -->
- **Mechanical close:** `python3 _system/scripts/marvin_cloud_refresh.py ASML --date 2026-10-06` (ASML lint/cross-check OK; repo-wide dashboard integrity gate failed on index membership and core.json size budget).
