# Rock / aggregates watchlist — implementation plan

**Date:** 2026-09-07
**Trigger:** Human ask — "rock stocks for housing/construction, Vulcan / MLM" — track a related-name universe in the watchlist section with a defined KPI set.
**Status:** **Implemented 2026-09-07** (P0-P3). See §8 for what shipped and what
changed against this plan; §7 records the decisions taken.
**Precedent followed:** `_system/proposals/competitive_advantage_banks_watchlist_2026-07-17.md` (NOL → banks screener stack).

---

## 0. What already exists — verified, not assumed

Checked against `_system/portfolio/registry.json`, `dashboard/data/`, the committed
SEC ticker→CIK map, and each ticker's `_download_log.txt`.

| Finding | Evidence | Consequence for this plan |
|---|---|---|
| **VMC, MLM, CRH, SUM, BLDR, MAS, URI, PWR are already registry `holdings`** — not watchlist entries | `registry.json` → `holdings`; `VMC/` … `PWR/` directories exist | Do **not** re-onboard. They enter the new screen as existing rows with `in_holdings: true`. |
| All eight carry `stance: watch`, `valuation_tier: 3` ("broad screening universe", `actionability_cap: screening_only`) | `dashboard/data/tickers/VMC.json` | The tier is honest. Nothing here is capital-actionable and the plan should not pretend otherwise. |
| **`registry.json → watchlist` is an empty `{}`** | direct read | The lightweight watchlist path is unused repo-wide. The real "watchlist section" users see is the **Ideas → Screens** tab (NOL, Advantaged banks). That is where this belongs. |
| **Every one of these names has zero PDFs.** VMC's download log reads `IR PDF URLs found: 0 … Done VMC. SEC=0 IR=0/0` | `VMC/_download_log.txt`, `find VMC -name '*.pdf'` → 0 | The CIK is *correct* (`1396009` in both registry and `us_ticker_config.json`), so this is **not** the known missing-CIK failure. `SEC=0` with a valid CIK on a 2026-07-10 run is a separate, unlogged bug. Compare AAPL `SEC=51`, TPL `SEC=107`. |
| **XBRL fundamentals for these names do exist and are healthy** | `_system/reference/market-data/fundamentals/{VMC,MLM,CRH}.json` = 37KB / 41KB / 21KB; CRH files 10-Q under US GAAP | The numeric screener layer works **today**. The document layer does not. Ship them on separate tracks. |
| Shared fundamentals cache exposes only 9 metrics: `revenues, operating_income, net_income, eps_basic, cfo, cash, total_assets, stockholders_equity, long_term_debt` | direct read | No capex, D&A, PP&E, shares, goodwill. The new builder must hit `companyfacts` directly with its own tag list — exactly what `build_advantaged_banks_screener.py` already does. |
| ~~**`SUM` resolves to no CIK**, likely acquired Summit Materials~~ **WRONG — corrected 2026-09-07** | registry entry; Yahoo | `SUM` here is **Summit Royalties Ltd.**, a TSXV royalty company (OTC `SUMMF`) onboarded 2026-08-25, *not* Summit Materials. It has no SEC CIK because it is Canadian, which is correct and expected. Both listings trade (OTCQX $1.05, TSXV C$1.46). **Nothing to fix; do not archive it.** The error came from reading a ticker collision as an identity. |
| `AMRZ` **is** in the CIK map (`0002035989`) | direct read | Amrize — the North American Holcim spin — is a first-class VMC/MLM peer and is currently untracked. Highest-value addition in the universe. |
| A `timber_housing` FRED theme already exists with `housing_starts.csv` + `building_permits.csv`, driven by `fetch_theme_panel.py` (keyless `fredgraph.csv` endpoint) | `theme_panel_config.json`, `_system/reference/market-data/themes/` | The entire macro KPI layer is a **config-only** change. No new fetcher, no API key. |
| `filing_panels/*.csv` (`tpl_operating_panel.csv`, `azlcz_lease_panel.csv`) is the existing mechanism for filing-sourced operating metrics XBRL cannot reach | `theme_panel_config.json` → `source: filing_panel` | This is the home for tons / price-per-ton / cash-gross-profit-per-ton. |

**The one sentence that matters:** the KPIs that actually decide an aggregates thesis —
tons shipped, freight-adjusted price per ton, cash gross profit per ton, permitted
reserve life — are **not in XBRL and never will be**. They live in press-release
tables and 10-K Item 2. The repo has the right mechanism for them (`filing_panels`),
but it needs source documents, and right now these tickers have none.

