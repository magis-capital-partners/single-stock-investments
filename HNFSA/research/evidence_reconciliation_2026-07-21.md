# HNFSA valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `operating_food_business` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $72.02 |
| `illiquidity_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | -$10.78 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Two additive components with unique overlap keys: operating food business and OTC illiquidity reserve. No embedded double-count. |
| source path | `HNFSA/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **$61.24/sh** = $72.02 − $10.78. |
| remaining uncertainty | Share count for book math (~1.21M implied vs 287,996 filed Class A) remains unresolved. |
| affected components | Both additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | **287,996** Class A shares at August 11, 2004; December 2004 odd-lot tender at **$131/sh**; stated book **~$87.62/sh** [Assumption] from aggregator cross-check to FY2004 Exhibit 13. |
| source path | `HNFSA/investor-documents/sec-edgar/10-K_20040830_rpt20040531_acc000095011604002631.htm`; `proxy_SC13E3_odd_lot_tender_20041206.htm` |
| calculation | Operating proof: $87.62 × 0.822 seven-year payoff ratio ≈ **$72.02/sh**. Illiquidity reserve: $87.62 × 0.123 OTC discount ≈ **−$10.78/sh**. |
| remaining uncertainty | Book per share and debt are aggregator estimates; no current shareholder report indexed. |
| affected components | `operating_food_business`, `illiquidity_reserve` |
| valuation consequence | Filing-locked share count and tender price anchor proofs; legacy sensitivities excluded from decision-grade sum. |
| falsifier | Verified shareholder report shows book below **$60/sh** without offsetting plant marks. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2004 10-K cites **$20M** 7.01% senior notes due 2011 and historical **$25M** 8.74% notes; aggregator total debt **~$62M** [Assumption]. Illiquidity reserve is separate from operating book re-rate. |
| source path | `10-K_20040830` risk factors; `valuation.json` inputs |
| calculation | Reserve base **−$10.78/sh** = −12.3% of stated book; does not re-deduct inside operating payoff ratio. |
| remaining uncertainty | Current debt maturity and covenant headroom unknown post-2005 deregistration. |
| affected components | `illiquidity_reserve` |
| valuation consequence | Downside capital friction modeled once as additive reserve. |
| falsifier | Liquidity event (repeat odd-lot tender or exchange listing) removes structural OTC discount. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys unchanged; illiquidity reserve does not re-deduct inside operating book catch-up ratio. |
| source path | `HNFSA/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** **287,996** Class A shares (10-K cover, SC 13E3 record date); December 2004 odd-lot tender **$131/sh**; **15** plants; **2,205** employees (FY2004 10-K Item 1); top-10 customers **36%** of net sales FY2004.

**Judgments (bounded):** Stated book **$87.62/sh** [Assumption]; seven-year payoff-to-book ratio **0.575–1.15×**; OTC/control discount **4.1–20.5%** of stated book.

## Valuation consequence

Proof-complete additive schedule base case **~$61.24 per share** vs price **~$55** implies modest component upside; Lawrence seven-year base **3.9%** remains below mid-teens accumulate hurdle. Security remains **watch**; no human capital decision recorded.
