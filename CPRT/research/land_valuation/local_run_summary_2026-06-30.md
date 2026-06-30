# CPRT land valuation — local run summary

**Date:** 2026-06-30 (updated)  
**Branch:** `cursor/cprt-yard-land-registry-521f`

---

## Book valuation (comp-based)

| Metric | Value |
|--------|------:|
| GAAP land at historical cost | **$2,395M** (~$2.45/sh) |
| Fair land — base | **$6,917M** (~$7.07/sh) |
| Filed book per share | **$9.40** |
| **Current economic book (base)** | **$14.02/sh** |
| Land uplift | **+$4.63/sh** (+49% vs filed book) |

**Refresh:**
```bash
python CPRT/_scripts/roll_up_land_marks.py --write
python _system/scripts/current_book_estimate.py CPRT --write
```

---

## Pilot yard marks (7 / 20)

| Yard | Base fair land | Status |
|------|---------------:|--------|
| #151 Antelope CA | $18.5M | template_complete |
| #59 San Diego CA | $30.0M | template_complete |
| #148 Homestead FL | $34.7M | template_complete |
| #47 Phoenix AZ | $7.0M | comp_assumption |
| #11 Houston TX | $7.0M | comp_assumption |
| #68 Denver CO | $19.8M | comp_assumption |
| #1 Vallejo CA | $0 | leased |

**Pilot sum:** ~$117M (not scaled to network; network uses transaction-weighted $/acre × ~17,100 owned acres).

---

## Artifacts

- `CPRT/research/book_estimate_config.json`
- `CPRT/research/book_estimate.json`
- `CPRT/research/land_valuation/fair_land_summary.json`
- `CPRT/research/land_valuation/transaction_anchors.json`
- `CPRT/research/deep_dive_2026-06-30.md`
- `CPRT/research/valuation.json` → `nav_overlay`, `book_estimate`

---

## Open gaps

1. Assessor APN / acres for all owned pilot yards  
2. Registry **231 / 281** rows  
3. **13** pilot yards without comp packets  
4. International land comps  
5. **[HUMAN REVIEW]** before overlay affects stance
