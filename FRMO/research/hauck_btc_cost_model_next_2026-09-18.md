# Next: make the Hauck cost model more accurate, precise, general, and understandable

**Date:** 2026-09-18
**Status:** Plan. Context only. Does not enter Lawrence base IRR.
**Depends on:** `FRMO/research/hauck_btc_cost_model_plan_2026-09-17.md` (implemented) and `FRMO/research/hauck_btc_cost_reconstruction_2026-09-17.md`.

The supply identity is now right. Cost is no longer a scaled hashrate chart. The remaining work is to stop mixing *today* with *later*, to replace constants with dated series, and to keep demand as a separate overlay.

## What is already true

As of 17 Sep 2026, ASIC vintage mix at $0.05/kWh and 60% power share prints:

- Average-fleet all-in **$57,101** (14.7 J/TH, 874 EH/s)
- 2024-04-20 reconstruction **$66,497** (next to HK's $65k identity)
- Mixed 2028 floor **$138,184**; naive 2× **$114,202**
- SOTA cash **$42,728**; SOTA + 25% ROIC **$89,288**

HK published $65k at ~16 J/TH and ~915 EH/s. We did not hard-code 16 J/TH. Demand \(k=4\) is still a different model.

## The display bug this plan sits on

The right-rail "Hauck all-in" was reading the last *smoothed chart point*, which blended today's $57k into the 2028 mixed path and printed ~$106k. Cards used `supply.bands`. Fixed 18 Sep 2026: rail uses today's bands; history is smoothed without forward points; mixed 2028/2032 is a dashed projection; the 2017–2028 zoom ends at 2028.

## Four jobs (do them in this order)

Do not mix them. Each has a different failure mode.

### 1. Understandable (small, first)

The reader should never wonder whether a number is *today*, *HK commentary*, or *a scenario*.

| Change | Why |
|---|---|
| Rail and cards always read `supply.bands` for today | One source of truth |
| Historical floor vs mixed projection as two lines | Stops the $106k smear |
| 2017–2028 zoom must not include 2032 | The button lied |
| Caption under the chart: "Red is reconstructed all-in. Dashed red after today is mixed_base, not history. Pink dots are HK quotes, not our model." | Chart without a sentence is a trap |
| Show kWh / power-share / fleet sensitivities as a 3-row table on the panel | JSON already has them; the page does not |
| Label naive 2× as "HK all-else-equal," not as the floor | Matches the meeting |
| Miner stance sentence stays under the cards | "Above fleet floor, below SOTA+ROIC" is the economic read |

Do **not** add a 6-year dollar target and attribute it to Hauck. He did not give one.

### 2. Precise (stop silent averaging)

Accuracy is the identity. Precision is not blending across events.

| Change | Why |
|---|---|
| Never smooth across a halving date or a `forward_*` event | 14-point window is how $57k became $106k |
| Keep daily prints at halving windows; monthly sample is fine elsewhere | The step lives in one week |
| Publish a residual vs HK $65k as a *diagnostic*, not a target to fit | If we retune J/TH to hit $65k we are back to calibration |
| Tornado on the panel: $0.04 / $0.05 / $0.06 and 0.55 / 0.60 / 0.70 | Shape is robust; level is not |
| Keep CBECI GUESS / MIN / ASIC mix as three J/TH series | Disagreement is information |
| Fees: add fee coins to the denominator as a *sensitivity*, not the base | HK identity uses subsidy; fees raise coins per day and lower cost |

### 3. Accurate (replace remaining constants)

These are the inputs Hauck had and we still fake.

| Input | What we use now | What to replace it with | Acceptance |
|---|---|---|---|
| Miner kWh | Flat $0.05 HK-comparable | Annual global miner-weighted series: CoinShares / Hashrate Index surveys, IEA industrial, **not** US residential `electricity_price_us.csv` | $0.05 remains one labeled scenario |
| Fleet mix | Hashrate-at-release × 5-year linear life × PUE 1.1 | CBECI hardware distribution when it updates; miner 10-Q fleet J/TH as a check; survival curve from scrap / resale listings | 2024-04-20 all-in stays near $65k *without* pinning J/TH |
| ASIC catalog | Spec sheets + [Assumption] street $/TH and 2026 S23 Hyd | Refresh from Bitmain / MicroBT pages; Hashrate Index historical listings for $/TH | SOTA+ROIC lands in HK's ~$117k / ~$149k neighborhood at their hashrate, or we document why not |
| CBECI TWh | Ends 12 Nov 2025 | Re-fetch; if Cambridge is stale, ASIC mix stays primary and we stamp `cbeci_through` | No cliff in the orange area at the last CBECI date |
| Public-miner costs | Unused | MARA, CLSK, RIOT, HUT, IREN, CMSG cash cost / J/TH / power from 10-Qs | Calibration overlay, **not** the floor. Promotional miners should sit *above* the fleet average |
| Difficulty history | Single-day snapshot | Full difficulty series (we already store a CSV; use it) | Cross-check vs hashrate, not a second floor |

The gold-miner rule still holds: the floor is the *average* fleet, not SOTA, not the worst public miner.

### 4. General (same machinery, other questions)

Keep one identity. Reuse it. Do not invent a second model.

| Extension | How | What not to do |
|---|---|---|
| Miner vs treasury vs holdco | Already tagged in `holdings_crypto.json`. Stance text differs; the floor does not | Do not put the floor into MSTR or FRMO base IRR |
| Scenario fan as a first-class object | Dashboard toggle: naive HK / efficiency deflation / power inflation / mixed | Do not pick one 2028 number and hide the fan |
| Demand power law | Separate pass: origin, fit window, constrained \(k=4\) vs HK \(k≈6\) | Do not "fix" demand by stuffing the cost series into \(t^k\) |
| Other PoW | Same watts × hours × kWh / coins identity if we ever need it | Out of scope until a holding needs it |
| Winland / CMSG | Patient-miner cost as a *marginal* check on the floor | Do not replace the global fleet with one company's books |

## Implementation order

1. Display contract (rail = today, projection dashed, 2017–2028 ends at 2028). **Done in this session.**
2. Panel: sensitivity table + one-sentence caption. No new data.
3. Stop smoothing across halvings. Unit test: last historical all-in equals `bands.all_in_usd` after downsample.
4. Miner kWh band from a real survey series; keep $0.05 as HK-comparable.
5. ASIC / CBECI refresh so 2024-04-20 and live prints stay auditable.
6. Public-miner 10-Q overlay as a scatter vs the floor.
7. Demand \(k\) calibration as its own note. Last.

## Open diligence

- Full Hauck spreadsheet is still not public. Reproduce; do not wait.
- Q3 2026 HK commentary: check the vault before changing numbers.
- Global miner-weighted electricity remains the weakest public series.
- Deploy to Pages still fails when `warrants.json` flags expired "active" series. That is unrelated, but it is how this panel reaches the live site.

## What would count as a better model

A later snapshot should still print one all-in for *today*, a fan for 2028 and 2032, and a sentence for miner stance. If those three disagree with the chart, the chart is wrong. If they only disagree with HK's $65k, we show the residual and the inputs, we do not retune J/TH until the identity matches.
