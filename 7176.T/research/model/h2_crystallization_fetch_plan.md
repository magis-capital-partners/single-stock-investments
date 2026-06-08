# FY2026H2 crystallization miss — data fetch plan

**Context:** v5 predicted **¥6,039m** vs actual **¥16,935m** on FY2026H2. **¥12,603m** of the **¥10,896m** revenue gap is missing performance fees (v5 perf = ¥0). Attribution JSON: `data/h2_crystallization_attribution.json`.

---

## What the three March H2 halves show

| Half | Actual rev | v5 est. | Rev gap | Perf gap | Structural drive (pre-k) |
|------|-----------|---------|---------|----------|--------------------------|
| FY2024H2 | ¥11,162m | ¥6,999m | ¥4,163m | ¥4,903m | ¥3,073m |
| FY2025H2 | ¥10,902m | ¥4,244m | ¥6,658m | ¥6,971m | ¥134m |
| **FY2026H2** | **¥16,935m** | **¥6,039m** | **¥10,896m** | **¥12,603m** | **¥0** |

Pattern: **every March H2 under-shoots on perf fees.** FY2026 is catastrophic because the mandate engine’s structural driver is literally zero.

---

## Root cause chain (FY2026H2)

```
build_panel.AUM["2026-03-31"] = (13_357, None, None)
        ↓
aum_nonlisted_jpym / aum_etf_jpym = NaN on H2 row
        ↓
_build_nonlisted_mandate_slices() returns []
ETF rows: period_return present, aum_jpym blank → skipped
Value-Up: H2 return < benchmark → excess_vs_hurdle = 0
        ↓
structural_perf_sum() = 0  →  v5 perf_hat = 0
        ↓
Revenue ≈ base only (~¥5,839m) + ¥200m other ≈ ¥6,039m
```

Actual **¥12,603m H2 perf** came from institutional/QIS/株式 buckets (+ record FY2026 success fees ¥14.3bn annual), none of which the engine could see.

---

## Reporting change (important)

From **Sep 2025 interim** (`20251225_中間発行者情報`), Simplex **stopped disclosing** 非上場/上場 and now reports by business line:

| Bucket | Sep 2025 (億円) | Perf relevance |
|--------|-----------------|----------------|
| 株式 | 5,329 | High — core institutional equity mandates |
| ETF | 2,721 | High — 2080/2081/2082 crystallization |
| QIS運用 | 5,421 | Medium — structured; partial perf |
| その他 | 261 | Low |

`build_panel.py` and `fund_registry.json` still assume the **old binary split**. FY2026 有報 (expected ~Jun 2026) will use the new table for **Mar 2026** — **not yet in repo**.

---

## Fetch plan (priority order)

### P0 — Unblock FY2026H2 mandate reconstruction

| # | Fetch | Source | Pipeline touch | Done? |
|---|-------|--------|----------------|-------|
| 1 | **Mar 2026 AUM by business line** (株式/ETF/QIS/その他) | FY2026 有報 `発行者情報` (~Jun 30 2026) | `aum_sleeves.py` / `build_panel.py` | **Provisional done** — `[Assumption]` mix scaled; replace when 有報 lands |
| 2 | **Provisional Mar 2026 sleeves** until 有報 | Scale Sep-2025 mix to total ¥13,357bn | Same; tag `[Assumption]` | Can compute now |
| 3 | **Annual fee split validation** | `Pnotice2026-1` + interim (already have) | Confirms H2 perf ¥12,603m | **Yes** |

### P1 — Fund-level inputs for perf engine

| # | Fetch | Source | Pipeline touch | Done? |
|---|-------|--------|----------------|-------|
| 4 | **ETF AUM at 2026-03-31** per 2080/2081/2082 | JPX outstanding units × NAV (`etf_aum_daily`, P5) | `mandate_nav_detail.csv` ETF `aum_jpym` | Partial — units exist; Mar-2026 end not wired to mandate build |
| 5 | **SAM monthly PDFs through Mar 2026** | simplexasset.com (Value-Up `0001`, Orka `0004*`) | `download_mandate_nav.py` → `mandate_nav_monthly.csv` | Stale — re-scrape |
| 6 | **Half-year fund returns Mar 2026** | Parsed from (5) + ETF yfinance | `mandate_nav_detail` period_return | Value-Up/Orka present; excess=0 vs benchmark |

### P2 — Model logic (requires data above)

| # | Work | Why | File(s) |
|---|------|-----|---------|
| 7 | **Remap registry to business-line buckets** | Old `nonlisted_funds` / `aum_share_of_nonlisted` invalid post-Sep-2025 | `fund_registry.json`, `acquire_data._build_nonlisted_mandate_slices` |
| 8 | **HWM roll-forward** | Crystallize when NAV > HWM at Mar-end even if H2 return < benchmark | `perf_engine.py`, `mandate_terms.json` |
| 9 | **Fix march_excess propagation** | v5 `use_march=true` collapsed FY2025H2 drive to ¥134m vs ¥13k bucket raw | `acquire_data._attach_march_excess` |
| 10 | **Half-year vs March driver fallback** | When march_excess=0 but half excess>0, use documented rule | `perf_engine._drive_excess` |

### P3 — Validation & secondary

| # | Fetch | Source | Notes |
|---|-------|--------|-------|
| 11 | Filing-implied bucket returns | Consecutive bucket AUM rows | Blocked until P0 #1 |
| 12 | Touki / Value-Up monthly NAV backfill | Already 138 months | Extend through Mar 2026 if PDF lag |
| 13 | JITA flows FY2026 H2 | P5 xlsx | AUM roll-forward sanity |
| 14 | CapIQ comp bridge | P7 paste | Ordinary/NI — not revenue miss |

---

## Recommended execution sequence

1. **Today (no 有報 yet):** Insert provisional Mar-2026 bucket AUM from Sep-2025 shares × ¥13,357bn total → re-run `build_panel` → `acquire_data` → `model`.
2. **When FY2026 有報 drops (~Jun 2026):** Download to `7176.T/01_Official/Issuer_Information/`, extract table, replace provisional values.
3. **Re-scrape SAM PDFs** + **JPX ETF units at Mar-2026** → rebuild `mandate_nav_detail`.
4. **Implement bucket remap + HWM** in perf_engine; re-fit k_scale; check perf H2 OOS RMSE gate.
5. **Reject** any spec change that worsens `perf_fee_h2` OOS RMSE vs current v5 (~¥10,184m).

---

## Acceptance criteria

- [ ] FY2026H2 `structural_perf_sum` > 0 with `[Filing]` tag (not `[Assumption]` after 有報)
- [ ] `mandate_nav_detail` has ≥7 fund rows for 2026-03-31 H2 (incl. institutional buckets)
- [ ] v5 `perf_hat_v5_m` for FY2026H2 within **50%** of actual ¥12,603m (stretch; historical k_scale is noisy)
- [ ] `perf_fee_h2` OOS RMSE ≤ current production gate
- [ ] Dashboard labels derived H2 actuals and flags `[Assumption]` bucket AUM

---

## Files to update when data lands

| File | Change |
|------|--------|
| `build_panel.py` | `AUM["2026-03-31"]` sleeves or new bucket dict |
| `fund_registry.json` | Business-line pools + perf eligibility |
| `acquire_data.py` | Bucket slices, march excess, ETF AUM join |
| `perf_engine.py` | HWM, drive_excess fallback |
| `data/mandate_nav_detail.csv` | Regenerated |
| `data/h2_crystallization_attribution.json` | Re-export after fix |
