# Podcast — Transcript & Insights Agent

**Workspace:** single-stock-investments (+ research-vault podcasts corpus)

Fleet peer of Marvin / Milly / Vicki. Ingests watchlist podcasts and Power Zone /
officer episodes, stores transcripts in the research vault, and emits Insights
records for the dashboard.

## Mission

1. **Discover** — every watchlist RSS episode (`--all-watchlist`) + optional Podcast Index guest/officer search; paginate capped feeds via Podcast Index API
2. **Fetch** — published HTML first; durable `whisper_backlog.json` for the rest (`--whisper-batch`)
3. **Resolve** — multi-signal guest / company / officer → ticker + persona (`resolve_podcast_entities.py`)
4. **Match** — build episode insights (`build_podcast_insights.py`)
5. **Summarize for readers** — every episode gets a short, plain-English `reader_summary` in its `*.meta.json`; investment relevance is **not** a gate (see the plan below)
6. **Analyse for claims** — local-model claims, figures and thesis for episodes with real speech (`analyze_podcast_batch.py`, writes `llm_analysis` to `*.meta.json`). This is a deeper, slower pass and must never block step 5
7. **Publish** — vault catalog → episode detail shards → merge via `build_insights.py` → Insights Podcasts panel, with a coverage check that the published shards — not just the vault meta — carry a summary for every episode

## Product goal

A visitor who has never heard an episode can open the Podcasts panel and, for
**every** episode, understand in about 20 seconds: what it is about, the main
points, and whether it is worth their time. No episode may present a raw
transcript fragment, a show intro, an advertisement, or a blank space as its
summary. Claims extraction is a separate investment feature; an episode with
no claim about a company we can own still gets a full reader summary.

## One-shot refresh

```bash
# Steady state (all watchlist RSS + published + Whisper batch 20)
python _system/scripts/podcast_cloud_refresh.py --date YYYY-MM-DD
# or: make podcasts-refresh

# Overnight backfill (ignore skip priority; larger Whisper batch)
make podcasts-backfill
# WHISPER_BATCH=50 make podcasts-backfill
```

Pipeline: discover `--all-watchlist --paginate-capped-feeds` → fetch (published / backlog) → whisper-batch → officer directory → **build insights** → summarize (meta; in CI this writes Tier B/C fallbacks and marks transcript episodes `pending_model`, since no local model runs there) → **build insights again** (pull `reader_summary` + detail shards) → `build_insights.py` → summary-coverage check on the published shards.

Capped feeds (e.g. Capital Allocators at 1000): set `PODCASTINDEX_API_KEY` + `PODCASTINDEX_API_SECRET` (or `PODCAST_INDEX_*`).

## Source of truth (no payload clones)

| Role | Path |
|------|------|
| Config registries | `_system/reference/podcasts/{show,guest,alias,officer}_*.json` |
| Transcripts + meta | `research-vault/podcasts/episodes/` (logical ref `_system/reference/podcasts/...`) |
| Whisper queue | `research-vault/podcasts/whisper_backlog.json` |
| Derived episode catalog | `research-vault/podcasts/insights.json` |
| Reader summary (source of truth) | `reader_summary` block inside each `*.meta.json` |
| Local-model analysis (claims) | `llm_analysis` block inside each `*.meta.json` |
| Episode click shards | `dashboard/data/insights/podcast_episodes/{id}.json` |
| CI slim index (fallback) | `_system/reference/podcasts/insights_index_mirror.json` (`podcast_index` rows only) |
| Dashboard shard | `dashboard/data/insights/podcasts.json` (`podcast_index` + thin `podcast_by_show`) |
| Session notes | `_system/memory/daily/{date}.md` as `[PROPOSED]` only |

Do **not** reintroduce `insights_mirror.json` as a full clone of vault insights. Highlights live in `*.meta.json` (and the vault catalog after rebuild); ticker fan-out records keep `episode_id` + claim only (no highlight arrays). Do **not** fetch full transcript `.txt` in the browser.

## Rules

- Do **not** edit `MEMORY.md`, `valuation.json`, deep dives, or base IRR
- Podcast claims never set `in_base_irr: true`
- Do **not** commit `audio-cache/` or media files (delete audio after successful Whisper)
- Hand thesis follow-up to **Marvin**; IR scrape gaps for officer directory to **Vicki**
- Deterministic resolve first; LLM only for reader summaries, claims / highlights, and ambiguous entity resolve (see `llm_usage_policy.json`)
- **Reader summaries are universal, not gated.** Every catalogued episode gets one, whatever its tickers, guests, or investment relevance. What stays gated is the expensive claims pass (`llm_analysis`) and ticker fan-out — not whether a human can understand the episode
- A stage that writes must name its reader. `llm_analysis` was written by
  `analyze_podcast_batch.py` for eight episodes — 117 claims and 229 verified
  figures — while `build_podcast_insights.py` still read only `highlights` and
  `summary`, so none of it reached the dashboard and nothing said so. The
  producer is not done until the shard carries the field.
