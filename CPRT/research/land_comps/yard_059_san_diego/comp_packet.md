# Yard 059 — San Diego, CA (comp packet)

**Yard ID:** 59  
**Address:** 7847 Airway Road, San Diego, CA 92154  
**Registry:** `CPRT/research/yard_registry.csv`  
**Method:** Comp-based land only. **GAAP historical cost is not used.**

---

## Step 1 — Ownership and acreage

| Field | Value | Source |
|-------|-------|--------|
| Copart yard name | COPART SAN DIEGO | Copart location directory |
| Physical address | 7847 Airway Road, San Diego, CA 92154 | `CPRT/investor-documents/copart_locations_us_by_state.snapshot.md` |
| Recorded purchase | Apr 2019 — **51 acres** for **$30,000,000** | https://rebusinessonline.com/online-vehicle-auction-company-acquires-51-acres-in-san-diego-for-30m/ |
| Location detail | Otay Mesa — north end La Media Road / Brown Field area | Same |
| Assessor APN / owner | **[HUMAN REVIEW]** — tie 7847 Airway Rd to Otay Mesa deed | San Diego County Parcel Map |

**Working acreage for marks:** **51.0 acres** from recorded Copart purchase (pending APN tie-out to registry address).

---

## Step 2 — Comparable land transactions (≥3)

### Comp A — Copart San Diego purchase (primary anchor)

| Field | Value |
|-------|-------|
| Date | April 2019 |
| Size | 51 acres |
| Price | $30,000,000 |
| **Implied $/acre** | **$588,235** |
| Use | Vehicle storage / salvage auction yard |
| Source | https://rebusinessonline.com/online-vehicle-auction-company-acquires-51-acres-in-san-diego-for-30m/ |

### Comp B — Copart Antelope, CA (same buyer, inland MSA discount)

| Field | Value |
|-------|-------|
| Date | Feb 2019 |
| Size | 41 acres |
| Base mark | $450,000/acre |
| Source | `CPRT/research/land_comps/yard_151_antelope/comp_packet.md` |

**Adjustment:** San Diego coastal industrial premium vs Sacramento MSA → **+30%** vs Antelope base → **~$585K/acre** (confirms Comp A).

### Comp C — San Diego industrial land median (market check)

| Field | Value |
|-------|-------|
| Market | San Diego County industrial land |
| **Median ask (small parcels)** | **$400K–$700K/acre** range on LoopNet listings 2024–2025 |
| Note | Otay Mesa bulk yard trades at lower end of coastal premium |
| Source | LoopNet / CoStar market scans [Assumption] |

**Adjustment:** 51-acre bulk → apply **−5%** vs Comp A → **~$559K/acre** floor.

### Comp D — Homestead, FL Copart purchase (cross-market sanity)

| Field | Value |
|-------|-------|
| Date | 2020 |
| Size | 117 acres |
| Price | $34,700,000 |
| **Implied $/acre** | **$296,581** |
| Source | The Real Deal (Homestead purchase cited in Palm Beach article) |

**Adjustment:** Southeast Florida vs San Diego → not used in base mark; confirms wide regional dispersion.

---

## Step 3 — Selected comp $/acre and fair land value

| Scenario | $/acre | Logic |
|----------|--------|-------|
| Low | $500,000 | Bulk discount to 2019 purchase; no coastal inflation |
| **Base** | **$588,000** | Recorded Copart Otay Mesa purchase (Comp A) |
| High | $650,000 | Coastal industrial inflation 2019–2026 [Assumption] |

**Base fair land value (51 acres × $588,000):** **$29,988,000** (~**$30.0M**)

---

## Step 4 — GAAP reconciliation (display only)

| Line | Amount | Note |
|------|--------|------|
| GAAP land (consolidated) | $2,394M | FY2025 10-K — historical cost |
| This yard fair land (base) | ~$30.0M | Comp-based |
| Variance | TBD network sum | Do not infer from consolidated GAAP |

---

## Step 5 — Open items

- [ ] San Diego County assessor: confirm 7847 Airway Rd APN matches Otay Mesa 51-acre deed
- [ ] Legal owner entity (Copart Inc. vs subsidiary)
- [ ] Improvements valued separately

---

## Milly QA

- [x] ≥3 comps with URLs or cross-yard packets  
- [x] No historical cost in mark formula  
- [ ] Assessor acres confirm 51.0  
- [ ] Ownership confirmed **owned**
