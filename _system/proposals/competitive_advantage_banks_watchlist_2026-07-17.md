# Competitive-advantage banks watchlist — implementation plan (v2)

**Date:** 2026-07-17 (v2, supersedes same-day v1)  
**Trigger:** Michael Cricenti names (TBBK, MCHB, CASH, CCB, TFIN, GBFH, CBNA, VBNK) + Moore community-bank handbook shelved at `_system/reference/investment-wisdom/moore/`  
**Status:** Implemented P1+P2 (2026-07-17) — human approved name `advantaged_banks` and greenlit P1+P2

## 0. Decisions made in this plan (v1 open questions resolved)

| Question (v1) | Decision | Rationale |
|---|---|---|
| Name | **Advantaged banks** (`advantaged_banks_*`) | TBBK/TFIN are specialty/fee banks, not Moore-classic community banks; "advantaged" covers both |
| VBNK (Canada) in v1? | **Yes** — it is NASDAQ-listed, so SEC companyfacts + Yahoo both work; `market` column kept for future non-US names | No extra plumbing needed |
| Onboard TBBK now? | **No** — everything enters as screener rows; human promotes via existing `+ Watchlist` / Onboard buttons | Matches NOL discipline; no auto-onboarding |

## 1. Architecture (unchanged from v1, now with anchors)

Clone the NOL stack. NOL is a seeded screener **section inside the Watchlist tab**, not a route:

```text
seed CSV ──> builder script ──> dashboard/data/advantaged_banks_screener.json
                     ▲                        │
   registry.json (in_holdings/in_watchlist)   ▼
              build_dashboard_data.py ──> payload["advantaged_banks_screener"]
                                          ▼
              renderWatchlistTab() (dashboard/index.html) — 3rd section
                                          ▼
              + Watchlist / Onboard → openOnboardModal → marvin-onboard.yml
```

Explicitly **not** doing: new top-level tab; overloading the `financial_services` sleeve; biotech-style 13F pipeline.

## 2. File-by-file changes

### 2.1 Seed — `_system/reference/market-data/screens/advantaged_banks_seed.csv` (new)

