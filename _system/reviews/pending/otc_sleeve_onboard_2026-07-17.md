# OTC special-situation sleeve — onboard + economic-value retrofit (2026-07-17)

## Tickers
| Ticker | Stance | Base return | Method |
|--------|--------|-------------|--------|
| GDRZF | watch | 11.3% (4yr) | economic_value / dated legal optionality |
| TPHS | watch | 14.4% (5yr) | economic_value / NOL shell optionality |
| GYRO | hold | 33.4% to $11.79 liq NAV | economic_value / dated liquidation NAV |
| SEVN | watch | 14.6% (7yr Lawrence) | economic_value / mREIT book + reserves |
| PLWN | watch | pending | economic_value provisional; share count blocked |
| HNFSA | watch | 3.9% | economic_value starter retrofit |

## Methodology
All six now set `valuation_mode: economic_value` and `valuation_methodology.mode: component_economic_value` with complete `component_valuation` + `economic_value` blocks. `marvin_valuation.py --write` reports `component_valuation_results.status=complete` and `economic_value_analysis.status=complete`.

## Human review
- GDRZF: SEDAR cash/shares; Amber/OFAC closing; creditor rank
- TPHS: OTC closing print; Steel plan disclosure
- PLWN: Form 990 PDFs + verified share count (Vicki brief)
- SEVN: keep Lawrence 14.6% as stance gate (synthesis 16.04% not promoted)
- HNFSA: starter EV retrofit only; deepen before sizing

## Git
Feature branch `marvin/otc-sleeve-economic-value-2026-07-17` — merge via PR so in-flight Actions on main are not force-overwritten.
