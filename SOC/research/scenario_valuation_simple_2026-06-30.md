# SOC — Simple scenario valuation (Revision 2)

**Date:** 2026-06-30  
**Price today:** **$3.08** per share (NYSE close June 30, 2026)  
**Method:** Each case is one path. Every row is one assumption. All arithmetic shown.

**Primary source for refi terms:** `investor-documents/sec-edgar/424B5_20260630_rpt_acc0001628280_26_046144.htm`  
**Reserve / interest data:** `investor-documents/sec-edgar/10-K_20260227_rpt20251231_acc0001831481_26_000026.htm`

---

## What changed from Revision 1 (and why)

Revision 1 had five problems. This version fixes each:

| # | Problem in Rev 1 | Fix in Rev 2 | Effect |
|---|------------------|--------------|--------|
| 1 | Used **$6.97** price | Use **$3.08**, the actual June 30 close (stock fell 56% on the financing news) | Lower entry price raises forward returns but signals market alarm |
| 2 | Revenue used **gross** barrels | Apply **83.6% net revenue interest** (10-K: 100% working interest, 83.6% NRI) | Cuts revenue ~16% |
| 3 | Base 54k / bull 65k bbl/d **exceeded the field's all-time peak** (29k in 2014) | Base **42k**, bull **52k**, grounded in history + current flush | Lower, defensible volumes |
| 4 | Bear used **165M shares** (counted an equity raise that would not happen) | Refi fails = cross-conditioned deal dies = **150.3M shares**; value via **asset liquidation** | More accurate bear |
| 5 | Ignored **dilution at $3** and **convert conversion** | Equity raise = ~33M shares at ~$3; bull converts $300M notes into ~75M shares | Heavier, realistic dilution |

---

## Shared facts (same in every case unless noted)

| # | Assumption | Value | Source |
|---|------------|-------|--------|
| F1 | Price today (June 30 close) | $3.08/sh | NYSE close, June 30, 2026 |
| F2 | Shares outstanding (Mar 31, 2026) | 150.3 million | 10-Q; 424B5 |
| F3 | Working interest | 100% | 10-K (76,000 acres, 16 federal leases) |
| F4 | **Net revenue interest** | **83.6%** | 10-K |
| F5 | Current gross oil production (Jun 18, 2026) | 43,000 bbl/day | 424B5 (52 of 77 wells; Hondo offline) |
| F6 | Historical field peak (2014 full year) | 29,000 bbl/day oil gross | 10-K SYU production history |
| F7 | WTI oil price (June 30, 2026) | ~$70/bbl | Market data (`wti_crude.csv`) |
| F8 | Exxon loan outstanding (May 31) | $979.5 million | 424B5 |
| F9 | Proposed Term Loan B | $675M at 15%/yr | 424B5 |
| F10 | Proposed convertible notes | $300M due 2031 | 424B5 (coupon/conversion TBD) |
| F11 | Proposed equity raise | $100 million | 424B5 |
| F12 | Equity raise price (assumed) | ~$3.00/sh | [Assumption] near June 30 close |
| F13 | New shares from equity raise | ~33.3 million | $100M ÷ $3.00 |
| F14 | Post-close gross debt (if refi closes) | $975 million | 424B5 ($675M + $300M) |
| F15 | Post-close cash (if refi closes) | $135 million | 424B5 sources/uses |
| F16 | Days per year | 365 | Constant |

> **Note on production:** Current 43k bbl/d comes from 52 of 77 wells after an 11-year shut-in. Initial post-restart ("flush") rates are usually elevated and decline. The 2014 full-field peak was 29k bbl/d. So a 5-year **average** above ~45k is optimistic; base uses 42k, bull 52k (Hondo + perforations offsetting decline).

---

## Bear case — refinancing fails (asset liquidation)

**Story:** The cross-conditioned Transactions do not close before July 24, 2026, or production is shut by regulators. No equity is issued. Value comes from selling the asset and paying the secured lender first.

### Every assumption

| # | Assumption | Value | Source or judgment |
|---|------------|-------|-------------------|
| B1 | Refinancing closes | **No** | Bear definition |
| B2 | Shares outstanding (no raise) | **150.3 million** | F2 (cross-conditioned deal dies) |
| B3 | Distressed sale value of the field | **$1.25 billion** | [Assumption]; vs ~$1.6B net book (10-Q) |
| B4 | Exxon secured loan (paid first) | **$0.98 billion** | F8 |
| B5 | Other liabilities net of cash | **$0.22 billion** | AP $117M + ARO $116M − cash $52M (10-Q) |
| B6 | Years to resolution | **2** | Restructuring timeline |
| B7 | Price today | **$3.08** | F1 |

### Arithmetic (show your work)