---

## 1. Architecture — clone the NOL/banks stack, add nothing new

```text
seed CSV ──> builder script ──> dashboard/data/rock_aggregates_screener.json
                   ▲                        │
  registry.json (in_holdings/in_watchlist)  ▼
             build_dashboard_data.py ──> payload["rock_aggregates_screener"]
                                         ▼
             renderWatchlistTab() — 3rd screen alongside NOL + banks
                                         ▼
             + Watchlist / Onboard → openOnboardModal → marvin-onboard.yml

theme_panel_config.json ──> fetch_theme_panel.py ──> themes/*.csv + manifest.json
             holdings_themes.json ──> apply_context_overlay.py ──> valuation.json context_overlay

filing_panels/aggregates_unit_economics.csv ──> theme series (source: filing_panel)
```

Explicitly **not** doing: a new top-level tab, a new route, a new JS file, a new
sleeve, or auto-onboarding. Rows enter as screener rows; a human promotes.

---

## 2. The universe

Verified against the committed SEC ticker→CIK map (2026-08-13). `dir` = folder
already in repo. `reg` = registry status.

### Tier A — Aggregates and cement pure-plays → **these become screener rows**

| Ticker | Company | CIK | dir | reg | Why it is in |
|---|---|---|---|---|---|
| VMC | Vulcan Materials | 0001396009 | yes | hold | #1 US aggregates. The reference asset. |
| MLM | Martin Marietta | 0000916076 | yes | hold | #2 US aggregates. Best direct comp to VMC. |
| CRH | CRH plc | 0000849395 | yes | hold | Largest by revenue; aggregates + asphalt + products; now a US domestic filer (10-Q, US GAAP). |
| **AMRZ** | **Amrize** | 0002035989 | — | — | **North American Holcim spin. Pure NA building materials. Currently untracked — the biggest gap.** |
| EXP | Eagle Materials | 0000918646 | — | — | Cement + wallboard. Cleanest pure-play cement read. |
| KNF | Knife River | 0001955520 | — | — | 2023 MDU spin. Aggregates + contracting, upper-Midwest/Northwest. |
| ACA | Arcosa | 0001739445 | — | — | Aggregates plus infrastructure products; ongoing mix shift toward rock. |
| USLM | United States Lime & Minerals | 0000082020 | — | — | Lime/limestone micro-cap. Highest-margin, most under-followed name in the set. |
| GVA | Granite Construction | 0000861459 | — | — | Vertically integrated: owns aggregates *and* bids the highway work. Reads both sides. |
| ROAD | Construction Partners | 0001718227 | — | — | Southeast asphalt/roadbuilding roll-up. Purest IIJA + Sunbelt-migration expression. |
| CX | Cemex | 0001076378 | — | — | US-listed cement major; large US footprint. |

### Tier B — International cement, optional

`LOMA` (0001711375, Argentina), `CPAC` (0001221029, Peru), `JHX` (0001159152,
fiber cement, absorbed AZEK). Different currency and macro drivers. **Recommend
holding these out of v1** — they dilute the screen's comparability without adding
to the US housing/infra question being asked.

### Tier C–F — Adjacency map (context, **not** screener rows)

These explain the demand and cost sides. Most are already holdings; leave them where they are.

- **Equipment / rental (cost + activity read):** URI *(hold)*, HRI, ASTE, TEX, CAT *(hold)*, MTW
- **Building products / distribution (housing pull-through):** BLDR *(hold)*, MAS *(hold)*, OC, MHK, AWI, TREX, IBP, CSL, SSD, WMS, ROCK, SITE, POOL
- **Infrastructure contractors (public-works demand):** PWR *(hold)*, STRL, TTEK, AGX, MYRG, IESC, FIX *(hold)*, EME *(hold)*, J *(hold)*, ACM, FLR, DY, PRIM, MTZ
- **Homebuilders (residential demand signal):** DHI, LEN, PHM, NVR *(all hold)*, TOL, KBH, MTH, TMHC, MHO, GRBK, LGIH

### Verify-before-seeding — absent from the committed CIK map