- The security master decides ticker attribution, and it decides by *equality*
  of names. A leading-word run ("Ford" for "Ford Motor Company") counts only
  when exactly one master row matches; anything ambiguous drops the symbol. The
  character-prefix version of that rule filed four Costco claims under CMRE, a
  Greek containership lessor, because the master stores Costamare before Costco.
  A missing ticker is recoverable; a wrong one is not.

## Readable summaries for every episode — plan

### Why this plan exists (audit, 2026-10-18 — recount before starting)

The old design optimised for investment claims, not for a reader. Measured on
that date: 4,670 catalogued episodes, 4,262 transcript files, but only 1,520
episodes with a model thesis and 2,085 with the legacy extractive `summary`;
1,773 had neither. The published episode shards were worse — 2,574 of 4,663
carried neither a thesis nor a summary — and the podcast list rendered no
summary text at all. Three structural causes:

1. `analyze_podcast_episode.py` only writes a thesis when a claim about an
   ownable company survives quote verification, so most analysed episodes
   legitimately end with no thesis and the page falls back to transcript
   fragments chosen by keyword ("risk", "growth").
2. `summarize_podcast_episode.py` is gated to universe / PZ / officer /
   ticker episodes, and its LLM path was never wired to a transport — it
   silently falls through to the extractive picker.
3. Eligibility for analysis is ≥25 KB of *unique* text, which excludes most
   of the 2,032 transcript files under 25 KB (median ~3.9 KB) and every
   episode whose only source is its show notes.

Coverage must be audited end-to-end (meta → vault catalog → dashboard index →
episode shards). A summary that exists in `*.meta.json` but not in the shard
the browser loads does not count.

### The contract: `reader_summary`

Stored in each `*.meta.json`; the single source the catalog, index, and
shards project from. It is separate from `llm_analysis` (claims) and replaces
the legacy extractive `summary` as the reader-facing lead.

```json
{
  "version": "reader_summary_v1",
  "status": "ready | pending_model | needs_review",
  "source_basis": "transcript | notes | metadata",
  "source_label": "From the full transcript",
  "headline": "One plain sentence saying what the episode is about (≤20 words)",
  "overview": "2–3 short sentences, 40–75 words, no jargon left unexplained",
  "key_points": [
    {"text": "One clear point (≤24 words)", "evidence_quote": "verified span", "timestamp_seconds": null}
  ],
  "why_it_matters": "One sentence on what a listener takes away, or null",
  "coverage": {"source_chars": 0, "chunks_total": 0, "chunks_used": 0, "kind": "full | partial | notes | metadata"},
  "generated_at": "…", "model": "…", "source_sha1": "…", "prompt_version": "reader_summary_v1"
}
```

Writing rules (enforced in code, not just in the prompt):

- Plain English first: average sentence ≤20 words, none over 30; company
  names spelled out with the ticker in brackets on first mention; acronyms
  expanded or avoided. No transcript filler, no raw quotes as prose.
- Never open with show boilerplate, sponsor copy, "in this episode", or a
  host intro. Strip per-show boilerplate and ads before summarising (reuse
  the shingle method in `analyze_podcast_batch.unique_text_bytes`).
- Every number and every company named must occur in the source text;
  tickers only via the security-master equality rule already used for
  claims. A key point for a transcript summary should carry a verbatim
  `evidence_quote` that passes the same normalised substring check as
  claims (`analyze_podcast_episode.verify_quotes`); unverifiable points are
  dropped or sent to one repair retry, never published on trust.
- Length discipline: transcript summaries get 3–5 key points, notes-based
  2–4, metadata-based exactly the known facts. If the source is thin, the
  summary is short and says so — padding is a defect.

### Source tiers — every episode lands somewhere

| Tier | Source | What publishes |
|------|--------|----------------|
| A | Cleaned transcript with ≥1,200 chars of unique speech | Model summary; `kind: full` when ≥90% of chunks were used, else `partial` |
| B | Show notes / description ≥200 cleaned chars (incl. transcript files that turn out to be notes) | Constrained summary labelled "From the episode notes — transcript not yet available" |
| C | Title, show, guests, date only | Deterministic factual placeholder labelled "Episode details only — no transcript or notes yet"; never written by the model from a title alone |

At ingest, an episode immediately receives a Tier B/C summary so the site is
never blank; the Mac lane later upgrades Tier A episodes to a model summary.
Until that upgrade, `status: pending_model` and `source_basis` records the
notes/metadata actually used — the label never claims a transcript basis the
text did not come from. If the model is down, the fallback stays and the
episode queues — an extractive fragment is never promoted to look like a
finished summary.

