# Optionality & Limited-Downside Valuation

**Purpose:** Secondary valuation layer for names where **Lawrence 10yr FCF IRR** and standard **Hohn operating bridges** understate the investment case. Use when the payoff is **asymmetric** — bounded floor + open-ended or dated catalyst — not when heroic growth assumptions are required.

**Canonical option rules:** **`option_treatment.md`** — mandatory option scan, treatment ladder, no auto-zero.

**Do not use for:** operating compounders priced on earnings with no hidden assets (Lawrence `full` alone is enough), or binary pre-revenue bets with no asset floor (use `scenario` with explicit failure modes).

---

## When to trigger (any of)

| Trigger | Examples |
|---------|----------|
| **Asset floor ≥ price risk** | Cash + book > ~50% of price; no debt; depleting trust with cash reserve |
| **GAAP book misstates assets** | Land/royalties at zero or historical cost (TPL 1888 Assigned interests); stakes at cost |
| **Look-through NAV / SOTP** | Holdco; private stakes marked below fair value |
| **Undeveloped reserves / dormant acreage** | Permian surface not in run-rate; NRA not yet drilled; KEWL Copperwood |
| **Dormant asset priced at zero** | Royalty not in run-rate; HK stake at cost |
| **HK transitory + yield curve** | Distribution suspension, bonus tier gap, legal recovery with timeline |
| **Market structure discount** | Royalty trust / OTC / K-1 excluded from yield screens |
| **In-business options buried in consolidated IRR** | Waymo, Reality Labs, Cloud backlog — use with `segment_cashflow` + `option_treatment.md` |

Set `valuation_mode: optionality` in `{TICKER}/research/valuation.json` and document `optionality_gate` (below).

---

## Three archetype overlays

### A. Holdco flywheel + catalyst stack (FRMO)

