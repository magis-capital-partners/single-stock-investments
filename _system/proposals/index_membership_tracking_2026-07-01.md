# Dashboard Feature Plan: Index Inclusion / Exclusion Tracking

**Date:** 2026-07-01
**Author:** Marvin
**Status:** Implemented (2026-07-09). Full-universe scorecards + Index Watch UI live.
**Runbook:** `_system/prompts/index_membership_runbook.md`
**Lens:** `_system/frameworks/index_membership_lens.md`
**Research basis:** `_system/reference/index-effects/SYNTHESIS.md` and the papers in
`_system/reference/index-effects/papers/` (Shleifer 1986; Wurgler & Zhuravskaya 2002;
Kaul, Mehrotra & Morck 2000; Barberis, Shleifer & Wurgler 2005; Petajisto 2011;
Chang, Hong & Liskovich 2015; Pavlova & Sikorskaya 2023; Bennett, Stulz & Wang 2020;
Greenwood & Sammon 2022), plus provider rulebooks in `_system/reference/index-effects/methodology/`.

---

## 1. Goal

Add a dashboard capability that keeps us abreast, per ticker, of:

- **Potential** index inclusion or exclusion (proximity to an eligibility boundary,
  before any announcement); and
- **Confirmed** announcements (an index provider has published an add / delete with an
  effective date).

The feature must fit the existing static, zero-runtime-cost architecture:
Python build scripts produce committed JSON; `dashboard/index.html` reads it. No new
runtime services, no runtime LLM calls (same discipline as the Insights tab upgrade).

## 2. Why this matters (grounded in the research)

- The one-shot large-cap S&P 500 "index premium" has shrunk toward zero over the last
  decade (Greenwood & Sammon 2022; Bennett, Stulz & Wang 2020). So this feature is
  primarily a **research / watch trigger**, not a mechanical trade signal. The UI must
  say so, to avoid over-weighting a fading effect.
- The **edge has shifted to anticipation**: more of the price move now happens before the
  official announcement, and events are more predictable (largest-eligible-firm rule;
  rules-based Russell cutoff). A watch that flags candidates early is where value remains.
- The effect **still bites for smaller, less liquid, less substitutable names**
  (Wurgler & Zhuravskaya 2002; Petajisto 2011) - which describes many of our holdings
  (thin-float, OTC, non-US small caps). Prioritize alerts by demand-shock size, not by
  the mere fact of a membership change.
- **Benchmarking Intensity (BMI)** predicts impact better than raw "% indexed"
  (Pavlova & Sikorskaya 2023); the impact-ranking should approximate it where feasible.
- Track **both directions and both causes**: size-driven moves across the Russell 1000/2000
  and S&P 500/400/600 boundaries, and corporate-action deletions (M&A, going-private,
  viability / float / listing failures).

## 3. Current state we build on

- `portfolio_news_common.py` already has an `index_inclusion` news category, but its regex
  only catches additions ("added to S&P 500", "joins Russell"). It misses deletions,
  removals, "under review", and provider notices. We extend it.
- News flows: `ingest_portfolio_news.py` -> `dashboard/data/portfolio_news.json` and into
  `build_insights.py` -> `insights.json` -> `events` / `events_by_ticker` -> Insights tab.
- Per-ticker fundamentals we already have: price, shares, market cap, float where available
  in `{TICKER}/research/valuation.json` and via `fetch_equity_prices.py`; GAAP earnings sign
  via filing evidence (`filing_facts.py`).
- Registry is the source of truth for the universe: `_system/portfolio/registry.json`.
- `build_dashboard_data.py` merges component JSONs into `dashboard/data/dashboard_data.json`;
  `validate_dashboard_data.py` gates it; `dashboard-pages.yml` deploys.

## 4. Data model

### 4.1 New static config (dated, human-owned)

`_system/data/index_rules.json` - eligibility thresholds per index, versioned by date so we
never hardcode a quarterly number in code:

```json
{
  "sp500": {
    "as_of": "2025-07-01",
    "min_company_mcap_usd": 22700000000,
    "min_float_pct": 0.50,
    "min_iwf": 0.10,
    "earnings_rule": "positive GAAP most recent quarter AND trailing 4 quarters",
    "liquidity_ratio_min": 1.0,
    "domicile": "US",
    "exchanges": ["NYSE", "NYSE Arca", "NYSE American", "Nasdaq"],
    "source": "_system/reference/index-effects/methodology/sp_dji_us_indices_methodology.pdf"
  },
  "sp400": { "band_usd": [8000000000, 22700000000], "...": "..." },
  "sp600": { "band_usd": [1200000000, 8000000000], "...": "..." },
  "russell": {
    "rank_metric": "total_market_cap",
    "r1000_r2000_breakpoint_rank": 1000,
    "band_pct_1000": 0.025,
    "band_pct_2000": 0.005,
    "source": "_system/reference/index-effects/methodology/ftse_russell_us_indexes_construction_and_methodology.pdf"
  }
}
```

`_system/data/index_calendar.json` - reconstitution / review dates:

```json
{
  "russell": {"rank_day": "2026-04-30", "effective": "2026-06-26", "kind": "annual_recon"},
  "russell_dec": {"rank_day": "2026-10-31", "effective": "2026-12-11", "kind": "semi_recon"},
  "sp_dji": {"cadence": "ad_hoc", "quarterly_share_update": ["03-21","06-20","09-19","12-19"]},
  "msci": {"reviews": ["2026-05-30","2026-11-30"], "kind": "semi_annual_review"},
  "nasdaq100": {"annual_recon": "2026-12-19"}
}
```

### 4.2 New generated payload

`build_index_membership.py` -> `dashboard/data/index_membership.json`:

```json
{
  "generated": "2026-07-01T00:00:00Z",
  "rules_as_of": "2025-07-01",
  "by_ticker": {
    "APLD": {
      "current_memberships": ["russell_2000"],
      "scorecards": [
        {
          "index": "sp500",
          "status": "inclusion_candidate",     // member | inclusion_candidate | deletion_risk | ineligible | n_a
          "checks": {
            "market_cap": {"pass": false, "value": 6.1e9, "threshold": 22.7e9, "distance_pct": -73.1},
            "float": {"pass": true, "value": 0.72, "threshold": 0.50},
            "earnings_positive": {"pass": false, "value": "TTM GAAP negative"},
            "liquidity": {"pass": true},
            "domicile": {"pass": true}
          },
          "gating_check": "market_cap",
          "distance_to_boundary_pct": -73.1,
          "confidence": "rules_only"
        },
        {
          "index": "russell_1000",
          "status": "inclusion_candidate",
          "rank_estimate": 1180,
          "distance_to_boundary_pct": -8.4,     // vs rank-1000 breakpoint, banded
          "within_band": false
        }
      ],
      "impact_proxy": {
        "demand_shock_pct_of_adv": 12.4,        // est shares bought/sold / ADV
        "bmi_change_est": null,                  // filled if benchmark AUM data available
        "priority_score": 0.61                   // 0-1, drives sort/alert threshold
      },
      "confirmed_events": [
        {
          "index": "russell_2000",
          "action": "add",
          "announced": "2026-06-06",
          "effective": "2026-06-26",
          "source_url": "https://www.lseg.com/.../notice",
          "source_type": "provider_notice"      // provider_notice | news | committee_release
        }
      ],
      "next_calendar_event": {"index": "russell", "kind": "annual_recon", "effective": "2026-06-26", "days_out": 12}
    }
  },
  "portfolio_summary": {
    "inclusion_candidates": ["APLD", "..."],
    "deletion_risks": ["..."],
    "confirmed_next_30d": ["..."]
  }
}
```

Notes:
- `status` and every `checks` entry are **deterministic** from `index_rules.json` +
  fundamentals. No LLM. Missing inputs -> `"n_a"` with an explicit reason, never a guess.
- `impact_proxy.priority_score` implements the research lesson: rank by demand-shock size
  relative to liquidity (Petajisto elasticity; Greenwood & Sammon size dependence),
  approximating BMI change (Pavlova & Sikorskaya). Exact weights in the framework doc.
- `confidence`: `rules_only` (proximity), `news_unconfirmed`, `provider_confirmed`.

## 5. Build scripts

1. **`_system/scripts/build_index_membership.py`** (new)
   - Reads `registry.json`, per-ticker `valuation.json` (mcap, shares, float, ADV),
     filing-facts earnings sign, `index_rules.json`, `index_calendar.json`, current
     memberships (seed file `_system/data/index_memberships_seed.json`, human-maintained
     + updated by confirmed events), and confirmed events harvested from news + provider notices.
   - Emits `dashboard/data/index_membership.json` (+ `docs/` mirror via `sync_pages_docs.py`).
   - Pure-Python, idempotent, re-runnable, committed output (matches house pattern).

2. **`portfolio_news_common.py`** (extend, small)
   - Broaden `index_inclusion` patterns to capture deletions / removals / reviews and
     provider language, e.g. `removed from|deleted from|dropped from (S&P|Russell|MSCI|Nasdaq)`,
     `to be (added|removed)`, `index (addition|deletion|removal|review)`,
     `set to join|will replace|replaces? .* in the (S&P|Russell)`.
   - Optionally split into `index_addition` / `index_deletion` sub-tags (keep the umbrella
     category for `REFRESH_CATEGORIES` so both remain refresh-eligible).

3. **`build_insights.py`** (small)
   - When an `index_inclusion` news item resolves to a confirmed add/delete, surface it as
     an `event_type = "index_change"` in `events` / `events_by_ticker` so it appears in the
     existing Insights "What changed" feed with an `impact_axis` of `catalyst`.

4. **`build_dashboard_data.py`** (small)
   - Merge `index_membership.json` into the top-level payload and attach the per-ticker
     `scorecards` / `status` / `confirmed_events` to each holding row (like insights merge).

5. **`validate_dashboard_data.py`** (small)
   - Assert every ticker with a scorecard exists in the registry; statuses are from the
     allowed enum; `rules_as_of` present; confirmed events have an `effective` date and source.