Source recovery is part of this plan: at audit, 405 of the 408 episodes with
no transcript file still had an `audio_url`, yet were in no queue. Any
episode with audio, no transcript, and no backlog entry is an orphan —
reconcile it into `whisper_backlog.json` by priority (recent / in-book /
PZ / officer first); after the attempt cap, settle it at Tier B/C with the
dead source recorded. A Whisper attempt that yields nothing must upsert a
pending backlog item instead of writing the terminal `whisper_unavailable`.

### Generation (extend `summarize_podcast_episode.py`)

- Wire the existing local transport (`llm_local.complete`, `qwen-gpu`) —
  the current `--llm` path records intent and falls back without calling a
  model. Local model only; this lane must not consume hosted-LLM budget,
  and must not route through the hosted `podcast_highlights` gate in
  `llm_usage_policy.json`. Any future hosted transport needs a policy
  change first, with its own consumer and limits.
- Map/reduce over cleaned chunks (~12k chars, as in the claims analyser):
  each chunk yields plain-language notes with evidence quotes; the reduce
  step writes only the contract fields. Summarise the whole episode, not
  just the opening or the densest company windows. Episodes over ~24 chunks
  use evenly spaced plus entity-dense chunks and publish as
  `kind: partial` — coverage is reported, never silently overstated.
- Resumable and content-addressed like the claims batch: skip only when
  `source_sha1` + `prompt_version` still match; checkpoint to the vault on
  the same cadence; one bad episode never ends a run.
- Implemented interface: `--status` (coverage by tier/status),
  `--limit/--hours/--model`, `--priority recent,in-book,pz,officer,all`,
  `--episode <id>` for spot regeneration, `--dry-run` for pilots, and
  `--push/--push-every-minutes` for vault checkpoints.
- Deterministic validation after generation: schema, word/sentence limits,
  banned boilerplate, entity/number grounding, evidence verification,
  duplicate points. One repair retry; persistent failure → `needs_review`
  with the fallback still published.

### Dashboard (what the reader sees)

- `build_podcast_insights.py`: index rows gain `summary_preview`
  (headline + overview, ≤220 chars), `summary_source_label`,
  `summary_status`; detail shards carry the full `reader_summary`. Keep the
  index thin — full key points live only in shards. Budget: podcasts index
  grows by no more than ~1.5 MB.
- Podcasts list: render the preview under every title in readable type
  (≥13px, 1.5 line-height) with its source label; include the preview in
  search; add a "Most useful" sort (transcript summary + verified claims
  first) beside newest-first. This mirrors what the video list already does.
- Episode detail, in order: **In short** (overview) → **Key points**
  (evidence expandable) → **Why it matters** → companies/people → verified
  claims and figures (existing, clearly labelled as investment claims) →
  source box (basis, coverage, generated date, transcript/episode links).
  With a ready `reader_summary`, the old extractive lead and "Analyzed. No
  investable claims were extracted." message are retired.
- Publish gate: add `check_podcast_summary_coverage.py` reporting
  meta/catalog/index/shard coverage by tier, status, show, and year. It
  warns during rollout; once the Tier B/C fallback has been written for the
  whole corpus (rollout step 3), the refresh fails loudly if any published
  index row lacks `summary_preview`/`summary_source_label` or any shard
  lacks `reader_summary`.

### Rollout

