# Human review queue

Generated 2026-10-16T17:58:38Z by `_system/scripts/build_review_queue_rollup.py`.
Pending files: **965** · needing a human verdict: **943** · approved/: 26 · expired/: 109 · auto_closed/: 0

## Needs a human verdict

| Type | Count | Oldest | Max age (d) | What it asks of you |
|------|-------|--------|-------------|---------------------|
| Deep dive | 44 | 2026-05-21 | 148 | Read the dive, set stance/archetype, then move to approved/. Never auto-expires. |
| One-off analysis / audit | 13 | 2026-06-01 | 137 | Read once and file; these were written for a specific question. |
| Plan / proposal | 12 | 2026-06-01 | 137 | Accept, amend or reject the proposed change of process. |
| Unclassified | 12 | - | - | Unclassified filename: add a pattern to QUEUE_TYPES. |
| World-model review | 12 | 2026-09-06 | 40 | Confirm or reject the proposed world-model / KPI context change. |
| CVR discovery | 10 | 2026-07-23 | 85 | Confirm newly discovered CVRs before they enter the universe. |
| Cross-check report | 4 | 2026-06-01 | 137 | Adjudicate the disagreements between sources before the valuation is trusted. |
| Sleeve onboard proposal | 2 | 2026-07-17 | 91 | Approve or reject the proposed sleeve additions, then move to approved/. |
| Deep dive depth scorecard | 1 | 2026-06-04 | 134 | Decide which thin dives get re-run. |
| Canonical memory triage | 1 | - | - | Disposition durable beliefs; company observations and artifacts are routed automatically. |
| Standing working document | 14 | - | - | No date, no cadence: the human moves it out when it stops being useful. |

## Onboard checklists

- In pending: **818**
- Closable by the registry gate now: **0**
- Blocked on something the gate cannot check: **818**
- Already auto-closed to `_system/reviews/auto_closed/`: 0

A checklist closes only on positive evidence. A registry field still at its
onboarding default (`unknown`, `unproven`, `pending`, `watch`, `-`), an unassigned
sleeve, an empty `ir_roots` or a deep dive that was never produced is a blocker,
not a pass.

**What the gate does and does not establish.** It checks that values are present,
well formed and agree across sources - not that they are correct. A CIK that is
present in both `registry.json` and `us_ticker_config.json` and identical in both
still passes when it belongs to a different issuer, and an `ir_roots` URL passes on
shape alone; nothing here fetches it or ties it to the company. Read an auto-close
as "internally consistent and off its defaults", not as "verified".

### Fix by class, not by file

Each row is one kind of missing registry data. Fixing the class clears every
checklist counted in it, so work top-down rather than file-by-file.

| Blocker | Checklists | One fix clears them all | Example tickers |
|---------|-----------|-------------------------|-----------------|
| `classification_unconfirmed` | 818 | The named fields are still at the onboarding defaults (archetype='unknown', moat='unproven', dhando='pending', stance='watch', cycle='-', moi_bucket='pending', payoff_lens='pending'). The checklist asks a human to confirm them, so a default cannot count as confirmed. | `0388.HK`, `319A.T`, `7176.T`, `9984.T`, `A`, `AAL`, `AAOI`, `AAPL` +810 more |
| `ir_roots_missing` | 676 | Add at least one investor-relations root URL to holdings.<T>.download.ir_roots. An empty list is not a verified IR URL. | `A`, `AAL`, `AAPL`, `ABMD.CVR`, `ABNB`, `ABT`, `ACA`, `ACGL` +668 more |
| `deep_dive_absent` | 609 | The checklist's 'review deep dive PR when Cloud Agent completes' line is only waivable once the dive exists. Run the deep dive (or drop the ticker) so that a {TICKER}/research/deep_dive_{date}.md or a {TICKER}_deep_dive_{date}.md review artifact is on disk. | `ABMD.CVR`, `ACA`, `AMGN`, `AMKR`, `AMPX`, `AMRZ`, `AMT`, `ANET` +601 more |
| `sleeve_unassigned` | 389 | Assign holdings.<T>.classification.investment_sleeve; '-' is the no-sleeve sentinel, not a sleeve. | `319A.T`, `9984.T`, `ACA`, `AMR`, `AMRZ`, `ASPN`, `AXON`, `B` +381 more |
| `company_name_placeholder` | 163 | holdings.<T>.company is still the bare symbol; set the real legal name. | `AAL`, `ACHR`, `ACLS`, `ACMR`, `AEHR`, `AFRM`, `AI`, `ALAB` +155 more |
| `cik_missing_in_registry` | 41 | Set holdings.<T>.download.cik from SEC EDGAR, and add the same CIK to _system/scripts/us_ticker_config.json (it is read first and shadows the registry). | `ABMD.CVR`, `ABX`, `ARKK`, `ASHR`, `AZLCZ`, `BWEL`, `CHNL`, `CMSG` +33 more |

