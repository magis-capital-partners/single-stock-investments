# Hauck BTC cost reconstruction (17 Sep 2026)

**Status:** Context only. Does not enter Lawrence base IRR.
**Method:** `_system/scripts/btc_cost_of_production.py` (ASIC vintage mix, $0.05/kWh, 60% power share).
**Linked plan:** `FRMO/research/hauck_btc_cost_model_plan_2026-09-17.md`.

## Live prints versus HK commentary

| Band | Reconstruction | HK Q2 2026 commentary |
|------|----------------|------------------------|
| Average-fleet all-in | **$57,101** (17 Sep 2026) | $65,000 |
| Fleet efficiency | 14.7 J/TH | Implied ~16 J/TH at ~915 EH/s |
| Network hashrate | 874 EH/s | ~915 EH/s at the print |
| 2024-04-20 all-in | $66,497 | Near their $65k identity |
| 2023-08 all-in | $19,855 | Not the old constant-16 print (~$11k) |
| Electricity only | $34,261 | ~60% of all-in |
| SOTA cash | $42,728 | n/a |
| SOTA + 25% ROIC | $89,288 | ~$117k / ~$149k on two current models |
| Mixed 2028 floor | **$138,184** | $130,000 naive 2× |
| Naive 2× 2028 | $114,202 | $130,000 |
| Mixed 2032 floor | $342,606 | Not published |
| Demand path 2028 | unchanged (k = 4.0) | $270,438 (k a touch under 6) |

The $57k versus $65k gap is hashrate (874 vs ~915 EH/s) plus a slightly more efficient mixed fleet (14.7 vs 16 J/TH). The identity is the same. We did not hard-code 16 J/TH.

Spot on 17 Sep 2026 is $76,210. That sits above the average-fleet floor and below SOTA-plus-25%-ROIC. Average miners are cash-profitable. New machines with a 25% ROIC hurdle are not earning that return at this spot.

## What this is not

- Not a 24-month or 6-year price target attributed to Hauck.
- Not a change to demand \(k\).
- Not a Power Zone contract.
- CBECI TWh ends 12 Nov 2025 and is stored as a comparison series. Primary fleet J/TH is the ASIC vintage mix.

## Overlays

FRMO, MSTR, CMSG, MARA, CLSK, GLXY get `btc_overlay.mining_economics_context` with these bands. Deep-dive refresh will render them under Bitcoin economics. Still context only.
