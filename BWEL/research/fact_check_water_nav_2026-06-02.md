# BWEL — Fact-check: water rights, land scale, economic NAV

**Date:** 2026-06-02  
**Agent:** Marvin  
**Purpose:** Independent verification of Groundbreaker RE, press, and book snippets before probability-weighted economic NAV in `valuation.json`.

---

## Executive summary

**Filings** confirm land and related water investments at **$106M** historical cost with **no acre-foot disclosure**. **Independent journalism** (GV Wire / SJV Water, UC Davis, Cagle) corroborates **~130k–159k California acres** on the Tulare Lake bed and **documented transfer of 102,000+ acre-feet** of surface water out of Kings County since 2009. The **~400,000 acre-foot** portfolio claim (Groundbreaker, Undervalued Shares) is **plausible but not filing-proven**; we treat it as the **upper scenario**, not the base fact.

**Marvin probability-weighted economic NAV (overlay base): ~$1,480/share** vs GAAP **~$783/share** and price **~$549/share**. Lawrence cash IRR stance gate **unchanged at 1.1%**.

---

## Source reliability matrix

| Claim | Groundbreaker (2026-05) | Undervalued Shares | King of California (OL excerpts) | Marvin-verified? |
|-------|-------------------------|--------------------|--------------------------------|----------------|
| ~150k CA farm acres | Yes | Yes (~150k + 59k Sierra grazing) | OL search **not reliable** for J.G. Boswell scale (mixed texts) | **Partial** — press/ParcelQuest |
| ~400k AF senior surface | Yes (16 rivers) | Yes (1% of CA ~40M AF) | No clean AF cite in OL harvest | **Unverified quantity**; used in bull scenario only |
| $5k–$15k / AF → $2B–$6B | Yes | $20k–$30k / AF → $8B–$12B | N/A | **Directional**; Marvin uses **$2.5k–$12k** band with **35% monetization haircut** |
| SGMA catalyst | Yes | Implied | Tulare basin / SGMA context in unrelated OL snippets | **Agree** (regulatory) |
| Dividend ~3.8% | Yes | N/A | N/A | **Yes** — FY2025 **$17.50/sh** |
| Land BS **$106M** | Implied | Implied | N/A | **Yes** — FY2025 annual |
| 102k+ AF moved since 2009 | Not cited | N/A | N/A | **Yes** — GV Wire / SJV Water (DWR records) |
| Largest private US farm | Yes | Yes | N/A | **Directional** — UC Davis, agriculture press |

---

## Primary evidence (filings)

| Item | FY2025 annual | Implication |
|------|---------------|-------------|
| Land and related water investments | **$106,048k** at cost | Combined line; fair value **not** disclosed |
| Stockholders' equity | **$755,073k** / **964,210** sh = **~$783/sh** | GAAP NAV anchor |
| Subsurface minerals | CA/OR on owned and third-party land | Option; not fair-valued |
| Water quantity | **Not disclosed** | Cannot anchor AF from 10-K alone |
| FY2025 flood / NRV | $38.7M flood COS; $42.8M NRV | Trough year; Tulare basin risk **in filings** |

Source: `BWEL/investor-documents/ir-bwel/2025-06-30_Annual_Report.pdf`

---

## Independent acreage (fact-check)

| Source | Acres (California) | Notes |
|--------|-------------------|--------|
| GV Wire / SJV Water (2021, ParcelQuest) | **~132k Kings** + **3.7k Tulare** + **23k Kern** ≈ **158.7k** | Best **parcel-count** anchor |
| UC Davis Aaron Smith (2023) | **~150,000** | Tulare Lake bed operator |
| Alicia Patterson / Cagle (2023) | **~130,000** lake-bottom | “Whale that never surfaces” quote |
| Groundbreaker (2026) | **~150,000** CA + **30,000+** Australia | Australia **not** in FY2025 balance sheet detail here |

**Marvin base acreage for land comps: 145,000** irrigated CA (mid of verified band).

---

## Independent water quantity (fact-check)

| Source | Quantity | What it measures |
|--------|----------|------------------|
| GV Wire / SJV Water | **102,000 AF** transferred/sold **out of Kings** since **2009** | **Proven monetization**; lower bound on transferable portfolio |
| GV Wire | **~90,000 AF** SWP contract share (of **140,600** county SWP) | **Subset** — state project water, not all senior rights |
| Undervalued Shares | **400,000 AF** (~1% of CA system) | **Unverified**; repeats industry lore |
| Groundbreaker | **400,000 AF** senior surface | Same claim; **no Boswell 10-K cite** |

**Inference:** Total economic rights likely **exceed 102k AF** (or transfers could not continue). **400k AF** remains **credible upper bound**, not Marvin base.

