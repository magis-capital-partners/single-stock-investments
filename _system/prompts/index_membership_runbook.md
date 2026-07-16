# Index membership operator runbook

**Feature:** Index inclusion / exclusion tracking  
**Lens:** `_system/frameworks/index_membership_lens.md`  
**Builder:** `python _system/scripts/build_index_membership.py`

## Daily / CI

1. Portfolio news ingest (existing `portfolio-news.yml`) classifies index adds/deletes into `index_inclusion`.
2. Optional float/ADV refresh (Yahoo crumb + SEC shares fallback): `python _system/scripts/fetch_float_adv.py --only-events --max 80`
3. `build_index_membership.py` runs before `build_insights.py` / `build_dashboard_data.py` in rebuild profiles.
4. Output: `dashboard/data/index_membership.json` (mirrored to `docs/` via rsync).

Russell breakpoint mcap lives in `index_rules.json` (`russell_1000.breakpoint_mcap_usd`, dated). Style/subset headlines never produce size-migration float impact.

## Refresh constituent lists

```bash
python _system/scripts/harvest_index_constituents.py
```

Use `--offline` to rebuild the seed from local constituent JSON only.

## Edit membership seed

File: `_system/data/index_memberships_seed.json`

- Per ticker: `memberships` list of index ids (`sp500`, `russell_1000`, `tsx_composite`, …).
- Provider-confirmed events with `effective <= today` auto-update the seed on build.

## Mark a provider-confirmed announcement

Append a line to `_system/data/index_announcements.jsonl`:

```json
{"ticker":"APLD","index":"russell_1000","action":"add","announced":"2026-06-06","effective":"2026-06-26","source_url":"https://...","source_type":"provider_notice","confidence":"provider_confirmed","title":"..."}
```

Then re-run `build_index_membership.py`.

## Quarterly rules refresh

When S&P DJI or FTSE Russell publish new mcap bands / methodology:

1. Update `_system/data/index_rules.json` (`as_of` + thresholds).
2. Update `_system/data/index_calendar.json` with next recon/review dates.
3. Re-run harvest + build.
4. Spot-check Holdings Index column and Insights → Index Watch.

## Vicki / browser harvest

Dynamic FTSE Russell / S&P DJI notice pages may need a Vicki brief under `{TICKER}/research/shopbot/` or a portfolio-level note. Do not automate licensed provider portals without human OK.

## News harvest (precision-first)

News is a **filtered secondary** signal only:

1. Title/summary must pass **subject-gated** extraction (`index_event_extract.py`): the portfolio ticker is the grammatical subject of an add / delete / **reclassify** clause.
2. Category is **not** required to be `index_inclusion` — Copart-style "CEO + Russell reclassification" headlines often land in `management`. Subject match is the gate.
3. **Membership gate:** skip contradictory deletes unless the title says exit/removed (seed lag). Adds and reclassifies are allowed even if seed already lists membership (seed often lags or is backfilled from constituents).
4. Co-mentions (SpaceX joins Nasdaq-100 → AMZN/META tagged) are rejected.
5. Prefer raising `index_inclusion` category priority above `management` so dual-topic headlines classify as index when patterns match.

### Archive recovery (automatic)

`build_index_membership.py` always runs **archive harvest** after the live `portfolio_news.json` pass:

- `_system/reviews/pending|approved/news_*.md` (aged review digests)
- `{TICKER}/research/news/news_index.json` (per-ticker archives)

This recovers AMD / WEST / ALS.TO / CSGP-style events that have rolled out of the live feed. Same subject-gated extract; dedupe via `append_announcement`.

Provider-confirmed appends remain the gold standard. After changing harvest logic, rebuild with purge:

```bash
python _system/scripts/build_index_membership.py --date YYYY-MM-DD
```

(Default purges prior `news_unconfirmed` rows, re-harvests live news, then re-harvests archives.)

## Scorecard candidacy

`inclusion_candidate` requires `|distance_to_boundary_pct| <= max_candidate_distance_pct` (default 15). Clearing a min-mcap floor alone (MSCI / Nasdaq-100) is **not** candidacy.

## Tests

```bash
python -m unittest _system.scripts.tests.test_index_event_extract
```
