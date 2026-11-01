# Commodity price models — gold, WTI/Brent, silver, copper

**Date:** 2026-10-28
**Status:** implemented as dated, context-only scenario models; data readiness is disclosed per panel
**Verdict:** Build four models on one scaffold. Use three price mechanisms. Copy the natural-gas model's discipline. Do not copy the Bitcoin power law onto metals.

These models are context for royalty, miner, and energy names (FNV, WPM, RGLD, NEM, GOLD, FCX, and the oil-linked themes). They stay out of Lawrence base IRR, the same rule as `energy_model.json` and `hk_snowball_model.json` (`in_base_irr: false`).

## Implementation and improvements — 2026-10-28

All four engines now publish through `build_commodity_models.py`, in oil → copper → gold → silver dependency order. `validate_commodity_models.py` gates publication. The dashboard puts them together under **Insights → Ticker insights → Portfolio context**, and attaches only explicitly relevant models to each company's **Models** view. Their scenarios never write company valuations, target prices, or base IRRs.

The implementation makes several corrections to the initial specification below:

- **Preserve the source's frequency and geography.** Oil uses the reviewed quarterly STEO tables; copper and silver use annual balances; gold uses quarterly reported observations and annual scenarios. We do not manufacture monthly observations by interpolating annual totals. World oil balances cannot be poured directly into OECD inventories. The model reports both separately and labels the assumed OECD share of scenario shocks.
- **Separate prices from identities.** Oil retains EIA's exact published price and OECD inventory anchors through 2027, then switches to labeled assumptions. Copper prices are assumed paths beside the two balance channels. Gold's monetary sensitivities are explicitly uncalibrated, and silver reads a named gold path divided by an assumed ratio. No accounting identity is advertised as an independently estimated price equation.
- **Do not confuse missing measurements with zero.** A concentrate balance requires dated concentrate supply and smelter intake; total mine output includes SX-EW and cannot substitute. The optional input contract calculates that balance when supplied. Aggregate exchange stocks divided by global use are shown separately from unavailable regional deliverable cover. Unreported Chinese absorption can reverse the refined surplus and is visible as its own scenario.
- **Audit the actual inputs.** Each source has a publication date, freshness window, URL, reviewed-input hash, and publisher-byte hash when captured. A hash of our transcription is never presented as a publisher-file hash. Changed source files trigger review; the collector does not quietly stamp an old forecast with a new publication date.
- **Fix the gold unit error without rewriting history.** `gold_futures_usd_oz` uses GC futures in USD/troy ounce under a new series identity. It is labeled futures, not spot. The old GLD-share series is withheld from the macro view; actual GLD security quotes are untouched. The historical real-yield diagnostic requires actual bullion, real-yield and dollar observations, fits only 2010–2021, and shows later residuals without claiming they identify a causal central-bank premium.
- **Make stock conservation explicit.** Recycling does not add to gold's above-ground stock. Silver subtracts ETP absorption exactly once. Its by-product bridge does not add a second supply shock. Oil stops infeasible negative-stock paths. Published forecasts beyond the source horizon fail validation.

### Current evidence limits

The release includes complete working scenario engines, not a claim that every desirable public series is available. Original-file capture succeeded for the reviewed reference publications. The initial FRED history refresh failed, so the historical gold diagnostic stays unavailable until aligned observations are obtained. It accepts prior valid cached observations on later fetch failures.

Cushing stocks, a five-year oil inventory normal, physical storage capacity and spare-capacity measurements remain unavailable; the current oil comparison is explicitly the same quarter of 2025. Copper's monthly inventory figures are reviewed proposal transcriptions, distinct from its captured ICSG forecast PDF; regional stock levels, concentrate splits and a verified treatment-charge series remain missing. Gold has no consistent attached AISC panel. Silver lacks identifiable starting inventories, observed ratio history and lease-rate history, so it reports cumulative inventory changes rather than invented exhaustion dates. The three PV decline rates and gold/silver ratios are analyst assumptions, not purported transcriptions of publisher scenario paths. Diesel/power cost transmission remains a non-additive context bridge until issuer cost exposures are measured.

