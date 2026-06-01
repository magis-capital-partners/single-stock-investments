# Darwin IRA — research download plan & optimization roadmap

**Account type:** Simple tax-advantaged IRA (Traditional or Roth — same turnover discipline; Roth has no RMD during life).  
**Objective:** 8–12 high-conviction single stocks, **≤10% one-way turnover per semiannual rebalance**, Marvin-grounded expected return, Darwin encoder/GA/PPO as **sanity check** not sole driver.

**Status:** Data-science tuning applied in `_system/portfolio/darwin_mandate.json` (`account_profile: ira`). Rebuild: `python3 _system/scripts/build_darwin_portfolio.py`.

---

## 0. Darwin AI investor letter (one-time)

| Step | Action | Output path |
|------|--------|-------------|
| 1 | **Drop PDF in repo** at `_system/frameworks/` (recommended), `quant-evolution/INCOMING/`, or run `copy_darwin_investor_pdf.ps1` | `Darwin_AI_Investments_1Q26.pdf` |
| 2 | `bash _system/scripts/copy_darwin_investor_pdf.sh` (from repo root) | copies from INCOMING or `DARWIN_PDF_SOURCE` |
| 3 | `pip install pypdf && python3 _system/scripts/ingest_darwin_investor_pdf.py` | `darwin_source_notes.md` + extract |
| 4 | Map PDF claims → `darwin_mandate.json` `source_overrides` | Human review |

