# Hub deployment verification October 12 2026

Research only; `research_only: true`, `in_base_irr: false`, `authority: none`.

The [Pages deployment](https://github.com/magis-capital-partners/single-stock-investments/actions/runs/38281528289) following the successful Monday reverse-split export completed successfully. Its [build job](https://github.com/magis-capital-partners/single-stock-investments/actions/runs/38281528289/job/114919767881) checked out `775173fa0c37d027e1d0230422e7b5d274f9510c` and completed the actual `Deploy dashboard to Cloudflare Pages and D1` step. This was a publication, not merely a successful gate that skipped deployment.

The resulting deployment URL was `https://6a9cd89a.single-stock-investments-2wt.pages.dev`. The source commit's `dashboard/data/core.json`, built at `2026-10-12T13:25:54Z`, contains the `desk_briefs` and `reverse_splits` shard references. The same source contains schema 1.2 Short Alpha with 199 candidates and the six Special Situations lanes.

An unauthenticated request to the hosted `data/core.json` returned HTTP 302 to Cloudflare Access. No Access login was available in this verification session. Authenticated hosted JSON and browser rendering are therefore not claimed; the workflow result, actual checkout SHA and publication log provide the fallback evidence requested in the verification brief. Local render evidence is recorded separately in PR #1152.

No new deploy was dispatched, no Access protection was bypassed, and no secrets or live portfolio data were copied into this record. The nightly intake failure remains recorded in PR #1151 even though a later core build and Pages publication succeeded. Future source changes and unmerged fixes require another deployment after human merge.

Before this documentation pull request, the requested local suites and validators were run. The known timer-test failure and graph findings remain disclosed; source, desk-brief, reverse-split, separation and Short Alpha checks pass, and P3/P6 stay OK. Generated graph baselines are not committed.