`SUM`, `BECN`, `GMS`, `AZEK`, `HEES`, `NVEE`, `BLD`. Absence from a 2026-08-13 map
is a **flag, not proof**. Most are probably acquired (working hypotheses to check:
SUM→Quikrete, BECN→QXO, GMS→Home Depot/SRS, AZEK→James Hardie, HEES→Herc,
NVEE→Acuren). `BLD` (TopBuild) is the odd one out and may simply be a map gap.
Each needs a one-line status check before it is seeded or archived.

**Recommendation:** v1 seed = **Tier A only, 11 rows.** Same order of magnitude as
the banks screen (9 rows), keeps the screen legible, and every row is answering
the same question.

---

## 3. KPI catalogue

Seven layers, ordered by how much each one decides the thesis.

### Layer 1 — Aggregates unit economics · *decides the thesis*

The whole sector thesis is one claim: **price per ton compounds faster than cost
per ton, through the cycle, because you cannot permit a new quarry near a city.**
These are the numbers that test it.

| # | KPI | Notes |
|---|---|---|
| 1.1 | **Aggregates shipments (tons)** — quarter and TTM | The cycle variable. Volatile, weather-affected, mean-reverting. |
| 1.2 | **Freight-adjusted average selling price ($/ton)** | *Freight-adjusted* is non-negotiable — haulage is a pass-through and unadjusted ASP moves with diesel, not with pricing power. |
| 1.3 | **Aggregates cash gross profit per ton** | VMC's own north-star metric; MLM reports gross profit/ton. **If you track one number, this is it.** The bull case is that it compounds regardless of volume. |
| 1.4 | Freight-adjusted revenue | Strips pass-through haulage from the top line. |
| 1.5 | **Same-store (organic) volume vs. acquired volume** | Mandatory for roll-ups (CRH, ACA, ROAD, KNF). Acquired growth at a full multiple is not the same asset as organic pricing. |
| 1.6 | **Price/cost spread** = ASP growth − unit cash cost growth | The single cleanest expression of pricing power. Negative for more than ~2 quarters breaks the thesis. |
| 1.7 | Unit cash cost per ton, with the diesel/energy component isolated | Separates a cost shock from a cost problem. |
| 1.8 | Volume mix by end market — residential / private nonres / public infra | Public infra is the counter-cyclical leg; know how big it is before assuming it cushions a housing downturn. |
| 1.9 | Geographic mix — % revenue from top-10 Sunbelt MSAs | The real growth differentiator between VMC/MLM and the rest. |
| 1.10 | Segment volume & price for asphalt, ready-mix, cement | Asphalt is a *spread* business (mix price − liquid AC cost), not a volume business. Model it that way. |

### Layer 2 — Moat and reserves · *decides durability*