**Sources:** `_system/reference/investment-wisdom/stahl/`; approved Substacks — `_system/frameworks/approved_substacks.md`, `FRMO/third-party-analyses/references.md`; [SSI FRMO flywheel](https://specialsituationinvesting.substack.com/p/frmo-corp-a-frictionless-flywheel); [LCI crypto conglomerate](https://lemoncakesinvesting.substack.com/p/frmo-frmo-corp-commentary-on-frmos)

| Lens | Question |
|------|----------|
| **Flywheel / permanent capital** | Does the vehicle compound book without fund-flow risk? |
| **Sum-of-parts** | List top stakes + cash; mark private assets at **fair** not GAAP |
| **Catalyst stack** | Dated or probable events: HK IPO, MIAX IPO, CMSG IPO, Winland control → operating earnings |
| **Insider alignment** | Director/officer ownership %; compensation structure |
| **Floor** | Book value, net cash, no recourse debt |

**Primary metrics (not 10yr FCF):**

1. **NAV / look-through discount** — price vs FRMO-attributable book and vs SOTP fair value  
2. **Catalyst IRR** — annualized return if named catalysts close in X years (HK re-mark, MIAX listing)  
3. **Dhando floor** — bear case = book erosion or flat NAV, not operating bankruptcy  

**Predictive attribute:** `dormant_asset` (private stakes below fair value)

---

### B. Mineral / land floor + free option (KEWL, TPL)

**Sources:** Special Situation Investing — [KEWL intro](https://specialsituationinvesting.substack.com/p/keweenaw-land-association-kewl), [KEWL update](https://specialsituationinvesting.substack.com/p/update-keweenaw-land-association); TPL 10-K Assigned land policy

| Lens | Question |
|------|----------|
| **GAAP vs fair value** | Does balance sheet exclude or understate land/royalties? (TPL: Assigned interests **$0** on BS) |
| **Floor** | Fair-value NAV (per-acre, per-NRA comps, land-sale marks) — **not** GAAP book when misstated |
| **Burn runway** | Pro forma cash burn ex one-offs (KEWL) |
| **Undeveloped option** | Model producing cash in operating segments; **undeveloped** acreage/NRA in overlay (`nav_floor` or **probability_weighted**) |
| **Segment build** | Land/Royalty vs Water vs Undeveloped reserves (`option_treatment.md`) |
| **Patient capital** | Repurchases above/below fair NAV |

**Primary metrics:**

1. **Fair NAV / price** — SOTP vs market cap; flag when price **above** fair NAV without growth option  
2. **Operating cash IRR** — Lawrence `full` on current royalties/easements/water (stance gate unless human overrides)  
3. **Option yield** — incremental royalty $ if undeveloped acreage drills ÷ market cap (bull)  

**Predictive attribute:** `dormant_asset` + optional `equity_yield_curve` if production date firms up

**TPL:** `nav_overlay` + segment build; never use **~$21/sh GAAP book** as floor.

---

## Discount magnitude (MOI Ch 3)

When SOTP or NAV overlay exists, report in Valuation & IRR:

| Field | Rule |
|-------|------|
| Premium or discount | As **% of current price** (not only % of NAV) |
| MOI framing | Distinguish compelling (~50% off) vs thin discount |
| Compensating factors | "Discount is / is not large enough for [no catalyst / illiquidity / governance]." |

---

### C. Passive royalty trust — HK curve (MSB)

**Sources:** `_system/reference/investment-wisdom/horizon-kinetics/HK-Q4-2024-Commentary-extract.txt` (Mesabi case study); `HK-Q1-2025-Commentary-extract.txt`; `HK-Q3-2025-Commentary-extract.txt`

| Lens | Question |
|------|----------|
| **Transitory problem** | Is distribution/bonus gap **temporary** with contractual/mechanical resolution? |
| **Equity yield curve** | Plot annualized return vs years until normalized payouts + legal clarity |
| **Normalized distribution yield** | Use **mid-cycle / post-recovery** $/unit, not single depressed quarter |
| **Market structure discount** | ETF/yield-screen exclusion; “almost unknown” despite decades of outperformance |
| **No management risk** | Trust admin only — operator dispute is legal, not governance |

**HK Mesabi facts (commentary):**

- 40yr annualized total return **~9.8%** to unitholders (1985–2024)  
- Arbitration award **$5.43/unit** — price moved one-for-one when spreadsheet-ready  
- At **~$26**, normalized annual distribution **>$2/unit** → **>8% yield**  
- Q1 2025: parallel to SJT — suspension/reinstatement, **time arbitrage**  
- Q3 2025: Cliffs premium dispute; **$72M** prior award; second arbitration on intercompany/idling  

**Primary metrics:**

1. **Normalized distribution yield** at current price (not TTM depressed)  
2. **Equity yield curve** — payoff = cumulative distributions + terminal unit value over 3–8 years  
3. **Legal catalyst** — arbitration timeline as dated recovery (curve steepness)  

**Predictive attributes:** `equity_yield_curve`, `transitory_problem`, `market_structure_discount`

---

## valuation.json shape

```json
{
  "valuation_mode": "optionality",
  "method": "yield_curve",
  "optionality_gate": {
    "framework": "holdco_sotp | mineral_floor_option | hk_royalty_curve",
    "floor_pass": true,
    "floor_metric": "book_per_share",
    "floor_value": 8.55,
    "primary_metric": "normalized_yield",
    "primary_return_pct": 8.0,
    "notes": "Do not use base Lawrence IRR as sole stance gate"
  },
  "scenarios": { "bear": {}, "base": {}, "bull": {} }
}
```

---

## Stance logic (optionality mode)

When `valuation_mode == optionality`, Marvin **does not** auto-downgrade to `watch` solely because Lawrence base IRR < 15%.

| Condition | Stance proposal |
|-----------|-----------------|
| `floor_pass` + `dhando` full/partial + primary metric ≥ 15% | `hold` or `accumulate` |
| `floor_pass` + bull scenario ≥ 20% + incumbent sleeve | `hold` (document override) |
| `floor_pass` + primary metric 7–15% (normalized yield / SOTP discount) | `hold` or `watch` — size for option |
| Price above floor / weak dhando | `watch` |
| `dhando` none or floor fails | `watch` or `trim` |

Always reconcile with human **stance** in `classification.json`; document overrides in `[HUMAN REVIEW]`.

---

## Report integration

In deep dives for optionality names, add after **Payoff & return**:

```markdown
### Optionality overlay

| Field | Value |
|-------|-------|
| Framework | holdco_sotp / mineral_floor_option / hk_royalty_curve |
| Floor | … |
| Free option / catalyst | … |
| Primary metric | … |
| Predictive attribute(s) | … |
```

Reference this file + external sources in `[PROPOSED MEMORY]` when promoting beliefs.

---

## Holdings map

| Ticker | Overlay | Primary metric |
|--------|---------|----------------|
| **FRMO** | Holdco SOTP + catalyst stack | Look-through NAV discount; catalyst IRR |
| **KEWL** | Mineral floor + Copperwood option | Fair NAV floor; option yield (bull) |
| **TPL** | Permian land + NRA + water; GAAP land at zero | `nav_overlay` + segment build; undeveloped reserves option |
| **MSB** | HK royalty curve | Normalized distribution yield + arbitration timeline |
| **SJT** | HK royalty curve (existing) | NPI deficit paydown curve |

---

## Mechanical refresh and market inputs

**Purpose:** Machine layer after `marvin_valuation.py --write`. Config lives in **`valuation.json`**; prose and option scan stay in **`option_treatment.md`**.

**Single runner:** `python _system/scripts/marvin_cloud_refresh.py {TICKER} --date YYYY-MM-DD --strict-evidence` (batch: `batch_portfolio_refresh.py`).

### When to set `evidence_refresh`

| Situation | JSON |
|-----------|------|
| Commodity-linked production royalty scaled to spot | `evidence_refresh.type: commodity_nav` |
| Economic floor ≠ GAAP book | `nav_overlay` + `optionality_gate.floor_metric: nav_per_share` |
| Stale $/unit in third-party bridge | Refresh spot first; cite `market_inputs` in ledger |

### Market inputs freshness (gate)

- Run `fetch_market_inputs.py {TICKER} --merge` when `evidence_refresh` or commodity keys in `inputs` affect IRR or option yield.
- Store `as_of`, `source`, `fetched_at` in `{TICKER}/research/market_inputs.json`.
- **Staleness:** commodity spot must be ≤ **7 days** old; `check_evidence_completeness.py` flags older spots.

### QA gates (`evidence_refresh` keys)

| Key | Role |
|-----|------|
| `base_payoff_mode` | `fixed_stance_gate` (default) pins payoff; `sum_lines` derives payoff from SOTP sum |
| `max_residual_uplift_per_share` | Strict run fails if residual/tie_out slack exceeds cap (default 5) |
| `synthesis_in_dive` | Default **false** for `yield_curve` — Lawrence base is sole headline IRR in deep dive |
| `synthesis_in_dive: true` | Enables Total synthesis IRR block in markdown |

**Post-pass:** `post_optionality_valuation_pass` (in `refresh_optionality_valuation.py`) syncs `implied_return.base_pct` to Lawrence results and disables or refreshes synthesis paths.

### Order inside `marvin_cloud_refresh`

1. Filing + management evidence (if not skipped)
2. `fetch_market_inputs.py --merge`
3. `marvin_valuation.py --write`
4. `refresh_optionality_valuation.py` when `evidence_refresh.type` is set
5. `fill_cross_check.py` (required when `--strict-evidence`)
6. `refresh_deep_dive_v2.py` (force-replaces look-through / SOTP when `evidence_refresh` set)
7. Lint + Milly + `check_evidence_completeness.py --date {date}` (+ second lint when strict)

### OTC filing facts

When XBRL/IX tags are absent, `filing_facts.py` uses `parse_otc_prose_metrics()` on full-tier `_text/`. Preserves existing metrics if a new parse is empty.

### Thematic context layer (demand tailwinds)

For names whose optionality is driven by an external demand chain (TPL water / LB easements / WBI infra / APLD hosting on the AI compute -> power -> Permian surface chain), maintain a **context layer** that is broadly ingested but consumed narrowly.

- **Config:** `_system/scripts/theme_panel_config.json` declares indicator series (FRED, Stooq, EIA, repo filings). Hyperscaler capex is derived from each ticker's filing-cited `ai_overlay` in `valuation.json` (no fabricated numbers).
- **Tags:** `_system/portfolio/holdings_themes.json` maps a theme to the holdings it explains.
- **Refresh:** `fetch_theme_panel.py` writes `_system/reference/market-data/themes/{id}.csv` + `manifest.json` (offline-safe; cached history kept on network failure). `apply_context_overlay.py` injects a `context_overlay` block into each tagged ticker's `valuation.json` and a `research/evidence/thematic_context_{date}.md` snippet.
- **Hard rule:** `context_overlay` is **context only**. Every indicator carries `in_base_irr: false`. A tailwind may inform **stance** and **overlay sizing**, but it never auto-inflates Lawrence base IRR. Promotion of any indicator to base case requires a human to set `in_base_irr: true` (preserved across refreshes) under **[HUMAN REVIEW]**.
- **Report use:** cite the snippet in a `#### Thematic context` table inside **Business & moat** (direction vs prior year, in-base-IRR yes/no). Do not move tailwind value into `inputs.fcf_per_share` or `nav_overlay` marks without filing-backed evidence.
- **Staleness:** indicators older than the per-series gate are flagged `stale` in the manifest and snippet; treat stale tailwinds as narrative only.

Order: runs after `marvin_valuation.py --write` (so the overlay survives recomputation) in both `marvin_cloud_refresh.py` (tagged tickers) and the daily `download_all_holdings.py` tail.

### Insider conviction layer (Form 4 cluster)

For US-listed holdings with CIK, maintain an **insider conviction** context block that tilts **scenario confidence** toward the bull case when qualified insiders buy on the open market. This is a qualitative corroboration layer for optionality names (water/land, holdco stakes, dated catalysts), not a second IRR engine.

- **Config:** `_system/scripts/insider_config.json` (ICS weights, scenario priors/tilt caps) + `_system/scripts/insider_domain_map.json` (ticker-specific domain multipliers, e.g. water-law expert on LMNR).
- **Refresh:** `fetch_insider_transactions.py` writes `_system/reference/market-data/insider/{TICKER}_transactions.csv` + `manifest.json` from SEC Form 4 submissions. `apply_insider_signal.py` injects `insider_signal` into `valuation.json` and `research/evidence/insider_signal_{date}.md`.
- **Hard rule:** `insider_signal.in_base_irr` stays **false**. ICS and `scenario_confidence.tilted` weights inform **stance discussion** and bull-scenario attention; they never auto-inflate Lawrence base IRR or `scenarios.bull.payoff`. Promotion requires **[HUMAN REVIEW]** (`promote_bull_weight`, optional `synthesis.qualitative_pp`).
- **Report use:** cite the snippet in **`#### Insider conviction`** inside **Business & moat** (ICS band, tilted scenario weights, top open-market buys). Pair with domain narrative when `bull_case_support` is `strong` or `exceptional`. Do **not** add ICS to the assumption ledger or IRR arithmetic.
- **Routine sales:** CFO 10b5-1 dribble sales score as low-weight noise, not a bearish thesis driver.
- **Quantification doc:** `_system/reviews/pending/insider_signal_quantification_2026-06-07.md` (Marvin recommendations).

Order: runs after `marvin_valuation.py --write` for US CIK tickers in `marvin_cloud_refresh.py` and `download_all_holdings.py`.
