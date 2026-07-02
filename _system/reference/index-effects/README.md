# Index Inclusion / Exclusion Research Library

Curated research on the **index effect**: what happens to a stock's price, ownership,
liquidity and fundamentals when it is added to or removed from a major index
(S&P 500, S&P MidCap 400, Russell 1000/2000, MSCI), and how predictable those events are.

**Path:** `_system/reference/index-effects/`

This library exists to support a dashboard feature that keeps us abreast of tickers with
**potential** or **confirmed** index inclusion / exclusion. See the build plan:
`_system/proposals/index_membership_tracking_2026-07-01.md`.

## Layout

```
index-effects/
├── README.md            ← this file (catalog + how to use)
├── SYNTHESIS.md         ← distilled findings + implications for the dashboard
├── papers/              ← downloaded academic PDFs (+ _download.sh, _download_log.txt)
├── methodology/         ← index-provider rulebooks (S&P DJI, FTSE Russell)
└── _text/               ← pypdf text extracts (machine-readable, for grep/build scripts)
```

Regenerate text extracts after adding a PDF:

```bash
python3 - <<'PY'
from pypdf import PdfReader; from pathlib import Path
base = Path('_system/reference/index-effects')
for pdf in sorted(base.glob('**/*.pdf')):
    r = PdfReader(str(pdf)); txt = "\n".join((p.extract_text() or "") for p in r.pages)
    (base/'_text'/(pdf.stem+'.txt')).write_text(txt, encoding='utf-8')
PY
```

## Academic papers (`papers/`)

| File | Cite | Contribution |
|------|------|--------------|
| `shleifer_1986...` (abstract only; PDF paywalled) | Shleifer 1986, JF | Original: S&P 500 additions earn permanent +abnormal return -> demand curves slope down. |
| `wurgler_zhuravskaya_2002_does_arbitrage_flatten_demand_curves.pdf` | Wurgler & Zhuravskaya 2002, JB | Stocks **without close substitutes** get bigger inclusion jumps; arbitrage cannot flatten the curve. |
| `kaul_mehrotra_morck_2000_demand_curves_slope_down_tse.pdf` | Kaul, Mehrotra & Morck 2000, JF | Clean natural experiment (TSE 300 float redefinition, info-free): ~2.3% price pressure -> downward-sloping demand. |
| `barberis_shleifer_wurgler_2005_comovement.pdf` | Barberis, Shleifer & Wurgler 2005, JFE | S&P 500 inclusion raises a stock's **beta/comovement** with the index (habitat/category view). |
| `petajisto_2011_index_premium_hidden_cost.pdf` | Petajisto 2011, JEmpFin | Add/delete impacts (+8.8%/-15.1% S&P 500; +4.7%/-4.6% R2000, 1990-2005). Elasticity rises with size, falls with idio risk. Defines **index turnover cost** (hidden drag on indexers). |
| `chang_hong_liskovich_2015_regression_discontinuity_indexing_nber_w19290.pdf` | Chang, Hong & Liskovich 2015, RFS | Russell 1000/2000 cutoff **regression discontinuity**: clean price effects for BOTH adds and deletes near the rank-1000 boundary. |
| `pavlova_sikorskaya_2022_benchmarking_intensity.pdf` | Pavlova & Sikorskaya 2023, RFS | **Benchmarking Intensity (BMI)** = cumulative index weight x AUM tracking each index. Higher BMI change -> larger index effect and lower future returns. Better predictor than raw "% indexed." |
| `bennett_stulz_wang_2020_joining_sp500_nber_w27593.pdf` | Bennett, Stulz & Wang 2020 | S&P 500 announcement effect has vanished; **long-run effect of inclusion turned negative**; governance/informativeness/ROA decline. |
| `greenwood_sammon_disappearing_index_effect_nber_w30748.pdf` | Greenwood & Sammon 2022 (JF 2025) | **The index effect has largely disappeared** (adds: 3.4%/7.6%/5.2%/0.8% by decade). Drivers: smaller relative size, lower trading costs, **MidCap<->500 migrations** (net demand smaller), predictability/front-running, better liquidity provision. |

## Index-provider methodology (`methodology/`)

| File | Source | Use for the feature |
|------|--------|--------------------|
| `sp_dji_us_indices_methodology.pdf` | S&P Dow Jones Indices, S&P U.S. Indices Methodology | S&P 500/400/600 **eligibility rules** (market cap bands, float >= 50%, IWF >= 0.10, positive trailing-4Q + latest-quarter GAAP earnings, liquidity ratio, US domicile). Additions announced ad hoc, ~3+ business days before effective. |
| `ftse_russell_us_indexes_construction_and_methodology.pdf` | FTSE Russell (LSEG) | Russell **reconstitution** mechanics: rank by total market cap on last business day of Apr/Oct; top 4,000 = Russell 3000E; **Russell 1000/2000 cutoff**; **banding rule** (+/-2.5% around breakpoint #1000) to cut turnover; effective 4th Friday June / 2nd Friday December (2026 semi-annual). |

Provider rules are the ground truth for computing "how close is this ticker to an inclusion/exclusion boundary." Thresholds change quarterly (S&P) - store them in config, not code. See SYNTHESIS.md.
