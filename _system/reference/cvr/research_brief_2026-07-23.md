# CVR research brief

**Date:** 2026-07-23  
**Author:** Marvin  
**Status:** Preliminary corpus + synthesis for master plan  
**Audience:** Human design review before building a CVR agent / sleeve

---

## 1. What a CVR is (two different animals)

Do not mix these. The literature and the market use the same acronym for different payoffs.

| Type | Payoff | Typical use | Tradeable? | Relevance to us |
|------|--------|-------------|------------|-----------------|
| **Price-protection CVR** (classic academic) | Cash/stock if *acquirer* share price falls below a floor (issuer put) | Stock-financed deals, restructurings | Sometimes | Historical theory; rare in current biotech deals |
| **Event / milestone CVR** (modern deal practice) | Cash if FDA approval, sales threshold, reserves, litigation win, etc. by a hard date | Biotech, increasingly mining / tech / PE take-privates | Usually **non**-tradeable; a minority are registered OTC | **Primary focus** for ABMD/MRTX/PRVL and the agent idea |
| **Private earnout** | Same economics, private contract | Private M&A | No | Math cousin; DiVA papers helpful for payout modeling |

**Fact:** Wachtell (2025) and Accelerate (2025–26) both note a sharp rise in public-company CVR usage; most new CVRs are non-tradeable.  
**Inference:** The investable set for a *secondary* CVR sleeve is much smaller than the set of “deals that mention CVR.” The agent must split **pre-close deal arb (CVR as free option in the spread)** vs **post-close tradeable CVR**.

---

## 2. Why issuers use them

### Academic (price-protection / signaling)

Chatterjee & Yan (SSRN 2003; JFQA 2008) model the classic CVR as a way for a higher-value bidder facing asymmetric information to *signal* type. Predictions (empirically supported in their sample):

1. Announcement returns for CVR-inclusive packages beat plain stock deals.  
2. Firms with worse information asymmetry are more likely to offer CVRs.  
3. Cash-constrained firms prefer CVRs to cash.

**Opinion:** Useful for understanding *why* a board accepts contingent paper; less useful for pricing a biotech milestone CVR.

### Empirical deal-completion (event CVRs)

An empirical review (~1,800 US deals, 41 CVRs) estimates that including a CVR raises deal-completion probability by roughly **14–22** percentage points (matched Probit). That is a *bidder/target negotiation* result, not a secondary-holder return result.

### Practitioner (modern event CVRs)

Cleary, Wachtell, Cooley surveys: CVRs bridge valuation gaps when the disputed value is a binary or delayed milestone (drug approval, ARR, mineral reserves). Typical negotiated levers:

- Milestone definitions (objective vs mushy)  
- **Commercially reasonable / diligent efforts** standard (objective peer vs subjective “same as our own programs”)  
- Tradable vs non-tradeable  
- Duration / outside date  
- Partial vs all-or-nothing stacks  
- Holder threshold to sue  

---

## 3. Historical “returns” and base rates (priors for the agent)

These are **practitioner databases**, not peer-reviewed return series. Treat as priors with wide error bars.

| Source | Sample | Finding | Caveat |
|--------|--------|---------|--------|
| Accelerate / AlphaRank (Nov 2025 primer) | Market-implied CVR value at close (~15y track) | Market prices ~**$0.15 per $1** max payout | Backed out from target price vs cash/stock consideration |
| Accelerate (same) | Resolved CVRs with payout data | Average realized ~**$0.54 per $1** | Spotty; selection / survivorship |
| Accelerate (May 2026 follow-up) | 84 CVRs since 2013; payout data on 26 | Average ~**$0.52 per $1** | Same caveats; wide 0–100% range |
| p05 / Cleary-cited stats (secondary writeups) | Life-sciences CVRs | ~**33%** any payout; ~**13%** full payout; litigation ~**30%+** of listed CVRs | Heterogeneous sources; verify before hardcoding |
| Edwards (2020, LES / SSRN) | BiosciDB biopharma | ~**9%** of acquisitions/asset purchases had CVR/earnout; rising to ~**12%** in one recent year | Frequency, not secondary IRR |
| Wachtell / Deal Point Data (2025) | Public M&A | 27 CVR deals YTD 2025 vs 7 / 18 / 9 in 2024 / 2023 / 2022 | Issuance boom, not returns |

**Inference for valuation:** A naive market-implied success probability of `price / max_payout` (your “10% over bid → 10% success” idea) is a useful *display* number, but it:

1. Ignores time value (milestones often 2–7 years out).  
2. Ignores multi-milestone stacks and partial payouts.  
3. Ignores litigation optionality and acquirer incentive to miss.  
4. May systematically understate fair value if Accelerate’s ~$0.50 realized vs ~$0.15 priced gap is real.

