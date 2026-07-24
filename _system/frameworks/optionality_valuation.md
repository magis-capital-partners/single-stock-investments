# Optionality & Limited-Downside Valuation

**Purpose:** Secondary valuation layer for names where **Lawrence 10yr FCF IRR** and standard **Hohn operating bridges** understate the investment case. Use when the payoff is **asymmetric** — bounded floor + open-ended or dated catalyst — not when heroic growth assumptions are required.

**Canonical option rules:** **`option_treatment.md`** — mandatory option scan, treatment ladder, no auto-zero.

**Universal publication contract:** **`economic_value_agent_protocol.md`** — exact economic claim, complete component coverage, comparable hierarchy, risk/timing bridge, valuation proof, committee gates, and outcome calibration.

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

## Separated-views method (default for operating business + hidden assets)

When an operating business also owns poorly observed land, royalties, stakes, or other options, use `valuation_methodology.mode: separated_views`.

The output has three views that must never be averaged:

1. **Operating owner cash.** Start with cash available to owners after fixed-asset spending and share-based compensation. Model segment economics when margins or capital intensity differ.
2. **Complete component schedule.** Give every material component a unique `overlap_key`, a valuation method, evidence, and low/base/high estimate. An asset with weak evidence receives a wider range; it never receives an implicit value of zero merely because the evidence is incomplete. Components already represented in an operating value are marked `embedded` and identify their additive parent.
3. **Reverse expectations.** At the quoted price, solve the owner-cash growth required for a stated end-of-horizon multiple. This is a diagnostic, not a forecast.

Required decision outputs:

- operating bear/base/bull return range
- segment owner-cash reconciliation
- complete low/base/high component value, including risked latent assets
- market-implied constant owner-cash growth
- entry prices for 10%, 12%, and 15% returns

The operating base return and the complete component value are separate decision views. `synthesis.status` must be `disabled_separated_views`; correlated DCFs, NAV illustrations, and third-party narratives cannot be blended into a consensus return.

## Universal component valuation schedule

Use `component_valuation` for any security where a whole-company conclusion needs more than a single operating-cash-flow model. It is deliberately method-neutral: operating companies can use owner-cash DCF, banks can use excess-return or book-value methods, funds can use look-through NAV, and asset owners can use risked transaction NAV.

Start from the matching component map in `_system/templates/component_valuation_templates.json`. It covers operating companies, banks/insurers, holding companies, resource and land owners, biotech/pre-profit issuers, and dated-payoff situations. The template is a checklist, not a valuation: every placeholder must be replaced with an evidence-backed range.

```json
{
  "component_valuation": {
    "version": "1.0",
    "all_material_components_identified": true,
    "components": [{
      "id": "unique_component_id",
      "label": "Plain-English component name",
      "category": "operating_business | financial_asset | real_option | liability_or_reserve",
      "overlap_key": "unique_economic_claim",
      "treatment": "additive | embedded",
      "included_in_component_id": "required only when embedded",
      "valuation": {
        "basis": "per_share | total_value_m",
        "method": "dcf | market_value | risked_nav | excess_return | manual",
        "low": 0,
        "base": 0,
        "high": 0,
        "evidence_tier": "filing | transaction | analyst_estimate",
        "evidence": "specific source and reasoning",
        "cross_check": "independent check"
      }
    }]
  }
}
```

Required rules:

- Each material component has `low <= base <= high`, an evidence statement, and a method.
- Additive components sum to total equity value. Liabilities use negative values.
- Embedded components still receive an estimate, but are not added because their value is already in the identified parent component.
- A schedule fails validation if a material component is omitted, has no range, duplicates an economic claim, or embeds into a non-additive parent.
- For a new issuer without an explicit schedule, the engine emits an operating-business fallback. It is compatible with every `full` or `scenario` valuation, but it is explicitly incomplete and cannot support an asset-level conclusion.

Use horizon-neutral keys for new work: `growth_y6_end` and `exit_pfcf_end`. Legacy `growth_y6_10` and `exit_pfcf_y10` remain readable for older valuations.

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

### D. Fund / CEF look-through (CEE, PSH, Urbana, NAN)

**Sleeve:** `fund_nav_discounts` in `_system/portfolio/investment_sleeves.json`  
**Proposal:** `_system/proposals/cef_etf_nav_discount_workflow.md`  
**Enforced by:** `lint_deep_dive.py` (shadow / zero-marked sleeve narrative checks)

Use when the security is a **closed-end fund**, **listed investment company**, or hard-to-arb **ETF**, and the edge is price versus reported or economic NAV.

| Edge tag (`fund_nav_overlay.edge`) | Meaning | Examples |
|------------------------------------|---------|----------|
| `classic` | Price meaningfully below *reported* NAV; catalyst may be tender/repurchase/activist | PSH, NAN, Urbana Class A |
| `shadow` | Reported NAV understates value (Level 3 / sanctions zero marks) | CEE Russia sleeve |
| `holdco` | Permanent-capital look-through with private + public marks | Urbana private sleeve |

**Three NAVs (never average silently):**

1. **Reported NAV** — sponsor/SEC figure (discount/premium to market).
2. **Liquid economic NAV** — freely transferable holdings + cash − liabilities − fee reserve (dhando floor).
3. **Complete economic NAV** — liquid NAV + risked zero-marked / private sleeves.

**Option treatment:** zero-marked sleeves default to `zero` in base until human sets `realization_probability_base`. Bull sensitivity may show recovery.

#### Mandatory narrative when `edge: shadow` or `zero_marked_sleeves` is non-empty

This is the CEE failure mode: agents wrote a classic CEF discount story (−4% to reported NAV) and buried Russia.

