# CPRT — Comp-based land valuation (yard registry)

**As of:** 2026-06-30  
**Rule:** Fair land = Σ (owned parcel acres × local comp $/acre). **GAAP historical cost is never a mark input.**

---

## Artifacts

| File | Role |
|------|------|
| `yard_registry.csv` | Master list of yards (address-level) |
| `yard_registry_meta.json` | Row counts vs 10-K 281 facilities |
| `yard_land_marks_pilot.csv` | 20-yard stratified pilot + mark status |
| `land_comps/yard_{id}/comp_packet.md` | Per-yard comps (≥3 when owned) |
| `international_yard_seed.json` | Non-US printable list seed (expand via Vicki) |
| `../investor-documents/copart_locations_us_by_state.snapshot.md` | US+Canada directory snapshot |
| `../_scripts/build_yard_registry.py` | Rebuild registry CSV |

**Template (complete):** `land_comps/yard_151_antelope/comp_packet.md` — Antelope CA #151, 41 acres, comp-based **~$18.5M** base land.

**Leased example:** `land_comps/yard_001_vallejo/comp_packet.md` — Vallejo #1, **$0** Copart land (lease).

---

## Refresh

```bash
python CPRT/_scripts/build_yard_registry.py
```

---

## Next steps

1. Vicki: scrape `copart.co.uk`, `copart.de`, `copart.com.br`, `copart.es`, `copartmea.com` for missing addresses (see `shopbot/yard_registry_build.md`).
2. Assessor lookup for each **pilot** owned yard (APN, acres, owner).
3. Scale comp packets from yard 151 template to remaining ~260 owned yards.
4. Sum fair land NAV → `nav_overlay` in `valuation.json` (human review before stance impact).
