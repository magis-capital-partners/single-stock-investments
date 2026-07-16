# Index float-impact model: expected forced flow as % of float

**Date:** 2026-07-15
**Status:** Implemented 2026-07-16 (extends `index_membership_tracking_2026-07-01.md`)
**Owner:** Marvin
**Frameworks:** `_system/frameworks/index_membership_lens.md`, `_system/reference/index-effects/SYNTHESIS.md`, Horizon Kinetics *Russell 2000 Index Construction: When Small Caps Became a Big Problem* (Jan 2013, `_system/reference/investment-wisdom/horizon-kinetics/pdfs/20160321035257_1cdcd84f_R2000_20Index_20Construction_20White_20Paper_Dec2013.pdf`)

## Goal

For every confirmed or potential index addition, deletion, or migration affecting a portfolio ticker, compute the **expected net forced flow as a percent of that company's float** (and as days of ADV), and surface it on the dashboard Index Watch panel. Replace the current flat `assumed_index_weight_bps_add = 5.0` proxy in `priority_score()` with a computed, per-index, per-ticker weight.

Validated reference case: APLD June 2026 R2000 → R1000/Midcap migration ≈ **3–5% of float net selling** (core Russell products), up to ~8% including benchmark-hugging active money.

## Horizon Kinetics wisdom to encode (normative)

From the HK R2000 white paper and Q4 2021 commentary; these are the design axioms, not optional tuning:

1. **The weight cliff.** Both R1000 and R2000 are cap-weighted, so the same company carries ~19 bps at the top of the R2000 but <1 bp at the bottom of the R1000 (~20x). A "graduation" is therefore usually a **net deletion event**, not an inflow.
2. **AUM asymmetry.** Dollars tracking the small-cap index exceed dollars tracking the large-cap index (HK measured ~2.5x via iShares products; still >1.5x today: IWM ~$82B vs IWB+VONE ~$56B). Weight cliff × AUM asymmetry compounded to ~40x demand differential in HK's 2013 arithmetic. **Never model only one side of a migration.**
3. **Float-adjusted vs total market cap.** Russell ranks by total market cap but weights by float-adjusted market cap. Low-float names get parked at near-zero weight; flow math must use **float-adjusted weight**, rank math must use **total market cap**. Never conflate them.
4. **Banding.** Since 2007 the ±2.5% cumulative-market-cap band around rank 1000 suppresses switching (switch rates fell from ~6–10% to ~3% per Chang–Hong–Liskovich). Candidate flags must apply the band before predicting migration.
5. **Float squeeze context (Q4 2021 commentary).** Impact scales inversely with float not held by indexers/insiders; % of float is the right denominator, not % of market cap.

Calibration sanity bands from the academic corpus already in `_system/reference/index-effects/`:
- Chang–Hong–Liskovich: near-cutoff weight ratio 10–15x; June migration effect ~±5%.
- Greenwood & Sammon: migrations offset (net shock is what matters); large-cap S&P effect ≈ 0 post-2010 — keep the existing dashboard caption.
- Pavlova & Sikorskaya: benchmarking intensity (BMI) — active benchmark-hugging money adds to passive flows; treat as a **scenario multiplier, not base case**.

## Constraints

- Must keep: `n_a`-on-missing-inputs guardrail (never invent float, ADV, or AUM); dated config files; confirmed vs potential visual distinction; existing caption.
- Must not break: existing `index_membership.json` schema consumers (`index-viz.js`, holdings table sort on `priority_score`).
- Non-goals: intraday trade timing, options/futures flow, non-US index flow modeling (phase later), automated trading signals.

## Proposed change

### Phase 1 — AUM registry (config, dated)

New file `_system/data/index_aum.json`:

```json
{
  "as_of": "2026-07-15",
  "indices": {
    "russell_2000": {
      "index_total_mcap_usd": 3.5e12,
      "mcap_source": "LSEG June 2026 recon summary",
      "tiers": {
        "etf_observed": {"aum_usd": 130e9, "products": ["IWM", "VTWO", "IWO", "IWN", "TNA-underlying-excl"], "confidence": "observed"},
        "index_funds_est": {"aum_usd": 250e9, "confidence": "estimate", "note": "mutual fund share classes + smaller trackers"},
        "benchmarked_bmi": {"multiplier": 1.75, "confidence": "scenario", "source": "Pavlova-Sikorskaya BMI logic"}
      }
    },
    "russell_1000": { "...": "IWB, VONE, index funds" },
    "russell_midcap": { "...": "IWR complex; subset of R1000 — flag overlap" },
    "sp500": { "...": "SPY, IVV, VOO, SPLG + est index funds" },
    "sp400": {}, "sp600": {}, "nasdaq_100": {}, "msci_usa": {}
  }
}
```

Rules:
- Every `aum_usd` has a `confidence` (`observed` / `estimate` / `scenario`) and source. Missing → tier omitted → model degrades gracefully to lower bound.
- Subset/overlap indexes (Russell Midcap ⊂ R1000; Microcap ∩ bottom-half R2000; style Growth+Value = parent) are marked `overlap_parent` so flows are not double counted. Style products (IWO/IWN) count only when not already counted through parent-tracking AUM.
- Refresh cadence: quarterly, and at each recon. Stale >120 days → dashboard shows staleness warning.

### Phase 2 — Weight and flow calculator (`_system/scripts/index_flow_impact.py`)

Per ticker × index event:

