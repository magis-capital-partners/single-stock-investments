# SOC — Simple scenario valuation

**Date:** 2026-06-30  
**Price today:** **$6.97** per share (424B5, NYSE close June 29, 2026)  
**Method:** Three separate paths. Each row is one assumption. No hidden steps.

**Primary source for refi terms:** `investor-documents/sec-edgar/424B5_20260630_rpt_acc0001628280_26_046144.htm`

---

## Shared facts (same in every case unless noted)

| # | Assumption | Value | Source |
|---|------------|-------|--------|
| F1 | Price today | $6.97/sh | 424B5 |
| F2 | Shares outstanding (Mar 31, 2026) | 150.3 million | 424B5 capitalization table |
| F3 | Gross oil production (Jun 18, 2026) | 43,000 bbl/day | 424B5 |
| F4 | Exxon loan outstanding (May 31, 2026) | $979.5 million | 424B5 |
| F5 | Exxon loan maturity (amended) | July 24, 2026 | 8-K Jun 22, 2026 |
| F6 | Proposed Term Loan B | $675 million at 15%/yr | 424B5 |
| F7 | Proposed convertible notes | $300 million due 2031 | 424B5 (coupon TBD) |
| F8 | Proposed equity raise | $100 million | 424B5 |
| F9 | Post-close gross debt (if refi closes) | $975 million | 424B5 ($675M + $300M) |
| F10 | Post-close cash (if refi closes) | $135 million | 424B5 sources/uses |
| F11 | Days per year | 365 | Constant |

---

## Bear case — refi fails or field shut-in

**Story:** Transactions do not close before July 24, 2026, or production is stopped by regulators. Equity is a distressed stub.

### Every assumption

| # | Assumption | Value | Source or judgment |
|---|------------|-------|-------------------|
| B1 | Refinancing closes by Jul 24, 2026 | **No** | Bear scenario definition |
| B2 | Average production after shock | **0 bbl/day** | Shut-in or default |
| B3 | Distressed equity recovery | **$75 million** total | [Assumption] asset sale / exchange residual |
| B4 | Share count used | **165 million** | [Assumption] 150.3M + ~14.3M from prior dilutive raises |
| B5 | Years to reach outcome | **2** | Near-term binary |
| B6 | Price today | **$6.97** | Same as F1 |

### Arithmetic (show your work)

1. **Equity value** = **$75 million** (assumption B3)
2. **Share count** = **165 million** (assumption B4)
3. **Value per share** = $75M ÷ 165M = **$0.45** → rounded **$0.50**
4. **Price today** = **$6.97**
5. **Total return** = $0.50 ÷ $6.97 − 1 = **−92.8%**
6. **Annual return over 2 years** = ($0.50 ÷ $6.97)^(1/2) − 1 = **−73.2% per year**

### Bear result

| Output | Value |
|--------|-------|
| Value per share | **$0.50** |
| Annual return | **−73.2%** |
| Probability (judgment) | **30%** |

---

## Base case — refi closes, steady production

**Story:** June 30 Transactions close on filed terms. Field runs at modestly above today's 43k bbl/d. Market applies a mid-range EBITDA multiple in year 5.

### Every assumption

| # | Assumption | Value | Source or judgment |
|---|------------|-------|-------------------|
| C1 | Refinancing closes | **Yes** | 424B5 plan |
| C2 | Average gross oil production | **54,000 bbl/day** | [Assumption] above 43k today, below full ramp |
| C3 | Days per year | **365** | Constant |
| C4 | Net oil price (after transport/fees) | **$58/bbl** | [Assumption] mid-cycle WTI netback |
| C5 | Lease operating expense | **$23/bbl** | [Assumption] offshore California steady state |
| C6 | General and administrative expense | **$70 million/year** | [Assumption] below FY2025 restart spend |
| C7 | Exit EV / EBITDA multiple (year 5) | **5.0×** | [Assumption] levered E&P |
| C8 | Term Loan B principal | **$675 million** | 424B5 |
| C9 | Convertible notes principal | **$300 million** | 424B5 |
| C10 | Cash on balance sheet | **$135 million** | 424B5 |
| C11 | Cash interest on all debt | **$125 million/year** | [Assumption] 15% on $675M + ~8% on $300M converts |
| C12 | Diluted share count | **175 million** | [Assumption] 150.3M + 14.3M equity raise + ~10M other dilution |
| C13 | Years to exit | **5** | Model horizon |
| C14 | Price today | **$6.97** | Same as F1 |

### Arithmetic (show your work)

**Production and revenue**

1. **Annual barrels** = 54,000 × 365 = **19,710,000 bbl**
2. **Annual revenue** = 19,710,000 × $58 = **$1,143.2 million**

**Costs and EBITDA**

3. **Annual lease operating expense** = 19,710,000 × $23 = **$453.3 million**
4. **General and administrative** = **$70.0 million**
5. **EBITDA** = $1,143.2 − $453.3 − $70.0 = **$619.9 million**

**Capital structure at exit**

6. **Gross debt** = $675 + $300 = **$975 million**
7. **Cash** = **$135 million**
8. **Net debt** = $975 − $135 = **$840 million**

**Equity value**

