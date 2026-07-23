# ALL — Evidence reconciliation (2026-07-21)

**Ticker:** ALL · **As-of:** 2026-07-21

## Summary

| Item | Status |
|------|--------|
| Economic ownership map | **met** — five additive components in `valuation.json` |
| Component calculation proofs | **met** — valid graphs on all five additive components |
| Owner-cash / NAV bridge | **met** — FY2025 segment table anchors normalized owner cash allocation |
| Downside capital claims | **met** — net debt in `net_financial_claims`; catastrophe reserve overlap key |
| Double-counting | **met** — non-overlapping overlap keys; full net reserves not subtracted twice |

**Contract status after agent pass:** pending mechanical close (`marvin_cloud_refresh.py`).

---

## Acceptance test: complete economic ownership map

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Five additive components: Property-Liability underwriting engine, Protection Services engine, investment float surplus, net financial claims, catastrophe/cycle reserve |
| **Source** | `ALL/investor-documents/sec-edgar/10-K_20260220_rpt20251231_acc0000899051_26_000031.htm` segment performance table |
| **Calculation** | PL underwriting **$8,540M** (Allstate Protection **$8,694M** less Run-off **$(154)M**) + PS adjusted NI **$218M** = **$8,758M** pool; normalized owner cash **$8,013M** (**$30/sh** on **267.1M** shares) allocated by pool share |
| **Remaining uncertainty** | Normalized **$30/sh** owner cash is **[Assumption]**; segment split uses profit-metric proportion |
| **Affected components** | property_liability_underwriting_engine, protection_services_engine |
| **Valuation consequence** | Base component sum **~$230/sh** vs price **~$249** |
| **Falsifier** | 10-K restates segment underwriting or Protection Services adjusted net income breaking proportional bridge |

---

## Acceptance test: primary cash / owner-cash bridge

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | FY2025 diluted EPS **$38.06**; net income applicable to common **$10,165M**; reserve releases **$1,809M** pretax (3.1 points on combined ratio); normalized owner cash **$30/sh** |
| **Source** | `ALL/investor-documents/sec-edgar/10-K_20260220_rpt20251231_acc0000899051_26_000031.htm` |
| **Calculation** | Owner cash haircut from peak GAAP EPS for favorable reserve development and mid-cycle combined ratio normalization |
| **Remaining uncertainty** | Human validation of **$30/sh** vs company-adjusted metrics |
| **Affected components** | property_liability_underwriting_engine, protection_services_engine |
| **Valuation consequence** | Lawrence base uses **$30/sh**, not GAAP EPS **$38.06** |
| **Falsifier** | Combined ratio exceeds **100%** for two consecutive years with no offsetting investment income |

---

## Acceptance test: downside and capital claims

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Long-term debt **$7,490M**; cash **$704M**; net debt **~$6,786M** (**~$25.4/sh**); catastrophe losses **$4,960M** FY2025 |
| **Source** | FY2025 10-K balance sheet and underwriting table |
| **Calculation** | `net_financial_claims` base **−$24/sh**; `catastrophe_and_cycle_reserve` base **−$18/sh** for cat/cycle stress |
| **Remaining uncertainty** | Social inflation and climate frequency remain widest judgment bands |
| **Affected components** | net_financial_claims, catastrophe_and_cycle_reserve |
| **Valuation consequence** | Low case component sum **~$109/sh** approximates cycle-stress floor before book cross-check |
| **Falsifier** | Net debt rises above **$10B** without matching equity growth or buyback suspension |

---

## Component proof summary

| Component | Method | Base ($/sh) | Proof status |
|-----------|--------|-------------|--------------|
| property_liability_underwriting_engine | owner_cash_or_dividend_discount@1.0 | 232.00 | valid |
| protection_services_engine | owner_cash_or_dividend_discount@1.0 | 12.00 | valid |
| investment_float_surplus | net_asset_value@1.0 | 28.00 | valid |
| net_financial_claims | net_asset_value@1.0 | −24.00 | valid |
| catastrophe_and_cycle_reserve | net_asset_value@1.0 | −18.00 | valid |
| **Sum** | | **230.00** | |

---

## Open gaps (partially_met / not_met)

| Gap | Status | Notes |
|-----|--------|-------|
| Normalized owner cash validation | partially_met | **$30/sh** pending human review per `[HUMAN REVIEW]` |
| Third-party cross-check | open | No approved external sources indexed; filings-only stance |
