# Letter classifications and all-company IRR readiness

The research workspace distinguishes model maturity, numerical sensitivities,
canonical forward-return eligibility, and human capital authority. A
`stock_specific` model is not sufficient to publish an IRR.

## Source-reviewed classifications

`_system/reference/letter_classification_corrections.json` contains 90 reviewed
fund/security/period decisions covering 95 published relationships in the
2026-10-24 audit snapshot. Each decision names its source documents, original
excerpt hashes, source URL, finding, rationale, and review date. Matching also
requires the source reference or exact document URL; ticker and period alone
cannot override another document. PDF and text versions of the same named
document share identity.

Wrong-issuer attributions are suppressed. Contextual mentions and other
instruments remain visible as context, without an equity ownership signal.
Sales of unspecified extent are labelled **sold (extent unspecified)**, rather
than asserted to be full exits. Long holdings incorrectly classified short
become holdings with no invented position change.

`letter_classification_review_queue.json` records 573 unresolved candidates.
These are **not 573 confirmed errors**. The source action is retained as
`reported_action`, while the public action is labelled as awaiting source
review. These records cannot generate bullish/bearish ownership signals.
HCA/Veristar 2021Q4, VRT/BWCP 2026Q1, and AMZN/Wedgewood 2026Q3 remain unchanged
after full-source review.

The same reconciler runs at letter ingestion, insight construction, and shard
publication. The matcher also binds verbs to clauses, distinguishes sales from
exits, rejects known word/issuer collisions at the individual mention, and
keeps action evidence beside the mention that established it.

The targeted refresh preserves existing feed/source dates and does not rebuild
from an older research-vault snapshot. Historical consensus retains only eight
source rows per company. When a correction invalidates a historical ranking,
that affected aggregate is withheld and its original is archived in
`classification_withheld_aggregates`. Reconstructing full-history counts from
eight retained rows would be misleading. The next full-source build computes
the aggregates from reconciled source positions.

## IRR checklist for every covered security

`dashboard/data/irr_readiness.json` covers exactly the company universe in
`dashboard/data/core.json`, including missing models. It contains company
requirements, source references, explicit next actions, work groups, and stable
open-work identifiers of the form `TICKER:irr:requirement`.

The ten checks are: company model, dated purchase price, per-share ownership,
source-locked economics, input freshness, dated bear/base/bull cash flows, cash
allocation and terminal bridge, company-specific underwriting, calculation and
evidence proof, and canonical return eligibility. A fresh quote cannot resolve
the remaining checks. Model and fact age thresholds match the existing
workbench's 365/548-day limits; quotes must be positive, sourced, dated within
seven days, and not future dated.

The initial work groups are 513 model builds, 130 generic screens to replace,
161 full cash-flow models to underwrite, and 61 specialist bridges. The 155
complete mathematical diagnostics are research sensitivities. None of the 865
companies currently passes all checks. Missing facts and judgments remain
missing; no source, growth forecast, payout policy, quote, or owner approval is
manufactured by this pipeline.

A `present_value_today` output must never be annualized as future proceeds.
Specialist models retain their issuer-specific asset, operating-business or
catalyst methods. They need explicit payout/exit timing, not a generic FCF
multiple substituted for their existing economics. For example, Copart's
owner-earnings model has reinvestment and terminal assumptions, but still needs
an explicit cash/net-asset timing policy and a dated shareholder schedule.

The legacy full-model sensitivity distributes all modeled FCF each year and
adds terminal equity proceeds. Publishing it requires explicit reconciliation
that modeled FCF is available **after** reinvestment, buybacks are not counted
again as distributions, and cash/debt are reflected in terminal equity value.
The schedule generator keeps these gaps in the canonical evidence gate.

Unsupported prospective IRRs and base-return claims are removed from current
thesis summaries. The original text remains in `return_claim_audit`, shown as
audit-only history. Historical returns and pure hurdle requirements remain.

## Rebuild and verify

```powershell
python _system/scripts/refresh_research_integrity.py
python _system/scripts/build_irr_readiness.py --as-of 2026-10-25
python _system/scripts/refresh_research_integrity.py --check
python _system/scripts/build_irr_readiness.py --as-of 2026-10-25 --check
python -m pytest -q _system/scripts/tests/test_research_integrity.py
```

Choose the actual observation date for a new snapshot. Normal dashboard builds
attach the checklist, and valuation-only refreshes rebuild the universe report.
Both commands are deterministic for unchanged inputs/date. Neither contacts
ThetaData, IB Gateway, market-data collectors, or external services.
