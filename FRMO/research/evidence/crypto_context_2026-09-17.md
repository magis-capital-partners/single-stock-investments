# FRMO - Crypto economics context (2026-09-17)

> Context only. Crypto and mining metrics inform stance and overlays; they do not auto-inflate Lawrence base IRR. Promotion to base case requires [HUMAN REVIEW].

**Exposure type:** holdco

| Indicator | Latest | As of | YoY | Direction | In base IRR? |
|-----------|--------|-------|-----|-----------|--------------|
| Bitcoin spot (USD) | 76209.859375 | 2026-09-17 | -34.6% | down | no (context) |
| Network hash rate (EH/s) | 873.9874431305159 | 2026-09-17 | -19.7% | down | no (context) |
| Mining difficulty (index) | 127450789715843.1 | 2026-09-17 | n/a | flat | no (context) |
| Avg transaction fees per block (USD) | 349.7329 | 2026-09-17 | n/a | flat | no (context) |
| Hashprice (USD/PH/day) | 0.039297 | 2026-09-17 | n/a | flat | no (context) |
| Breakeven power cost at 30 J/TH ($/kWh) | 0.0546 | 2026-09-17 | n/a | flat | no (context) |

## Hauck reconstructed cost floor

ASIC vintage mix at $0.05/kWh and 60% power share. Not US residential power. Not in Lawrence base IRR.

| Band | USD |
|------|-----|
| Spot | $76,210 |
| Electricity only | $34,261 |
| Average-fleet all-in | $57,101 |
| SOTA cash | $42,728 |
| SOTA + 25% ROIC | $89,288 |
| Mixed 2028 floor | $138,184 |
| Mixed 2032 floor | $342,606 |
| Naive 2× 2028 (labeled scenario) | $114,202 |

**Miner stance:** above_fleet_floor_below_sota_roic. Average fleet is cash-profitable at this spot. New state-of-the-art machines with a 25 percent ROIC hurdle are not earning that return.


Source: `_system/reference/market-data/crypto/manifest.json` and `dashboard/data/hk_snowball_model.json`.
