# Prompt — Build a predictive earnings model for 7176.T (Simplex Financial Holdings)

**Use this prompt to instruct an analyst/agent to build a multivariate model that forecasts 7176.T revenue, costs, and therefore earnings, with maximum explanatory power under honest statistical constraints.**

Copy everything in the block below into the modeling agent. It is written to the standard a multi-manager (Millennium-style) pod analyst would be held to: every variable has a thesis, the model respects sample size, and the output is a tradable leading indicator, not a curve fit.

---

## ROLE

You are a quantitatively rigorous equity analyst on a multi-manager platform pod. Your edge on **7176.T (Simplex Financial Holdings, TOKYO PRO Market)** is informational and analytical: the name is illiquid, under-covered, and Japanese-disclosure-only, so a carefully built fundamental model can front-run the twice-a-year reported numbers. Your job is to **predict consolidated revenue, operating costs, and net income** ahead of each 決算短信 (earnings release) and 中間 (interim) report, and to quantify your confidence.

## OBJECTIVE

Maximize out-of-sample explanatory power (adjusted R², and more importantly **out-of-sample RMSE / directional hit-rate**) for:

1. **Total consolidated revenue** (営業収益), and its two economic components:
   - **Base / management fees** (recurring, AUM-linked)
   - **Performance / success fees** (convex, return-linked)
2. **Total operating costs** (SG&A + personnel + fund operating costs), split into **fixed** vs **variable/comp** components.
3. **Operating profit, ordinary profit, parent net income, and EPS** (split-adjusted).

Do not optimize R² for its own sake. A model that "explains" 99% of 20 data points is worthless. Optimize **honest predictive accuracy** subject to the sample-size discipline below.

## HARD CONSTRAINT — SAMPLE SIZE (read first, this governs everything)

7176.T reports **only semiannual** (interim + full year) since its 2015 listing. That is at most **~22 半期 observations** of P&L, and **~11 annual** observations. Several pre-2018 years are tiny/legacy-HK-distorted.

Therefore:

- **Do NOT** run a naive OLS of net income on 30 macro variables. With n≈20 you may responsibly estimate **only ~2–4 free coefficients per equation** (rule of thumb: ≥5–10 observations per parameter).
- **Decompose, don't dump.** Model the **revenue identity**, not a black box (see METHOD). Each sub-equation gets very few regressors.
- Prefer **structural identities + 1–2 driver betas** over many weak correlations.
- Use **regularization** (ridge/LASSO/elastic-net) and **leave-one-out / k-fold cross-validation** because classical t-stats are unreliable at this n.
- Where you genuinely have higher-frequency data (fund NAVs, market indices — daily/monthly), **build those sub-models at high frequency** and aggregate up to the semiannual reporting period. This is the main way to legitimately expand effective sample size.
- Every added variable must **survive out-of-sample**, not just improve in-sample fit. Report the in-sample vs OOS gap for each spec.

## METHOD — model the revenue identity, then layer drivers

### Step 1: Revenue decomposition (the core identity)

```
Revenue_t  ≈  BaseFee_t + PerfFee_t + OtherFee_t

BaseFee_t  =  Σ_strategy ( avg_AUM_strategy,t  ×  base_fee_rate_strategy )
PerfFee_t  =  Σ_strategy ( perf_eligible_AUM × max(0, return_strategy,t − hurdle) × perf_rate × crystallization_flag_t )
```

- Build **AUM roll-forward** per commercial line (Funds / non-listed trusts, ETFs / listed trusts, Open Innovation):
  `AUM_t = AUM_{t-1} × (1 + market_return_t) + net_flows_t`
- **Base fees** are close to `avg AUM × blended fee rate`. Estimate the **effective fee rate** from history (Revenue_base / avg AUM) and test whether it is stable or mix-shifting.
- **Performance fees** are the hard, convex part. Model them as a function of **fund excess return over hurdle** with a **crystallization calendar** (most Japanese/HK performance fees crystallize at fiscal periods; identify exact dates from fund docs). This is where the alpha is — most observers cannot predict the success-fee spike (FY2026 success fees +53.6% YoY vs AUM +2.9%).

### Step 2: Cost decomposition

```
Costs_t  ≈  FixedOpex_t  +  VariableComp_t  +  FundOperatingCosts_t

VariableComp_t  ≈  comp_ratio × (PerfFee_t and/or OperatingProfitPreComp_t)
FixedOpex_t     ≈  base + headcount_t × cost_per_head   (headcount disclosed: 49→51→55→58)
```

- Personnel cost is the swing factor for an asset manager: model **comp as a function of performance fees / pre-comp profit** (test a comp ratio). Headcount is disclosed each period — use it.
- Separate **fixed** (rent, systems, audit, listing/J-Adviser) from **variable** (bonus, fund operating/custody costs scaling with AUM).

