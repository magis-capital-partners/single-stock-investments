# QDEL — Catalyst cross-check: POC divestiture (Jun 27, 2026)

**Date:** 2026-06-29  
**Framework:** `_system/frameworks/third_party_cross_reference.md`  
**Catalyst source:** Financial Times report via [Seeking Alpha](https://seekingalpha.com/news/4607870-quidelortho-sell-testing-unit) (Jun 27, 2026)  
**Our dive:** `QDEL/research/deep_dive_2026-06-29.md`  
**Model:** `QDEL/research/valuation_model.html`

---

## Summary

Press reports QuidelOrtho is exploring a **~$1.5 billion** sale of its **point-of-care testing unit** to reduce merger debt. Marvin treats this as an **unconfirmed event catalyst** — sized in the interactive SOTP model and option scan, **not** in base Lawrence owner-cash IRR until SEC filing.

---

## What we can verify from filings

| Fact | Value | Source |
|------|-------|--------|
| POC FY2025 revenue | **$601.6M** (-13.4% YoY) | `10-K_20260219...htm` |
| Consolidated LT debt | **$2,471.9M** | Same 10-K |
| Cash (FY25) | **$169.8M** | Same 10-K |
| FY26 EBITDA guide | **$615–630M** | Q1 FY2026 deck |
| Company confirmation of sale | **None** as of 2026-06-29 | No 8-K located |

---

## Marvin scenario sizing (independent)

| Scenario | POC proceeds | Pro forma net debt | SOTP equity / sh (base multiples) |
|----------|-------------|-------------------|-----------------------------------|
| Bear | $800M | ~$1,580M | ~$44 |
| **Base** | **$1,500M** | **~$880M** | **~$52** |
| Bull | $2,000M | ~$380M | ~$58 |

Assumptions: Labs 10× EBITDA ($346M), IH 11× ($136M), molecular option $50M, 67.8M shares. See `qdel_data.json`.

**Pro forma core business:** ~**$2,050M** revenue (Labs + IH), ~**$482M** EBITDA **[Assumption]** after removing POC contribution.

---

## Agreements with McIntyre letter (context)

| Topic | Both note |
|-------|-----------|
| Strategic lever | Division sale to pay down debt |
| POC volatility | Respiratory / flu-driven; not core franchise |
| Leverage | High but refinanced to 2030 |

McIntyre **IH sale ~$1.7B** estimate is **not** in Marvin base — no active filing evidence.

---

## Divergences (Marvin vs press / external)

| Topic | Marvin | Press / McIntyre | Marvin use |
|-------|--------|------------------|------------|
| POC value | $1.5B base scenario | FT ~$1.5B | Scenario overlay only |
| Primary IRR | $1.65/sh filings path | McIntyre ~$4/sh 2028 | **Marvin primary**; McIntyre context |
| Multiple on core | 9–11× (turnaround discount) | McIntyre 15× | Filing-implied ~5× spot; recovery to 9× in base |

---

## Synthesis (best estimate)

**[Inference]** A **$1.5B** POC sale would materially improve the risk profile even if the multiple on remaining core does not immediately re-rate. Equity value rises mainly through **debt paydown** (~$22/share of debt reduction per share) plus optional pure-play re-rating.

**Not in base IRR:** Proceeds until 8-K. **In model:** `valuation_model.html` POC slider.

**Returns statement (catalyst sensitivity):** If POC closes at **~$1.5B** and core trades at **10×** on ~**$482M** EBITDA, implied equity **~$52/share** vs **~$13.79** spot (+280%). Base Lawrence path remains **~14%** annual return on owner cash without assuming the sale closes.

## [HUMAN REVIEW]

- Verify FT report primary source  
- Confirm tax leakage and transaction costs on divestiture  
- Update base IRR if company files definitive agreement  