These limits are displayed with the relevant evidence and falsifiers. They do not disappear behind a successful build. A refresh failure preserves the last validated file and marks the failure; a source's age continues to advance independently of rebuild time.

### Operation and checks

`refresh_commodity_models.py --optional` is part of the existing weekly world-model profile. It performs bounded public HTTPS collection, rebuilds, validates and atomically replaces the context file. Reference-vintage updates remain reviewed changes to `commodity_configs/*.json`, following each publisher's cadence. `build_compounder_roster.py` publishes the same extensible 44-company configuration used by the long-term research process.

Offline checks cover accounting identities, official oil anchors, delayed shale response, separate copper balances and unit conversion, gold stock conservation and historical fit isolation, silver's gold dependency and ETP accounting, source freshness, forecast horizons, and exclusion from base IRR. Browser checks cover desktop/mobile layout, all 44 compounders, ticker-only QDEL models, the consolidated flow route, model scenario selection, archive access, and buyback leaderboard ordering.

The remaining sections retain the research rationale and the original detailed specification. Where they call for an unavailable measurement, the limits above describe the implemented behavior rather than an inferred value.

---

## 1. What we already have

| Model | Engine | What sets the path | What it refuses to do |
|---|---|---|---|
| Natural gas | `build_energy_model.py`, `energy_balance.py`, `energy_model_config.json` | Monthly US mass balance. EIA STEO is the published spine through 2027. After that, named scenarios. Storage conserves mass inside capacity and flow limits. | It does not solve an equilibrium price. Gas price paths are assumptions. |
| Bitcoin | `build_hk_snowball_model.py` | Demand power law, price roughly proportional to time-since-2011 raised to a power near 6, against a production-cost floor (hashrate, joules per terahash, power price, halvings) and a premium band. | It does not claim a cost floor is a price floor. Context only. |

The gas model is the template for **how a model is allowed to speak**: hashed sources, staleness, a conservation identity, a published forecast where one exists, analyst extensions labeled as such, scenarios, historical validation, and falsifiers.

The Bitcoin model is the template for **a monetary asset whose flow supply is small next to the stock people want to hold**. That analogy fits gold only in spirit. The functional form does not transfer. Bitcoin's power law is an adoption curve for a new network. Gold's above-ground stock has existed for millennia.

A third idea sits in the literature and in EIA's own oil handbook, and we should use it where the commodity is consumed: **price is a convex function of inventories**. Holbrook Working's theory of storage (1949) and the competitive-storage models of Williams and Wright, and of Deaton and Laroque (1992), say the same practical thing the gas model already implements. Most of the time stocks clear the market and price sits near the cost of new supply. When stocks hit a wall, price spikes. We keep that as storage bounds and scenario fans. We do not build a latent-factor futures model (Schwartz 1997 is for option pricing, not for a balance a person can falsify).

---

## 2. One taxonomy, four markets

Annual flow versus the stock that already exists decides the engine.

| Commodity | Stock vs annual new supply | Price is set by | Engine |
|---|---|---|---|
| Crude oil | Commercial stocks are weeks of use | Inventory deviation from normal, spare capacity, and the cost of the marginal barrel | Flow + storage. Sibling of the gas model. |
| Copper | Visible exchange stocks are days to weeks of use, and they are not one pool | Two balances at once: concentrate tightness and refined surplus, plus a slow mine pipeline | Two-balance industrial. |
| Gold | About 222,600 tonnes above ground at end-Q2 2026. Mine supply was 3,672 tonnes in 2025, about 1.6% of the stock. World Gold Council. | Who wants to hold the existing stock: real rates, the dollar, and official-sector buying. Mine supply and scrap are dampers. | Monetary stock. |
| Silver | Hybrid. Primary mines were 26% of 2025 mine supply. By-product mines supplied 625.5 Moz of 846.6 Moz. Metals Focus, World Silver Survey 2026. | Gold's monetary path, plus a physical deficit and identifiable-stock tightness. Primary-mine cost is slack. | Hybrid. Built after gold. |

Kilian's 2009 result (not all oil-price shocks are alike: supply, aggregate demand, precautionary demand) is the labeling scheme for oil and copper scenarios. It is a way to name shocks after the fact. It is not the forecasting engine.