> Status (2026-10-18): steps 0 and 2 are implemented and tested; the
> deterministic Tier B/C fallback has been written for the whole corpus
> (step 3's coverage wave) and published; the Mac lane now runs the
> reader-summary phase in steady state (step 4), draining model summaries
> in priority order — recent, in-book, PZ, officer, then all — while the
> claims phases continue behind it. The legacy extractive lead is retired
> wherever a `reader_summary` exists (step 5); it remains only as the
> transitional preview for shards not yet rebuilt.

0. **Contract + audit.** Schema, validator, coverage checker, tests.
   Exit: `summarize_podcast_episode.py --status` reproduces the audit
   numbers above from live data, split by tier and pipeline stage.
1. **Pilot (100 episodes, unpublished).** Stratified: recent, in-book,
   analysed-with-no-claims, short transcripts, published transcripts,
   notes-only, old. Reviewer scores each 1–5 on "I understand this episode
   in 20 seconds", accuracy, and usefulness. Exit: ≥90% score ≥4 on
   clarity, zero fabricated tickers/numbers, validator failure ≤10%.
   Measure episodes/hour here and only then schedule the backfill.
2. **Dashboard.** Index/detail rendering + publish gate on the pilot set.
   Exit: shard/index coverage matches meta; index size within budget.
3. **Backfill in waves** (each wave ends with rebuild + coverage report):
   new episodes at ingest → last 12 months + in-book/PZ/officer → all
   Tier A transcripts → Tier B notes → orphan-audio recovery for the rest.
4. **Steady state.** Mac lane order is: Whisper (bounded windows,
   rotating with the analysis phases so a transcription backlog cannot
   starve summaries) → YouTube captions → reader summaries (new +
   priority backlog, alternating with video analysis when both are
   waiting) → video claims → podcast claims, so episodes become readable
   before the slow claims pass. Orphan audio is reconciled into the
   Whisper backlog every cycle. The freshness check warns when the
   published reader-summary count stalls for four days while a backlog
   remains; the coverage checker gates any published episode lacking a
   preview or shard summary.
5. **Retire the legacy path.** Extractive `summary`/`highlights` stop being
   the reader-facing lead (highlights may survive as evidence quotes);
   remove the gated `should_summarize` rule and this plan's audit section.

Transcription stays as-is (`distil-large-v3` + per-episode hotwords); the
only transcription changes in scope are recording the model and segment
timestamps in meta so summaries can cite timings. Speaker diarisation is
explicitly not a blocker for readable summaries.

### Acceptance

- 100% of published podcast index rows have a non-empty `summary_preview`
  and source label; 100% of episode shards have a `reader_summary`.
- ≥98% of Tier A episodes reach `status: ready` (the rest are visible
  `needs_review`, still showing their Tier B/C fallback).
- Zero published summaries fail the boilerplate/garbled validator; a fresh
  stratified sample of 50 passes the pilot rubric at the same thresholds.
- New episodes publish with at least a Tier B/C summary in the same refresh,
  and a transcript-based upgrade within 7 days on the Mac lane.

## Analyse stage

```bash
# Coverage, no work
python _system/scripts/analyze_podcast_batch.py --status

# Run it. Yields to the Whisper backfill by default -- see --share-with-whisper.
python _system/scripts/analyze_podcast_batch.py --model qwen-gpu --hours 8
```

Needs a local model served on an OpenAI-compatible endpoint (`llm_local.py`);
there is no hosted LLM transport in this repo. CI does not run this analyser.
The workstation scheduled task **SSI Podcast Analysis** (`analysis_supervisor.ps1`,
installed by `install_local_lane_tasks.ps1`) runs it, and the same task drains
video analysis. Research Watchdog only notices when the analysed count stops
moving (`check_media_analysis_freshness.py`, 4 days). Claims are verified against the
transcript in code, so a quote the model invented is dropped rather than
believed — but verification cannot catch a *real* quote filed under the wrong
company, which is why attribution goes through the security master.

Eligible episodes are those with genuine speech: ≥25 KB of text that is unique
to the episode after per-show boilerplate is removed (run
`analyze_podcast_batch.py --status` for the live count; 1,656 eligible at the
2026-10-18 audit). That ceiling applies to claims only — reader summaries use
the lower Tier A/B/C thresholds in the plan above and cover the whole corpus.

**It shares one box with the Whisper backfill.** When both run, transcription
fell from ~3.0 to ~0.55 episodes/hour — a 5.5× collapse measured across the
checkpoints either side of `llama-server` starting on 2026-08-26. The analyser
now waits for the daemon to be idle by default.

## Mac Mini always-on lane

For the Apple Silicon Mac Mini, do **not** run the Windows PowerShell supervisors.
Install one sequenced LaunchAgent that keeps Whisper, YouTube captions, and the
qwen analysis draining without overlapping the heavy phases:

```bash
# On the Mac Mini, from a checkout of this repo:
bash _system/scripts/install_mac_media_lane.sh
# Optional: RESEARCH_VAULT_ROOT=/path/to/research-vault bash _system/scripts/install_mac_media_lane.sh

python _system/scripts/media_lane_supervisor.py --status
# Logs: ~/Projects/ssi-local-lanes/tmp/media_lane_supervisor.log
# Unload: bash _system/scripts/install_mac_media_lane.sh --unload
```

Defaults chosen so the Mini stays usable: `nice 15`, Whisper threads capped at 4,
pause below ~2.5 GB reclaimable memory, launchd soft RSS 8 GiB, YouTube Whisper
off by default (captions only; podcast Whisper owns the CPU). Same models as the
Windows lane: Whisper `distil-large-v3`, analysis `qwen-gpu` / `qwen/qwen3.5-9b`
via LM Studio (`llm_local.py` discovers the Mac `llama-server` port).

`media_lane_supervisor.py` runs `phase=reader-summary` after YouTube and
before the claims phases (and `--status` reports
`reader_summary_remaining`): making episodes readable is cheaper and more
visible than extracting claims, so it goes first, and the claims backlog
must not be allowed to starve it. Reader and video-analysis windows
alternate when both queues have work.

## Config

- `_system/reference/podcasts/show_registry.json`
- `_system/reference/podcasts/podcast_guest_registry.json`
- `_system/reference/podcasts/company_alias_overrides.json`
- `_system/reference/podcasts/officer_directory.json`
