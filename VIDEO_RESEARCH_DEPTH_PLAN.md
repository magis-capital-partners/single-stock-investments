# Video research depth — implementation plan

**Status:** proposed, 2026-09-11
**Surface:** `/#/insights/videos` — "Transcript-gated video research"
**Goal:** turn 63 admitted videos from a list of caption fragments into a clickable
research surface with a real thesis, verified quotes, stance-tagged tickers, and
jump-to-timestamp deep links.

---

## 1. Diagnosis

### 1.1 The card text is not a summary, and was never meant to be one

`_system/scripts/build_video_insights.py:33`

```python
def _preview(path: Path, limit: int = 260) -> str:
    text = " ".join(path.read_text(encoding="utf-8", errors="replace").split())
    return text[:limit].rstrip()
```

Every card's body is the literal first 260 characters of the transcript. That is
why the live surface reads:

| Video | Published card text |
|---|---|
| Mohnish Pabrai / New Money | `[music] [music] [music] Thank you, man, for taking the time to talk with me.` |
| Kan Oljefondet forsvinne? | `[applause] [snøfter] Hvor mange av dere har lagret hermetikk og vann i kjelleren` |
| Rekordhøy kroneavkastning | `[musikk] [musikk] United [musikk] States and Israel are launching air strikes` |

There is no summarization step anywhere in the video pipeline. The field is doing
exactly what it was written to do.

### 1.2 Timestamps are destroyed at fetch time

`_system/scripts/fetch_video_transcript.py:218`

```python
text = " ".join((s.text or "").strip() for s in fetched)
```

`youtube_transcript_api` returns snippets carrying `.start` and `.duration`. Both
are dropped, and the transcript lands as a single 46,000-character line. The
Whisper path discards the same thing at `fetch_podcast_transcript.py:281`
(`seg.start`).

This is the largest loss in the pipeline. A deep link to `&t=1234s` is the one
thing video research can do that letters and podcasts cannot — "jump to the 90
seconds where he says the margin thing" is the whole point of the medium — and
the data arrives free with every caption fetch.

**All 63 admitted videos are `transcript_source: youtube_captions`. Zero are
Whisper.** So the entire backlog can be re-timestamped through the caption path
with no audio re-download.

### 1.3 There is no LLM analysis for videos at all

Podcasts have `analyze_podcast_batch.py` → `llm_analysis` in the vault meta →
thesis, claims with verbatim-verified quotes, stance-tagged themes, per-ticker
commentary. 332 episodes have been through it.

Videos have no analog. What a video has instead is `relevance.sustained_tickers`,
which is keyword counting. On the XPeng interview:

```json
"sustained_tickers": [
  {"ticker": "BABA", "mentions": 4, "distinct_chunks": 2, "aliases": {"alibaba": 4}}
]
```

BABA is on that card because the string "alibaba" occurred four times. Nothing
has read what was said about it.

### 1.4 The index row throws away what the pipeline already computed

`build_video_insights.py:41` keeps `sustained_tickers` and discards, per video:

- `relevance.mentioned_only` — on the XPeng video that is NVDA, TSLA and EVO.ST,
  all computed, none shown
- `description` — YouTube's own blurb, frequently a serviceable human summary
- `aliases` — which words actually fired the ticker match
- `resolve_preview.ambiguous` — the unresolved person/company pairs
- `chars_per_minute`, `caption_manual_available`, `caption_track_count`

### 1.5 Nothing is clickable

`dashboard/insights-viz.js:885` renders a bare `<article class="video-research-row">`
with no click target, and there is no per-video shard to load.

Podcasts already have the whole pattern working: `data-podcast-episode` on the row
(`insights-viz.js:824`) → `selectedEpisodeId` → lazy fetch of
`data/insights/podcast_episodes/<id>.json` → `renderPodcastEpisodeDetail`
(`insights-viz.js:632`). Videos need the same thing and most of it is copyable.

---

## 2. Plan

