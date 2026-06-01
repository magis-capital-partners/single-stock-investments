# Low IRR portfolio audit — optionality & hidden value

**Date:** 2026-06-01  
**Agent:** Marvin  
**Trigger:** Human review of sub-15% Lawrence base IRRs; GOOGL and TPL flagged as surprising  
**Sources:** `{TICKER}/research/valuation.json` and latest deep dives (as of 2026-06-01)

---

## Summary

Of **25** holdings, **14** have Lawrence base annual return below **10%**; **22** are below the **15%** stance gate. Low IRR is often **correct at spot price**, not a modeling bug. Three distinct buckets:

| Bucket | Meaning | Examples |
|--------|---------|----------|
| **A. Priced for quality** | High multiple on strong cash; no hidden asset floor | TPL, CPRT, SPGI, CSGP |
| **B. Capex-cycle timing** | FCF₀ from pre-ramp year while guide implies trough | GOOGL, AMZN, META |
| **C. Needs optionality overlay** | Lawrence `full` understates; alternate metric exists or missing | FRMO, MSB (done); TPL, SJT (partial) |

**GOOGL:** Optionality is **documented but zeroed in base** (Waymo, TPU, backlog). AI inflection sensitivity **11.2%** suggests the surprise is **capex timing**, not missing narrative.  
**TPL:** **Real gap** — no segment build, no optionality overlay, no run-rate bridge. Even after fixes, **~50×** cash flow likely keeps base IRR below **15%** unless growth re-accelerates.

---

## Full low-IRR map (base case)

| Ticker | Base IRR | Archetype | Overlay status | Verdict |
|--------|----------|-----------|----------------|---------|
| **TPL** | **-1.0%** | infrastructure | None | **Gap: segment + optionality refresh** |
| **GOOGL** | **2.1%** | compounder | segment + ai_overlay | **Gap: backlog/TPU/Waymo quant; capex bridge** |
| **AMZN** | **3.6%** | compounder | segment + ai_overlay | Same as GOOGL; ads not split |
| **8697.T** | **4.7%** | croupier (peak) | None | Mid-cycle normalization appropriate |
| **META** | **5.9%** | compounder | segment + ai_overlay | Segment sum **>$633**; Lawrence vs segment mismatch |
| **3905.T** | **5.7%** | compounder | scenario only | Execution-risk DC; low IRR intentional |
| **SJT** | **5.8%** | optionality | yield_curve | Bull **19.4%**; base uses recovery curve |
| **SNOW** | **6.7%** | platform | None | Growth-at-premium; no dormant asset |
| **MSB** | **8.4%** yield* | optionality | hk_royalty_curve | *Primary metric; hold via optionality gate |
| **CSGP** | **8.6%** | platform | None | Fair price for platform |
| **CMSG** | **8.7%** | optionality | partial | Treasury option; not in Lawrence base |
| **CPRT** | **9.2%** | compounder | None | Quality compounder at full price |
| **OTCM** | **9.7%** | croupier | None | Appropriate for cycle |
| **DHR/SPGI** | **10.1%** | compounder/croupier | None | Near fair |

*MSB displays normalized distribution yield **8.4%**; yield-curve base **10.3%**; stance **hold**.

---

## GOOGL — why 2.1% and what is missing

**What the model does today**

- Lawrence base on **FY2025 FCF $5.85/sh** at **~$386** (~66× cash flow).
- Segment sum (Services + Cloud, drags burdened): **~$164/sh** at **10%** discount → implied business return **~0%** on segment assumptions.
- **Waymo / Other Bets:** **$0** terminal; **$7.5B** FY2025 op loss fully in drag.
- **Alphabet-level AI R&D:** **$16.8B** loss, no offset for future monetization.
- **AI inflection bull (sensitivity only):** normalized **$8/sh** FCF → **11.2%** 10yr return.

**Documented but not in base math** (`ai_overlay.not_in_model_requires_refresh`)

1. Cloud backlog **>$460B** — no revenue conversion schedule  
2. **TPU / custom silicon** external sales — press only  
3. **2026–2027 capex peak** then normalization — FCF₀ still FY2025  
4. Search / Services **AI monetization** — Services growth **9%** vs Q1 Search **+19%**  
5. **Blackstone JV** data-center economics  
6. **Waymo** — zero terminal by design (Speedwell/TCI discipline); bull case only if re-marked

**Synthesis:** The low IRR is **mostly intentional conservatism + capex-cycle staleness**, not absent research. The market at **$386** embeds either (a) post-capex FCF normalization toward **$8–10/sh**, (b) higher Cloud growth than segment base **25%**, or (c) option value in Waymo/TPU the model assigns **$0**. Human surprise is **reasonable** if you believe capex normalizes by **2028**; the **11.2%** sensitivity is the right mental anchor, not the **2.1%** gate.

**Recommended refresh**

- [ ] Q2 2026 10-Q: Cloud margin, capex run-rate, backlog $  
- [ ] Build **backlog-to-revenue** bridge (even rough 5-year draw) in segment Cloud  
- [ ] Separate **Services AI yield** sensitivity (Search +19% vs model 9%)  
- [ ] Waymo: bull-only terminal or external mark if disclosed  
- [ ] Do **not** silently swap FCF₀ to normalized — keep Lawrence filing-based + overlay

---

## TPL — why -1.0% and what is missing

**What the model does today**