1. **Residual equity** = $1.25B − $0.98B − $0.22B = **$0.05 billion ($50M)**
2. **Value per share** = $50M ÷ 150.3M = **$0.33** → rounded **$0.35**
3. **Total return** = $0.35 ÷ $3.08 − 1 = **−88.6%**
4. **Annual return over 2 years** = ($0.35 ÷ $3.08)^(1/2) − 1 = **−66.3% per year**

### Bear sensitivity (it hinges entirely on the distressed asset value vs the $980M secured claim)

| Distressed asset value | Residual equity | Value/sh | Annual return (2yr) |
|------------------------|-----------------|----------|----------------------|
| $1.10 billion | ~$0 (wiped) | $0.00 | −100% |
| $1.25 billion | $50M | $0.35 | −66% |
| $1.50 billion | $300M | $2.00 | −19% |

### Bear result

| Output | Value |
|--------|-------|
| Value per share | **$0.35** |
| Annual return | **−66.3%** |
| Probability (judgment) | **35%** |

---

## Base case — refi closes, production near current, modest multiple

**Story:** Transactions close on filed terms. Field averages a little under today's flush rate over five years as new wells and Hondo offset decline. Market pays a mid-range multiple.

### Every assumption

| # | Assumption | Value | Source or judgment |
|---|------------|-------|-------------------|
| C1 | Refinancing closes | **Yes** | 424B5 plan |
| C2 | Average **gross** oil production | **42,000 bbl/day** | [Assumption]; ≈ current, < flush, > 2014 peak |
| C3 | Net revenue interest | **83.6%** | F4 |
| C4 | Days per year | **365** | Constant |
| C5 | Net realized oil price | **$58/bbl** | [Assumption]; WTI ~$70 less heavy-crude differential + transport |
| C6 | Lease operating expense | **$24 / gross bbl** | [Assumption]; high-cost offshore California |
| C7 | General and administrative | **$70 million/year** | [Assumption]; below FY2025 restart spend |
| C8 | Exit EV / EBITDA multiple (year 5) | **5.0×** | [Assumption]; single-asset levered E&P |
| C9 | Gross debt | **$975 million** | F14 |
| C10 | Cash | **$135 million** | F15 |
| C11 | Cash interest (check only) | **$122 million/year** | 15% × $675M + 7% × $300M |
| C12 | Diluted shares | **184 million** | 150.3M + 33.3M equity raise (converts not in money) |
| C13 | Years to exit | **5** | Model horizon |
| C14 | Price today | **$3.08** | F1 |

### Arithmetic (show your work)

**Revenue (net of royalty)**

1. **Gross barrels/year** = 42,000 × 365 = **15,330,000**
2. **Net barrels/year** = 15,330,000 × 83.6% = **12,815,880**
3. **Revenue** = 12,815,880 × $58 = **$743.3 million**

**Costs and EBITDA**

4. **Lease operating expense** = 15,330,000 (gross) × $24 = **$367.9 million**
5. **General and administrative** = **$70.0 million**
6. **EBITDA** = $743.3 − $367.9 − $70.0 = **$305.4 million**

**Debt service check**

7. **Cash interest** = $122 million → EBITDA − interest = $305.4 − $122 = **$183.4 million** (positive; serviceable)

**Equity value**

8. **Net debt** = $975 − $135 = **$840 million**
9. **Enterprise value** = $305.4 × 5.0 = **$1,527.0 million**
10. **Equity value** = $1,527.0 − $840 = **$687.0 million**
11. **Value per share** = $687.0M ÷ 184M = **$3.73**

**Return**

12. **Total return** = $3.73 ÷ $3.08 − 1 = **+21.1%**
13. **Annual return over 5 years** = ($3.73 ÷ $3.08)^(1/5) − 1 = **+3.9% per year**

### Base sensitivity to the exit multiple (the biggest swing factor)

| Exit EV/EBITDA | Equity value | Value/sh | Annual return (5yr) |
|----------------|--------------|----------|----------------------|
| 4.0× | $382M | $2.08 | **−7.6%** |
| 5.0× | $687M | $3.73 | **+3.9%** |
| 6.0× | $992M | $5.41 | **+11.9%** |

### Base result

| Output | Value |
|--------|-------|
| EBITDA | **$305 million** |
| Enterprise value (5.0×) | **$1,527 million** |
| Equity value | **$687 million** |
| Value per share | **$3.73** |
| Annual return | **+3.9%** |
| Probability (judgment) | **45%** |

> At $3.08 the market is roughly pricing this base case. The 56% one-day drop suggests investors moved from a richer expectation toward this leveraged, diluted reality.

---

## Bull case — full ramp, firmer oil, converts convert

**Story:** Refi closes. Hondo and the perforation program lift volumes. Oil firms. The stock recovers enough that the $300M convertible notes convert into shares (removing the debt but adding shares).

### Every assumption

