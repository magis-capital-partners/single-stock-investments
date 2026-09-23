# Hauck / HK bitcoin cost-of-production model vs our snowball overlay

**Date:** 2026-09-17
**Status:** Implemented 2026-09-17. Context only. Does not enter Lawrence base IRR or a Power Zone contract.
**Sources:** FRMO 2026 Annual Meeting (2026-09-10); Horizon Kinetics Q2 2026 Commentary (July 2026), section *What's With the Price of Bitcoin?* / *The Supply Side of Bitcoin's Value*; `_system/scripts/btc_cost_of_production.py`; `_system/scripts/build_hk_snowball_model.py`.
**Live reconstruction:** `FRMO/research/hauck_btc_cost_reconstruction_2026-09-17.md`.

Bregman named the work: Matt Hauck (Winland CEO, former Horizon Kinetics employee) built a supply-side cost-of-production model. HK published **part** of it in the Q2 2026 commentary and said the fuller version is on horizonkinetics.com. The annual-meeting remarks add method detail that the commentary summarizes but does not fully specify.

## What their model actually says

### 1. Price is bounded below by the *average* miner's all-in cost, not by hashrate

Hashrate and "hashing network effort" charts are a **demand-side / security proxy**. Bregman was explicit that those overlays are *not* cost of production. Hauck's model is the supply-side reconstruction: what it costs the *global mixed fleet* to produce one coin.

Gold-miner rule: if spot stays below cost of production, miners shut in. If that happens at system scale, the blockchain stops. So long as anyone wants bitcoin, spot cannot remain below the fleet's all-in cost for long.

### 2. Cost identity (what they actually compute)

From the Q2 commentary, reconstructed:

1. Build (or take) a historical **network electricity-consumption** schedule. They built their own. Cambridge Judge (CBECI) is the public analogue.
2. Divide by known **network hashrate** to get **fleet-average efficiency** (joules per terahash). Not the newest rig. The whole installed base: old machines still running plus state of the art.
3. Multiply by **electricity price** to get electricity cost per coin.
4. Gross that up because electricity / hosting is only about **60%** of all-in cost. The other 40% is ancillary opex plus rapidly depreciating ASICs, treated as a normalized expense.
5. Coins per day = 144 blocks × current subsidy (halves every four years).

In words:

> All-in cost per coin = (network watts × hours × dollars per kWh) / coins mined that day / 0.60

The commentary chart uses a flat **$0.05/kWh**. They say $0.04 or $0.06, and 55% vs 60% power share, do not change the shape. They claim those figures sit close to Winland's real-world observations.

### 3. What Hauck added beyond the published chart (annual meeting)

These are the pieces Bregman said were *not* in the simplified hashrate overlay and only partly in the commentary:

| Input | What they did | Why it matters |
|---|---|---|
| ASIC generations | Went back through successive mining-rig models, including current state of the art | Efficiency is a *history*, not a constant 16 J/TH |
| Mixed fleet | The global fleet is never all new; older, thirstier machines stay on | Average J/TH is worse than the brochure number |
| Global power price | Annual historical **global** cost of electric power, not a US residential series | Miners do not pay $0.20/kWh household rates |
| Granularity | Spreadsheets with hundreds to thousands of notes | Bottom-up, not a one-line identity |
| Chart form | Area chart of **annual cost of production**, with spot oscillating around it | The empirical claim: price hugs the cost floor between halvings and spikes at halvings |

### 4. Published numerical claims (Q2 2026 commentary)

These are the only numbers HK actually printed. The meeting did **not** give a dollar target.