| Section | Required |
|---------|----------|
| **Why the market might be wrong** | Lead with the **accounting / mark** problem (zero, Level 3, frozen, sanctions). Do **not** lead with “trades at X% to reported NAV” when that discount is thin and a zero-marked sleeve is material. |
| **Executive summary** | Name the zero-marked sleeve and that reported NAV excludes it. State base still prices the sleeve at zero until human sets recovery probability. Give an **illustration** of economic NAV or $/share sleeve size when evidence exists. |
| **Option scan** | Explicit row for the zero-marked sleeve with treatment `zero` or `probability_weighted`. |
| **Valuation & IRR** | Three-NAV table (reported / liquid / complete or illustration). Sleeve cost and/or mark-to-market illustration in the assumption ledger. |
| **Lens failure mode** | “Treating price ≈ reported NAV as ‘fair’ while ignoring zero-marked sleeves.” |

**Anti-pattern (forbidden):** Calling the fund “almost at NAV” or sizing on a thin reported-NAV discount when `fund_nav_overlay.edge` is `shadow` or any `zero_marked_sleeves[]` row has material cost / share count.

**Primary metrics:**

- `classic` / `holdco`: discount to reported (and liquid) NAV; scenario IRR on discount close.
- `shadow`: **primary** = discount to economic NAV *illustration* (or sleeve $/share); reported-NAV discount is secondary context only. Base IRR may still keep the sleeve at $0.

**Predictive attributes:** `cef_market_structure_discount`, `level3_or_sanction_zero_mark`, `tender_or_repurchase_catalyst`

**Dashboard:** sleeve filter **NAV discounts**; row field `fund_nav` (discount %, edge chip).

---

## valuation.json shape

```json
{
  "valuation_mode": "optionality",
  "method": "yield_curve",
  "optionality_gate": {
    "framework": "holdco_sotp | mineral_floor_option | hk_royalty_curve | fund_lookthrough_nav",
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

Fund / CEF shape (in addition to the above):

```json
{
  "instrument_type": "closed_end_fund",
  "optionality_gate": {
    "framework": "fund_lookthrough_nav",
    "floor_metric": "liquid_nav_per_share",
    "primary_metric": "discount_to_reported_nav"
  },
  "fund_nav_overlay": {
    "edge": "classic | shadow | holdco",
    "as_of": "YYYY-MM-DD",
    "market_price": 0,
    "reported_nav": 0,
    "discount_to_reported_nav_pct": 0,
    "liquid_nav_per_share": 0,
    "complete_nav_per_share_base": 0,
    "currency": "USD",
    "zero_marked_sleeves": [],
    "evidence_refresh": { "type": "fund_nav" }
  }
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

### World Model layer (Courtenay foresight)

Thin KPI graph over themes, industry nodes, Superorgs, and expert horizons. **Context only.**

- **Coverage:** every industry-linked ticker has `{TICKER}/research/kpi_ledger.json` (scaffold via `scaffold_industry_kpi_ledgers.py`; 6 curated pilots kept).
- **Industries (13):** 11 thesis + 2 horizon (`agi`, `robotaxi`). Taxonomy: `_system/reference/world_model/README.md`.
- **Strip:** Insights → Ticker insights (`dashboard/data/world_model.json`).
- **Weekly CI:** Data Pipeline Sunday `0 16 * * 0` UTC → profile `world-model-weekly`.
- **Hard rule:** fail → open diligence / agent re-fetch; never rewrite universal-contract components, Power Zone routes, IC packets, `human_decision.json`, or legacy Lawrence keys. Auto-link: `apply_world_model_context.py` + promotion template. Production valuation authority: `proof_first_valuation.md`.
- **Magis predictability class:** strip `claim_ceiling` / per-row `predictability_class` from `predictability_classes.json`. Horizon dates stay `P0_ill_defined`. Darwin stress caps market-path language at `P1_ecology`. Do not merge World Model with Santa Fe into one simulator; Santa Fe only forbids overclaim (Goodhart / ill-defined paths).

### Insider conviction layer (Form 4 cluster)

For US-listed holdings with CIK, maintain an **insider conviction** context block that tilts **scenario confidence** toward the bull case when qualified insiders buy on the open market. This is a qualitative corroboration layer for optionality names (water/land, holdco stakes, dated catalysts), not a second IRR engine.

- **Config:** `_system/scripts/insider_config.json` (ICS weights, scenario priors/tilt caps) + `_system/scripts/insider_domain_map.json` (ticker-specific domain multipliers, e.g. water-law expert on LMNR).
- **Refresh:** `fetch_insider_transactions.py` writes `_system/reference/market-data/insider/{TICKER}_transactions.csv` + `manifest.json` from SEC Form 4 submissions. `apply_insider_signal.py` injects `insider_signal` into `valuation.json` and `research/evidence/insider_signal_{date}.md`.
- **Hard rule:** `insider_signal.in_base_irr` stays **false**. ICS and `scenario_confidence.tilted` weights inform **stance discussion** and bull-scenario attention; they never auto-inflate Lawrence base IRR or `scenarios.bull.payoff`. Promotion requires **[HUMAN REVIEW]** (`promote_bull_weight`, optional `synthesis.qualitative_pp`).
- **Report use:** cite the snippet in **`#### Insider conviction`** inside **Business & moat** (ICS band, tilted scenario weights, top open-market buys). Pair with domain narrative when `bull_case_support` is `strong` or `exceptional`. Do **not** add ICS to the assumption ledger or IRR arithmetic.
- **Routine sales:** CFO 10b5-1 dribble sales score as low-weight noise, not a bearish thesis driver.
- **Quantification doc:** `_system/reviews/pending/insider_signal_quantification_2026-06-07.md` (Marvin recommendations).

Order: runs after `marvin_valuation.py --write` for US CIK tickers in `marvin_cloud_refresh.py` and `download_all_holdings.py`.