| # | Assumption | Value | Source or judgment |
|---|------------|-------|-------------------|
| L1 | Refinancing closes | **Yes** | Same as base |
| L2 | Average **gross** oil production | **52,000 bbl/day** | [Assumption]; Hondo + perforations; still < flush sustained |
| L3 | Net revenue interest | **83.6%** | F4 |
| L4 | Net realized oil price | **$64/bbl** | [Assumption]; WTI ~$80 environment |
| L5 | Lease operating expense | **$21 / gross bbl** | [Assumption]; scale efficiency |
| L6 | General and administrative | **$60 million/year** | [Assumption] |
| L7 | Exit EV / EBITDA multiple | **5.5×** | [Assumption]; de-risked production |
| L8 | Term Loan B at exit | **$600 million** | [Assumption]; ~$75M paid from excess cash flow |
| L9 | Convertible notes | **convert to equity** | [Assumption]; in the money |
| L10 | Conversion price | **~$4.00/sh** | [Assumption]; ~30% premium to $3 raise |
| L11 | New shares from conversion | **75 million** | $300M ÷ $4.00 |
| L12 | Cash at exit | **$180 million** | [Assumption] |
| L13 | Diluted shares | **258.6 million** | 150.3M + 33.3M raise + 75M conversion |
| L14 | Years to exit | **5** | Model horizon |
| L15 | Price today | **$3.08** | F1 |

### Arithmetic (show your work)

**Revenue (net of royalty)**

1. **Gross barrels/year** = 52,000 × 365 = **18,980,000**
2. **Net barrels/year** = 18,980,000 × 83.6% = **15,867,280**
3. **Revenue** = 15,867,280 × $64 = **$1,015.5 million**

**Costs and EBITDA**

4. **Lease operating expense** = 18,980,000 (gross) × $21 = **$398.6 million**
5. **General and administrative** = **$60.0 million**
6. **EBITDA** = $1,015.5 − $398.6 − $60.0 = **$556.9 million**

**Equity value (converts now equity, so excluded from debt)**

7. **Net debt** = $600M (Term Loan B) − $180M (cash) = **$420 million**
8. **Enterprise value** = $556.9 × 5.5 = **$3,063.0 million**
9. **Equity value** = $3,063.0 − $420 = **$2,643.0 million**
10. **Value per share** = $2,643.0M ÷ 258.6M = **$10.22**

**Return**

11. **Total return** = $10.22 ÷ $3.08 − 1 = **+231.8%**
12. **Annual return over 5 years** = ($10.22 ÷ $3.08)^(1/5) − 1 = **+27.1% per year**

### Bull result

| Output | Value |
|--------|-------|
| EBITDA | **$557 million** |
| Enterprise value (5.5×) | **$3,063 million** |
| Equity value | **$2,643 million** |
| Value per share | **$10.22** |
| Annual return | **+27.1%** |
| Probability (judgment) | **20%** |

---

## Side-by-side: the assumptions that differ

| Assumption | Bear | Base | Bull |
|------------|------|------|------|
| Refi closes | No | Yes | Yes |
| Gross production (bbl/day) | 0 (sold) | 42,000 | 52,000 |
| Net revenue interest | 83.6% | 83.6% | 83.6% |
| Net oil price ($/bbl) | n/a | 58 | 64 |
| LOE ($/gross bbl) | n/a | 24 | 21 |
| G&A ($M/yr) | n/a | 70 | 60 |
| Exit EV/EBITDA | n/a (asset value) | 5.0× | 5.5× |
| Net debt at exit ($M) | n/a | 840 | 420 (converts convert) |
| Diluted shares (M) | 150.3 | 184 | 258.6 |
| **Value per share** | **$0.35** | **$3.73** | **$10.22** |
| **Annual return** | **−66.3%** | **+3.9%** | **+27.1%** |

**Probability-weighted value** = (35% × $0.35) + (45% × $3.73) + (20% × $10.22) = **$3.85/share** versus **$3.08** today.

---

## Honest read

- At **$3.08**, the market is pricing close to the **base case** ($3.73). This is a **bet on the bull** (full ramp + recovery) against a real chance of the **bear** (refi failure or distressed asset value below the $980M secured claim).
- The **base case return is only ~4% per year** and swings from **−8% to +12%** on the exit multiple alone. It clears a 15% target only in the bull.
- The single most important number is **whether the refinancing closes by July 24, 2026**. Everything else is secondary.

## What this model still ignores (on purpose)

- Production decline curve year by year (uses flat 5-year averages)
- Mandatory hedge costs and the Term Loan B excess-cash-flow sweep schedule
- Exact convert coupon and conversion price (preliminary 424B5)
- Cash taxes (large NOLs from the $1.3B accumulated deficit likely shield several years)
- California litigation outcomes beyond the bear shut-in

**Stance:** **watch.** Base return ~4%/yr at $3.08; attractive only if you underwrite the bull and can tolerate a possible near-total loss in the bear.
