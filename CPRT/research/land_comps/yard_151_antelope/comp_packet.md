# Yard 151 — Antelope, CA (template comp packet)

**Yard ID:** 151  
**Address:** 8650 Antelope North Road, Antelope, CA 95843  
**Registry:** `CPRT/research/yard_registry.csv`  
**Method:** Comp-based land only. **GAAP historical cost is not used.**

---

## Step 1 — Ownership and acreage (primary sources)

| Field | Value | Source |
|-------|-------|--------|
| Copart yard name | COPART ANTELOPE | `CPRT/investor-documents/copart_locations_us_by_state.snapshot.md` |
| Physical address | 8650 Antelope North Road, Antelope, CA 95843 | https://www.copart.com/locations/antelope-ca-151 |
| Opening / acquisition | Feb 2019; **41-acre facility** | https://www.prnewswire.com/news-releases/copart-opens-new-location-in-antelope-california-300790971.html |
| CEO quote | "proud of the team behind this **land acquisition**" | Same PR |
| Assessor parcel (APN) | **[HUMAN REVIEW]** — lookup 8650 Antelope North Rd in Sacramento County Parcel Viewer | https://assessor.saccounty.gov/content/assessor/us/en/maps-property-data-and-records/assessor-parcel-viewer.html |
| Legal owner on assessor roll | **[HUMAN REVIEW]** — confirm Copart Inc. or subsidiary | Same |
| Assessed acres | **[HUMAN REVIEW]** — use assessor map acres, not deed guess | Same |

**Working acreage for marks:** **41.0 acres** from Copart PR (pending assessor tie-out).

---

## Step 2 — Comparable land transactions (≥3 required)

### Comp A — Copart San Diego purchase (same company, same use, bulk yard)

| Field | Value |
|-------|-------|
| Date | April 2019 |
| Location | Otay Mesa, San Diego, CA (La Media Rd / Brown Field area) |
| Size | 51 acres |
| Price | $30,000,000 |
| **Implied $/acre** | **$588,235** |
| Use | Truck/vehicle storage yard; Copart vehicle auction |
| Source | https://rebusinessonline.com/online-vehicle-auction-company-acquires-51-acres-in-san-diego-for-30m/ |

**Adjustment:** Same buyer and use; Otay Mesa vs Sacramento MSA — apply **−15%** location adjustment → **~$500,000/acre**.

### Comp B — Sacramento MSA industrial land (market median, small/medium parcels)

| Field | Value |
|-------|-------|
| Period | 12 months to Dec 2025 |
| Market | Sacramento, CA |
| **Median $/acre** | **$459,000** |
| Note | High dispersion ($59K–$886K/acre); large parcels trade at discount |
| Source | https://landydandy.com/stats/california/sacramento |

**Adjustment:** Antelope 41-acre bulk → **−20%** vs median for size → **~$367,000/acre**.

### Comp C — Large greenfield industrial (Placer County, bulk discount floor)

| Field | Value |
|-------|-------|
| Date | Roseville Industrial Park agreement (staff report) |
| Size | 236 acres (191 developable) |
| Price | $34,519/acre |
| Use | Greenfield industrial park (not entitled yard) |
| Source | https://roseville.novusagenda.com/AgendaPublic/CoverSheet.aspx?ItemID=8687&MeetingID=1383 |

**Adjustment:** Greenfield without improvements; salvage yard with fencing/paving commands premium → **+100%** to **~$69,000/acre** as **floor only** (wide uncertainty).

### Comp D — Light industrial / yard listing (small parcel premium, ceiling check)

| Field | Value |
|-------|-------|
| Location | Sacramento, CA |
| Size | 1.34 acres |
| Ask | $820,285/acre |
| Use | Automotive / warehouse / yard space |
| Source | https://muellercommercial.com/for-sale/ |

**Adjustment:** Small-parcel premium; **not** applied to 41-acre mark — used as ceiling sanity check only.

---

## Step 3 — Selected comp $/acre and fair land value

| Scenario | $/acre | Logic |
|----------|--------|-------|
| Low | $370,000 | Sacramento median with large-parcel discount (Comp B) |
| **Base** | **$450,000** | Midpoint of adjusted Comp A ($500K) and Comp B ($367K); Copart-specific transaction weight |
| High | $500,000 | Copart San Diego adjusted (Comp A) |

**Base fair land value (41 acres × $450,000):** **$18,450,000** (~**$18.9M** rounded)

**Per share (978M diluted, illustrative only):** ~**$0.02/share** land at this yard alone — full network sum is TBD.

---

## Step 4 — GAAP reconciliation (display only, not an input)

| Line | Amount | Note |
|------|--------|------|
| GAAP land (consolidated, all yards) | $2,394,553K | FY2025 10-K PP&E note — **historical cost** |
| This yard fair land (base) | ~$18.5M | Comp-based |
| Variance | TBD after assessor APN tie-out | Do not infer from consolidated GAAP land |

---

## Step 5 — Open items

- [ ] Sacramento County APN + assessor acres for 8650 Antelope North Road
- [ ] Deed owner name (Copart Inc. vs subsidiary)
- [ ] Second independent comp set from county recorded deeds (Sacramento industrial ≥10 acres, 2022–2025)
- [ ] Improvements (paving, buildings) valued separately — not in land row above

---

## Milly QA

- [x] ≥3 comps with URLs  
- [x] No historical cost in mark formula  
- [ ] Assessor acres confirm 41.0  
- [ ] Ownership confirmed **owned** (not leased)