**Opinion:** Edge, if any, is in (a) reading the CVR agreement + efforts clause + milestone objectivity, (b) independent probability of the *science/ops* event, and (c) liquidity / custody for tradeable names — not in the raw 15¢ print alone.

---

## 4. Risk map (what kills CVR holders)

1. **Milestone miss** — Celgene/BMS-style hard date failure (classic example: full wipe when a deadline is missed by days).  
2. **Efforts games** — acquirer deprioritizes the asset; CRE litigation is common and settlements often haircut claims.  
3. **Non-transferability** — most holders cannot exit; secondary market only for registered CVRs.  
4. **Illiquidity / OTC** — even tradeable CVRs can be unquoted for months.  
5. **Unsecured claim** — usually junior contractual right, not secured debt.  
6. **Information orphan** — after delisting, updates hide in acquirer 8-K/10-Q footnotes.  
7. **Fairness-opinion theater** — board process does not equal probability-weighted value of the CVR stub.

---

## 5. Mapping to your five product ideas

| Your idea | What research supports | Design implication |
|-----------|------------------------|--------------------|
| 1. Pull announcements + risk-arb sites + SEC links + timeline/IRR | AlphaRank screener; SEC DEFM14A / S-4 / 8-K; Wachtell structuring fields | **Two pipelines:** pre-close deals *with* CVR language; post-close tradeable CVRs |
| 2. Market-implied success from price vs max payout | Accelerate $0.15 vs $0.54 gap | Show `p_mkt = price/max` **and** `p_hist_prior` and `p_marvin`; never only one |
| 3. Fairness opinion + thoughts on ultimate value | Always in merger proxy | Link DEFM14A fairness appendix; separate **board DCF** from **CVR stub EV** |
| 4. Buy-price IRR + max size / max loss + accumulate to close | Standard risk-arb sizing; Pabrai loss-budget | Sleeve rules: max $ loss per CVR, max book %, no average-up past loss budget |
| 5. Prior academic / practitioner data | This folder | Seed `cvr_base_rates.json`; refresh when human adds papers |

---

## 6. Fit inside current SSI / Marvin stack

**Already present**

- Tickers: `ABMD.CVR`, `MRTX.CVR`, `PRVL.CVR` (stubs; valuation is price stub / evidence-blocked).  
- Lenses: `payoff_lens: event` → `special_situation_lens.md` (annualized return when dated).  
- MOI Part H covers special sits but **does not** yet define CVR-specific fields.  
- Index membership: CVRs marked ineligible (correct).

**Gaps**

- No `instrument_type: cvr` contract.  
- No CVR agreement extract schema (milestones, dates, CRE, tradeable flag).  
- No sleeve-level position / loss-budget tracker.  
- No mechanical harvest of “CVR” from 8-K / merger proxies.  
- Special-situation lens does not mention CVRs explicitly.

**Recommended classification defaults for tradeable event CVRs**

| Field | Suggested default |
|-------|-------------------|
| `archetype` | `optionality` or dedicated `cvr` if governance allows |
| `payoff_lens` | `event` |
| `irr_method` | `binary_milestone` or `scenario` |
| `lawrence_bucket` | `other` / special sit |
| `stance` | `watch` until agreement + probability ledger complete |

---

## 7. Source confidence

| Claim | Confidence | Source tier |
|-------|------------|-------------|
| CVR issuance rising in 2025 | High | Wachtell / Deal Point; Accelerate |
| Most new CVRs non-tradeable | High | Wachtell |
| Market prices ~15¢ / $1; resolved ~50¢ / $1 | Medium | Accelerate proprietary DB (not audited here) |
| ~1/3 any payout, ~1/8 full | Medium-low | Secondary writeups citing Cleary/life-sciences surveys |
| CVRs raise deal completion odds | Medium | Small-N academic / thesis samples |
| Systematic free lunch | **Opinion / unproven** | Needs our own closed-trade ledger |

---

## 8. What was downloaded vs blocked

**Downloaded to** `_system/reference/cvr/`

- Cleary Gottlieb pharma CVR bites (PDF)  
- Wachtell CVR guide (PDF)  
- DiVA earnout expected-payout thesis (PDF)

**Blocked (need human click-through)**

- SSRN Chatterjee/Yan and Edwards (Cloudflare)  
- Academia empirical review PDF  

See `README.md` for URLs.

---

## 9. [OPEN DILIGENCE]

1. Confirm sleeve thesis: **pre-close arb with CVR kicker** vs **post-close tradeable CVR book** vs both.  
2. Accept Accelerate base rates as provisional priors, or require our own reconstruction from SEC Form 425 / 8-K payout notices before any capital.  
3. Approve adding a thin framework file (governance checklist) vs extending `special_situation_lens.md` only.  
4. Manually drop SSRN PDFs into `papers/` when convenient.  
