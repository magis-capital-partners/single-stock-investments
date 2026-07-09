# Index membership operator runbook

**Feature:** Index inclusion / exclusion tracking  
**Lens:** `_system/frameworks/index_membership_lens.md`  
**Builder:** `python _system/scripts/build_index_membership.py`

## Daily / CI

1. Portfolio news ingest (existing `portfolio-news.yml`) classifies index adds/deletes into `index_inclusion`.
2. `build_index_membership.py` runs before `build_insights.py` / `build_dashboard_data.py` in rebuild profiles.
3. Output: `dashboard/data/index_membership.json` (mirrored to `docs/` via rsync).

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

## Guardrails

- Never invent float, ADV, or earnings in scorecards.
- UI must keep the Greenwood & Sammon caption (research trigger, not a trade signal).
