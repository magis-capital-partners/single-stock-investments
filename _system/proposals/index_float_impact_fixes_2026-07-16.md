# Float-impact fix plan: kill false migrations, false candidates, and misleading constants

**Date:** 2026-07-16
**Status:** Implemented 2026-07-16
**Owner:** Marvin
**Follows:** `index_float_impact_plan_2026-07-15.md` (implemented), dashboard screenshot review 2026-07-16
**Human decisions:** (1) mcap-heuristic seed backfill APPROVED; (2) graduation ceiling = **4× breakpoint** (~$22.8B) — keeps APLD-class graduates, excludes mega-caps; band-top too tight for inferred path; (3) candidates **stay** in float-impacts table (expected + actual); (4) Yahoo float OK with SEC shares cross-check/fallback.
**Verdict from review:** APLD is correct. Most other rows are wrong for event-classification reasons, not float-math reasons. The calculator is sound; its inputs are polluted.

---

## 1. Root causes (traced to exact code)

### RC1 — Style/subset aliases collapse into `russell_1000`

`_system/scripts/index_event_extract.py` → `INDEX_ALIASES` maps "russell 2500", "russell midcap", "russell defensive", "russell top 50", "russell growth/value", and bare "russell" all to `russell_1000`. A WEST "added to Russell 2500 Value Benchmark" headline becomes `reclassify russell_1000`.

The extractor *does* have `_is_style_or_subset_index()`, and some announcement rows carry `style_subset: true` (WEST R2000 row), but:
- the flag is not attached on every harvest path (AMAT/CPRT/AMP rows in `index_announcements.jsonl` have no `style_subset` field), and
- `extract_index_events()` does not return the flag per event, so downstream consumers must re-derive it.

### RC2 — Flow model treats every `reclassify russell_1000` as a graduation

`_system/scripts/index_flow_impact.py` → `expand_migration_legs()`:
- `_GRADUATION_CUES` regex contains `reclassif`, which matches every "reclassification" headline;
- the `reclassify` branch falls into full graduation legs whenever `primary_index == "russell_1000"`;
- the `add` branch assumes graduation when memberships are unknown (`not mems`).

Result: AMD (mega-cap, already R1000/S&P 500), AMAT, AMP, CPRT, HE, WEST all print the APLD-shaped −6.4% with a bogus HK-cliff badge.

### RC3 — Style/subset events reach the flow model at all

`events_from_ticker_row()` skips `style_subset` news notes only when another parent event exists. Style-box moves (Value↔Growth, Defensive, Top 50, 2500) change *style product* weights, which our AUM registry does not model. They must produce **no size-migration flow** — `n_a` with reason `style_subset`.

Also: `build_index_membership.py` promotes `quality_gated` news into `confirmed_events` without carrying/checking `style_subset`, so the confirmed table shows style noise as if they were membership flips.

### RC4 — Membership seed gaps make mega-caps look index-less

`_system/data/index_memberships_seed.json` has empty `memberships` for AMAT, AMP, ADBE, ABNB, ACN, SNOW, RPRX, etc. Consequences:
- unknown membership triggers RC2's "assume graduation" path;
- non-membership + RC5's broken breakpoint makes mega-caps `inclusion_candidate` for the Russell 2000.

### RC5 — Portfolio-proxy Russell breakpoint is nonsense

`build_index_membership.py` → `russell_breakpoint_mcap()` returns the **median market cap of seed R1000 members in our portfolio** (~$86.5B). The real June 2026 breakpoint is **$5.7B** (band $2.7B–$9.6B, LSEG). Everything within ±15% of $86.5B became an R2000 "candidate" (ADBE, ACN, CME, SNOW, ABNB...), each printing the constant +7.1%.

### RC6 — `float_unknown` rows display precise-looking constants

Cap-weighted math makes pure-add % of float equal `AUM / index_total_mcap` for every stock (that part is correct math), but rows missing float/ADV still display "+7.1%" with no visual downgrade. Only APLD has real float/ADV in `index_float_adv.json`.

---

## 2. Constraints