1. **Weight before/after** (bps): `float_mcap / index_total_mcap`, where `float_mcap = market_cap_usd × float_pct` from `index_market_inputs.py`. If `float_pct` missing → weight from total mcap flagged `float_unknown` (upper bound), or `n_a` if mcap missing.
2. **Flow legs**: for each affected index and each AUM tier: `leg_usd = Δweight × tier_aum`. A migration produces sell legs (old index + its counted subsets) and buy legs (new index + subsets).
3. **Net flow**: `net_usd = Σ buys − Σ sells` per tier stack:
   - `low` = etf_observed only
   - `base` = etf_observed + index_funds_est
   - `high` = base × benchmarked_bmi multiplier
4. **Outputs per event**: `net_flow_usd_{low,base,high}`, `pct_of_float_{low,base,high}` (= net_usd / float_mcap), `pct_of_adv_days` (= |net_usd| / adv_dollar), `hk_weight_cliff_ratio` (= weight_old × AUM_old / max(weight_new × AUM_new, ε)) — the HK ~40x diagnostic, shown when a migration crosses the R1000/R2000 breakpoint.
5. **Event sources** (in priority order): provider-confirmed announcements (`index_announcements.jsonl`), news-unconfirmed announcements, and **pre-announcement candidates** from existing scorecards (`inclusion_candidate` / `deletion_risk`) — the anticipation edge per Greenwood & Sammon. Candidates get the banding check (axiom 4) before a migration is predicted.

### Phase 3 — Integrate into `build_index_membership.py`

- Call the flow calculator per ticker; write results to a new `float_impact` block in `index_membership.json` (`by_ticker.{T}.float_impact.events[]` + `portfolio_summary.top_float_impacts[]`).
- Replace `assumed_index_weight_bps_add` in `priority_score()` demand-shock term with computed `pct_of_adv_days` when available; keep the 5 bps fallback for `n_a` names.
- Keep schema additive — no removals.

### Phase 4 — Float / ADV input coverage

Currently `float_pct` and `adv` are frequently missing (APLD scorecard shows both `n_a`). Extend the fundamentals cache fetcher to populate `float_pct` (shares float / shares outstanding) and `adv_shares` for US names from the existing market-data source used by `fetch_equity_prices.py`. Missing values remain `n_a` — never inferred.

### Phase 5 — Dashboard UI (`dashboard/index-viz.js`)

- Add **"% float"** column (base case, signed: negative = net forced selling) to the potential and confirmed tables; tooltip shows low/base/high band and days-of-ADV.
- Detail drawer per event: flow bridge table (sell legs by product tier, buy legs, net), `hk_weight_cliff_ratio` badge when a Russell breakpoint migration ("HK graduation penalty: ~Nx demand differential"), confidence tier, and AUM as-of date.
- Keep the Greenwood–Sammon caption; append one sentence: "Migrations across the Russell 1000/2000 breakpoint are typically net-negative for the promoted stock (HK 2013)."

### Phase 6 — Validation and calibration

- Backtest the three June 2026 recon cases we can observe: APLD (graduation, expect ~-3 to -5% float), Bloom Energy (graduation), one R1000→R2000 demotion (expect net buying). Compare modeled `pct_of_float` vs realized June flow proxies (ETF share-count changes pre/post recon).
- Record results in `_system/reference/index-effects/SYNTHESIS.md` § "Model validation" and note residuals.
- Acceptance: modeled base-case within ±50% of observed ETF share-count changes for the two graduations.

## Success criteria

- APLD row on the dashboard shows a confirmed June 2026 migration with base-case net forced selling of ~3–5% of float, with the HK cliff diagnostic visible.
- No ticker shows a float-impact number without `float_pct`, ADV, and AUM inputs present (`n_a` otherwise).
- `build_index_membership.py` runs clean in the batch pipeline; existing dashboard columns unaffected.
- Both sides of every migration are modeled (axiom 2); no "joined bigger index = inflow" outputs anywhere.

## Risks of simplification

- AUM tiers are estimates; benchmarked/BMI money is genuinely unknowable to ±2x. Mitigation: three-tier band always shown, base ≠ high.
- Index total float-adjusted mcap approximated by total mcap from recon summaries (~10–15% overstatement of denominators, understating weights). Acceptable for a research trigger; note in config.
- Subset/overlap double counting is the biggest correctness trap (Midcap ⊂ R1000, style ⊂ parent). Mitigated by `overlap_parent` flags and a unit test with the APLD case.

## Redundancy we keep on purpose

- Existing `priority_score` fallback path (5 bps proxy) for names with missing inputs.
- Caption + confidence tags; Milly-style skepticism: the number is a research trigger, not a trade signal.

## Implementation scope

- [x] Docs: `index_membership_lens.md` § "Float impact" (edit existing framework, no new framework file per `framework_governance.md`)
- [x] Scripts: `index_flow_impact.py` (new), `build_index_membership.py` (extend), `index_market_inputs.py` (float/ADV coverage)
- [x] Config: `_system/data/index_aum.json` (new, dated); `index_float_adv.json` float/ADV cache
- [x] Dashboard: `index-viz.js` (column + drawer + float impacts table)
- [x] CI: unit test for APLD migration case (both-sided, no double count)
- [x] Validation: SYNTHESIS.md § Model validation

## [HUMAN REVIEW]

1. Default display tier: base (ETF + index-fund estimate) vs low (observed ETFs only)?
2. BMI multiplier default 1.75x — keep as scenario-only, or show in main column band?
3. Approve AUM sources: iShares/Vanguard product pages (observed) + FTSE "$12.2T benchmarked" style figures (estimate ceiling only, never used directly)?
4. Should the HK graduation-penalty note appear in ticker README / thesis files automatically, or dashboard-only?
