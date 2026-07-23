# AFL — Evidence reconciliation (2026-07-21)

**Ticker:** AFL · **As-of:** 2026-07-21

## Summary

| Item | Status |
|------|--------|
| Economic ownership map | **met** — four additive components in `valuation.json` |
| Component calculation proofs | **met** — valid graphs on all four additive components |
| Owner-cash / NAV bridge | **met** — FY2025 normalized owner cash anchors segment allocation |
| Downside capital claims | **met** — investment_and_currency_reserve overlap key; net debt in net_financial_claims |
| Double-counting | **met** — non-overlapping overlap keys; policy liabilities not subtracted twice |

**Contract status after agent pass:** pending mechanical close (`marvin_cloud_refresh.py`).

---

## Acceptance test: complete economic ownership map

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Four additive components: Japan supplemental engine, U.S. worksite engine, net financial claims, investment/currency reserve |
| **Source** | `AFL/investor-documents/sec-edgar/10-K_20260225_rpt20251231_acc0001628280_26_011402.htm` segment earned premium table |
| **Calculation** | Japan earned premium **$10,664M** + U.S. **~$6,900M** = **~$17,564M**; owner cash **$3,129M** allocated by premium share (61% / 39%) |
| **Remaining uncertainty** | Segment operating income not separately disclosed; premium proportion is judgment |
| **Affected components** | japan_supplemental_engine, us_worksite_engine |
| **Valuation consequence** | Base component sum **~$116/sh** vs price **~$122** |
| **Falsifier** | 10-K restates segment earned premium or shows material intersegment eliminations breaking proportional bridge |

---

## Acceptance test: primary cash / owner-cash bridge

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Operating income **$3,440M** FY2025; net investment income **$4,076M**; normalized owner cash **$5.85/sh** on **534.9M** diluted shares |
| **Source** | `AFL/investor-documents/sec-edgar/10-K_20260225_rpt20251231_acc0001628280_26_011402.htm` |
| **Calculation** | Normalized owner cash bridges GAAP operating cash flow **~$4.78/sh** and operating income **~$6.44/sh** |
| **Remaining uncertainty** | Investment marks moved GAAP net income to **$3.65B** (EPS **$6.82**) from **$5.44B** in 2024 |
| **Affected components** | japan_supplemental_engine, us_worksite_engine |
| **Valuation consequence** | Lawrence base uses **$5.85/sh**, not GAAP EPS **$6.82** |
| **Falsifier** | Benefit ratio rises above 70% for two years with no offsetting investment income |

---

## Acceptance test: downside and capital claims

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Debt **$8,409M**; cash **$6,245M**; net debt **~$2,164M** (**~$4.05/sh**); shareholders' equity **$29,490M** |
| **Source** | FY2025 10-K balance sheet |
| **Calculation** | net_financial_claims base **−$4.05/sh**; investment_and_currency_reserve base **−$8/sh** for mark/yen stress |
| **Remaining uncertainty** | Yen translation and JGB credit spread moves remain unmodeled event trees |
| **Affected components** | net_financial_claims, investment_and_currency_reserve |
| **Valuation consequence** | Low case component sum **~$80/sh** approximates book-adjusted stress |
| **Falsifier** | Net debt rises above **$12B** without matching investment portfolio growth or equity raise |

---

## Component proof summary

| Component | Method | Base ($/sh) | Proof status |
|-----------|--------|-------------|--------------|
| japan_supplemental_engine | owner_cash_or_dividend_discount@1.0 | 78.00 | valid |
| us_worksite_engine | owner_cash_or_dividend_discount@1.0 | 50.00 | valid |
| net_financial_claims | net_asset_value@1.0 | −4.05 | valid |
| investment_and_currency_reserve | net_asset_value@1.0 | −8.00 | valid |
| **Sum** | | **115.95** | |

---

## Open gaps (partially_met / not_met)

| Gap | Status | Notes |
|-----|--------|-------|
| Segment-level operating income split | partially_met | Consolidated operating income; allocated via earned premium proportion |
| Q1 2026 adjusted operating bridge | partially_met | Q1 10-Q filed; supplemental earnings exhibits not in ticker folder |
| Approved third-party IRR inputs | not_met | No approved external sources in base IRR |