## 6. UI (dashboard/index.html + new `index-viz.js`)

Two surfaces, reusing existing dark tokens (DM Sans / JetBrains Mono):

1. **Holdings table**: a compact **Index** badge column.
   - `member` (neutral), `inclusion_candidate` (amber, with distance %), `deletion_risk`
     (red), plus a small dot when a confirmed event is within 30 days. Sortable by
     `priority_score`.

2. **New "Index Watch" panel** (either a section on the Insights tab or a 5th view tab):
   - **Confirmed changes** table: ticker, index, action, announced, effective, countdown, source link.
   - **Potential** table: ticker, index, gating check, distance-to-boundary, priority score,
     next calendar event. Filter by index and by direction (inclusion / exclusion).
   - **Reconstitution calendar** strip: next Russell recon, S&P quarterly share update,
     MSCI review, with day counts (from `index_calendar.json`).
   - A short standing caption citing Greenwood & Sammon: "The average large-cap S&P 500
     index effect has fallen to near zero since 2010; treat these as research triggers,
     weighted by demand-shock size, not mechanical trades."

Decision for review: separate tab vs Insights sub-section. Recommendation: start as an
**Insights sub-section** (lower surface-area, reuses `insights-viz.js` patterns), promote to
its own tab if it earns attention.

## 7. Data sourcing for confirmed announcements

- **Provider primary (preferred):** FTSE Russell index notices / reconstitution files;
  S&P DJI announcements (committee releases / press). Harvest into
  `_system/data/index_announcements.jsonl` (dated, append-only, deduped like `news_seen.json`).
  May require a Vicki browser task where pages are dynamic. [HUMAN REVIEW] on licensing.
- **Secondary:** existing Polygon + Google News pipeline via the broadened `index_inclusion`
  category (already `refresh_eligible`). Tagged `news_unconfirmed` until matched to a
  provider notice.
- **Membership state of record:** `_system/data/index_memberships_seed.json`, seeded by hand
  for our ~105 holdings, then auto-updated from confirmed events.

## 8. Workflow wiring

- Add `build_index_membership.py` to the `dashboard-pages.yml` build sequence
  (after `build_nol_screener.py`, before `build_dashboard_data.py`).
- Run it in `daily-sync.yml` after the news ingest so confirmed events refresh daily and
  can trigger `marvin_pick_ticker.py` (index changes are already refresh-eligible).
- Recompute proximity when `fetch_equity_prices.py` updates market caps.

## 9. Phasing

| Phase | Scope | Output |
|-------|-------|--------|
| 1 | Config + deterministic scorecards for **Russell 1000/2000** and **S&P 500/400/600** from data we already hold; membership seed; Holdings badge column. | `index_rules.json`, `index_calendar.json`, `build_index_membership.py`, `index_membership.json`, badge column |
| 2 | Confirmed-events pipeline: broaden news category, `index_change` events, Insights "Index Watch" sub-section, reconstitution calendar strip. | news + insights changes, `index-viz.js` panel |
| 3 | Impact ranking: demand-shock-vs-ADV priority score; deletion-risk detection (M&A / viability / float). | `impact_proxy`, `deletion_risk` status |
| 4 (optional) | MSCI GIMI, Nasdaq-100, and home-market indices (TOPIX, FTSE, STOXX) for non-US holdings; BMI approximation if benchmark AUM data is licensed. | extended `index_rules.json`, provider harvest |

## 10. Framework governance

A new lens doc `_system/frameworks/index_membership_lens.md` (scoring weights for
`priority_score`, status definitions, the "effect is fading; weight by demand shock"
guidance) is a **new framework file**, so per `framework_governance.md` it must go through
the `_system/prompts/architecture_review_template.md` checklist before creation. This plan
does not create it yet; it is listed as a Phase 1 deliverable pending that approval.

## 11. Non-goals / guardrails

- No runtime API calls or LLM calls in the dashboard; all data pre-built and committed.
- Scorecards never fabricate missing fundamentals; unknown inputs render as `n_a` with a reason.
- The feature is a research trigger, not a trade recommendation; the UI states the fading-effect caveat.
- Provider methodology thresholds live in dated config and are refreshed when providers update them
  (S&P reviews cap bands quarterly).

## 12. [HUMAN REVIEW]

- Which indices to cover first for our universe (exchanges, royalties, non-US small caps)?
- Separate "Index Watch" tab vs Insights sub-section?
- Appetite / licensing for provider notice harvesting and benchmark-AUM data for true BMI?
- Approve the Phase 1 framework-governance proposal for `index_membership_lens.md`.

---

*Files this plan would add: `_system/data/index_rules.json`, `_system/data/index_calendar.json`,
`_system/data/index_memberships_seed.json`, `_system/scripts/build_index_membership.py`,
`dashboard/data/index_membership.json`, `dashboard/index-viz.js`; plus small edits to
`portfolio_news_common.py`, `build_insights.py`, `build_dashboard_data.py`,
`validate_dashboard_data.py`, `dashboard/index.html`, and the two GitHub workflows.*