Hotelling's rule (the resource price rises at the rate of interest) fails in the data for oil. Leave it out.

Stock-to-flow, and any power law fitted to the gold or silver price, fails for a different reason. The stock is about sixty years of mine supply. Dividing stock by flow does not identify the price. The 2022-2026 gold market is the demonstration: the real-yield model and the flow model both miss a buyer who wants the stock (central banks).

---

## 3. Shared scaffold

Copy the gas contract, not a new framework file.

```text
_system/scripts/commodity_common.py          hash, staleness, atomic write, identity checks
_system/scripts/commodity_configs/
  crude.json
  copper.json
  gold.json
  silver.json
_system/scripts/fetch_commodity_panel.py     public sources only, no API key required where possible
_system/scripts/build_commodity_models.py
_system/scripts/validate_commodity_models.py
_system/scripts/tests/test_commodity_models.py
dashboard/data/commodity_models.json
dashboard/commodity-model-viz.js             sibling of energy-model-viz.js
```

Each commodity block in the JSON carries:

- `in_base_irr: false`
- `status: research_scenarios`
- `history` with `status: observed`
- `scenarios[]` whose rows are `published_forecast` or `analyst_extension`
- `price_path` with an explicit `price_status`: `published_forecast`, `reduced_form`, or `analyst_assumption`
- `cost_floor` (may be non-binding; say so)
- `validation` against the last published balance
- `falsification[]` with a metric, a threshold, and a source URL
- `limitations[]`
- source hash, publication date, and age

Hard rules, same as gas:

- A price path is never written into `valuation.json` or a Lawrence base case.
- Post-horizon numbers are scenarios. The horizon matches the gas model: published source through its last forecast year, analyst extension through 2032.
- If a series is missing, the model runs with that input marked absent. It does not invent a cost-curve percentile from a paid dataset (CRU, WoodMac, S&P Global).
- Paid survey numbers may be typed in as a reviewed reference, the way STEO quarterly rates are typed into `energy_model_config.json`, with URL, publication date, and sha256 of the file we read.

Dashboard: a fourth card on the world-model strip beside the gas panel and the Bitcoin snowball panel. Banner text: context only, not a price target, not in base IRR.

### Data bug to fix while doing gold

`themes/manifest.json` series `gold_spot_usd` is Yahoo `GLD`, the ETF share price. On 2026-10-23 that printed about $366. The LBMA Gold Price PM averaged $4,506/oz in Q2 2026 (World Gold Council, Gold Demand Trends Q2 2026). The gold model uses the LBMA fix or `GC=F` in dollars per ounce. The theme series should be repointed in the same change, still as context, still out of base IRR.

---

## 4. Crude oil (WTI and Brent) — build first

Closest sibling of the gas model, and EIA has already published the price method.

### Current public spine (October 2026 STEO, inputs finalized 2026-10-01)