| Claim | Number | Basis |
|---|---|---|
| Current all-in cost (average fleet) | **$65,000** | Electricity at $0.05/kWh, 60% power share, current average efficiency |
| Next-halving cost (2028-04-15) | **$130,000** | Double the current all-in because subsidy halves and operating costs do not |
| Post-halving price with miner return | **~$225,000** | 75% premium above $130,000 (time and risk; they could do something else) |
| Supply-side 2028 band | **$150,000–$250,000** | Same machinery, rounded |
| Latest-rig all-in *with 25% ROIC* | **~$117,000 or ~$149,000** | Two current SOTA models; this is **not** cash cost; it includes a 25% annual return (midpoint of breakeven and 50%) |
| Demand-side 2028 | **$270,438.05** | Power law \(P(t)=A t^k\) with \(k\) a touch under 6 (Metcalfe \(t^2\) × snowball volume \(t^3\)) |
| Halving cost drift, all else equal | **~19%/year** | Doubling every four years |
| Network hashrate, last five years | **10×** | Security / Metcalfe proxy, not the cost model |

Bregman at the meeting: in **about 24 months** the price will be "a lot higher" (that is the April 2028 halving window). Looking out **six years** the compounding is "mind blowing." He did not publish a six-year dollar figure. He also said he does not know if it will happen.

### 5. Economic reading, not just the spreadsheet

- Bitcoin is still early. If it becomes merely a parallel currency (dollar, euro, bitcoin), the mining industry that secures the chain has to operate at a much larger scale. Think global money supply, not today's hashprice.
- That scale path is **intrinsic compounding** on the supply side (halvings raise cost) plus network adoption on the demand side. Cost of production is the floor. The power law is the path above it.
- Public miners mostly destroyed capital by buying rigs at cycle peaks, then pivoted to AI when they could no longer issue equity accretively. Winland's edge is gradual deployment only when capital can be recovered, and accumulating coins per share from operating profit. That is capital allocation, not a different physics. It does tell you the **marginal** cost that should set the floor is the patient miner's cost, not the promotional miner's.

### 6. What they did **not** claim

- They did not publish Hauck's full ASIC-by-ASIC series or the electricity time series.
- They did not give a 24-month or 6-year **price target** in dollars at the meeting.
- They did not say SOTA efficiency is the right number for the floor. They used the **average** fleet, then showed SOTA-plus-ROIC as a separate, higher band.
- Hashrate-on-price charts are a different model (demand / security). Do not fold them into the cost floor.

## Where our model stands today

Live snapshot from `dashboard/data/hk_snowball_model.json` (as of 2026-09-17), **after** the supply-side rebuild:

| Piece | Ours now | HK published |
|---|---|---|
| Spot | $76,210 | n/a |
| All-in cost | **$57,101** (ASIC mix, 14.7 J/TH, 874 EH/s) | $65,000 at ~16 J/TH / ~915 EH/s |
| 2024-04-20 all-in | $66,497 | ~$65,000 identity |
| 2023-08 all-in | $19,855 | Far above the old constant-16 ~$11k |
| Mixed 2028 floor | $138,184 | $130,000 naive 2× |
| Naive 2× 2028 | $114,202 | $130,000 |
| Mixed 2032 floor | $342,606 | Not published |
| SOTA + 25% ROIC | $89,288 | ~$117k / ~$149k on two models |
| 2028 premium (1.75× mixed) | $241,823 | ~$225,000 on naive $130k |
| 2028 demand path | still ~half of HK | **$270,438** |
| Demand exponent \(k\) | 4.0 constrained | "a touch less than 6" |
| Efficiency | **Time-varying ASIC vintage mix** | Time-varying fleet average |
| Electricity | $0.05 HK-comparable; $0.04 / $0.06 in JSON | Commentary chart uses $0.05 |
| Hashrate history | Mempool + blockchain.info (2009+) | Full history plus consumption |
| Power share | 0.60 (0.55 / 0.70 in JSON) | 0.60 (sensitivity 0.55) |

The old $65k match was **calibration**. Live all-in is now reconstructed. Lower hashrate and a slightly more efficient mix print $57k instead of $65k. The 2024 halving-day reconstruction ($66.5k) sits next to their identity.

CBECI GUESS was too thirsty versus HK $65k and goes stale after 12 Nov 2025. Primary path is ASIC mix; CBECI remains a comparison series.

### The actual failure (pre-rebuild)

Hold efficiency and $/kWh constant and all-in cost becomes:

> cost(t) ∝ hashrate(t) / subsidy(t)

That is a **scaled hashrate chart**. It is exactly the overlay Bregman said is *not* cost of production.

