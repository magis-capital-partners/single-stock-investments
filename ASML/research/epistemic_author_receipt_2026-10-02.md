# Epistemic author receipt — ASML — 2026-10-02

**Work ID:** `290e1242482eb2878775b1a4`  
**Task:** `author_forecast` / `operating_business_and_net_assets`  
**Route:** `quality_reinvestment` / `owner_earnings_reinvestment_dcf`

## Outcome

**Success.** v3 falsifier draft refreshed at `ASML/research/falsifier_drafts/290e1242482eb2878775b1a4.json`, status **`awaiting_review`**.

## Remediation (prior rejection of draft `2750cd7278c04903d8dacb51`)

| Review reason | Author response |
|---|---|
| `source_recipe_incompatible` (sec_companyfacts_ttm vs 20-F-only filer) | Observation plan `source_adapter`: **`fact_ledger`**; accepted forms `20-F` / `20-F/A`; FY duration. |
| `unit_mismatch` (USD plan vs EUR companyfacts) | `source_unit` / `canonical_unit`: **USD millions** via locked `normalized_owner_earnings_m` with evidenced EUR/USD conversion. |
| `historical_replay_not_adapter_verified` | FY2025 replay **13,024.816 USD millions** via `ASML/research/valuation_fact_ledger.json#normalized_owner_earnings_m`. |

## Spec summary

- **Metric:** normalized owner earnings, comparator `lt`, threshold **13,024.816 USD millions** (low-case proof trace).
- **Measurement period end:** 2026-12-31; observable after ~2027-02-28 (annual 20-F cadence).
- **Probability fires:** 0.22 (unchanged; reconciled to cutoff evidence).

## Calibration / loop (analysis receipt)

- **Epistemic loop:** `health_state=COLLECTING` (not BOOTSTRAP_BLOCKED / DEGRADED / HALTED).
- **Calibration:** `global_status=insufficient_outcomes`; `release_hash=null`; route `quality_reinvestment`; **named_challenge:** null; **calibration_response:** `not_applicable`.

## Provenance

- Research agent manifest and agent run state under `ASML/research/` (2026-10-02 run).
- **Mechanical close:** `python3 _system/scripts/marvin_cloud_refresh.py ASML --date 2026-10-02`