| # | KPI | Notes |
|---|---|---|
| 2.1 | **Permitted reserve life (years at current production)** — company-wide and for the top 5 markets | The moat, quantified. Company-average life hides a depleting quarry inside a critical metro. |
| 2.2 | Permitted + proven reserve tons; owned vs. leased split | Leased reserves carry renewal risk that owned reserves do not. |
| 2.3 | Active site count; sites within ~25 miles of a >1M-population metro | Proximity is the moat. Remote tonnage is a commodity. |
| 2.4 | Pending / contested zoning and permit renewals | The tail risk that is never in the model. |
| 2.5 | Average haul distance / distance-to-market | Rising haul distance = silent margin erosion. |
| 2.6 | Share of volume moved by rail, barge or water | Changes the radius and the competitive map (VMC's Gulf/Mexico quarries). |
| 2.7 | Estimated #1/#2 market-share position in served markets | Aggregates is priced locally; national share is close to meaningless. |

### Layer 3 — Financial quality · *fully automatable today*

| # | KPI | Source |
|---|---|---|
| 3.1 | Revenue, TTM and YoY | XBRL |
| 3.2 | Adjusted EBITDA and margin — consolidated **and** aggregates segment | XBRL + segment note |
| 3.3 | **Incremental (flow-through) margin** — Δ EBITDA ÷ Δ revenue | derived; guided by both VMC and MLM |
| 3.4 | Operating income margin | XBRL |
| 3.5 | **ROIC** and cash ROIC (NOPAT ÷ invested capital) | derived; the right test for a long-lived, heavily depreciated asset base |
| 3.6 | FCF = CFO − capex; FCF conversion (FCF ÷ EBITDA) | XBRL |
| 3.7 | **Capex split: maintenance vs. growth**, as % of revenue and per ton | maintenance capex disclosure; underspending flatters FCF for years before it bites |
| 3.8 | D&A, and D&A ÷ capex | XBRL |
| 3.9 | Working capital as % of revenue | XBRL |
| 3.10 | Net debt ÷ adj. EBITDA; interest coverage; maturity ladder | XBRL + debt note |
| 3.11 | **(Goodwill + intangibles) ÷ equity** | XBRL — the roll-up quality check |
| 3.12 | Share count trend; buyback yield; total capital return yield | XBRL |
| 3.13 | Annual acquisition spend and EV/EBITDA multiple paid, pre- and post-synergy | filings — are they buying rock cheaper than the market prices theirs? |

### Layer 4 — Demand and cost drivers · *macro, all FRED IDs validated 2026-09-07*

Every ID below was fetched live and returned data. Titles are FRED's own.

| Series | FRED ID | Reads |
|---|---|---|
| **PPI: Crushed and Broken Limestone Mining** | `PCU212312212312` | **Independent third-party read on crushed-stone pricing.** Cross-check against company-reported ASP — divergence is the tell. |
| PPI: Construction Sand and Gravel Mining | `PCU212321212321` | sand/gravel pricing |
| PPI: Construction Sand, Gravel and Crushed Stone | `WPU1321` | longer history for cycle work |
| PPI: Cement, Hydraulic | `WPU1322` | EXP / CX / AMRZ |
| PPI: Ready-Mix Concrete Manufacturing | `PCU327320327320` | downstream concrete |
| PPI: Asphalt Paving Mixture and Block Mfg | `PCU324121324121` | asphalt segment spread |
| Housing starts (SAAR) | `HOUST` | residential demand, ~25–30% of aggregates volume |
| Single-family starts | `HOUST1F` | SF uses far more rock per unit than MF |
| Building permits / SF permits | `PERMIT` / `PERMIT1` | 1–2 quarter lead on starts |
| Total construction spending | `TTLCONS` | |
| Private residential | `PRRESCONS` | |
| Private nonresidential | `PNRESCONS` | |
| Total nonresidential | `TLNRESCONS` | |
| **Total public** | `TLPBLCONS` | the counter-cyclical leg |
| **Highway and street** | `TLHWYCONS` | the single most important public series for this sector |
| Manufacturing construction | `TLMFGCONS` | fab / megaproject boom |
| Power construction | `TLPWRCONS` | data-center and grid build |
| 30-yr mortgage rate | `MORTGAGE30US` | the housing gate |
| 10-yr Treasury | `DGS10` | already in the repo |
| Construction employment | `USCONS` | |
| **Heavy and civil engineering employment** | `CES2023700001` | labor is what converts funded backlog into shipped tons |
| Diesel price | `GASDESW` | cost side, and the driver of unadjusted ASP noise |

**Non-FRED demand inputs — no automated source, treat as curated:**

- **IIJA obligations vs. outlays**, and the status of surface-transportation
  **reauthorization**. Authorized money becomes rock demand on a 2–4 year lag, so
  obligations lead outlays lead volume. *Reauthorization is the largest single
  sector-level swing factor over the plan horizon and deserves an explicit,
  dated tracking item rather than a footnote.*
- Federal Highway Trust Fund balance / solvency — drives what reauthorization can fund.
- State DOT lettings and backlog (TX, FL, GA, NC, TN carry the Sunbelt thesis).
- **Dodge Momentum Index** — nonres planning, ~12-month lead.
- **AIA Architecture Billings Index** — ~9–12-month lead, free monthly release.
- **USGS Mineral Industry Surveys** — crushed stone and sand/gravel production, free.
- PCA cement consumption outlook.

### Layer 5 — Valuation

| # | KPI | Notes |
|---|---|---|
| 5.1 | EV/EBITDA, TTM and forward, vs. own 10-yr range and vs. the Tier A set | the sector's primary multiple |
| 5.2 | **EV per annual ton shipped** | normalizes across very different balance sheets |
| 5.3 | **EV per ton of permitted reserves** | the asset floor. Private-market aggregates M&A is quoted in $/ton of reserves — this is the only multiple with a real transaction comp behind it. |
| 5.4 | FCF yield; earnings yield | |
| 5.5 | **P/E on mid-cycle normalized volume** | Never on trough or peak tons. Cyclical multiples on cyclical earnings is the classic error here. |
| 5.6 | Implied replacement cost per site vs. market value | New urban quarries are close to un-permittable; replacement cost should sit far above book. |

### Layer 6 — Risk and red flags

| # | Watch item |
|---|---|
| 6.1 | **Volume down while price is up** — pricing power, or share loss to a local competitor? These look identical in the consolidated numbers. Disaggregate by market before concluding. |
| 6.2 | Weather / rain-day commentary — real, recurring, quarterly noise. Do not let it become the trend narrative in either direction. |
| 6.3 | Backlog and bid margin (GVA, ROAD, STRL) — a growing backlog at falling bid margin is a warning, not growth. |
| 6.4 | Antitrust divestiture conditions on aggregates M&A (precedent: VMC/US Concrete). |
| 6.5 | Silica dust (OSHA), reclamation and mine-closure liabilities, environmental litigation. |
| 6.6 | Public-contract customer concentration and DOT payment cycles. |
| 6.7 | Cycle position — residential trough against a public-infra peak is a very different setup from both rising. State which one you think you are in. |
| 6.8 | Roll-up integration risk — goodwill/equity ratio plus serial-acquirer accounting (see 3.11, 3.13). |
| 6.9 | Rate sensitivity of the levered roll-ups vs. the low-leverage majors. |

### Layer 7 — Repo-native process KPIs (already computed; surface them on the screen)

`valuation_tier` · `proof_status` / `decision_eligibility` · `completeness %` ·
`pdf_count` / `sec_filings` · open `evidence_task_queue` items · transcript
coverage and gap · `insider_signal` · activist flags · `index_membership` ·
`power_zones`.

These are the honesty layer. A row showing `evidence_blocked` and `pdf_count: 0`
is telling the truth about what is known — which is currently the state of every
name in Tier A that the repo already holds.

---

## 4. Feasibility matrix — what can actually ship

| Layer | Source | Automatable now? | Effort |
|---|---|---|---|
| L3 Financial quality | SEC `companyfacts` direct | **Yes** — identical to the banks builder | ~1 day |
| L4 Macro (FRED rows) | `fredgraph.csv`, keyless | **Yes** — config-only change to an existing fetcher | ~2 hours |
| L5 Valuation (5.1, 5.4, 5.5) | XBRL + Yahoo price | **Yes** | included in L3 |
| L7 Process | already in `dashboard/data/tickers/*.json` | **Yes** — read-through | ~2 hours |
| L5 (5.2, 5.3, 5.6) | needs tons + reserves | No — depends on L1/L2 | after P3/P4 |
| **L1 Unit economics** | **press-release tables** | **No** — not in XBRL | needs P0.2 + P3 |
| **L2 Reserves / moat** | **10-K Item 2 Properties** | **No** — not in XBRL | needs P0.2 + P4 |
| L4 non-FRED (IIJA, DOT, ABI, Dodge) | web / PDF releases | No | curated, recurring |

Read across the two bold rows: **the highest-value KPIs are blocked on the
document pipeline, not on the screener.** That is why P0.2 exists and why it is
ranked above the pretty parts.

---

## 5. Implementation phases

### P0 — Preflight and repair *(blocking for research, not for the screener)*

- **P0.1 — CIK + IR roots for the seed universe.** Resolve every Tier A ticker in
  **both** `registry.json` and `_system/scripts/us_ticker_config.json`. A `null`
  in `us_ticker_config.json` beats a correct registry entry, so both must be
  right or the download silently returns SEC=0. Populate `ir_roots` (currently
  `[]` for VMC, MLM, CRH), which is why the IR leg found zero URLs.
- **P0.2 — Diagnose `SEC=0` with a valid CIK.** VMC has CIK `1396009` in both
  places and still logged `SEC=0` on 2026-07-10 while AAPL logged 51 and TPL 107
  in the same period. Reproduce against one ticker, find the divergence, fix.
  **This one fix unblocks Layers 1, 2 and half of 5 for the whole sector.** Rank
  it first among the repair items.
- **P0.3 — Resolve SUM.** Confirm the acquisition, then either archive the folder
  or mark the registry entry `status: acquired` with a date. Do not leave a
  no-CIK shell sitting in `holdings`.
- **P0.4 — Status-check the verify list** (BECN, GMS, AZEK, HEES, NVEE, BLD)
  before any of them is seeded.

### P1 — Macro theme panel `aggregates_infrastructure` *(ship first — cheapest, highest ratio)*

- Add the theme to `_system/scripts/theme_panel_config.json` with the Layer 4
  FRED series. Give the housing series `staleness_max_days: 60` and the PPI
  series `90` (monthly, published on a lag).
- Add a `yahoo_daily` fallback for the daily-frequency series only; the monthly
  FRED series have no equivalent and should be allowed to go stale visibly rather
  than be faked.
- Tag Tier A plus the adjacency names in `_system/portfolio/holdings_themes.json`
  with an explicit `rationale`. `apply_context_overlay.py` then injects
  `context_overlay` into each `valuation.json` — **context only, never a base-IRR
  input**, per the file's own contract.
- Run `python _system/scripts/fetch_theme_panel.py --theme aggregates_infrastructure`.

**No UI work. No new script. Ships in an afternoon.**

### P2 — Screener `rock_aggregates_screener` *(clone the banks stack)*

1. **Seed** — `_system/reference/market-data/screens/rock_aggregates_seed.csv`
   ```text
   ticker,company,market,cap_tier,rock_type,notes
   ```
   `rock_type` vocabulary: `aggregates_pure` | `aggregates_vertical` |
   `cement` | `lime` | `asphalt_rollup`.
2. **Builder** — `_system/scripts/build_rock_aggregates_screener.py`, starting as a
   copy of `build_advantaged_banks_screener.py` (keep `load_registry_sets`,
   `load_cik_map`, `fetch_json`, `latest_usd_fact`, `latest_shares_fact`,
   `fetch_yahoo_price`, cap buckets, formatters, `--write`). Swap the metric layer
   for Layer 3 tags: `Revenues` / `RevenueFromContractWithCustomerExcludingAssessedTax`,
   `OperatingIncomeLoss`, `NetIncomeLoss`, `DepreciationDepletionAndAmortization`,
   `PaymentsToAcquirePropertyPlantAndEquipment`, `NetCashProvidedByUsedInOperatingActivities`,
   `PropertyPlantAndEquipmentNet`, `Goodwill`, `IntangibleAssetsNetExcludingGoodwill`,
   `LongTermDebtNoncurrent`, `StockholdersEquity`, `Assets`,
   `CommonStockSharesOutstanding` / `dei:EntityCommonStockSharesOutstanding`.
   Derive: EBITDA proxy (`OperatingIncomeLoss + DD&A`), EBITDA margin, FCF,
   FCF conversion, capex % of revenue, net debt/EBITDA, ROIC, goodwill/equity,
   EV/EBITDA, FCF yield.
   Flags: `is_pure_rock` (`rock_type` in `aggregates_pure`/`aggregates_vertical`),
   `screen_status` = `ok` | `pending_sec`.
   Envelope: `built_at`, `criteria`, `seed_path`, `row_count`, `pure_rock_count`,
   `rows`. Degrade to seed-only rows with `pending_sec` on any SEC/Yahoo failure —
   the table must still render.
3. **Payload hook** — `build_dashboard_data.py`: add `build_rock_aggregates_screener()`
   beside the banks call, subprocess `--write`, 300s timeout, then merge into
   `payload["rock_aggregates_screener"]` and `payload["summary"]["rock_aggregates_count"]`.
4. **UI** — `dashboard/index.html`:
   - `WATCHLIST_VIEWS` → add `'rock'`; extend the `#/ideas/…` and `#/watchlist/…`
     route regexes.
   - `renderWatchlistSubNav()` → third button, `Aggregates · N`.
   - `renderWatchlistRockBody()` modelled on `renderWatchlistBanksBody()`.
     Columns: Ticker · Company · Type · Rev TTM · EBITDA margin · FCF conv ·
     Capex % rev · Net debt/EBITDA · ROIC · EV/EBITDA · Reserve life · Filing as-of · Action.
     Leave **Reserve life** as a visible `—` until P4 fills it, rather than
     hiding the gap.
   - Action cell: `holding` label when `in_holdings`, else `+ Watchlist` on
     `data-rock-watch` → `openOnboardModal({ watchlistOnly: true })`.
   - Empty state naming the exact build command.
   - Optional `Show pure rock only` checkbox → `localStorage.rockPureOnly`.
5. **Validator** — `validate_dashboard_data.py`: mirror the `nol_screener` check —
   `rows` non-empty, every row has `ticker`, `row_count` matches, warn (never
   fail) when `built_at` is over 7 days old. **Warn, not error** — a validator
   ERROR skips the deploy step without saying so.
6. **Tests** — `_system/scripts/test_rock_aggregates_screener.py`, stdlib
   `unittest`, following `test_advantaged_banks_screener.py`.

### P3 — Unit-economics filing panel *(the crown jewels; needs P0.2)*

`_system/reference/market-data/themes/filing_panels/aggregates_unit_economics.csv`

```text
as_of,ticker,period,aggregates_tons_mm,freight_adj_asp_per_ton,cash_gross_profit_per_ton,organic_volume_pct,source_path
```

Seed manually from the latest quarter for VMC, MLM, CRH, AMRZ, EXP — five rows
proves the shape end to end. Automate extraction only once P0.2 lands and the
press releases are actually on disk. Surface as theme series with
`source: filing_panel`, exactly like `tpl_operating_panel.csv`.

### P4 — Reserves and properties panel *(needs P0.2)*

`filing_panels/aggregates_reserves.csv`

```text
as_of,ticker,fiscal_year,permitted_reserve_tons_mm,reserve_life_years,active_sites,owned_pct,source_path
```

Annual cadence, sourced from 10-K Item 2. Feeds KPIs 2.1–2.3 and unlocks
valuation 5.2/5.3 — the only multiples in this sector with real transaction comps.

### P5 — Promotion

Once P2 and P3 are live, pick the **two or three** rows that clear on
price/cost spread and EV per ton, and run the existing deep-dive path. Nothing is
capital-actionable until `valuation_tier` and `decision_eligibility` say so on
their own terms — this plan does not shortcut that.

---

## 6. Verification

- `python _system/scripts/build_rock_aggregates_screener.py --write` → non-empty
  `rows`, `pure_rock_count` ≥ 1, no `pending_sec` for names with a known CIK.
- `python _system/scripts/fetch_theme_panel.py --theme aggregates_infrastructure --offline`
  → manifest recomputes from cached CSVs with no network.
- `python _system/scripts/validate_dashboard_data.py` → no new ERROR.
- `python _system/scripts/test_rock_aggregates_screener.py`.
- Rebuild the dashboard locally to confirm the screen renders, then **revert
  `dashboard/data/`** — a local rebuild drags in local-only state.
- Confirm `SUM` no longer appears as a live holding.

**Nothing in this plan touches IB Gateway.** No broker connection, no client ID,
no market-data line. It is FRED + SEC + Yahoo chart over HTTPS, which is the
correct and only shape for research work in this repo.

---

## 7. Open decisions for the human

1. **Screen name.** `rock_aggregates` (proposed) vs. `aggregates` vs.
   `construction_materials`. Affects file names, the payload key and the route.
2. **Universe breadth for v1.** Recommended: Tier A only, 11 rows. Alternative:
   add Tier B international cement (14 rows), at the cost of comparability.
3. **Order of work.** Recommended: **P1 (macro, ~2 hours) → P0.2 (the `SEC=0`
   bug) → P2 (screener)**. P1 is nearly free and immediately useful; P0.2 is what
   actually unblocks the KPIs that matter. Deferring P0.2 means the screen ships
   looking complete while every thesis-deciding column stays empty.
4. **AMRZ.** Onboard now as a full ticker, or let it enter as a screener row and
   be promoted by hand like everything else? (Consistency argues for the latter.)
5. **Adjacency names.** Do Tiers C–F get theme tags in `holdings_themes.json`
   (context overlay only), or stay untouched? Recommended: tag them — it is a
   config line each and it is how the demand chain becomes legible.
6. **IIJA reauthorization.** This is the largest sector-level swing factor over
   the plan horizon and has no automated source. Should it become a dated,
   explicitly tracked research item rather than a KPI-table footnote?


---

## 8. What shipped, and what this plan got wrong

Implemented 2026-09-07 in this repo. Every check below was run; nothing here is projected.

### Shipped

| Phase | Artifact |
|---|---|
| **P1** | `aggregates_infrastructure` theme in `theme_panel_config.json` — 22 FRED series, all fetched live; 23 tickers tagged in `holdings_themes.json`; `context_overlay` applied to the 15 that have a `valuation.json` |
| **P0** | Tier A filings restored: VMC `SEC=0 → 55`, MLM `→ 56`, CRH `→ 49` |
| **P2** | `rock_aggregates_seed.csv` (11 rows) · `build_rock_aggregates_screener.py` · payload hook in `build_dashboard_data.py` · `rock_aggregates_screener` validator block · third screen in the Ideas tab (`#/ideas/rock`) · 23 unit tests, green |
| **P3** | `filing_panels/aggregates_unit_economics.csv` + `README.md`, wired as four theme series |

### Three things this plan had wrong

**1. P0.2 was not a live bug — the artifacts were stale.** The `SEC=0`-with-a-valid-CIK
failure was real, but it was fixed on 2026-08-09 by commit `9c97a372354`
("Stop the silent SEC-download skip"), which added the `sec_map_cik()` fallback
*and* the missing `else: log("SEC SKIPPED: no CIK")` branch. VMC's download ran
2026-07-10, a month earlier, so it silently skipped the SEC leg and logged nothing
— the log jumps from "Starting" to "Done ... SEC=0" in three milliseconds. Re-running
the downloader was the whole fix. **257 of 810 tickers are still in that pre-fix
state** and need the same treatment; that is filed as its own task, not folded in here.

**2. P0.3 was based on a misread.** See the corrected row in §0. `SUM` is Summit
Royalties on the TSXV, not Summit Materials. Real Summit Materials is simply absent
from this repo and stays out of the seed.

**3. The screener's first output was confidently wrong in two ways**, both caught
before anything reached the UI, both now regression-tested:

- **A 10-K carries its own Q4 alongside the full year**, tagged `form="10-K"`,
  `fp="FY"`. Keying "is this annual?" off the form picked whichever the JSON
  happened to list last — for MLM that was a $1.53B quarter instead of the $6.15B
  year, which surfaced as a **135% EBITDA margin** that looked like a real number.
  Only the fact's own `start`/`end` duration distinguishes them.
- **Scanning revenue tags in order and stopping at the first hit** pinned Knife
  River to FY2023: it retired `RevenueFromContractWithCustomerExcludingAssessedTax`
  after FY2023 and moved to `Revenues`. The row reported a confident figure two
  years stale. Every tag must be scanned and the latest period taken.

Both are the house failure mode — a number that is wrong in a way that looks right.
The validator now warns when any EBITDA margin falls outside ±100%.

### Deliberate design calls

- **Flow metrics are full-year only, never a bare "latest fact".** Aggregates volumes
  are seasonal; mixing a quarter for one company with a year for another produces a
  table that looks comparable and is not. Balance-sheet items still take the latest
  quarter.
- **Holdings are not demoted to the bottom of this screen** (the banks screen does
  demote them). VMC, MLM and CRH are the benchmark the other rows are read against.
- **CX renders as a labelled blank, not a silent one.** Cemex files 20-F under
  `ifrs-full` with no `us-gaap` namespace at all, so the row carries
  `IFRS filer (namespaces: dei, ffd, ifrs-full, invest); US-GAAP tag map does not apply`.
- **The Reserve life column ships visibly empty**, with a tooltip pointing at 10-K
  Item 2, rather than being hidden until P4.
- **`read_filing_panel()` does not filter by ticker.** Two companies sharing a metric
  column would interleave into one series that looks like a trend. Every company gets
  its own column; this is written down in the panel README because it is invisible
  from the CSV itself.
- **Staleness gates were recalibrated** from 60 to 85/100 days. Census construction
  spending stamps an observation at month start and publishes up to two months later,
  so a 60-day gate marked *current* data STALE — and a gate that fires on healthy data
  is one everyone learns to ignore.

### What the panel says today

VMC FY2025, from the 10-K: shipments **226.8 Mt**, freight-adjusted price
**$21.98/ton** (+4.3%), **cash gross profit $11.33/ton** — up from $9.46 in FY2023.
Against that, housing starts are **-13.5% YoY** and private residential construction
**-7.3%**, while highway and street spending is **+4.5%** and the crushed-limestone
PPI **+6.0%**. That is the sector thesis in miniature: price compounding through a
residential downturn, cushioned by public infrastructure. It is also only two data
points on the metric that matters, which is the honest state of the evidence.

### Still open

- **L1 for MLM and CRH.** MLM publishes average selling price *by division* in the
  10-K and consolidated per-ton figures only in its earnings release; CRH gives
  volumes but no unit profitability. Filling their columns means parsing the releases.
- **P4 reserves panel** — not started. `reserve_life_years` is null on every row.
- **The 257 stale tickers** — filed as a separate task.
- **IIJA reauthorization** — still no automated source, still the largest
  sector-level swing factor on this horizon.