- Single consolidated Lawrence path: **$7.91/sh** FY2025 OCF, **5%/3%** growth, **22×** exit at **~$393**.
- Implied **~50×** year-0 cash flow; **~19×** book (**$21/sh**). No book floor.
- Archetype **infrastructure**; no `segment_build`, no `optionality_gate`.

**Hidden value not quantified**

| Theme | Filing fact | In base IRR? |
|-------|-------------|--------------|
| **Water segment acceleration** | **$307.5M** FY2025 (+16% YoY); **38%** of revenue | Blended **5%** growth only |
| **Easement annuity** | **$78.2M**; 30+ yr terms, CPI escalators | Not modeled as separate lower-discount stream |
| **Q1 2026 run-rate** | OCF **$162M** Q1 (+21% rev YoY) | Uses FY2025 **$545.9M**, not **~$648M** annualized |
| **Undeveloped acreage option** | **~880k** acres; royalties on future drilling | Zero — correct for base, but no bull overlay |
| **Regulatory / water tailwind** | SSI approved note | Qualitative only |
| **Governance catalyst** | LCI post-HK note | **[HUMAN REVIEW]** only |
| **Hard-asset floor** | Book **$21/sh** vs **$393** price | **floor_pass: false** — no dhando floor |

**Run-rate sensitivity (illustrative, not in valuation.json)**

- Q1 2026 OCF **$162M** × 4 ≈ **$9.4/sh** starting cash (+**19%** vs **$7.91**).
- Same growth/multiple assumptions → rough IRR **~2–4%** (still below **15%**).
- To reach **15%** at **$393** requires either **~10%+** sustained cash growth for a decade or **multiple expansion** beyond **22×** from an already premium **50×**.

**Synthesis:** TPL low IRR reflects **paying up for a scarce toll**, not a failure to see water/royalty quality. The **analysis gap** is structural: no **segment cash-flow build** (water vs land), no **optionality overlay** for undeveloped reserves, and no **run-rate bridge**. Even with those, **15%** at spot is **heroic** unless Permian super-cycle persists.

**Recommended refresh**

- [ ] Add `valuation_overlay: segment_cashflow` — Land/Royalty vs Water paths  
- [ ] Evaluate `valuation_mode: optionality` for undeveloped-acreage bull (zero in base)  
- [ ] Run-rate sensitivity row in assumption ledger (Q1 OCF annualized)  
- [ ] Clarify archetype: **infrastructure** vs **optionality** per deep dive [HUMAN REVIEW]

---

## Other low-IRR names (brief)

**AMZN (3.6%)** — Same capex-cycle story as GOOGL. Normalized FCF **$5.35/sh** vs TTM **$0.11/sh**. AI inflection **14.2%** at **$9/sh**. **$70B+** advertising buried in segment growth, not split out.

**META (5.9%)** — Segment PV **$762/sh** vs **$633** price at **10%** discount (segment-implied **12.4%**). Lawrence consolidated lower because it uses reported **$17.91/sh** FCF without FoA gross-up. **Reality Labs** zero terminal. Messaging monetization, Llama, capex normalization in `not_in_model`.

**8697.T (4.7%)** — Croupier at **peak** cycle; normalized **¥70/sh** vs spot EPS **¥76.81**. Data monetization option mentioned, not separate overlay. Low IRR is **mid-cycle discipline**.

**SJT (5.8%)** — Already on **yield_curve**; zero distributions since May 2024. Base **5.8%** on **8yr** recovery; bull **19.4%**. Optionality framework appropriate; `dhando: none`.

**MSB (8.4% yield / hold)** — **Optionality mode working as designed.** Normalized yield **>8%** + arbitration catalyst; stance **hold** despite sub-15% Lawrence display metric.

**FRMO (21.9%)** — Contrast: **holdco SOTP** + book floor → primary metric **21.9%**, not Lawrence FCF.

**CPRT, SPGI, CSGP, DHR, SNOW** — Low IRR = **quality at full price**. No obvious dormant asset or HK curve; overlays would not change stance materially.

---

## Framework recommendations

1. **Hyperscaler bucket (GOOGL, AMZN, META):** Treat **AI inflection sensitivity** as the decision aid alongside Lawrence base; refresh after each capex guide update. Do not auto-upgrade stance until filing-backed normalization bridge exists.

2. **TPL:** Priority refresh — **segment build + optionality gate** before human overrides **watch** → **hold**.

3. **Optionality names (MSB, FRMO, SJT, KEWL, CMSG):** Stance already uses alternate metrics where configured. **SJT** may need `optionality_gate` formalization like MSB.

4. **Stance vs IRR display:** Portfolio dashboard should show **primary metric** when `valuation_mode: optionality` to avoid false "surprise" on MSB/FRMO.

---

## [HUMAN REVIEW]

- Accept **sub-15% Lawrence IRR** for quality sleeves (GOOGL, TPL) as **priced-in**, or override with documented sensitivity (AI inflection, run-rate)?
- TPL archetype: **infrastructure** vs **optionality**?
- Prioritize GOOGL vs TPL segment refresh in next Marvin cycle?

---

## [PROPOSED MEMORY]

- [PROPOSED PABRAI] Low Lawrence IRR often means **no dhando at spot**, not missing research. TPL **~50×** OCF and GOOGL **~66×** FCF are fat-pitch failures by definition; AI inflection **11%** and segment overlays are the honest bull case.
- [PROPOSED COMPANY] Portfolio low-IRR audit 2026-06-01: **14** names **<10%** base; largest gaps **TPL** (no segment/optionality overlay) and **GOOGL** (capex staleness + zeroed Waymo/TPU in base).
