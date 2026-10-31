# tape_index index backfill

Known-answer set for the index desk. Each row compares `dashboard/data/index_membership.json` as it was committed before an index review with the same file as it was committed after that review. The comparison is point-in-time. The file at HEAD is not used to judge a past date.

This folder is research only. It is not a dashboard feed, and nothing here is a position or a stance.

## File

```
_system/data/desk_evals/tape_index/index_backfill_<YYYY-MM-DD>.json
```

The date is the day the set was generated. A later generation is a new file.

## How the two snapshots are chosen

Commit date is the America/New_York calendar date of the committer timestamp. A trading day is an NYSE session. Weekends and the 2026 full-day NYSE holidays listed in `history.nyse_holidays_2026` are not sessions. An early close still counts as a session.

- **Before.** The last commit on or before the date that is ten NYSE sessions prior to the effective date. The effective date itself is not counted.
- **After.** The first commit after the effective date.

Events come from the `calendar` array inside the historical files. A known answer is a change in `current_memberships` for an index in that event's family, and only for a ticker present in both snapshots. A ticker that exists in only one snapshot is not graded.

## Grades

On a case:

| Grade | Meaning |
|---|---|
| `hit` | The before scorecard flagged that index, and membership changed in the flagged direction. |
| `miss` | The before scorecard flagged that index, and membership did not change in the flagged direction. |
| `unflagged_change` | Membership changed, and the before scorecard had no candidate, near-miss, or deletion-risk flag on that index. |

On an event, `grade` is `graded` or `insufficient_history`. Insufficient history means there is no commit on or before the ten-session cutoff, or no commit after the effective date. Those events are listed and not scored.

## Flags

The flag is the before snapshot's scorecard `status` for that index.

| Status | Role | Direction that counts as a hit |
|---|---|---|
| `inclusion_candidate` | candidate | index was added to `current_memberships` |
| `banding_hold` | near-miss | index was added |
| `committee_watch` | near-miss | index was added |
| `deletion_risk` | deletion risk | index was removed |

`flagged_status` is that status, or null when the case is an unflagged change.

`mcap_before` is the scorecard market-cap check value. `rank_before` is `rank_estimate` when the file stored one, otherwise the rank check value. Both are null when that scorecard did not store them.

## Case outcomes

`outcome` is `added`, `removed`, or `unchanged`, except for a Russell 1000/2000 migration:

- `promoted_into_russell_1000` and `promoted_out_of_russell_2000` when a ticker leaves Russell 2000 and enters Russell 1000
- `demoted_into_russell_2000` and `demoted_out_of_russell_1000` for the reverse

`russell_1000_2000` at the top of the file lists every such migration in the graded windows and in the whole history of this file.

## Catch rate

`hits / (hits + unflagged_changes)`.

Misses stay in the summary and stay out of the denominator. The rate is null when the denominator is 0, which means the two snapshots show no membership change for that family.

## Other fields

- `generated_at` is when this file was built.
- `method` is the point-in-time rule in one paragraph.
- `before_commit` and `after_commit` carry `sha` and `date`. Graded rows also carry `committed_at`, the file's own `as_of`, and, on the before commit, `nyse_sessions_before_effective`.
- `before_portfolio_summary` is the before file's `inclusion_candidates`, `deletion_risks`, and `provider_confirmed_events`. The last of those is the count stored on `portfolio_summary`, not a list of events. The candidate list is the whole book. A case is opened only when the flag is on an index in this event's family.
- `off_calendar_membership_edits` lists commits that changed `current_memberships` outside a graded before/after pair, so those edits are not silently treated as the June Russell reconstitution.
- `summary` on each event, and the top-level `summary`, count hits, misses, unflagged changes, and the catch rate. Insufficient events store null counts and are not added into the top-level totals.