Six phases. Phase 0 unblocks Phase 2's timestamp anchoring; Phase 1 ships visible
value with no model involved and can land independently.

### Phase 0 — stop discarding timestamps

**Files:** `fetch_video_transcript.py`, `fetch_podcast_transcript.py`

Write a `.segments.json` sidecar beside each `.txt`:

```json
[{"t": 12.4, "d": 4.1, "text": "How far ahead of uh Europe and the US"}, ...]
```

Keep the `.txt` **byte-identical**. The relevance scorer, the alias matcher and
the verbatim-quote check all read the flat text; changing its shape would ripple
through the gate and invalidate the ratchet. A sidecar is additive and reversible.

In the Whisper path, capture `seg.start` the same way — that path produces no
admitted videos today but will.

**Done when:** a newly fetched video has a sidecar whose concatenated `text`
fields reproduce the `.txt` under whitespace normalisation.

### Phase 1 — per-video detail shard and click-through (no model)

**New:** `_system/scripts/build_video_detail.py` →
`dashboard/data/insights/video_details/<video_id>.json`

Carry everything §1.4 currently drops. This alone replaces "260 characters of
applause" with an actual evidence trail: which aliases fired, how many times, in
how many chunks, plus the mentioned-only tickers and YouTube's own description.

**Frontend:** `insights-viz.js`

- add `data-video-id` to the row at :885, make the card a click target
- `renderVideoDetail()` mirroring `renderPodcastEpisodeDetail()` at :632
- reuse the existing lazy-load and `← Back` machinery verbatim

**Done when:** clicking a card opens a detail view; no card body shows `[music]`.

### Phase 2 — local-model video analysis

**New:** `_system/scripts/analyze_video_batch.py`, forked from
`analyze_podcast_batch.py`

Inherit as-is: chunking with overlap (12k/1.2k), density ranking, the `MAX_CHUNKS`
spend cap, **verbatim-quote verification in code**, `quote_verified_rate`,
`vault_lock` push, and resume-by-`transcript_sha1`.

Three video-specific changes:

**(a) Anchor every claim to a timestamp.** After a quote passes verification it is
by definition a literal substring of the flat transcript. Take that character
offset, walk the Phase 0 sidecar, attach `t_start`. Exact, not fuzzy — this is the
payoff from Phase 0.

**(b) Prompt by channel role.** `_system/reference/video/channel_registry.json`
already classifies the six channels. An operator interview and an allocator
interview are different evidence and deserve different questions:

- *Norges Bank / In Good Company, Fundsmith* → the guest runs the business or the
  fund. Extract what they claim about their own economics — capacity, pricing,
  competition, reinvestment — and flag it as self-reported.
- *Mohnish Pabrai, Talks at Google–style* → the guest is an outside allocator.
  Extract position views and the reasoning chain behind them.

**(c) Emit chapters.** Chunk boundaries already exist; ask for one topic label per
chunk and keep its `t_start`. Cheap, and it makes a 51-minute video navigable.

**Output** (into vault meta as `llm_analysis`, mirroring podcasts):

```json
{
  "thesis": "3-4 sentences on what this video actually argues",
  "claims": [{"company","ticker","stance","claim","quote","t_start","speaker","self_reported"}],
  "numbers": [{"what","value","quote","t_start"}],
  "themes": [{"theme","stance"}],
  "chapters": [{"topic","t_start"}],
  "quote_verified_rate": 0.0,
  "transcript_sha1": "...", "analyzed_at": "..."
}
```

**A model-proposed ticker is a suggestion, not a fact.** It must resolve through
the existing alias master before it is published — the podcast lane already filed
Costco claims under a Greek shipping company and let IVZ stand for Vanguard.
Reuse `resolve_podcast_entities` / `repair_claim_tickers`.

**Cost:** 2,533,565 transcript characters across 63 admitted videos ≈ **211 chunks**
at 12k. Podcast runs logged 324–438s per episode at up to 8 chunks. The entire
backlog is one overnight run; steady state is 1–2 new videos/day.