Header (superset of NOL's so the loader stays trivial):

```text
ticker,company,market,cap_tier,edge_type,notes
```

`edge_type` vocabulary: `low_cost_deposits` | `baas_fintech` | `niche_platform` | `niche_community`.

Initial rows (company names auto-corrected by builder from SEC `entityName`; verify MCHB at seed time):

```text
TBBK,The Bancorp Inc,US,small,baas_fintech,"BaaS/credit sponsorship (Chime, Cash App); fee income > NII; 13% buyback yield FY25"
MCHB,,US,micro,low_cost_deposits,"Michael C: cheap deposits, great operator [verify company name]"
CASH,Pathward Financial,US,small,low_cost_deposits,"Michael C: low-cost deposits; BaaS/payments heritage (ex-Meta Financial)"
CCB,Coastal Financial,US,small,low_cost_deposits,"Michael C: low-cost deposits sourced from neo-bank partners (CCBX)"
TFIN,Triumph Financial,US,small,niche_platform,"Michael C: trucking payments/factoring software company inside a bank"
GBFH,GBank Financial Holdings,US,micro,niche_community,"Michael C: niche bank (gaming/fintech)"
CBNA,Chain Bridge Bancorp,US,micro,niche_community,"Michael C: niche bank; political/trust deposits, very low cost"
VBNK,VersaBank,CA,micro,niche_community,"Michael C: niche digital bank; US listing VBNK"
```

### 2.2 Builder — `_system/scripts/build_advantaged_banks_screener.py` (new)

Start as a copy of `build_nol_screener.py` (keep `load_registry_sets`, `load_cik_map`, `fetch_json`, `latest_usd_fact`, `latest_shares_fact`, `fetch_yahoo_price`, cap buckets, formatters, CLI `--write`). Swap the metric layer:

**v1 metrics (ship immediately, all from companyfacts + Yahoo):**

| Field | Source (XBRL tags, latest 10-K/10-Q) |
|---|---|
| `deposits_total_usd` | `Deposits` |
| `deposits_noninterest_usd` | `NoninterestBearingDepositLiabilities` |
| `dda_share_pct` | noninterest ÷ total deposits (Moore's #1 buyer attribute) |
| `cost_of_deposits_pct` | `InterestExpenseDeposits` (annual) ÷ total deposits — approximate; label as such |
| `equity_usd`, `tangible_equity_usd` | `StockholdersEquity` − `Goodwill` − `IntangibleAssetsNetExcludingGoodwill` |
| `tbv_per_share_usd` | tangible equity ÷ shares |
| `p_tbv` | price ÷ TBV per share |
| `roe_pct` | `NetIncomeLoss` (annual) ÷ equity |
| `total_assets_usd` | `Assets` |
| `market_cap_usd`, `cap_bucket` | shares × Yahoo price (NOL pattern) |
| `in_holdings`, `in_watchlist` | registry sets (NOL pattern) |
| `edge_type`, `notes` | seed passthrough |

Deliberately **skipped** (not reliably in companyfacts): NPL %, NIM, efficiency ratio, criticized loans. If wanted later they come from FFIEC call reports (separate v3 ingest, see §5).

**Flags and sort:**

- `is_low_cost` = `cost_of_deposits_pct` < 1.5 or `dda_share_pct` > 30 (tunable constants at top of file)
- `screen_status` = `ok` / `pending_sec` (NOL pattern)
- Sort: `in_holdings` last within groups → `is_low_cost` first → ascending `cost_of_deposits_pct` → descending `roe_pct` → ticker

**Payload envelope** identical shape to NOL (`built_at`, `criteria`, `seed_path`, `row_count`, counts, `rows`) with `low_cost_count` instead of `actionable_count`. Output: `dashboard/data/advantaged_banks_screener.json`.

Failure behavior: SEC/Yahoo errors degrade to seed-only rows with `screen_status: pending_sec` — table still renders (same as NOL).

### 2.3 Payload hook — `_system/scripts/build_dashboard_data.py`

Add `build_advantaged_banks_screener()` next to `build_nol_screener()` (line ~2491): subprocess `--write`, timeout 300s (8 tickers, not 89), then `_load_json`. In `main()` next to the NOL merge (line ~2607):

```python
banks = build_advantaged_banks_screener()
if banks:
    payload["advantaged_banks_screener"] = banks
    payload["summary"]["advantaged_banks_count"] = banks.get("row_count") or 0
```

### 2.4 UI — `dashboard/index.html` `renderWatchlistTab()` (line ~2249)

Third section appended after the NOL block, same `darwin-table` styling:

- Header: `Advantaged banks screener (N · M low-cost)` + criteria line + link text pointing at the Moore shelf (`_system/reference/investment-wisdom/moore/`) so the framing is explicit.
- Columns: Ticker · Company · Edge · Cost of deposits · DDA % · ROE · P/TBV · Assets · Mkt cap · Filing as-of · Action.
- Action cell: reuse the NOL pattern exactly — `holding` label when `in_holdings`, else `+ Watchlist` button with `data-bank-watch="${ticker}"` wired to `openOnboardModal({ watchlistOnly: true })` (copy the `data-nol-watch` listener block at line ~2348).
- Empty state: `Advantaged banks screener not built. Run: python _system/scripts/build_advantaged_banks_screener.py --write`.
- Optional filter checkbox `Show low-cost only` persisted to localStorage key `banksLowCostOnly` (mirror `nolHideZeroRealizable`, line ~2278).

No new routes, tabs, or JS files.

### 2.5 Validation — `_system/scripts/validate_dashboard_data.py`

Add a check mirroring whatever exists for `nol_screener`: if `advantaged_banks_screener` present, require `rows` non-empty, each row has `ticker`, and `row_count` matches. Warn (not fail) when `built_at` is older than 7 days.

### 2.6 Tests — `_system/scripts/test_advantaged_banks_screener.py` (new)

Follow existing test conventions (`test_power_zone_pricing.py` style, stdlib `unittest`):

1. Seed loader: parses CSV, uppercases tickers, dedupes, preserves `edge_type`.
2. Metric math: DDA share, cost of deposits, TBV/share, P/TBV, ROE from a fixed fake `sec` dict (no network).
3. `is_low_cost` boundary cases.
4. Sort order: low-cost before others; holdings flagged not dropped.
5. Payload envelope keys present.

Network calls must be injectable/mocked — keep `fetch_json` as a module-level function the tests monkeypatch (already true in the NOL script).

### 2.7 Docs

- `_system/reference/investment-wisdom/moore/README.md`: add one line under Apply when — "Advantaged banks screener seed lives at `_system/reference/market-data/screens/advantaged_banks_seed.csv`".
- Daily log `_system/memory/daily/{date}.md`: implementation note + `[PROPOSED MEMORY]` bullet on the funnel pattern (screener → watchlist → onboard).

## 3. Biotech quant 13F recharacterization (small, separate change)

Keep it in **Insights → Research Memory → Biotech** — it is ownership/factor intelligence, not a prospecting funnel. Two cosmetic changes only:

1. In the Biotech sub-tab header (`dashboard/insights-viz.js`, `MEMORY_VIEW_TABS` render), add a one-line hint: *"Specialist 13F ownership signals — not a watchlist; prospecting lists live under Watchlist."*
2. No data moves, no schema changes.

This keeps a clean two-surface mental model: **Watchlist = who we might want to own** (NOL, banks); **Insights = what the market/specialists are doing** (13F, letters, themes).

## 4. Rollout phases and acceptance criteria

| Phase | Scope | Done when |
|---|---|---|
| **P1** (~half day) | Seed CSV + builder (seed-only rows, registry flags, no SEC enrich) + payload hook + UI section + tests 1/4/5 | Watchlist tab shows 8 banks with edge/notes; `+ Watchlist` opens onboard modal prefilled; `make research-check`-adjacent lint green |
| **P2** (~half day) | SEC companyfacts enrich (deposits, DDA %, cost of deposits, TBV, ROE, P/TBV) + tests 2/3 + validation check | All 8 rows show `screen_status: ok` with plausible metrics (spot-check TBBK: ~$8.2B deposits, ROE ~30%, P/TBV ~3.5–4×) |
| **P3** (optional) | `advantaged_banks` sleeve in `investment_sleeves.json` once ≥2 names are full holdings; biotech hint line | Sleeve chip filters Holdings; no watchlist coupling |
| **P4** (later, separate proposal) | FFIEC call-report ingest for NIM / NPL / efficiency; takeout-comp column (franchise premium / core deposits) for classic community names | Not in scope now |

Rollback: every artifact is additive (`advantaged_banks_*` files, one payload key, one UI section). Deleting the seed CSV degrades to an empty section; deleting the builder leaves the dashboard untouched (payload key simply absent).

## 5. Known limits (stated up front)

- **Cost of deposits from XBRL is approximate** (period-end deposits, not average balances; some banks tag interest expense differently). Label the column "approx." and treat FFIEC call reports (P4) as the fix, not more XBRL heuristics.
- **MCHB company identity needs human verification** before P2 enrich (builder will fall back to SEC `entityName` once CIK resolves).
- **VBNK** is a Canadian filer with a US listing; if companyfacts is thin, the row degrades to seed-only — acceptable.
- Framework governance: this adds **no new framework file**; it is a screener + dashboard section, same class of change as the NOL screener.

## 6. Implementation notes (2026-07-17)

- MCHB resolved as **Mechanics Bancorp** (CIK 1518715).
- Live enrich: TBBK ROE ~33%, P/TBV ~4.1×, assets ~$9.9B (matches deep-dive ballpark). VBNK `pending_sec` (Canadian filer / thin US-GAAP tags).
- Cost-of-deposits uses FY interest expense ÷ period-end deposits (approx.); TBBK prints ~1.9% so may not get the LC badge even with a strong franchise — edge_type column carries the thesis.
- Remaining human action: promote names via Watchlist `+ Watchlist` / Onboard; suggest TBBK first with PDF at `c:\Users\drewg\Projects\investing-docs\TBBK_Deep_Dive_2026-05-18.pdf`.