That is why the old 2023 cost path printed ~$11k. A 16 J/TH fleet in 2023 is fantasy. The reconstruction now prints ~$19.9k in August 2023.

**Shipped 2026-09-17:** time-varying ASIC mix, CBECI comparison CSVs, kWh / power-share / fleet sensitivities in JSON, 24-month and 6-year scenario fan (naive 2× labeled), dashboard orange area plus SOTA+ROIC, overlays on FRMO / MSTR / MARA / CMSG. Demand \(k\) left alone. Remaining open diligence: global miner-weighted electricity survey, public-miner 10-Q calibration, CBECI stale after 2025-11-12.

## Plan: rebuild the supply side so it is actually Hauck's model

Keep the demand power law as a **separate** overlay. Rebuild supply as a dated, auditable cost path. Do not auto-promote any of this into base IRR.

### Phase 0 — Data (this is the whole game)

| Series | Why | Source to try first | Fallback |
|---|---|---|---|
| Full hashrate history (not 3y) | Denominator of efficiency | mempool `hashrate/3y` is insufficient; use Cambridge CBECI or blockchain.info `hash-rate` all-time | CoinMetrics / mempool longer window if added |
| Network electricity consumption (TWh) | Numerator of fleet J/TH | Cambridge CBECI `E_hat` / mining electricity | Reconstruct from ASIC catalog × hashrate |
| Fleet-average J/TH over time | The missing state variable | CBECI implied efficiency, or consumption / hashrate | ASIC-mix reconstruction below |
| ASIC generation catalog | Hauck's "successive models" | Bitmain / MicroBT spec sheets by release date: J/TH, TH/s, TDP, street price | Hashrate Index / ASIC Miner Value historical listings |
| Mixed-fleet weights | Not all SOTA | Assume survival curve: new shipments (vendor + miner 10-Qs) displace old rigs over 3–5 years | Three buckets: SOTA / mid / tail, weights from CBECI hardware distribution if published |
| Global miner electricity ($/kWh) | Hauck's annual global power series | Cambridge default $0.05 as **one** scenario; Hashrate Index / CoinShares miner surveys; IEA industrial electricity | EIA industrial, **not** our `electricity_price_us.csv` residential series |
| Subsidy + fees | Coins and extra revenue per day | We already have the subsidy schedule; add fee history (mempool / blockchain.info) | Constant 144 blocks/day |
| Public-miner 10-Q costs | Calibration, not the floor | MARA, CLSK, RIOT, HUT, IREN cash cost / J/TH / power | Winland / CMSG when consolidated |

Deliverable: `_system/reference/market-data/crypto/` CSVs:

- `btc_hash_rate_eh.csv` extended to origin (2011+)
- `btc_network_twh.csv`
- `btc_fleet_jth.csv`
- `btc_miner_kwh_usd.csv` (global miner-weighted, with scenario tags)
- `asic_generations.json` (model, release date, J/TH, TH/s, watts)
- `btc_all_in_cost_usd.csv` (the orange area)
- `btc_electricity_only_cost_usd.csv`

### Phase 1 — Reproduce the orange area chart

Identity, dated, no constants except where labeled `[Assumption]`:

```
fleet_jth(t)     = network_watts(t) / hashrate_ths(t)
                 = mix_i weight_i(t) * jth_i
elec_per_coin(t) = hashrate(t) * fleet_jth(t) * 24h * kwh_price(t) / coins_per_day(t)
all_in(t)        = elec_per_coin(t) / power_share(t)     # 0.60 base, 0.55 high-efficiency
sota_cash(t)     = same with jth = best shipping model
sota_roic(t)     = sota_cash(t) grossed for 25% annual ROIC on capex
```

Acceptance test: overlay `all_in(t)` on `btc_spot_usd`. Between halvings, drawdowns should approach the area, not sit at 1/5 of it. Current print should land near **$65k** at $0.05/kWh without hard-coding 16 J/TH. If it doesn't, the fleet mix or kWh series is wrong, not the identity.

Sensitivities to ship in the JSON, not in the narrative:

- kWh: $0.04 / $0.05 / $0.06 / live survey
- power share: 0.55 / 0.60 / 0.70
- fleet: average / SOTA cash / SOTA + 25% ROIC

### Phase 2 — Forward 24 months and 6 years without naive doubling

HK's $130k is "all else equal." Hauck's model says all else is not equal. Project three states to 2028-04-15 (the meeting's "24 months") and to ~2032 (two halvings, the "six years"):

| Case | Efficiency | Electricity | Subsidy | What it is |
|---|---|---|---|---|
| HK naive | freeze today's average J/TH | freeze $0.05 | 1.5625 in 2028, 0.78125 in 2032 | Recovers $130k then ~$260k |
| Efficiency deflation | J/TH keeps falling on the historical ASIC curve | freeze $0.05 | same | Cost rises **less** than 2× per halving |
| Power inflation | freeze or slow J/TH gains | miner kWh up as AI bids for the same interconnects | same | Cost rises **more** than 2× |
| Mixed (base) | slow J/TH improvement (fleet lag, not brochure) | kWh up modestly | same | The one to plot |

Premium band stays 1.75× all-in (HK's 75% miner return). Publish the band, not a point target.

Do **not** invent a 6-year dollar figure and attribute it to Hauck. He did not give one. Show the compounding of the cost floor and, separately, the demand \(t^k\) path.

### Phase 3 — Wire into the existing snowball builder

`build_hk_snowball_model.py` changes:

1. Stop using constant `efficiency_j_th=16` for history. Read `btc_fleet_jth.csv`.
2. Stop using constant `$0.05` for history. Read `btc_miner_kwh_usd.csv`. Keep $0.05 as the HK-comparable scenario.
3. Replace `cost_curve`'s backward doubling with the reconstructed path. Keep the 2× **projection** as a labeled scenario, not as fake history.
4. Add series: electricity-only, all-in, SOTA+ROIC, premium band.
5. Extend mempool hashrate fetch from `3y` to full history (or merge CBECI).
6. Leave demand \(k\) alone until a separate calibration pass. Mixing a better cost floor into a badly constrained power law will just confuse the dial.
7. Tests: (a) 2026 all-in within ~10% of $65k at $0.05 and CBECI efficiency, **without** a hardcoded 16 J/TH; (b) 2023 all-in is *not* $11k; (c) cost path is not a scalar multiple of hashrate once J/TH varies.

Dashboard: the orange area vs blue price is the chart that matters. The current step-function and the $65k badge can stay as the "HK commentary markers."

### Phase 4 — Use it, still as context

Once the path exists:

- FRMO / MSTR / MARA / CMSG overlays can show **spot vs reconstructed floor** and **spot vs SOTA+ROIC**, instead of hashprice at a single 30 J/TH.
- Miner stance: if spot is at the average-fleet floor, promotional public miners with worse power and newer unpaid capex are underwater. That is the HK inversion.
- Do not put Hauck's 2028 $150–250k band, or our $142k demand fit, into a Lawrence ledger.

## Implementation order (smallest change that actually changes the answer)

1. Pull CBECI hashrate + electricity + implied J/TH. This alone kills the scaled-hashrate bug.
2. Build `btc_all_in_cost_usd.csv` with $0.05 and 60% share so we can plot the orange area against our existing spot series.
3. Only then add the ASIC catalog and a time-varying kWh series. Those refine the level; step 1–2 fix the **shape**.
4. Then replace the naive 2028 2× with scenario fan-out.
5. Last, revisit demand \(k\). That is a different model.

## Open diligence

- Full Hauck spreadsheet is not public. Reproduce from CBECI + ASIC specs; do not wait for horizonkinetics.com to post the xlsx.
- Confirm whether Q3 2026 commentary (not yet in the vault) adds numbers beyond Q2. Meeting on 2026-09-10 pointed at "the most recent quarterly commentary," which is Q2 (July 2026) unless a later file appears.
- Global miner-weighted electricity is the weakest public series. Until a survey series is in hand, keep $0.05 as the HK-comparable case and show a band, not a single kWh path.
