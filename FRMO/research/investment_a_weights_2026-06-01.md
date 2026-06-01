# Investment A look-through weights — FRMO

**Date:** 2026-06-01  
**Filing anchor:** `2026-02-28_Quarterly_Report.pdf` (Investment A **$308,984,000**, **82%** of FRMO-attributable equity)  
**Measurement date for marks:** **2026-02-27** (Feb 28, 2026 was Saturday)  
**Used in:** `FRMO/research/book_estimate_config.json`

---

## Method

Investment A is a consolidated equity position; FRMO does **not** publish a full look-through table. We proxy **mark-to-market roll-forward** with **weight_pct** slices of `$308.984M` that sum to **100%**, each tied to a listed quote on **measurement date** (not a later Stooq date).

Weights are **Marvin estimates** from public HK/FRMO sources — not filing facts. Replace when FRMO publishes look-through.

---

## Weight table (base case)

| Holding | Weight % | Filing slice ($M) | Price source (2026-02-27) | Evidence |
|---------|----------|-------------------|---------------------------|----------|
| **TPL** | **52%** | 160.67 | Yahoo TPL ~$524.29 | HK Q4 2024 Commentary: TPL **59%** of flagship fund; FRMO Q3 FY2026 call: TPL largest holding, +82% in quarter; LCI/fintel HKAM **~44%** public book TPL. **52%** = haircut vs 59% for consolidated mix. |
| **GBTC** (crypto sleeve) | **14%** | 43.26 | Yahoo GBTC ~$51.13 | HK Q4 2024: **cryptocurrency funds 17%**; LCI: HK crypto exposure substantially GBTC. **14%** = slight haircut. |
| **MIAX** (inside funds) | **8%** | 24.72 | Yahoo MIAX ~$42.60 | FRMO call: MIAX strong YTD; **separate** from direct MIH line in config. |
| **WPM** | **5%** | 15.45 | Yahoo WPM ~$163.65 | LCI HKAM top-five / fintel peer list. |
| **ICE** | **4%** | 12.36 | Yahoo ICE ~$164.13 | LCI HKAM top holdings. |
| **FNV** | **3%** | 9.27 | Yahoo FNV ~$280.61 | LCI HKAM top holdings. |
| **HKHC** (fund overlap) | **5%** | 15.45 | Yahoo HKHC ~$33.00 | HK listed affiliate; **not** same as FRMO 4.42% direct equity-method line. |
| **Residual** | **9%** | 27.81 | static | Cash, private names, other fund positions until filed look-through. |
| **Total** | **100%** | **308.98** | | |

---

## Sources (online / approved context)

| Source | Claim used |
|--------|------------|
| [Horizon Kinetics Q4 2024 Commentary](https://horizonkinetics.com/app/uploads/Horizon-Kinetics-Q4-2024-Commentary_Final.pdf) | TPL **59%**, crypto funds **17%** of flagship portfolio |
| [LCI SLGD / HKAM](https://lemoncakesinvesting.substack.com/p/slgd-scotts-liquid-gold-horizon-kinetics) | HKAM public book **~44% TPL**; energy **42%** from TPL; crypto via **GBTC**; top names WPM, ICE, FNV |
| FRMO Q3 FY2026 earnings / [Ticker Report summary](https://www.tickerreport.com/banking-finance/13413801/frmo-q3-earnings-call-highlights.html) | TPL largest; MIAX strong; HKHC +20% in quarter |
| `FRMO/research/cross_check_approved_substacks_2026-05-26.md` | TPL + GBTC concentration in FRMO book (Stahl/LCI) |

---

## Not in Investment A proxy (separate config lines)

| Item | Where modeled |
|------|----------------|
| Direct MIH / MIAX **$13.917M** | `mih_miax` listed_shares (implied **~326,700** sh at **$42.60** on 2026-02-27) |
| FRMO **4.42% HKHC** equity method | `hkhc_equity` ownership_market_value |
| CMSG stake **$0.742M** | `cmsg_stake` manual_price |
| Investment B (South LaSalle LP) | Inside filing anchor / static remainder |

---

## MIAX date alignment (corrected)

**Wrong (prior dives):** $13,917,000 ÷ **$51.42** (Stooq **2026-05-22**) → 270,563 shares.

**Correct:** $13,917,000 ÷ **$42.60** (Yahoo MIAX **2026-02-27**) → **~326,690** shares.

See `_system/frameworks/mark_date_alignment.md`.

---

## [HUMAN REVIEW]

- Confirm HKHC **shares_outstanding** (22.4M assumed).
- Replace weights when FRMO files Investment A look-through.
- CMSG filing_price at measurement date is approximate (OTC).
