# Watchlist

Companies under consideration — promote via dashboard **+ Add holding** (click watchlist chip) or:

```powershell
python _system/scripts/onboard_ticker.py --ticker XYZ --company "Name" --market US --watchlist-only --notes "Reason"
```

**Source of truth:** `_system/portfolio/registry.json` → `watchlist` section (synced to dashboard JSON).

| Ticker | Company | Market | Notes | Added |
|--------|---------|--------|-------|-------|
| — | — | — | — | — |