- Keep: APLD result (−3.3% low / −6.4% base, HK cliff ~10×, both-sided legs); never-invent guardrail; additive schema; existing caption.
- Do not break: `index-viz.js` consumers, holdings-table `priority_score` sort, `test_index_event_extract.py` golden tests (extend, don't regress).
- Non-goals: modeling style-box (Growth/Value) flow magnitudes; non-US indexes; licensing constituent data.

---

## 3. Fixes (phased, with exact touch points)

### Phase A — Event extraction returns style/subset truth (RC1, RC3-input)

`_system/scripts/index_event_extract.py`:

1. `extract_index_events()` returns `style_subset: bool` **per event** (computed via `_is_style_or_subset_index` against the matched alias text, not the whole title).
2. Add dedicated alias targets instead of collapsing to parent where we have AUM config: "russell midcap" → `russell_midcap` (exists in `index_aum.json`). Keep 2500/3000E/Defensive/Top 50/Growth/Value → parent id **with `style_subset: true` always**.
3. Bare-"russell" and "index reclassification" defaults (`_default_index_from_text`) must also set `style_subset: true` — a headline that never names R1000/R2000 explicitly cannot assert a parent membership flip.
4. Golden tests to add (extend `_system/scripts/tests/test_index_event_extract.py`):
   - AMD "Joins Russell Top 50" → event has `style_subset: true`
   - CPRT "Index Reclassification" → `style_subset: true`
   - WEST "added to Russell 2500 Value Benchmark" → `style_subset: true`, index stays parent-tagged
   - APLD "Joins Russell 1000" → `style_subset: false` (regression)

### Phase B — Harvest writes the flag everywhere (RC3)

`_system/scripts/build_index_membership.py`:

1. Every announcement row written to `index_announcements.jsonl` (live harvest **and** review/archive recovery paths) carries `style_subset` from the extractor.
2. One-time migration: re-tag existing rows in `index_announcements.jsonl` by re-running titles through the extractor; log changed rows.
3. `confirmed_events` and `news_notes` rows keep `style_subset`; the Confirmed table label shows "style/subset" like the news-notes table already does.
4. Quality gate: `reclassify` events that are `style_subset` never set scorecard `confidence` upgrades and never mark `confirmed_soon`.

### Phase C — Flow model hard-gates migrations (RC2)

`_system/scripts/index_flow_impact.py`:

1. **Remove `reclassif` from `_GRADUATION_CUES`.** Graduation cues become explicit only: "joins russell 1000", "added to russell 1000", "removed/dropped from russell 2000", "graduat", "moves up to russell 1000".
2. **`style_subset` events → no flow.** `compute_event_impact` returns `status: "n_a", reason: "style_subset"` when the event carries the flag. (Optional later: model style flow with style-product AUM; out of scope now.)
3. **`reclassify` action → no size legs by default.** Only compute when the title contains explicit two-sided evidence ("from Russell 1000 to Russell 2000" or vice versa). Otherwise `n_a`, reason `reclassify_ambiguous`.
4. **Membership-aware add legs.** For `add russell_1000`:
   - R2000 sell leg only when `russell_2000` is in `current_memberships` **or** title has explicit graduation cues;
   - when memberships are unknown, apply an **mcap sanity gate**: add the R2000 exit leg only if `market_cap_usd ≤ graduation_mcap_ceiling` (config: 4 × real breakpoint ≈ $23B). APLD ($10–13B) passes; AMD ($300B+) fails → one-sided tiny R1000 add, no fake cliff.
   - flag `assumed_graduation: true` whenever the pair was inferred rather than announced, and cap its confidence at `news_unconfirmed`.
5. **Member no-op guard.** If seed says the ticker is already a member of the target index, an `add` event produces `n_a`, reason `already_member` (covers AMD/CPRT being "added to" an index they are in).
6. **Candidate impacts require real inputs.** `events_from_ticker_row` computes candidate (`rules_only`) impacts only when: scorecard confidence is not `portfolio_proxy`-ranked (see Phase D), `float_flag == "float_adj"`, and ADV is present. Otherwise skip — no more +7.1% wallpaper.

### Phase D — Real Russell breakpoint, real candidate logic (RC4, RC5)

1. `_system/data/index_rules.json` → add dated breakpoint facts:
   ```json
   "russell_1000": { "breakpoint_mcap_usd": 5.7e9, "band_usd": [2.7e9, 9.6e9], "breakpoint_as_of": "2026-06-26" }
   ```
   (Source: LSEG June 2026 recon summary; refresh at each recon alongside `index_aum.json`.)
2. `build_index_membership.py`:
   - `russell_breakpoint_mcap()` prefers the config value; the portfolio-median proxy survives only as a labeled last-resort fallback (`rank_method: "portfolio_proxy_fallback"`), and candidates from the fallback are **suppressed** from float impact and the Potential table by default.
   - R1000 candidacy: non-member with mcap **above** breakpoint (within band → note "banding may hold").
   - R2000 candidacy: non-member with mcap **inside [band_low, breakpoint]** — a $150B ADBE can never be an R2000 candidate again.
3. **Seed backfill** (one-time script `_system/scripts/backfill_russell_seed.py`):
   - For US holdings with `market_cap_usd ≥ 2 × breakpoint` and empty memberships: seed `russell_1000` (+ `sp500` only if already seeded elsewhere — do not invent S&P committee decisions), tagged `source: "mcap_heuristic_2026-07-16"` and `confidence: "heuristic"`.
   - For US holdings inside the R2000 mcap range: seed `russell_2000` with the same heuristic tag.
   - Emit a review file `_system/reviews/pending/russell_seed_backfill_2026-07-16.md` listing every seeded row for human sign-off; heuristic seeds display with a distinct badge until approved.
4. Lint additions (`lint_announcement_conflicts` or new checks in the build): warn when
   - an `add` event targets an index the seed already lists as member;
   - a `reclassify` event lacks `style_subset` and any explicit parent pair;
   - a float-impact event fires with `float_flag != "float_adj"` and `|pct_of_float_base| > 3%`.

### Phase E — Display honesty (RC6)

`dashboard/index-viz.js` (+ `docs/` copy):

1. `% float` cell shows **"~+7.1%*"** style with an asterisk and muted color when `float_flag == "float_unknown"`, and a tooltip: "Cap-weighted constant (AUM ÷ index mcap); not stock-specific — float/ADV missing".
2. Rows with `status: n_a` (style_subset, reclassify_ambiguous, already_member) show "—" with the reason in the tooltip; HK cliff badge renders **only** when `is_russell_breakpoint_migration && float_flag == "float_adj"`.
3. Float-impacts table default filter: confirmed/news events with `float_adj` first; a "show estimates" toggle reveals `float_unknown` and candidate rows.
4. `assumed_graduation` rows get a small "pair inferred" badge.

### Phase F — Float/ADV coverage engine (makes % floats stock-specific)

New `_system/scripts/fetch_float_adv.py`:

1. Sources, in order: SEC company-facts (`shares_outstanding`, free — `_system/reference/securities/sec_company_tickers.json` already exists for CIK mapping); Yahoo quote summary (float, 3-mo ADV) with the same descriptive User-Agent and rate limits as existing fetchers.
2. Writes `_system/reference/market-data/fundamentals/index_float_adv.json` rows: `float_pct`, `float_shares`, `shares_outstanding`, `adv_shares`, `adv_dollar`, `price`, `source`, `as_of`. Missing stays missing.
3. Priority order for the first run: tickers with confirmed/news index events, then near-boundary candidates, then remaining US holdings. `--tickers`, `--only-events`, `--max` flags.
4. Wire into runbooks: `marvin_cloud_refresh.py` step and `batch_portfolio_refresh.py` weekly; staleness >90 days flags the row.
5. BE (Bloom Energy) gets real numbers, replacing the approximate seed, and becomes validation case #2.

### Phase G — Regression tests + validation rerun

`_system/scripts/tests/test_index_flow_impact.py` additions:

| Test | Expectation |
|------|-------------|
| AMD "Joins Russell Top 50" (member R1000, mcap $300B) | `n_a` (style_subset / already_member); no legs; no cliff |
| CPRT "Index Reclassification" | `n_a` reclassify_ambiguous |
| WEST "Russell 2500 Value Benchmark" | `n_a` style_subset |
| HE "Russell Defensive Indexes" | `n_a` style_subset |
| ADBE with real breakpoint | not an R2000 candidate; no float impact |
| Unknown-membership add with mcap $8B | graduation legs + `assumed_graduation: true` |
| Unknown-membership add with mcap $300B | one-sided add, no R2000 leg |
| APLD golden case | unchanged: low −3.3%, base −6.4%, cliff ~10×, both-sided |

Then: rebuild `index_membership.json`, verify the screenshot pathologies are gone (no identical −6.4% pack, no +7.1% mega-cap pack), update `SYNTHESIS.md` § Model validation with the post-fix table, sync `docs/`, run full unittest suite.

---

## 4. Success criteria

1. APLD row unchanged (low −3.3% / base −6.4%, HK cliff ~10×).
2. AMD, AMAT, AMP, CPRT, HE, WEST show "—" (n_a: style/ambiguous/member) — zero fake graduations.
3. ADBE, ABNB, ACN, CME, SNOW no longer R2000 candidates; no constant +7.1% block.
4. Every displayed % float is either float-adjusted (normal styling) or explicitly asterisked as a cap-weighted constant.
5. HK cliff badge appears only on genuine breakpoint migrations with real float.
6. Breakpoint used everywhere is the dated $5.7B config value, never the $86.5B portfolio median (unless labeled fallback, suppressed from display).
7. All existing + new unit tests pass; announcement lint reports zero unexplained conflicts on rebuild.

## 5. Risks / trade-offs

- **Recall loss:** hard-gating reclassify events will drop some genuine size migrations reported with sloppy headlines. Mitigation: mcap sanity gate + `assumed_graduation` path keeps plausible ones; lint surfaces dropped events for review.
- **Heuristic seeds are beliefs:** mcap-based R1000 seeding could be wrong near the band. Mitigation: heuristic tag + pending-review file + distinct badge; never feeds Milly-final claims.
- **Yahoo float quality varies** (insider vs restricted definitions). Mitigation: record source per row; SEC shares outstanding as cross-check; APLD/BE spot-validated by hand.
- **Breakpoint staleness:** semi-annual recon (next: 2026-12-11) changes the breakpoint. Mitigation: `breakpoint_as_of` + same staleness warning as AUM registry.

## 6. Implementation order & effort

| Step | Files | Size |
|------|-------|------|
| A. Extractor style flag per event | `index_event_extract.py`, extractor tests | S |
| B. Harvest carries flag + jsonl re-tag | `build_index_membership.py`, `index_announcements.jsonl` | S |
| C. Flow-model gates | `index_flow_impact.py` | M |
| D. Real breakpoint + candidate logic + seed backfill | `index_rules.json`, `build_index_membership.py`, new backfill script, review file | M |
| E. Display honesty | `index-viz.js` (+docs copy) | S |
| F. Float/ADV fetcher | new `fetch_float_adv.py`, runbook wiring | M |
| G. Tests + rebuild + validation docs | tests, `SYNTHESIS.md`, `index_membership_lens.md` | S |

Recommended sequence: A → B → C → D (unblocks correctness) → G (verify) → E (cosmetic honesty) → F (coverage, can trail).

## 7. [HUMAN REVIEW]

1. Approve the mcap-heuristic Russell seed backfill list before heuristic badges are removed (`_system/reviews/pending/russell_seed_backfill_2026-07-16.md`).
2. Graduation mcap ceiling: 4 × breakpoint (~$23B) — right multiple, or prefer band-top ($9.6B) strictness?
3. Should candidate (`rules_only`) rows appear in the float-impacts table at all, or confirmed/news only (candidates stay in the Potential table)?
4. Yahoo as float source: acceptable, or SEC-only (shares outstanding, float approximated as 1 − insider%) until a licensed source exists?