*Automated copy from `C:\Users\werdn\Downloads\` is not available in the cloud VM — use INCOMING folder in Cursor (drag-and-drop into repo) then step 2.*

---

## 1. IRA strategy constraints (why downloads matter)

| IRA reality | Research implication |
|-------------|---------------------|
| No capital-gains tax **inside** the account | Optimize **pre-tax compound return**, not tax-loss harvesting |
| Still pay **commissions/spreads** | Keep turnover low; semiannual rebalance |
| Limited capital / no margin | Long-only, 8–12 names, max **15%** per issue |
| No shorting | Falsifier → **trim to floor**, not short |
| Foreign / OTC frictions | Prefer **US exchange** names; flag 8697.T, TEQ.ST, KEWL, OTCM for sizing caps |
| Required minimum distributions (Traditional IRA, age 73+) | Plan **liquidity sleeve** (ICE, SPGI, CPRT) for future withdrawals |

---

## 2. Document tiers — what to download

### Tier A — Required before next rebalance (portfolio-quality)

| # | Document | Source | Save to | Used for |
|---|----------|--------|---------|----------|
| A1 | Latest **10-K / 20-F** per holding | SEC EDGAR / company IR | `{TICKER}/investor-documents/` | Filing falsifiers, FCF₀ |
| A2 | Latest **10-Q** (or semi-annual abroad) | Same | Same | Growth ledger refresh |
| A3 | **valuation.json** refresh | `marvin_cloud_refresh.py` | `{TICKER}/research/` | IRR prior for Darwin |
| A4 | **Monthly total return** 10+ years | Yahoo/Stooq → CSV | `_system/reference/market-data/returns/{TICKER}.csv` | Backtest (replace synthetic IRR) |
| A5 | **SPY** + **AGG** (or **BND**) monthly returns | Stooq/FRED | `_system/reference/market-data/benchmarks/` | Relative Sharpe, IRA passive benchmark |
| A6 | **Darwin 1Q26 PDF** | Your Downloads | `quant-evolution/Darwin_AI_Investments_1Q26.pdf` | Strategy alignment |

**Automation:** `python3 _system/scripts/download_ira_research.py --tier A` (see manifest below).

### Tier B — Optimization cycle (quarterly research)

| # | Document | Source | Save to | Used for |
|---|----------|--------|---------|----------|
| B1 | **Fama-French 5 factors** monthly | [Kenneth French Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html) | `_system/reference/market-data/french/F-F_Research_Data_5_Factors_2x3.csv` | Factor regression vs holdings |
| B2 | **CPI / 10Y Treasury** | [FRED](https://fred.stlouisfed.org/) (`CPIAUCSL`, `DGS10`) | `_system/reference/market-data/macro/fred_*.csv` | Regime (inflation / rates) |
| B3 | **VIX** monthly | FRED `VIXCLS` | `_system/reference/market-data/macro/vix.csv` | AMH “stressed” regime |
| B4 | Per-name **DEF 14A** (governance) | SEC | `investor-documents/sec-edgar/` | Moat / capital allocation |
| B5 | **Earnings release** last 4 quarters | IR sites | `ir-{ticker}/` | Event study around prints |
| B6 | Marvin **deep dive** refresh | Cloud/local Marvin | `research/deep_dive_*.md` | Narrative covariates |

### Tier C — Academic / industry context (annual refresh)

| # | Document | Source | Status in repo |
|---|----------|--------|----------------|
| C1 | Lo — Adaptive Markets (JPM 2004) | Wharton PDF | ✅ `Lo_AMH_JPM2004.pdf` |
| C2 | Lo — New World Order (FAJ 2012) | Hillsdale mirror | ✅ downloaded |
| C3 | Arthur — Complexity economics intro | SFI | ✅ downloaded |
| C4 | Liu & Yang — CAFPO DRL factors (2025) | arXiv:2509.16206 | ✅ downloaded |
| C5 | IRS **Pub 590-B** (RMD rules) | irs.gov | Download → `ira-compliance/` |
| C6 | BlackRock / AQR factor primers | Public PDFs | `quant-evolution/industry/` |
| C7 | De Prado — AFML (book) | Purchase / library | Ch. on backtest overfitting |

### Tier D — Optional (single-stock edge)

| # | Document | When |
|---|----------|------|
| D1 | Horizon Kinetics commentaries | HK overlap tickers (FRMO, ICE, …) |
| D2 | TCI letters (operating mindset) | `_system/reference/investment-wisdom/tci/` ✅ |
| D3 | Third-party Substack / HK PDFs | Per `third_party_sources.md` |
| D4 | Segment IR decks (hyperscalers) | AMZN, GOOGL, META AI overlay |

---

## 3. Holdings-specific download checklist (25 names)

Prioritize **IRA core book** (stance core/hold/accumulate + dhando + IRR ≥ 8%):

| Priority | Ticker | Stance (registry) | Tier A focus |
|----------|--------|-------------------|--------------|
| P0 | CPRT, CSU | core | 10-K, 10-Q, returns CSV |
| P0 | FRMO | hold / accumulate | NAV lines, annual report, returns |
| P1 | ICE, SPGI, OTCM, BN | hold | Filing + croupier cycle data |
| P1 | AMZN, GOOGL, DHR | hold | AI/capex stress in 10-Q |
| P2 | QDEL | hold | Turnaround falsifiers |
| P2 | APLD, CMSG, MSB, SJT | watch | Optionality — size cap until dive upgrades |
| P3 | 8697.T, TEQ.ST | hold/watch | FX + ADR liquidity notes |
| P3 | KEWL, TPL, SNOW, LSEG | watch | Negative/low IRR — **no IRA add** until thesis fixes |

**Exclude from IRA target weights (until review):** negative IRR names (KEWL, TPL), unless `approved_stance` in valuation.json.

---

## 4. Data-science tuning log (2026-06-01)

Applied in `darwin_mandate.json` → policy **`ira_marvin`** (overrides ML champion when backtest panel is thin):

| Knob | Old | IRA tuned | Rationale |
|------|-----|-----------|-----------|
| `rebalance_frequency` | quarterly | **semiannual** | Fewer trades; IRA doesn't need quarterly factor churn |
| `max_one_way_turnover_pct` | 15% | **10%** | Stricter drift cap |
| `max_weight_pct` | 18% | **15%** | Diversification; FRMO was 20%+ |
| `max_names` | 15 | **12** | Manageable IRA book |
| `turnover_penalty_kappa` | 0.35 | **0.85** | Stop PPO from winning on noisy short panel |
| `min_irr_pct_for_weight` | — | **6%** | Drop negative-IRR tails unless core |
| `stance_multipliers` | — | core 1.25, hold 1.0, watch 0.45 | Align with Marvin gate |
| `preferred_policy` | auto | **ira_marvin** | Until ≥24 months price history |
| `transaction_cost_bps` | 10 | **5** | IRA: no tax drag; keep spread cost |
| `us_listed_bonus` | — | 1.05 | Slight US tilt for simple custody |

**Champion selection rule:** Use ML (PPO/GA) only if `champion.sharpe_annualized > 0.3` and `periods >= 12`; else **`ira_marvin`**.

---

## 5. Execution schedule (12 weeks)

| Week | Task | Deliverable |
|------|------|-------------|
| 1 | Copy PDF + Tier A returns CSVs | `market-data/returns/*.csv` |
| 2 | `download_ira_research.py --tier A` + refresh valuations | Updated `valuation.json` all P0/P1 |
| 3 | Re-run Darwin full (not `--fast`) | `darwin_portfolio.json` |
| 4 | Marvin deep dives: CPRT, CSU, FRMO | New `deep_dive_*.md` |
| 5 | Tier B French + FRED macro | Regime features in encoder |
| 6 | Backtest report notebook / script output | `darwin/backtest_report.md` |
| 7 | Human approve IRA weights vs stance | `ira_target_weights.json` |
| 8 | Paper trade 6 months | Log drift vs mandate |
| 9–12 | Quarterly Tier B refresh | Repeat |

---

## 6. Success metrics (IRA)

| Metric | Target |
|--------|--------|
| Active names | 8–12 |
| Max weight | ≤ 15% |
| Semiannual turnover | ≤ 10% one-way |
| Marvin conflicts | 0 high-weight + watch without `[HUMAN REVIEW]` |
| OOS vs SPY | Positive excess over 3y after real returns loaded |
| Falsifier exits | Documented within 30 days |

---

## 7. Commands

```powershell
# 1. Copy PDF (local Windows)
powershell -ExecutionPolicy Bypass -File _system/scripts/copy_darwin_investor_pdf.ps1

# 2. Download Tier A/B manifests
python3 _system/scripts/download_ira_research.py --tier A
python3 _system/scripts/download_ira_research.py --tier B

# 3. Rebuild Darwin IRA portfolio
python3 _system/scripts/build_darwin_portfolio.py
python3 _system/scripts/build_dashboard_data.py
```

---

*Not tax or investment advice. Confirm Traditional vs Roth and RMD rules with your CPA.*