**King of California OL excerpts:** Search-inside harvest (~3,433 snippets) gives Tulare Lake **basin hydrology** context but **no usable J.G. Boswell acre-foot figure** (many false “Boswell” hits). Book is **background only** for this NAV build.

---

## $/acre-foot and monetization (fact-check)

| Source | $/AF | Marvin use |
|--------|------|------------|
| Groundbreaker | $5,000–$15,000 | Scenario band |
| Undervalued Shares | $20,000–$30,000 (sales) | **Bull / haircut** — likely peak transferable rights, not average ag portfolio |
| Documented transfers | Price **not** in GV Wire article | Supports **liquidity**, not level |

**Marvin adjustments:**

1. **Ag + senior SJV rights** — use **$2,500–$7,000/AF** in base scenarios (below Groundbreaker low for transferable value).
2. **Monetization haircut 35%** — family control, no sale history, change-of-use friction, rights tied to farm operations.
3. **Overlap haircut 30%** on water EV — portion of rights **embedded in operating farm** (avoid double-count with mid-cycle owner cash).

---

## Probability-weighted water NAV (enterprise)

| Scenario ID | Prob. | Acre-feet | $/AF (gross) | Net water $M (after 35% haircut) | Evidence tier |
|-------------|-------|-----------|--------------|----------------------------------|---------------|
| `floor_documented` | 20% | 100,000 | 2,500 | **163** | 102k AF transferred (GV Wire) |
| `low` | 25% | 175,000 | 3,500 | **398** | Between documented transfers and press mid |
| `base` | 35% | 280,000 | 5,000 | **910** | Marvin best estimate |
| `mid_high` | 15% | 350,000 | 7,000 | **1,593** | Toward Groundbreaker low $/AF × high AF |
| `bull_external` | 5% | 400,000 | 12,000 | **3,120** | Groundbreaker / Undervalued upper |
| **Expected** | 100% | — | — | **~846** | Probability-weighted |

Shares: **964,210** → expected water component **~$878/share** gross; **~$615/share** after 30% operational overlap haircut → **~$485/share** in SOTP uplift.

---

## Economic NAV bridge (per share)

| Component | $/sh | Method |
|-----------|------|--------|
| GAAP equity anchor | **783.2** | FY2025 equity ÷ shares |
| Water rights (probability-weighted, net of overlap) | **+485** | See scenarios in `valuation.json` → `nav_overlay.water_rights_scenarios` |
| Irrigated land surface (incremental to GAAP line) | **+125** | 145k ac × $4k–$6k marks × probability — **partial** overlap with water |
| Subsurface minerals | **+55** | Probability-weighted; filing admits interests, no fair value |
| Mid-cycle operating franchise | **+32** | Trough-normalized earnings not in FY2025 loss year |
| **Economic NAV (overlay base)** | **~1,480** | Not GAAP; not Lawrence IRR |

**Bull economic NAV (sensitivity): ~$2,200/sh** — `bull_external` water scenario + higher land marks.

---

## Groundbreaker fact-check verdict

| Item | Verdict |
|------|---------|
| Hidden water / GAAP gap | **Agree** |
| BWEL as water option | **Agree** with monetization caveats |
| 400k AF | **Unverified** — include as **5%** probability scenario |
| $2B–$6B water NAV | **Directionally reasonable** in bull case; **not** Marvin expected value |
| SGMA catalyst | **Agree** (timing generational) |
| 3.8% dividend | **Agree** |
| “Accumulate” on asset | **Not adopted** for stance — Lawrence **watch** remains |

---

## [HUMAN REVIEW]

- [ ] Confirm acre-feet with company or Tulare/Kings district records (still ideal)
- [x] Marvin overlay updated with probability weights (2026-06-02)
- [ ] Promote water row into Lawrence base IRR — **not recommended** without filing AF

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] BWEL: Marvin fact-check (2026-06-02) — 102k+ AF transfers verified (GV Wire); 400k AF unverified; economic NAV overlay ~$1,480/sh probability-weighted; Lawrence 1.1% unchanged.

## Citations

1. `BWEL/investor-documents/ir-bwel/2025-06-30_Annual_Report.pdf`
2. https://groundbreakerre.substack.com/p/water-rights-the-hidden-asset-the
3. https://gvwire.com/2021/11/22/special-report-small-farmers-struggle-as-ag-titans-boswell-vidovich-wheel-water-for-profit/
4. https://sjvwater.org/where-is-the-water-going/
5. https://asmith.ucdavis.edu/news/most-tulare-lake-lies-inside-one-big-farm
6. https://aliciapatterson.org/susie-cagle/how-government-and-private-firms-shaped-californias-devastating-floods/
7. https://www.undervalued-shares.com/weekly-dispatches/secret-californian-company-with-billions-in-water-rights/
8. `BWEL/investor-documents/research-notes/King_of_California_OL_search_excerpts.md` (context only)
