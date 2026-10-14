# Hub payload verification October 12 2026

Verified main commit `775173fa0c37d027e1d0230422e7b5d274f9510c`. Research only; `research_only: true`, `in_base_irr: false`, `authority: none`.

The nightly intake did **not** finish successfully. Its [intake-full job](https://github.com/magis-capital-partners/single-stock-investments/actions/runs/38235435274/job/114764869861) stopped at `check_desk_briefs.py` because the runtime lacked `jsonschema`. Earlier source builders committed partial progress. PR #1150 already supplied the dependency and corrected warn-only behavior; that fix is not repeated here.

The committed core was subsequently rebuilt by the valuation lane at `3c534158c272dce0fa6696f2f1a2dc538ddeba5e`. Its build timestamp is `2026-10-12T13:25:54Z`, and `shards.desk_briefs` and `shards.reverse_splits` point to the committed feeds. A successful later rebuild does not change the failed nightly run's status.

| Artifact | Committed build timestamp | Observed coverage |
|---|---|---|
| core.json | 2026-10-12T13:25:54Z | Both new shard references |
| desk_briefs.json | 2026-10-12T01:01:13Z | Special Situations desk brief |
| reverse_splits.json | 2026-10-12T17:01:42Z | Successful Monday discovery export |
| short_alpha.json | 2026-10-12 | Schema 1.2 and 199 candidates |
| special_situations.json | 2026-10-12T11:14:54Z | Six lanes including split_offs |
| separations.json | 2026-10-12T11:14:53Z | Separation terms and modeled forced-seller rows |

`python _system/scripts/check_hub_payloads.py` verifies build stamps, references, count reconciliation, lane coverage and the authority flags on the new research feeds. It reads committed data and never edits derived JSON. It does not prove browser rendering, authenticated hosted access or a successful next scheduled intake. Those require their own evidence.

The exact requested local test command ran: 1,061 passed, seven skipped, and one failed. The failure is the existing `test_hot_routes_do_not_scan_full_history` timer assertion, already listed in `KNOWN_FAILURES` on main. The CI-parity command reports it separately and retains the repository's existing exclusion; no test or allowance was changed. Source, desk-brief, reverse-split, separation and Short Alpha checks pass. P3 and P6 pass. The full graph still reports its pre-existing E7 violation; the sparse clone additionally lacks some E5 support files, so the full source checkout at the same main SHA was checked separately. Regenerated graph reports and baselines remain outside git.
