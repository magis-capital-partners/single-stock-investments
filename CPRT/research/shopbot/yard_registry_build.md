# Vicki brief — CPRT yard registry completion

**Date:** 2026-06-30  
**Ticker:** CPRT  
**Goal:** Complete `CPRT/research/yard_registry.csv` to **281 facilities** (FY2025 10-K Item 2) with confirmed street addresses.

---

## Context

- US + Canada (195 rows) captured from Copart printable list snapshot.
- Direct `curl` to copart.com is blocked (Incapsula). WebFetch succeeded for snapshot on 2026-06-30.
- International seed has partial UK addresses; Brazil/Spain/Finland need country-site scrape.

---

## Tasks

### 1. Refresh US snapshot (if stale)

- URL: https://www.copart.com/Content/US/EN/Landing-Page/print-locations-by-state
- Save markdown/table to `CPRT/investor-documents/copart_locations_us_by_state.snapshot.md`
- Run `python CPRT/_scripts/build_yard_registry.py`

### 2. UK (19 centres + Ireland)

- Base: https://www.copart.co.uk/locations/
- For each city, open `/locations/{slug}-gb-{num}` and extract **Physical address**
- Known slugs: sandy-gb-401, sandtoft-gb-402, york-gb-410, colchester-gb-416, corby-gb-425
- Update `CPRT/research/international_yard_seed.json`

### 3. Germany (9)

- https://www.copart.de/locations/ — cities: Aachen, Berlin, Dortmund, Frankfurt, Hannover, Leipzig, Mannheim, München-ost, Stuttgart

### 4. Brazil (~23), Spain (11), Finland (4)

- https://www.copart.com.br/ , https://www.copart.es/ , Finland site
- Match 10-K counts: Brazil 23, Spain own 8 + lease 3, Finland 4

### 5. Middle East (leased)

- https://www.copartmea.com/locations/ — UAE, Oman, Bahrain (10-K: lease one each)

---

## Output

- Updated `international_yard_seed.json` with full addresses
- Rebuilt `yard_registry.csv` with `registry_status=address_confirmed`
- Log run to `CPRT/_download_log.txt`

---

## Do not

- Use GAAP land balance ($2.39B) as valuation input
- Mark leased yards with comp land value (land = $0 to Copart unless fee owned)