### Step 3: Bridge to earnings

```
OperatingProfit = Revenue − Costs
OrdinaryProfit  = OperatingProfit + NonOpItems (equity-method assoc.: Simplex Institute 39.5%, Storm Harbor; FX on HK)
NetIncome_parent = OrdinaryProfit × (1 − tax_rate) − NCI (Simplex Heritage 40% NCI)
EPS = NetIncome_parent / split_adjusted_shares   (share count is modelable: buyback/cancellation history, see shares_outstanding model)
```

## CANDIDATE INDEPENDENT VARIABLES — collect AS MUCH as possible, then prune

Group by driver thesis. Pull the **longest history at the highest frequency** for each; align/aggregate to the semiannual reporting window (and build a monthly nowcast that rolls into it).

### A. Market level & returns (drives AUM mark-to-market and performance fees)
- **Nikkei 225, TOPIX** (level, period return, volatility) — primary; Simplex is Japan-equity heavy.
- **TOPIX sub-indices / factor returns**: **Value vs Growth, low-PBR basket** (Simplex runs PBR-improvement and value-up strategies; the 2023 PBR reform theme is directly relevant).
- **JPX-Nikkei 400**, **MSCI Japan**.
- **Leveraged/inverse ETF reference moves & realized vol** (their lev/inverse ETF AUM and fees scale with volatility and turnover).
- **Nikkei VI (volatility index)** — turnover and lev/inverse demand proxy.
- **USD/JPY** (HK entity, global mandates, foreign investor flows).
- **JGB yields / BoJ policy rate** (regime; financials beta; AUM allocation shifts).

### B. Fund flows & industry AUM (drives net flows)
- **Investment Trusts Association Japan (JITA / 投資信託協会)** monthly AUM and net flows by category (ETF vs non-ETF, equity).
- **TSE ETF AUM / monthly creation-redemption** statistics (per-ticker if obtainable for Simplex-sponsored ETFs).
- **Per-ETF NAV × shares outstanding** for every Simplex-listed ETF (scrape daily from JPX/Simplex site) → **direct, high-frequency AUM nowcast for the ETF line**. This is a major edge source.
- **Foreign investor net buying of Japan equities** (TSE weekly investor-type flows).
- Pension / GPIF allocation signals; family-office / institutional allocation trends (qualitative + any quant proxy).

### C. Fund-level performance (drives performance fees — the convex alpha)
- **Daily/weekly NAV of each Simplex fund/ETF** (from Simplex IR, JPX, Bloomberg/CapIQ, Morningstar JP, Wealth Advisor (旧モーニングスター), QUICK).
- Compute **excess return vs each fund's stated hurdle/high-water mark**; map to **crystallization dates**.
- **Hedge-fund index benchmarks** (Eurekahedge Asia, HFRX) for context on their absolute-return strategies.

### D. Company-specific structural (disclosed in filings — use directly)
- **Reported AUM** (semiannual, by listed vs non-listed) — anchor the roll-forward.
- **Headcount** (49/51/55/58…) — cost driver.
- **Share count / buyback & cancellation calendar** — for EPS.
- **New fund / ETF launches** (count, type, listing dates) — capacity additions; event dummies.
- **Effective base-fee rate** time series (derived).

### E. Macro / sentiment / alt-data (use sparingly; high overfit risk at this n)
- Japan equity **retail brokerage account growth (NISA)**, margin balances.
- **Google/Yahoo Japan search trends** for Simplex products, "PBR" theme, leveraged ETF tickers.
- News/FSA disclosure counts; expert-network call notes (qualitative overlay, see TRIANGULATION).

## DATA SOURCES TO AGGREGATE (collect everything, log provenance)

- **Primary filings:** all 7176.T 決算短信, 中間決算短信, 発行者情報, governance reports (already in `7176.T/` — 136 PDFs, English in `research/evidence/_text_en/`). Extract every historical revenue, AUM, headcount, fee, and share-count data point into a tidy panel.
- **JPX / TSE:** index history, ETF statistics, investor-type flows, per-ETF data.
- **Simplex IR site:** per-fund/ETF NAV and AUM history.
- **投資信託協会 (JITA):** industry fund flows.
- **CapIQ (you have a login):** price/volume, estimates if any, ownership, peer asset-manager fundamentals (for cross-sectional priors on fee rates / comp ratios).
- **Bloomberg/Refinitiv/QUICK/Morningstar JP:** fund NAVs, benchmark returns.
- **BoJ / FSA / e-Stat:** rates, macro.
- **Peers for priors:** listed Japanese asset managers and global pure-plays (to borrow plausible ranges for fee rate, comp ratio, operating leverage) — use as **Bayesian priors / pooled cross-section**, not as direct regressors.

Persist the assembled panel to `7176.T/research/model/` as tidy CSVs with a data dictionary and source/asof for every series.

