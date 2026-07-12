# Darwin IRA — covered-call & universe improvement plan

**Date:** 2026-07-11  
**Status:** Phases A–D **done** (2026-07-11).  
**Context:** Darwin production is Roth IRA only (`account_scope: ira_only`). Universe is `registry_sp500_liquid` (SPX ∩ ADV$ buckets A/B); covered-call track is a **synthetic** monthly overlay (not Darwin AI Ventures proprietary NN). Source meeting: Jun 24 Dan Still / Tom Cullum (S&P 500, options liquidity, mostly ~7-day covered calls).

---

## Current gaps (honest)

| Area | Today | Gap vs Dan/Tom product |
|------|-------|------------------------|
| Universe | Registry ∩ S&P 500 ∩ ADV$ A/B (`registry_sp500_liquid`) | ADV$ is options-liquidity **proxy** only; nearly all SPX clear $50M/$10M today — tighten later if needed |
| Stock pick | `ira_marvin` + dual-score scenario (`ira_marvin_cc`); OOS-gated before production promote | Live IV sparse until champion options refresh with API keys |
| Covered call | Tenor-aware, name-level, regime coverage, stress cases | Still synthetic (not proprietary NN); chain marks optional via cache |
| Benchmarks | SPY + XYLD + QYLD | BXM not licensed; XYLD/QYLD from Yahoo vault |
| Rebalance | Semiannual equity; monthly CC marks with weekly tenor map | No true weekly path dependence on daily bars |
| Execution | Paper weights only | Options cache lab only |

---

## Phase A — Universe quality ✅ DONE (2026-07-11)

**Goal:** Eligible book = names we can actually write liquid calls on, with enough history to trust backtests.

1. **SPX coverage expansion** ✅  
   - Registry ∩ SPX = **503/503** (full onboard). Returns CSV on **~490** of liquid-eligible names.  
   - Gate: `universe_count >= 20` with Tier A monthly returns — **pass** (`coverage_gate_ok`).

2. **Liquidity screen (options-aware, PIT-safe)** ✅  
   - File: `_system/reference/market-data/index/sp500_options_liquidity.json`  
   - Refresh: `python _system/scripts/darwin/refresh_sp500_liquidity.py` (also via `make darwin-sp500-refresh` / `make darwin-sp500-liquidity`)  
   - Universe spec: `registry_sp500_liquid` = registry ∩ SPX ∩ liquidity_bucket ∈ {A,B}  
   - Stale (>30d) or missing → fall back to `registry_sp500` + UI `liquidity fallback` badge  

3. **Exclusion hygiene** ✅  
   - IRA IRR/stance gates counted in `universe_exclusions.by_reason.irr_stance_miss`  
   - Explicit: no-options flag, ADR/OTC market/exchange, dual-class aliases (BRK.B)  

4. **Dashboard** ✅  
   - Darwin tab: eligible vs excluded table (SPX miss / liquidity / no options / returns / IRR-stance)  

**Deliverables:** `universe.py` + mandate `universe: registry_sp500_liquid`; refresh in `make darwin-sp500-refresh`; serving fields `universe_exclusions`.

---

## Phase B — Covered-call model fidelity ✅ DONE (2026-07-11)

**Goal:** Transparent research overlay that behaves more like short-dated buy-writes without claiming proprietary NN performance.

1. **Tenor + strike knobs** ✅ — `tenor_days`, `otm_pct`, `roll_frequency`, `bid_ask_haircut`; formula in `darwin_source_alignment.md`
2. **Name-level overlay** ✅ — vol scale + stance/liquidity coverage (`covered_call.py` / `backtest.benchmark_covered_call`)
3. **Path dependence** ✅ — monthly marks with tenor→roll mapping; `assignment_bps` haircut
4. **Benchmark completeness** ✅ — XYLD + QYLD returns vaulted; side-by-side in serving
5. **Stress cases** ✅ — bull/crash/sideways + `test_covered_call_bcd.py`

---

## Phase C — Selection that favors the strategy ✅ DONE (2026-07-11)

1. **Dual score** ✅ — `ira_marvin_cc` = Marvin × `cc_suitability`; watch+high-CC → human warn
2. **Concentration** ✅ — `max_names_cc: 8`; `darwin_cc_scenarios.json`
3. **Regime link** ✅ — coverage_mult_calm / adapting / stressed
4. **PIT OOS gate** ✅ — `require_oos_for_dual_score`; fail → keep long-only `ira_marvin` paper weights

---

## Phase D — Lab ✅ DONE (2026-07-11)

- Options cache: etf-dashboard overlaps (free) + champion-only live refresh with hard caps — see `darwin_options_data_plan.md`
- CC-knob GA lab: `evolution.enable_cc_ga` → `darwin_cc_lab_scenarios.json` (does not overwrite Marvin stance)
- XYLD/QYLD sleeve vs champion CC-sim in benchmarks

**Out of scope:** Claiming identity with Darwin AI Ventures returns; taxable-account optimization (retired).

---

## Suggested sequence

| Week | Work |
|------|------|
| ✅ | Phase A complete |
| ✅ | Phase B–D complete |
| Next | Optional: `make darwin-options-cache-live` when API keys free; tighten ADV$ thresholds; human-approve CC scenario weights |

## Success metrics

| Metric | Target |
|--------|--------|
| SPX-liquid eligible names with returns | ≥ 20 |
| Production names | 8–12 (IRA) |
| CC-sim vs SPY in sideways subsample | Positive excess (documented) |
| Bull-month CC lag vs champion | Expected and labeled, not hidden |
| Marvin conflicts on CC book | 0 high-weight + watch without review |
| Disclaimer | Always present in UI + mandate |

## Commands

```bash
make darwin-sp500-refresh
make darwin-options-cache
make darwin-cc-test
make darwin-build
make darwin-pit-check
```

*Not tax or investment advice. IRA wrapper removes capital-gains drag inside the account; options still have economic risk.*