### Phase 3 — rebuild the card

Replace `transcript_preview` with a fallback chain, first hit wins:

1. `llm_analysis.thesis`
2. YouTube `description`, first two sentences
3. the highest-confidence verified claim
4. the existing 260-char preview — **only** after stripping `[music]`,
   `[applause]`, `[musikk]` and leading filler

Add to the card: stance-tagged ticker pills (bullish/bearish/mixed, not bare
tickers), claim count, chapter count, and the verified-rate badge.

Sort: the list is currently pure reverse-chronological. With stance and claims
available, offer "most relevant to book" as the default ordering — the
"Our book overlap" checkbox already exists and currently only filters.

### Phase 4 — the detail view proper

Sections, in order: thesis · chapters with jump links · claims grouped by ticker,
each with its verbatim quote and a `youtube.com/watch?v=ID&t=NNNs` link · numbers ·
themes · provenance footer (caption type, manual vs auto, chunks analysed,
verified rate, model, analysed-at).

Provenance is not decoration. A video analysed at `quote_verified_rate: 0.5` had
half its claims discarded, and that is a fact about the video, not a debugging
statistic — the podcast lane already treats it that way.

### Phase 5 — lanes, backfill, tests

**Backfill captions with timestamps.** 63 videos through the existing paced
fetcher. YouTube blocks even at 150s pacing from this IP — 15 blocks in one 10h
run — so this runs overnight through `youtube_supervisor.ps1` with its existing
backoff. **Do not add a second fetch path.**

**New supervisor:** `video_analysis_supervisor.ps1`, modeled on
`analysis_supervisor.ps1`. It must contend for the *same* mutex as podcast
analysis (`Global\ssi-podcast-analysis`) or a sibling that excludes it — running
the analyser beside Whisper cost 5.5× throughput last time. One local-model
consumer at a time.

**`publish_video_dashboard.py`** writes the detail shards and counts them in
`manifest.source_health.videos`.

**Extend `_system/scripts/test_video_delivery.py`:**

- the detail shard exists for every admitted video and is lazy-loaded, not bundled
- every published claim's `quote` verifies as a literal substring of its transcript
- every `t_start` falls inside `0 .. duration_seconds`
- no published card body contains `[music]`/`[musikk]`/`[applause]`

---

## 3. Known hazards

| Hazard | Mitigation |
|---|---|
| Windows console is cp1252; these titles carry Norwegian characters and em-dashes. A progress line that *reports* success is what crashes. | Copy the `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` guard from `analyze_podcast_batch.py`. |
| The Whisper daemon commits to the vault every 15 minutes; two git processes collide on `.git/index.lock`. | Reuse `vault_lock` — already in the podcast batch. |
| A failed vault push is silently reverted on the next lane run. The tell is `insights_index_mirror.json` disagreeing with `videos.json`. | Assert the two agree in `test_video_delivery.py`. |
| The count of admitted videos will not move; quality will. A green lane proves nothing. | `quote_verified_rate` and claims-per-video are the metrics, not `video_count`. |
| `youtube-refresh.yml` targets `[self-hosted, linux, youtube-egress]` and **has never run** — zero runners carry that label. | All of this runs through the local scheduled tasks. Do not assume CI exercises any of it. |
| No CI workflow in this repo runs pytest. | Run `test_video_delivery.py` locally and paste the result in the PR body. |

Nothing in this plan touches ThetaData, the IB Gateway, or D1 write volume.

---

## 4. Sequencing

Phase 1 is independent and ships first — it is a visible improvement with no model
in the loop. Phase 0 must land before Phase 2 can anchor timestamps. Phases 3 and 4
consume Phase 2's output and can land together. Phase 5 closes the loop.

```
Phase 0 ──┐
          ├── Phase 2 ── Phase 3 ─┬── Phase 5
Phase 1 ──┘                       │
                       Phase 4 ───┘
```