9. **Enterprise value** = $619.9 × 5.0 = **$3,099.5 million**
10. **Equity value** = $3,099.5 − $840 = **$2,259.5 million**
11. **Value per share** = $2,259.5 ÷ 175 = **$12.91** → rounded **$13.00**

**Return**

12. **Price today** = **$6.97**
13. **Total return** = $13.00 ÷ $6.97 − 1 = **+86.5%**
14. **Annual return over 5 years** = ($13.00 ÷ $6.97)^(1/5) − 1 = **+13.3% per year**

**Sanity check: can debt be serviced?**

15. **Cash interest** = **$125 million** (assumption C11)
16. **EBITDA minus interest** = $619.9 − $125 = **$494.9 million** (positive; base case hangs together)

### Base result

| Output | Value |
|--------|-------|
| EBITDA | **$620 million** |
| Enterprise value | **$3,100 million** |
| Equity value | **$2,260 million** |
| Value per share | **$13.00** |
| Annual return | **+13.3%** |
| Probability (judgment) | **45%** |

---

## Bull case — full ramp, strong oil, some deleveraging

**Story:** Refi closes. Hondo and perforations drive production higher. Oil prices firm. Excess cash flow pays down part of Term Loan B before year 5.

### Every assumption

| # | Assumption | Value | Source or judgment |
|---|------------|-------|-------------------|
| L1 | Refinancing closes | **Yes** | Same as base |
| L2 | Average gross oil production | **65,000 bbl/day** | [Assumption] Hondo + more wells online |
| L3 | Days per year | **365** | Constant |
| L4 | Net oil price | **$63/bbl** | [Assumption] WTI ~$75 with strong realizations |
| L5 | Lease operating expense | **$20/bbl** | [Assumption] scale efficiency |
| L6 | General and administrative expense | **$60 million/year** | [Assumption] costs normalize |
| L7 | Exit EV / EBITDA multiple (year 5) | **6.0×** | [Assumption] de-risked production |
| L8 | Term Loan B at exit | **$600 million** | [Assumption] $75M paid down from excess cash flow |
| L9 | Convertible notes at exit | **$300 million** | 424B5 (unchanged) |
| L10 | Cash at exit | **$180 million** | [Assumption] cash build from operations |
| L11 | Cash interest (year 5 run-rate) | **$114 million/year** | [Assumption] lower TL B balance |
| L12 | Diluted share count | **182 million** | [Assumption] slightly more dilution than base |
| L13 | Years to exit | **5** | Model horizon |
| L14 | Price today | **$6.97** | Same as F1 |

### Arithmetic (show your work)

**Production and revenue**

1. **Annual barrels** = 65,000 × 365 = **23,725,000 bbl**
2. **Annual revenue** = 23,725,000 × $63 = **$1,494.7 million**

**Costs and EBITDA**

3. **Annual lease operating expense** = 23,725,000 × $20 = **$474.5 million**
4. **General and administrative** = **$60.0 million**
5. **EBITDA** = $1,494.7 − $474.5 − $60.0 = **$960.2 million**

**Capital structure at exit**

6. **Gross debt** = $600 + $300 = **$900 million**
7. **Cash** = **$180 million**
8. **Net debt** = $900 − $180 = **$720 million**

**Equity value**

9. **Enterprise value** = $960.2 × 6.0 = **$5,761.2 million**
10. **Equity value** = $5,761.2 − $720 = **$5,041.2 million**
11. **Value per share** = $5,041.2 ÷ 182 = **$27.70** → rounded **$28.00**

**Return**

12. **Price today** = **$6.97**
13. **Total return** = $28.00 ÷ $6.97 − 1 = **+301.7%**
14. **Annual return over 5 years** = ($28.00 ÷ $6.97)^(1/5) − 1 = **+32.1% per year**

**Sanity check**

15. **Cash interest** = **$114 million** (assumption L11)
16. **EBITDA minus interest** = $960.2 − $114 = **$846.2 million**

### Bull result

| Output | Value |
|--------|-------|
| EBITDA | **$960 million** |
| Enterprise value | **$5,761 million** |
| Equity value | **$5,041 million** |
| Value per share | **$28.00** |
| Annual return | **+32.1%** |
| Probability (judgment) | **25%** |

---

## Side-by-side: the assumptions that differ

| Assumption | Bear | Base | Bull |
|------------|------|------|------|
| Refi closes | No | Yes | Yes |
| Production (bbl/day) | 0 | 54,000 | 65,000 |
| Net oil price ($/bbl) | n/a | 58 | 63 |
| LOE ($/bbl) | n/a | 23 | 20 |
| G&A ($M/yr) | n/a | 70 | 60 |
| Exit EV/EBITDA | n/a | 5.0× | 6.0× |
| Net debt at exit ($M) | n/a | 840 | 720 |
| Share count (M) | 165 | 175 | 182 |
| Value per share | **$0.50** | **$13.00** | **$28.00** |
| Annual return | **−73.2%** | **+13.3%** | **+32.1%** |

---

## What this model ignores (on purpose)

- Convertible note conversion price and dilution if stock rises (preliminary 424B5)
- Term Loan B excess-cash-flow sweep mechanics year by year
- Mandatory hedge costs
- California litigation binary beyond bear shut-in
- Warrant overhang ($121M liability, FY2025 10-K)

**Stance:** **watch** · Base case **13.3% per year** is only marginal versus a 15% target and depends on refi closing.
