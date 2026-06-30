# CPRT — Book Valuation Overview

**As of:** 2026-06-30  
**Scope:** Comp-based economic book estimate (land mark only)  
**Status:** Partial — **[HUMAN REVIEW]** before use in stance decisions

---

## Purpose

This document summarizes Copart’s **economic book value** after re-marking owned yard land at **local transaction comps**. It is a **parallel cross-check** to Lawrence free-cash-flow valuation. It does **not** replace the primary return model in `CPRT/research/valuation.json`.

---

## Headline numbers

| Measure | Per share | Total ($M) |
|---------|----------:|-----------:|
| **Filed GAAP book** | **$9.40** | 9,187 |
| **Current economic book (base)** | **$14.02** | 13,710 |
| **Change from filing** | **+$4.63** (+49%) | +4,523 |

**Price today (reference):** ~$33.07 — the stock trades at a large premium to both filed and economic book because the market prices operating earnings, not land marks alone.

---

## Two book numbers (always show both)

| Field | Definition | Base case |
|-------|------------|----------:|
| **Filed book per share** | GAAP stockholders’ equity ÷ shares from FY2025 10-K | **$9.40** |
| **Current book estimate per share** | Filed book plus comp-based land adjustment | **$14.02** |

**Filing anchor**

| Item | Value |
|------|------:|
| Period end | July 31, 2025 |
| Source | `CPRT/investor-documents/sec-edgar/10-K_20250926_rpt20250731_acc0001628280_25_042946.htm` |
| Stockholders’ equity | $9,187M |
| Diluted shares | ~977.6M |

---

## What changed: land only

Only **land** is re-marked in this estimate. Buildings, equipment, cash, and all other balance-sheet lines remain at filed values.

| Line | Filed (GAAP) | Current (comps) | Delta |
|------|-------------:|----------------:|------:|
| Land | $2,395M | $6,917M | **+$4,523M** |
| All other equity (static) | $6,792M | $6,792M | $0 |
| **Total equity** | **$9,187M** | **$13,710M** | **+$4,523M** |

| Per share | Filed | Current (base) |
|-----------|------:|---------------:|
| Land | ~$2.45 | ~$7.07 |
| Other | ~$6.95 | ~$6.95 |
| **Total book** | **~$9.40** | **~$14.02** |

---

## Methodology

### Core rule

**Fair land = sum of (owned parcel acres × local comp $/acre).**

GAAP historical cost is **never** used as a mark input. It appears only in the reconciliation column above.

### Network roll-up (base case)

| Input | Value | Source |
|-------|------:|--------|
| Disclosed operating acreage | ~19,000 | Investor presentation / ESG materials |
| Owned share | ~90% | Copart ESG letter (>90% of acreage owned) |
| **Owned acres (base)** | **~17,100** | 19,000 × 90% |
| **Implied $/acre (base)** | **~$405,000** | Weighted average of 6 Copart land transactions |
| **Fair land (base)** | **~$6,917M** | 17,100 × $405K |

### Transaction sample (base $/acre)

Six recorded Copart purchases, excluding the 2025 Palm Beach outlier ($1.6M/ac):

| Transaction | Acres | Price | $/acre |
|-------------|------:|------:|-------:|
| San Diego, CA (2019) | 51 | $30.0M | $588K |
| Homestead, FL (2020) | 117 | $34.7M | $297K |
| Englewood, CO (2025) | 40 | $32.0M | $800K |
| Morrison / Bandimere, CO (2024) | 126 | $51.0M | $405K |
| Fletcher, NC (2023) | 57 | $8.6M | $151K |
| Antelope, CA (2019 comp mark) | 41 | $18.5M | $450K |
| **Weighted sample** | **432** | **$175M** | **~$405K** |

Full detail: `CPRT/research/land_valuation/transaction_anchors.json`

### Scenario range

| Scenario | Owned acres | $/acre | Fair land | Economic book/sh |
|----------|------------:|-------:|----------:|-----------------:|
| Low | 15,000 | ~$263K | $3,944M | ~$10.98 |
| **Base** | **17,100** | **~$405K** | **$6,917M** | **~$14.02** |
| High | 19,000 | ~$546K | $10,376M | ~$17.56 |

High scenario includes coastal premium implied by the 2025 Palm Beach purchase ($65M / 40 acres).

---

## Pilot yard marks (ground-truth sample)

Seven of twenty stratified pilot yards carry numeric marks (~$117M combined). These validate methodology but are **not** scaled directly to the network total.

| Yard | Location | Base fair land | Notes |
|------|----------|---------------:|-------|
| #151 | Antelope, CA | $18.5M | 41 ac; comp template |
| #59 | San Diego, CA | $30.0M | Recorded 51 ac purchase |
| #148 | Homestead, FL | $34.7M | Recorded 117 ac purchase |
| #68 | Denver, CO | $19.8M | Assumed acres [Assumption] |
| #47 | Phoenix, AZ | $7.0M | Assumed acres [Assumption] |
| #11 | Houston, TX | $7.0M | Assumed acres [Assumption] |
| #1 | Vallejo, CA | $0 | Leased — no Copart fee-simple land |

Comp packets: `CPRT/research/land_comps/`  
Pilot tracker: `CPRT/research/yard_land_marks_pilot.csv`

---

## Price vs book

At ~**$33.07** per share:

| Comparison | Result |
|------------|--------|
| vs filed GAAP book ($9.40) | ~252% premium |
| vs economic book base ($14.02) | ~136% premium |

**Interpretation:** Copart is priced as a high-quality compounder on cash flow and franchise value. Economic book confirms GAAP **understates** embedded land, but even the marked book sits well below the market price.

---

## What this estimate excludes

- Buildings and site improvements (not separately re-marked)
- Fair value of machinery and equipment
- Leasehold yards (marked at **$0** Copart land; lease economics stay in GAAP ROU / liability)
- International yards without local land-registry comps
- **231 of 281** registry rows still lack assessor-confirmed ownership and acreage

---

## Relationship to other models

| Model | Role |
|-------|------|
| Lawrence FCF / synthesis (**10.78%** base) | **Primary stance gate** — unchanged |
| This book estimate | Parallel cross-check; land hidden asset |
| `nav_overlay` in `valuation.json` | Machine-readable mirror of land mark |

Lawrence IRR does **not** include fair land uplift unless promoted through **[HUMAN REVIEW]**.

---

## Source files and refresh

| File | Role |
|------|------|
| `CPRT/research/book_estimate_config.json` | Human-maintained filing anchor and land line |
| `CPRT/research/book_estimate.json` | Script output (live summary) |
| `CPRT/research/land_valuation/fair_land_summary.json` | Network land roll-up detail |
| `CPRT/_scripts/roll_up_land_marks.py` | Fair land calculator |
| `_system/scripts/current_book_estimate.py` | Book roll-forward script |

```bash
python CPRT/_scripts/roll_up_land_marks.py --write
python _system/scripts/current_book_estimate.py CPRT --write
```

---

## Open items [HUMAN REVIEW]

1. County assessor tie-out on owned pilot yards (APN, acres, legal owner)
2. Complete comp packets for remaining 13 pilot yards
3. Close yard registry gap (231 → 281 facilities)
4. International land comps (UK, Germany, Brazil, Spain, Finland)
5. Human approval before land overlay affects stance or base IRR