`classification_unconfirmed` by field set:

- `archetype,moat,dhando,stance,cycle,moi_bucket,payoff_lens` - 781
- `moat,dhando,stance,cycle,moi_bucket` - 9
- `moat,stance,moi_bucket` - 9
- `stance` - 4
- `stance,moi_bucket` - 4
- `moat,dhando,stance,cycle,moi_bucket,payoff_lens` - 3
- `moat,stance,cycle,moi_bucket` - 3
- `moat,stance,cycle,moi_bucket,payoff_lens` - 3
- `moat,cycle,moi_bucket,payoff_lens` - 1
- `moat,stance,moi_bucket,payoff_lens` - 1

## Superseded snapshots and receipts (auto-expiring)

| Type | Count | Cutoff (d) | Keep latest | Expiring now | Why it expires |
|------|-------|-----------|-------------|--------------|----------------|
| Portfolio news scan | 3 | 30 | 3 | 0 | Digest of a rolling 30-day feed window; at 30 days a newer digest covers the same window. |
| Activist triage table | 2 | 30 | 2 | 0 | Cumulative: row count only grows, so the newest table strictly contains the older ones. |
| Agent dispatch receipt | 2 | 30 | 2 | 0 | Records that jobs were dispatched; carries no verdict. |
| Batch onboard receipt | 2 | 30 | 2 | 0 | Run receipt for a batch whose per-ticker artifacts are queued separately. |
| Darwin regime brief | 2 | 14 | 2 | 0 | States the CURRENT regime. A stale regime label is not reviewable, it is wrong. |
| Event triage table | 2 | 30 | 2 | 0 | Full daily restatement of every unresolved row; still-open rows carry forward. |
| Filing insights table | 2 | 30 | 2 | 0 | Full daily restatement of unresolved parser rows. |
| Fund family proposals | 2 | 21 | 2 | 0 | Re-detected from scratch each run; unpromoted proposals reappear in the newer file. |
| ls-algo IC queue | 2 | 14 | 2 | 0 | Snapshot of live triggers at that day's prices; a stale trigger list is misleading. |
| Transcript coverage report | 2 | 14 | 2 | 0 | Restates coverage for all holdings every run; the newest file dominates. |
| Activist press digest | 1 | 30 | 2 | 0 | Restated from a fixed seed list each run; nothing is unique to an old copy. |

## Oldest items awaiting a verdict

- `3905.T_deep_dive_2026-05-21.md` — 148d (deep_dive)
- `AMZN_deep_dive_2026-05-21.md` — 148d (deep_dive)
- `APLD_deep_dive_2026-05-21.md` — 148d (deep_dive)
- `BN_deep_dive_2026-05-21.md` — 148d (deep_dive)
- `CPRT_deep_dive_2026-05-21.md` — 148d (deep_dive)
- `CSGP_deep_dive_2026-05-21.md` — 148d (deep_dive)
- `CSU_deep_dive_2026-05-21.md` — 148d (deep_dive)
- `DHR_deep_dive_2026-05-21.md` — 148d (deep_dive)
- `FRMO_deep_dive_2026-05-21.md` — 148d (deep_dive)
- `GOOGL_deep_dive_2026-05-21.md` — 148d (deep_dive)
- `ICE_deep_dive_2026-05-21.md` — 148d (deep_dive)
- `KEWL_deep_dive_2026-05-21.md` — 148d (deep_dive)
- `OTCM_deep_dive_2026-05-21.md` — 148d (deep_dive)
- `QDEL_deep_dive_2026-05-21.md` — 148d (deep_dive)
- `SJT_deep_dive_2026-05-21.md` — 148d (deep_dive)
- `SPGI_deep_dive_2026-05-21.md` — 148d (deep_dive)
- `TEQ.ST_deep_dive_2026-05-21.md` — 148d (deep_dive)
- `WBI_deep_dive_2026-05-21.md` — 148d (deep_dive)
- `ICE_deep_dive_2026-05-22.md` — 147d (deep_dive)
- `3905.T_deep_dive_2026-05-23.md` — 146d (deep_dive)
- `MSB_deep_dive_2026-05-25.md` — 144d (deep_dive)
- `3905.T_deep_dive_2026-05-26.md` — 143d (deep_dive)
- `8697.T_deep_dive_2026-05-26.md` — 143d (deep_dive)
- `AMZN_deep_dive_2026-05-26.md` — 143d (deep_dive)
- `APLD_deep_dive_2026-05-26.md` — 143d (deep_dive)
