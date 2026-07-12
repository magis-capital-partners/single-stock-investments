# Darwin options data — low-API plan

**Goal:** Real IV / mid marks for covered-call research **without** burning Polygon/Tradier quota used by etf-dashboard.

## Do not

- Symlink full etf-dashboard `options_cache.json` into SSI as the primary store (LETF/YB universe, different cadence).
- Refresh all 503 SPX names with options chains.
- Compete with etf-dashboard nightly budgets.

## Do (priority order)

| Priority | Source | API cost | Use |
|----------|--------|----------|-----|
| 1 | **Realized vol** from returns CSV | 0 | Always-on synthetic IV for name-level premium scale |
| 2 | **etf-dashboard cache overlaps** | 0 (read-only) | Import NVDA/AMD/… if present via `refresh_darwin_options_cache.py --import-etf-only` |
| 3 | **SSI champion cache** | Low | Live fetch **only** current Roth weights (≤8 names) with hard caps |
| 4 | Full chain lab | High | Human-triggered `make darwin-options-cache-live` when keys available |

## Caps (live mode)

```
DARWIN_OPTIONS_MAX_SYMBOLS=8
DARWIN_OPTIONS_MAX_POLYGON=20
DARWIN_OPTIONS_MAX_TRADIER=40
```

Cache-first merge: prior local + etf overlaps preserved on fetch failure.

## Commands

```bash
make darwin-options-cache          # free import + write local cache
make darwin-options-cache-live     # champion weights only (needs API keys)
```

## Files

- `_system/scripts/darwin/options_cache.py` — merge + ATM IV lookup
- `_system/scripts/darwin/refresh_darwin_options_cache.py` — refresh
- `_system/reference/market-data/options/options_cache.json` — SSI local cache
