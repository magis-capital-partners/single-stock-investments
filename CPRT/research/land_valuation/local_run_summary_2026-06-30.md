# CPRT land valuation — local run summary

**Date:** 2026-06-30  
**Branch:** `cursor/cprt-yard-land-registry-521f`  
**Command:** `python CPRT/_scripts/build_yard_registry.py`

---

## What ran locally

| Step | Result |
|------|--------|
| Registry rebuild | **231 rows** → `CPRT/research/yard_registry.csv` |
| US + Canada addresses | **195** from Copart printable list snapshot |
| International seed | **36** rows (UK partial, DE, MEA, placeholders for BR/ES/FI) |
| Pilot cohort | **20 yards** in `yard_land_marks_pilot.csv` |
| Template comp (owned) | Yard **#151 Antelope** — full packet |
| Leased example | Yard **#1 Vallejo** — $0 land to Copart |
| San Diego draft | Yard **#59** — transaction comp only, APN pending |

---

## Registry vs 10-K

| Metric | Count |
|--------|------:|
| FY2025 10-K operating facilities | **281** |
| Registry rows (local) | **231** |
| **Gap** | **50** (mostly Brazil ~23, Spain ~11, Finland ~4, plus UK address cleanup) |
| Addresses confirmed | **199** |
| Addresses pending | **32** |

---

## Comp-based marks (no GAAP historical cost)

### Yard 151 — Antelope, CA (template)

| Input | Value |
|-------|-------|
| Address | 8650 Antelope North Road, Antelope, CA 95843 |
| Acres (working) | **41** (Copart PR Feb 2019 land acquisition) |
| Comps | 4 (Copart SD purchase, Sacramento median, Roseville bulk floor, small-yard ceiling) |
| **Base fair land** | **~$18.5M** (41 × $450K/ac) |
| Range | ~$15.2M – ~$20.5M |
| Assessor APN/acres/owner | **[HUMAN REVIEW]** — Sacramento County Parcel Viewer |

### Yard 001 — Vallejo, CA (leased)

| Finding | Value |
|---------|-------|
| CEQANET | Copart **leases 8 of 18 acres** from F.P. Smith |
| **Copart land mark** | **$0** |

### Yard 059 — San Diego, CA (draft)

| Anchor | $30M / 51 ac = **$588K/ac** (Apr 2019, Copart purchase) |
| Illustrative base | **~$30M** if 51 ac owned at registry address |
| Blocker | Confirm 7847 Airway Rd = Otay Mesa purchase parcel |

---

## GAAP reconciliation (display only)

| Line | Amount |
|------|--------|
| GAAP land at historical cost (FY2025) | **$2,394M** |
| Comp-based fair land (2 pilot owned yards, partial) | **~$48M illustrative** (151 + 59 if confirmed) |
| **Network total fair land** | **Unknown** — need all owned parcels |

Do **not** mark up GAAP land. Sum parcel comps when registry + assessor work complete.

---

## Pilot status (20 yards)

| Status | Count |
|--------|------:|
| `template_complete` | 2 (151 owned template, 001 leased) |
| `pending_assessor` | 1 (059) |
| `pending` | 17 |

---

## Next local / human steps

1. Sacramento + San Diego assessor: APN, acres, owner for yards 151 and 59
2. Expand `international_yard_seed.json` (Vicki or manual country-site scrape) to close **50-row gap**
3. Replicate yard 151 comp packet for remaining **~17 pilot owned** candidates
4. Roll sum to `nav_overlay` in `valuation.json` after ≥90% owned acres marked

---

## File index

```
CPRT/research/yard_registry.csv
CPRT/research/yard_registry_meta.json
CPRT/research/yard_land_marks_pilot.csv
CPRT/research/land_comps/yard_151_antelope/comp_packet.md
CPRT/research/land_comps/yard_001_vallejo/comp_packet.md
CPRT/research/land_comps/yard_059_san_diego/comp_packet_draft.md
CPRT/research/land_valuation/README.md
CPRT/research/shopbot/yard_registry_build.md
CPRT/_scripts/build_yard_registry.py
```