From [STEO Table 3a](https://www.eia.gov/outlooks/steo/tables/pdf/3atab.pdf) and [Table 2](https://www.eia.gov/outlooks/steo/tables/pdf/2tab.pdf), and the October STEO narrative:

- 2026 world liquids production 101.1 million b/d, consumption 102.4, so the year draws stocks. OPEC total liquids average 23.9 million b/d in 2026 versus 29.3 in 2025. Second-quarter 2026 OPEC total was 20.4. That is a disruption regime, not a normal year. The October narrative cites attacks on the Saudi East-West pipeline and distillate stocks about 32% below the five-year average on the US East Coast in September.
- Brent spot average: $96.32/b in 2026, $83.74/b in 2027. Fourth-quarter 2026 Brent $104.69. WTI: $88.21 then $79.74. Fourth-quarter 2026 WTI $97.00.
- Our theme print of WTI near $103 on 2026-10-23 (`yahoo:CL=F`) sits with that fourth-quarter path. It is a spot, not a contradiction of the annual average.

### Price method (use EIA's, do not invent a second one)

EIA's handbook, [STEO Crude Oil Price Forecasts](https://www.eia.gov/analysis/handbook/pdf/STEO_Crude_Oil_Price.pdf):

1. Forecast Brent first. WTI equals Brent minus a forecast spread.
2. Brent inputs are a pool of five real-time models (Baumeister-style simple average), a regression of the monthly Brent change on US inventory change, OECD inventories versus the prior four-year seasonal norm, and global GDP, plus analyst judgment.
3. US weekly stocks are the timely proxy because the US is about a fifth of world use and the weekly report is fast.

Our model does three jobs EIA's table does not do for this repo:

1. **Store the balance** the way gas does: OPEC, non-OPEC crude, other liquids, OECD and non-OECD consumption (China split out), and implied stock change. Seasonal factors from history. Identity: production minus consumption minus stock change equals a statistical difference that we show, not hide.
2. **Extend past 2027** with named scenarios, through 2032.
3. **Show the cost floor separately from the price.** Dallas Fed Energy Survey, Q1 2026: firms needed $66/b on average to drill a new well ($67 in the Permian, $59 for large firms) and the operating cost of existing wells is far below that. During that survey, WTI averaged $94.65 while respondents expected $74 at year-end 2026. The survey is a supply-response band. It is a poor point forecast in a disruption, which is the point of keeping it in its own row.

### Scenarios

| Id | What it is | Price status |
|---|---|---|
| `steo` | Typed quarterly STEO through 2027, including the Brent and WTI paths | `published_forecast` |
| `disruption_persists` | Middle East flows stay constrained, OPEC liquids stay near the 2026 rate, distillate tightness remains. Post-2027 price is an assumption above the STEO 2027 average. | extension is `analyst_assumption` |
| `flows_normalize` | OPEC liquids return toward the 2025 rate (~29 million b/d) and OECD stocks rebuild to the seasonal band. Price path glides toward the Dallas Fed new-well band plus a stated transport and quality spread. | `analyst_assumption` |
| `shale_response` | WTI stays above the Dallas Fed new-well breakeven for four quarters, so US tight oil growth is raised. Tests the 6 to 18 month shale lag. | `analyst_assumption` |

WTI minus Brent is its own small logistics block: Cushing stocks and US export capacity. It does not feed back into the world balance. Same pattern as the gas model's LNG train cross-check, which is `included_in_national_balance: false`.

### Falsifiers

- OPEC+ liquids print above the disruption path for two consecutive quarters.
- OECD commercial stocks, seasonally adjusted, back inside the prior four-year band for six months.
- Dallas Fed new-well breakeven moves by more than $10/b (cost inflation), so the floor row is stale.
- East Coast distillate stocks back within 10% of the five-year average, removing the diesel-driven crude bid the October STEO describes.

### Sources

EIA STEO Tables 2, 3a, 3c, 4a (same PDF habit as gas). EIA Weekly Petroleum Status Report. FRED `DCOILWTICO`, `DCOILBRENTEU`. Dallas Fed breakeven page. OPEC monthly report PDF as a cross-check on spare capacity, typed in when we read it, not scraped into the price. Yahoo `CL=F` and `BZ=F` for a spot stamp only.

---

## 5. Copper — build second

The live market is a trap for a one-balance model.

ICSG, Lisbon, 13-14 October 2026, forecast dated 14 October 2026:

- Mine production +1.3% in 2026 (cut from +1.6% in April) and +3.1% in 2027. Grasberg and Kamoa-Kakula still constrained after 2025 incidents. Chile down in 2026.
- Refined production +0.4% in 2026 because concentrate is scarce, then +3.4% in 2027 as smelters in Indonesia, India, and the EU ramp. Primary refined about +3% in 2027, secondary (scrap) about +4.7%.
- Apparent refined usage +1.5% in 2026 and +2.5% in 2027. China is 59% of world refined use, and China's 2026 apparent use is +2.5%.
- Refined balance: surplus about 104,000 tonnes in 2026 and 368,000 tonnes in 2027.
- January-July 2026 apparent surplus was 32,000 tonnes. Adjusted for an estimated 37,000 tonne drop in Chinese bonded stocks, the balance was a 5,000 tonne deficit. ICSG states that unreported Chinese stocks can flip the sign.
- Exchange stocks (LME + COMEX + SHFE) were 997,600 tonnes at end-August 2026, the highest since June 2003, up 253,000 tonnes year to date. COMEX was up 238,000 tonnes. SHFE was down 73,000 tonnes. This is a location build, largely US, not a single world vat.
- LME cash averaged $14,353/t in August 2026. Year-to-date average about $13,395/t, 35% above the 2025 average.
- Treatment charges for 2026 concentrate contracts settled at zero (Antofagasta and a Chinese smelter, December 2025), and spot charges have been reported negative. The smelter pays the miner. Concentrate is scarce while refined metal, on ICSG's unadjusted definition, is in surplus.

A regression of price on the refined surplus would learn the wrong decade.

### Two balances

**Concentrate balance.** Mine production, minus ICSG's own disruption allowance, versus smelter intake. The observable price of tightness is the TC/RC, in dollars per tonne of concentrate and cents per pound of payable copper. We do not subscribe to Fastmarkets. The series is a reviewed headline: date, number, URL, status `headline_not_a_series`, refreshed when ICSG or a company filing quotes it. Absence of a weekly TC tape is acceptable. Pretending we have one is not.

**Refined balance.** Primary electrolytic + SX-EW + scrap, minus apparent usage, equals the ICSG surplus. A second line subtracts the bonded-stock adjustment when ICSG publishes one. Exchange stocks are stored as three locations. Days of cover use refined usage as the denominator and are computed per location as well as in total. Total days of cover is a diagnostic. It is not the scarcity signal.

### Price

There is no honest reduced form that turns a 104,000 tonne surplus into $14,353/t. The model therefore:

- Stores the ICSG balance as `published_forecast` through 2027.
- Stores the LME cash price as an observation.
- Offers scenario price paths only as `analyst_assumption`, each tied to which balance the user thinks is clearing:
  - `refined_surplus_dominates`: post-2027 price eases while the surplus widens and COMEX stocks stay elevated.
  - `concentrate_dominates`: TC stays near zero, mine disruptions persist, and the cathode price stays high even if the refined sheet shows a surplus. This is the 2026 fact pattern.
  - `china_unreported`: bonded and SRB stocks swing by a few hundred thousand tonnes and the apparent surplus is an accounting residue. Price path is a sensitivity, not a forecast.
- Long-cycle row, 2028-2032: mine projects take most of a decade, so the post-2027 sheet is an analyst extension of ICSG growth rates plus a disruption allowance, the same shape as gas after 2027. An "incentive price" for new mine FIDs is included only when we can cite project disclosures or a reviewed public range. Otherwise the cell is empty and marked open. We do not type a round number from memory.

Scrap is the damper. ICSG already has secondary growth faster than primary in 2027 (+4.7% vs about +3%). Scenarios that hold the price up must also raise scrap supply, or explain why they do not (scrap collection already maxed, or export bans).

### Falsifiers

- Spot TC back above a stated positive threshold for a full quarter (concentrate scarcity over).
- COMEX stocks give back the 2026 build, so the "US vat" story is over.
- ICSG bonded adjustment and the apparent balance agree in sign for two consecutive bi-annual forecasts.
- Grasberg and Kamoa-Kakula guidance return to pre-incident rates.

### Sources

ICSG monthly press release and the April/October forecast PDFs. LME, COMEX, and SHFE stock reports. USGS Mineral Commodity Summaries for the annual mine check. Cochilco for Chile. Yahoo `HG=F` as a spot stamp, with the unit written down ($/lb on COMEX versus $/t on LME; the model stores both and converts explicitly).

---

## 6. Gold — build third

Flow supply does not set the price. At end-Q2 2026 the World Gold Council puts above-ground stocks at 222,600 tonnes (about $29 trillion at the period-end LBMA price): jewellery ~99,700 t, central banks ~39,000 t, bars and coins ~47,800 t, ETFs ~4,000 t, OTC ~10,000 t, other ~22,100 t. Below ground: reserves ~61,000 t, resources ~114,400 t. Mine production was 3,671.6 tonnes in 2025 and total mine supply 3,598 tonnes after producer hedging. Recycled gold was 1,404 tonnes. Annual new metal is a rounding error next to the stock.

2025 demand, including OTC, exceeded 5,000 tonnes. The bid was investment: ETF holdings up 801 tonnes, bar and coin at a 12-year high, central banks 863 tonnes. Jewellery volumes fell and jewellery value rose. Q2 2026 LBMA PM average was $4,506.29/oz, 8% below the Q1 record and 37% above Q2 2025. Q2 central-bank buying was 289 tonnes after a weak first quarter. The Council's outlook: investment remains the demand driver, central banks stay buyers at a pace below 2025, mine supply and recycling respond only modestly.

That is the opposite of a cost-curve market. Primary-mine all-in sustaining cost is a floor that is slack at $4,500/oz. We still record it, from Newmont, Barrick, and the Council's cost commentary in filings we already have, so the margin is visible. We do not back into a price from AISC.

### What replaced the real-yield model

Erb and Harvey, "The Golden Dilemma" (Financial Analysts Journal, 2013), documented the long link between the real gold price and real interest rates, and also showed that a stable real price is a poor description of any given decade. From 2022 through 2026 the link broke in the direction of higher gold while real yields were high, because official-sector buying is a separate bidder for the stock. The model keeps the real-yield chart and demotes it.

Three layers, all shown, none of them silent:

1. **Real-rate residual.** Log of the LBMA price against the 10-year TIPS yield (`DFII10`), plus the broad dollar as a second panel. Report the residual in dollars per ounce. This is a description of history. When the residual stays large, the model says the real-rate anchor is not the clearing bidder.
2. **Official-sector regime.** World Gold Council quarterly net purchases, tonnes. The regime flag is on when trailing-year central-bank buying is in the post-2022 range (2025 was 863 tonnes; the Council expects 2026 below that and still historically high). In that regime the price path is an assumption conditional on the buying pace, not a fitted coefficient on TIPS.
3. **Dampers.** Jewellery volume and recycled supply rise when the price jumps and holders need cash. The Council's own outlook says both responses are modest while owners expect still-higher prices. Scenarios that mean-revert the price must raise recycling and jewellery volume, or state why the damper is stuck.

Above-ground stock identity, checked every quarter: stock goes up by mine production (gold is not consumed; recycling moves metal between categories). Category sums (jewellery, official, bars and coins, ETFs, OTC, other) must match the Council's total within their stated rounding. Demand categories in the quarterly table must match supply. A broken sum fails the build, the same way a broken gas balance fails.

### Scenarios (all `analyst_assumption` on the price)

- `official_bid_holds`: central-bank buying stays in a 600-900 tonne band and ETF holdings do not reverse the 2025 build. Real-rate residual stays wide.
- `real_rates_matter_again`: TIPS yields stay elevated and official buying falls back toward the pre-2022 pace. Price path is the real-rate fit plus a shrinking residual. This is the scenario the 2013 paper would have ranked first. It is not the base case for 2026.
- `damper_engages`: recycling and jewellery-volume destruction accelerate (the Council currently says they have not). Price path eases even if the official bid continues.

There is no `power_law` scenario.

### Falsifiers

- Trailing-year central-bank net buying under 300 tonnes.
- ETF holdings down more than 400 tonnes over four quarters.
- Recycled supply up more than 25% year on year while the price is flat or down (distress selling, a different regime).
- The real-rate residual closes to inside its pre-2022 band for two quarters.

### Sources

World Gold Council Gold Demand Trends PDF and the above-ground stock workbook (quarterly). LBMA Gold Price PM. FRED `DFII10` and the broad dollar. USGS for a mine-production cross-check. GLD and other ETF holdings in tonnes, from the sponsor, not the share price. COMEX eligible and registered stocks as a location diagnostic only.

---

## 7. Silver — build last, because it hangs off gold

World Silver Survey 2026 (Metals Focus, April 2026), million ounces:

| | 2024 | 2025 | 2026F |
|---|---:|---:|---:|
| Mine production | 823.6 | 846.6 | 844.1 |
| Recycling | 194.5 | 197.6 | 211.3 |
| Total supply | 1,019.6 | 1,090.4 | 1,066.4 |
| Industrial, of which PV | 679.0 / 197.5 | 657.4 / 186.6 | 639.6 / 151.0 |
| Jewellery | 205.1 | 189.3 | 159.4 |
| Coin and bar | 190.9 | 217.7 | 257.6 |
| Total demand | 1,157.4 | 1,130.6 | 1,112.6 |
| Market balance | -137.9 | -40.3 | -46.3 |
| Net ETP investment | 67.5 | 278.1 | 30.0 |
| Balance less ETPs | -205.4 | -318.4 | -76.3 |
| London price, $/oz | 28.27 | 40.03 |  |

The physical deficit shrank in 2025 (from 138 Moz to 40 Moz) while the price rose 42%. ETPs absorbed 278 Moz, so the balance after ETPs was -318 Moz. Lease rates and regional premia, not the headline deficit, were the tightness signal the Survey leads with. A model that maps "deficit in Moz" onto price in a straight line will miss both the ETP swing and the PV thrift.

Supply is mostly not silver's decision. Primary mines were 26% of 2025 mine supply, a new low. By-product supply was 625.5 Moz, up 4%. Lead/zinc mines are still the largest source. Copper-by-product silver was 237.3 Moz, up 6%. Primary-mine all-in sustaining cost was $12.21/oz and total cash cost $5.21/oz, against a $40 price. About 99% of primary production was profitable. The cost floor is slack by a wider margin than gold's. Raising the silver price does not bring forth most of the next ounce. That ounce comes from copper, lead, zinc, and gold mines.

PV is the industrial swing, and it is going the other way from the 2021-2024 story. Photovoltaic demand fell 6% in 2025 to 186.6 Moz and is forecast down 19% in 2026 to 151.0 Moz, on thrifting and substitution, even where gigawatts installed do not fall as fast. The industrial bull case has to survive grams-per-cell falling faster than installations rise. The Survey's own bridge (base, progressive thrifting, aggressive substitution) is the scenario set. Type those three paths in from the Survey rather than fitting a new one.

### Two-step price

1. **Monetary leg.** Silver price = gold price / gold-silver ratio. The gold model supplies the gold path. The ratio is an observed series (LBMA), not a mean-reverting trade. We show where the ratio sits against its history. We do not forecast it back to a historical average.
2. **Physical leg.** The Survey balance, with ETPs on their own line so the 2025 lesson stays visible. Identifiable stocks (COMEX, LBMA vaults where published, ETP holdings, and India/China premia if we have a public print) are the storage analog. Lease rate, when LBMA publishes a usable series, is the convenience-yield analog of Working: a high lease rate means the nearby metal is scarce even if a global spreadsheet shows a small deficit.

Scenario price paths are `analyst_assumption`. They move when the gold path moves, and they widen or narrow against gold only when the physical block changes (PV thrift faster or slower, ETP inflow reverses, lease rate normalizes).

### Falsifiers

- PV demand falls through the Survey's aggressive-substitution path.
- Primary share of mine supply rises back above 35% (silver price finally calling forth primary mines; the cost floor would start to matter).
- ETP holdings reverse the 2025 build of 278 Moz.
- Lease rates back to ordinary levels for a full quarter while COMEX stocks rebuild.

### Sources

World Silver Survey PDF (annual, free). LBMA silver price. COMEX stocks. ETF sponsor holdings (SLV and peers) in ounces. USGS. The PV installation cross-check can cite IEA PVPS public summaries; grams per watt come from the Survey's thrifting cases, not from a cell-maker model we would be guessing.

---

## 8. How the four models talk to each other

Small bridges, each marked `included_in_balance: false`, matching the gas model's generator cross-check.

- **Diesel and power into mine costs.** The oil model's WTI path and the existing gas/power path move the AISC rows for gold, silver, and copper. They do not change the metal balances.
- **Silver reads gold.** Silver has no independent monetary forecast.
- **Copper reads the power story only as a caption.** Data-center and grid demand are already inside ICSG's usage line ("digitalisation, data centres and AI" is in the October 2026 text). We footnote the energy model. We do not add a second copper-demand term on top of ICSG.
- **By-product link, silver and copper.** Copper mine disruptions (Grasberg, Kamoa-Kakula) change silver by-product supply. A copper `concentrate_dominates` scenario can optionally cut silver by-product ounces by the Survey's copper-share (237 Moz in 2025). Default off, so the two models stay independently refreshable.

Nothing in this set writes a deck price into a royalty IRR. FNV, WPM, RGLD, NEM, GOLD, and FCX can cite the scenario fan in research notes. Promotion into a base case stays a human edit of `valuation.json`.

---

## 9. Methods considered and left out

| Method | Where it looks clever | Why it stays out of the engine |
|---|---|---|
| Bitcoin-style power law, stock-to-flow | Gold and silver are monetary | The stock is ~60 years of mine supply. The functional form is an adoption curve. Gold's 2022-2026 residual is official buying, which S2F does not contain. |
| Hotelling rule | Oil, copper "running out" | Price has not tracked the interest rate. Shale and scrap break the fixed-stock premise. |
| Schwartz one- and two-factor models | Futures curve | Right tool for options. The curve is an observed diagnostic (backwardation, lease rate). We store it. We do not fit a latent convenience yield and call it a forecast. |
| Kilian structural VAR as the forecaster | Oil | Use the three shock names on scenarios. Estimating the VAR is a research paper, and it would duplicate EIA's pool. |
| Full competitive-storage estimation (Deaton-Laroque) | Oil, copper | The operational piece is already in the gas model: capacity, injection and withdrawal limits, unmet demand and spill shown explicitly. A structural estimator needs a price elasticity we do not have cleanly. |
| Machine-learning price model | All four | No identity, no falsifier, no source hash. |
| Paid cost curves | Copper incentive price, gold AISC percentile | Use filings, USGS, Dallas Fed, ICSG, WGC, and the Silver Survey. An empty incentive-price cell beats a remembered round number. |

---

## 10. Build order

Each phase ends with `validate_commodity_models.py` green and the JSON still carrying `in_base_irr: false`.

**Phase 0 — scaffold.** `commodity_common.py`, config shape, validator, empty dashboard slot. Tests: identity closes, stale source warns, a price row cannot be tagged `published_forecast` past the source's last forecast period, `in_base_irr` must be false or the build throws (the gas builder already does this).

**Phase 1 — crude.** Type October 2026 STEO Tables 2 and 3a into `crude.json` the way gas types Table 5a. Fetch EIA history and FRED spots. Four scenarios. WTI-Brent block. Dallas Fed floor. This is the one to copy from `energy_balance.py` most literally.

**Phase 2 — copper.** Type the 14 October 2026 ICSG forecast. Three exchange-stock series. Two balances. TC as a reviewed headline. Three scenarios. Unit test that COMEX $/lb and LME $/t convert by 2204.62 and that a sign-flip between apparent and bonded-adjusted balance is displayed, not averaged away.

**Phase 3 — gold.** LBMA or `GC=F` in $/oz. Fix the GLD-share theme series. Quarterly stock identity from the Council's workbook. Real-rate residual chart. Three scenarios. AISC margin from filings, labeled non-binding.

**Phase 4 — silver.** Survey table typed in, including the balance-less-ETPs line and the three PV paths. Ratio against the gold model. Lease rate optional. Primary-share series (26% in 2025) on the cost panel so the slack floor stays obvious.

**Phase 5 — strip UI and bridges.** `commodity-model-viz.js` next to `EnergyModelViz` in `insights-viz.js`. Diesel/power cost bridge. Silver reads gold. Copper footnotes the energy model. Still context only.

Refresh cadence follows the source, not a daily job: STEO monthly (the gas config already keys off the October 2026 STEO), ICSG monthly plus April/October forecast, World Gold Council quarterly, World Silver Survey annually. Stale windows: STEO and ICSG monthly 45 days, gold 120 days, silver survey 400 days.

---

## 11. What "done" means for a reader

A person looking at the strip can answer, for each commodity, without opening a spreadsheet:

1. Is the latest number a published balance or our extension?
2. Which stock is tight, and is that stock the one that matters (Cushing versus OECD; COMEX versus SHFE; ETF tonnes versus jewellery; ETP ounces versus the 40 Moz headline deficit)?
3. Is the cost floor binding or slack?
4. Which named scenario is just the public forecast, and which ones are ours?
5. What print would kill the scenario?

If a panel shows a single price target, the panel is wrong and should fail review.
