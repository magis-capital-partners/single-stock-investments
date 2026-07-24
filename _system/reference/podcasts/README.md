# Podcast Insights config

Committed registries for the Podcast agent (see `_system/agents/PODCAST.md`).

| File | Role |
|------|------|
| `show_registry.json` | Watchlist feeds (+ The Synopsis) |
| `podcast_guest_registry.json` | Tier A Power Zone + Tier B Oakcliff-extended guests |
| `company_alias_overrides.json` | Manual company→ticker (Evolution Gaming → `EVO.ST`, in book) |
| `officer_directory.json` | Person ↔ company ↔ ticker |
| `insights_mirror.json` | Lightweight mirror of vault `podcasts/insights.json` for CI |

Transcript corpus lives in **research-vault** `podcasts/` (logical ref `_system/reference/podcasts/...`). Audio stays in `audio-cache/` (gitignored).

```bash
make podcasts-check
make podcasts-refresh
```
