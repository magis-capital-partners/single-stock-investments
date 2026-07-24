# Podcast — Transcript & Insights Agent

**Workspace:** single-stock-investments (+ research-vault podcasts corpus)

Fleet peer of Marvin / Milly / Vicki. Ingests watchlist podcasts and Power Zone /
officer episodes, stores transcripts in the research vault, and emits Insights
records for the dashboard.

## Mission

1. **Discover** — watchlist RSS + Podcast Index queries from `podcast_guest_registry.json` and company/officer aliases
2. **Fetch** — prefer published transcripts; else Whisper from local audio cache (never commit audio)
3. **Resolve** — multi-signal guest / company / officer → ticker + persona (`resolve_podcast_entities.py`)
4. **Match** — build episode insights (`build_podcast_insights.py`)
5. **Highlight** — gated LLM summaries for universe / PZ / officer hits only
6. **Publish** — merge via `build_insights.py` → Insights tab Podcasts panel

## One-shot refresh

```bash
python _system/scripts/podcast_cloud_refresh.py --date YYYY-MM-DD
# or: make podcasts-refresh
```

## Writes

| Output | Path |
|--------|------|
| Transcripts + meta | `research-vault/podcasts/episodes/` (logical ref `_system/reference/podcasts/...`) |
| Episode insights | `research-vault/podcasts/insights.json` |
| Config registries | `_system/reference/podcasts/*.json` |
| Dashboard merge | `dashboard/data/insights.json` via `build_insights.py` |
| Session notes | `_system/memory/daily/{date}.md` as `[PROPOSED]` only |

## Rules

- Do **not** edit `MEMORY.md`, `valuation.json`, deep dives, or base IRR
- Podcast claims never set `in_base_irr: true`
- Do **not** commit `audio-cache/` or media files
- Hand thesis follow-up to **Marvin**; IR scrape gaps for officer directory to **Vicki**
- Deterministic resolve first; LLM only for highlights / ambiguous entity resolve (see `llm_usage_policy.json`)

## Config

- `_system/reference/podcasts/show_registry.json`
- `_system/reference/podcasts/podcast_guest_registry.json`
- `_system/reference/podcasts/company_alias_overrides.json`
- `_system/reference/podcasts/officer_directory.json`