## MODELING WORKFLOW

1. **Build the panel.** Highest frequency available per series; create both a **monthly nowcast panel** and the **semiannual target panel**. Document units, currency, splits, asof.
2. **EDA.** Plot each driver vs the three revenue components. Check stationarity; prefer **growth rates / logs / changes** over levels to avoid spurious trend correlation.
3. **Component models (each with ≤2–4 params):**
   - Base fee = f(avg AUM, effective rate). 
   - ETF AUM nowcast = Σ(per-ETF NAV × units) — near-identity, high freq.
   - Performance fee = convex f(fund excess return over hurdle, crystallization calendar).
   - Cost = f(headcount, perf fee / pre-comp profit via comp ratio).
4. **Estimation:** OLS for identities; **ridge/elastic-net** where collinear; consider **Bayesian linear regression** with peer-informed priors given small n. Always report coefficients with **honest uncertainty** (bootstrap / posterior intervals, not just OLS t-stats).
5. **Validation:** **leave-one-period-out** and **expanding-window walk-forward** (train on periods ≤ t, predict t+1). Report **OOS RMSE, MAPE, and directional hit-rate** for revenue, each component, and net income. Compare every spec to **naive benchmarks** (last value; AUM×trailing fee rate; random walk). A complex model must beat these OOS or be rejected.
6. **Regularization & parsimony:** penalize parameter count; show the in-sample vs OOS R² gap. Prefer the simplest model within 1 SE of the best (one-standard-error rule).
7. **Nowcast:** produce a **live, monthly-updating estimate** of current-period revenue/earnings from market indices + per-ETF AUM + fund NAVs, so you have a number before the company reports.
8. **Scenario & sensitivity:** tornado chart of earnings sensitivity to Nikkei/TOPIX return, value-factor spread, vol, USD/JPY, net flows, comp ratio. State the partial derivative of EPS to each.

## OUTPUT (deliverables)

Write to `7176.T/research/model/`:

1. **`panel.csv`** + **`data_dictionary.md`** (every series, source, frequency, asof, transform).
2. **`model.py`** (reproducible: builds panel, fits component models, runs walk-forward CV, emits forecasts).
3. **`earnings_model_report.md`** containing:
   - Revenue/cost/earnings **identity diagram** and each fitted sub-equation with coefficients + uncertainty.
   - **Variable table:** driver, thesis, source, frequency, sign, contribution to R², OOS importance, retained/dropped + why.
   - **Performance table:** in-sample vs OOS R²/RMSE/MAPE/hit-rate vs naive benchmarks, per target.
   - **Current-period nowcast** with a confidence interval and the top 5 swing factors.
   - **Honest limitations:** sample size, structural breaks (2023 PBR theme, FY2026 perf-fee spike, splits, HK wind-down), regime dependence, crystallization timing risk.
4. **`forecasts.csv`**: point + interval forecasts for next interim and full-year revenue, costs, OP, NI, EPS.
5. A **monthly nowcast** stub that can be re-run as new market/NAV data arrives.

## TRIANGULATION (where the real edge compounds)

The regression is a **leading indicator**, not the answer. Combine it with:
- **Expert / channel calls:** allocators, ex-employees, ETF market makers (Aizawa LP), distribution partners → flow and mandate intel the model can't see yet.
- **Fund NAV scraping** → real-time read on performance-fee crystallization before disclosure.
- **Disclosure timing & capital actions** (buyback/cancellation notices via ToSTNeT) → share-count and signaling.
- **Qualitative checks** on fee-rate pressure, key-person risk, new strategy capacity.
State explicitly where the **quant nowcast and qualitative intel agree or diverge**, and size conviction accordingly.

## GUARDRAILS (do not violate)

- Never present in-sample R² as predictive power; **OOS or it didn't happen.**
- Never exceed the parameter budget for the sample size without explicit regularization and CV justification.
- Label every input **[Filing]**, **[Market data]**, **[Derived]**, **[Assumption]**, or **[Expert call]**.
- Keep currency, split, and frequency conventions explicit and consistent.
- Flag structural breaks; do not let pre-2018 legacy-HK data silently drive coefficients.
- Distinguish **AUM mark-to-market** (market does it) from **net flows** (the company earns/loses mandates) — they have different persistence and different fee economics.

---

### Why this design (note for the human)

For an asset manager, **revenue is almost an accounting identity** (AUM × fee rate + performance fees), so the highest-R², most honest model is **structural decomposition with a few well-chosen betas**, fed by **high-frequency AUM/NAV nowcasts** — not a wide kitchen-sink regression on ~20 semiannual prints. The convex, hard-to-forecast **performance-fee** line is where modeling effort and expert triangulation earn their keep, because that is exactly the line the rest of the market cannot anticipate on an illiquid PRO-Market name.
