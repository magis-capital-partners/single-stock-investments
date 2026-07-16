# Index membership lens

**Date:** 2026-07-15  
**Status:** Active (dashboard research trigger)  
**Config:** `_system/data/index_rules.json`, `_system/data/index_calendar.json`, `_system/data/index_aum.json`  
**Research:** `_system/reference/index-effects/SYNTHESIS.md`  
**HK source:** Horizon Kinetics *Russell 2000 Index Construction: When Small Caps Became a Big Problem* (Jan 2013)

## Purpose

Track **potential** (proximity to eligibility boundaries) and **confirmed** (provider-announced) index inclusion and exclusion for every holding. This is a research / watch trigger, not a mechanical trade signal.

Compute **expected net forced flow as % of company float** for each event (`index_flow_impact.py`), encoding the Horizon Kinetics reconstitution axioms below.

## Status definitions

| Status | Meaning |
|--------|---------|
| `member` | Seed or constituent list says the name is in the index |
| `inclusion_candidate` | Not a member; passes most gates; within distance band of the boundary |
| `deletion_risk` | Member that fails continued-eligibility checks, or M&A / going-private news |
| `ineligible` | Security type or venue cannot join (CVR, OTC Pink, preferred, private, etc.) |
| `n_a` | Applicable in principle, but required inputs missing (float, ADV, earnings, FIF) |

## Confidence

| Tag | Meaning |
|-----|---------|
| `rules_only` | Deterministic scorecard from rules + fundamentals |
| `news_unconfirmed` | News classified as index change; not matched to provider notice |
| `provider_confirmed` | Provider notice or committee release with effective date |

## Priority score (0–1)

Weights in `index_rules.json` → `scoring.weights`:

1. **Boundary closeness** (0.35) — closer absolute distance to cutoff → higher  
2. **Calendar proximity** (0.25) — nearer reconstitution / review → higher  
3. **Demand shock** (0.30) — `|net forced flow| / ADV` from float-impact model when available; else flat `assumed_index_weight_bps_add` fallback  
4. **Illiquidity** (0.10) — lower ADV → higher residual impact for small names  

Do **not** rank by the mere fact of a membership change. Large-cap S&P 500 addition returns have fallen toward zero (Greenwood & Sammon 2022); residual edge is anticipation and smaller / less liquid names.

## Float impact (forced flow)

Per event in `by_ticker.{T}.float_impact` and `portfolio_summary.top_float_impacts`:

| Field | Meaning |
|-------|---------|
| `pct_of_float_{low,base,high}` | Net forced dollars / float market cap (signed; negative = net selling) |
| `pct_of_adv_days` | `|net_flow_base| / ADV` |
| `hk_weight_cliff_ratio` | Sell-side demand ÷ buy-side demand on Russell breakpoint migrations |
| `legs[]` | Per-index buy/sell bridge (both sides of migrations required) |
| `style_subset` / `reason` | Style-box moves and ambiguous reclass → `status: n_a` (no size flow) |
| `assumed_graduation` | R2000 exit inferred (membership unknown + mcap ≤ 4× breakpoint) |

### Horizon Kinetics axioms (normative)

1. **Weight cliff** — same name ~20× heavier at top of R2000 than bottom of R1000  
2. **AUM asymmetry** — more dollars in R2000 products than dedicated R1000 products → graduation is usually **net selling**  
3. **Float-adj weight for flow; total mcap for rank** — never conflate  
4. **Banding** — ±2.5% band suppresses predicted candidate migrations  
5. **% of float** is the right denominator (not % of market cap)

AUM tiers in `index_aum.json`: `low` = observed ETFs; `base` = + index-fund estimate (default display); `high` = base × BMI scenario multiplier. Never invent float, ADV, or AUM — emit `n_a` / omit tier.

**Breakpoint:** use dated `russell_1000.breakpoint_mcap_usd` in `index_rules.json` ($5.7B as of 2026-06-26). Never use portfolio-median mcap as the Russell breakpoint for candidacy.

**Event gates:** style/subset (Top 50, Defensive, 2500, Growth/Value Benchmark) and bare "index reclassification" never produce size-migration float impact. Candidates (expected impact) and confirmed/news (actual impact) both appear in the float-impacts table.

## Inclusion probability band

Deterministic heuristic from distance, days-to-event, and fraction of gates passed (`high` / `medium` / `low` / `n_a`). Not a machine-learning model. S&P committee discretion keeps S&P candidates at `rules_only` confidence even when the band is `high`.

## UI caption (required)

> The average large-cap S&P 500 index effect has fallen to near zero since 2010; treat these as research triggers, weighted by demand-shock size, not mechanical trades. Migrations across the Russell 1000/2000 breakpoint are typically net-negative for the promoted stock (Horizon Kinetics 2013).

## Guardrails

- Never invent float, ADV, earnings, or AUM; emit `n_a` with a reason  
- Provider thresholds and AUM live only in dated config (`index_rules.json`, `index_aum.json`)  
- Confirmed vs potential always visually distinct  
- Always model **both sides** of a migration (never "joined bigger index = inflow")  
- Stale AUM (>120 days) → dashboard warning  

## Validation reference

APLD June 2026 R2000→R1000/Midcap graduation: low ≈ −3% to −5% of float (ETF-observed), base ≈ −6% with index-fund estimate; HK cliff ≈ 10×. See `_system/reference/index-effects/SYNTHESIS.md` § Model validation.
