# Third-plus reverse-split signal study

This is an offline research tool. It has no broker connection, order command, deployment step or scheduler.

- [Findings and interpretation](FINDINGS.md)
- [Complete report](REPORT.md) and [HTML report](REPORT.html)
- [Results](summary.json), [experiment register](experiment_register.json), and [source manifest](manifest.json)
- [Original plan](plan.json) and [frozen protocol](protocol_frozen.json)
- [Implementation correction history](implementation_revision.json)

Run from the repository root using Node 24 or newer:

    node _system/scripts/third_plus_signal_study.cjs verify
    node _system/scripts/third_plus_signal_study.cjs build
    node _system/scripts/third_plus_signal_study.cjs shadow-status

The fixture tests use synthetic financial statements, prices and temporary journals. They require no licensed market files or network. The full build requires the existing local price SQLite, action shards, financial files and disclosure cache. A missing input is an error, not a reason to fetch paid replacements.

The build reproduces both earlier full-size baselines, computes seven signals and four combinations against two comparators, and runs covered-universe controls, capacity/cost/account cases, source-clock diagnostics and walk-forward selection. Its primary account is a declared $1 million research reference, with 1% volume limits, a three-name limit and the existing per-name/sleeve squeeze reserves. A $25,000 target therefore usually becomes a much smaller position. The full-size benchmark remains separate.

Outputs are versioned by data/code/review fingerprint under runs/. The root files point to the latest successful build. No historical year is newly labeled an untouched holdout. The original protocol remains frozen; bug corrections and their exact source hashes are preserved in implementation_revision.json rather than rewriting that registration. The source manifest separately states whether code matches the original freeze and whether every difference is accounted for.

## Source review

The source audit produces a private financing_source_review_queue.local.json under _system/data/reverse_splits/local/third_plus_signal_study/. It contains source hashes and bounded clauses for review, not verified transactions.

Import a reviewed JSON array:

    node _system/scripts/third_plus_signal_study.cjs review-import --input reviewed-financing.json

Use financing_review.schema.json as the structural reference. Each review must include:

- SEC issuer ID, accession and unique economic deal ID.
- Source URL, exact cached source hash, clause locator and aware public-availability time.
- Actual closing date and state: completed, not_dilutive or terminated.
- Reconciled identity, share units, cash and saleability.
- Saleable share quantity for a completed equity-linked transaction.
- Cash currency and net cash change, including documented uses; null retains cash uncertainty.
- Two different independent reviewers and a truthful outcome-blinded attestation.

A review imports only after the entire batch passes validation and the cached issuer/source/hash/clock bindings are checked. It cannot silently overwrite a different frozen review for the same deal. Do not claim outcome blinding if the reviewer inspected the relevant trade outcomes.

Then rerun build. Missing independent reviews keep S2 and its dependent combinations unknown; source extraction does not promote them. S1 blocks known unresolved fundraising rather than treating stale cash as current cash. Its remaining estimates still depend on incomplete cached filing coverage.

## Forward shadow evidence

Registered policies are immutable JSON snapshots under forward_policies/. forward_policy.json is the current pointer plus hash. Existing journal records retain their own policy/input snapshots and hashes when a newer registration exists.

Manual evidence imports:

    node _system/scripts/third_plus_signal_study.cjs shadow-import --input observed-evidence.json
    node _system/scripts/third_plus_signal_study.cjs shadow-status

The input is a JSON array. Supported kinds are enrollment, locate, order_attempt, fill, cashflow, loan_return and closure. The private journal is forward_shadow.jsonl.

Enrollment requires a registered policy, a future entry timestamp, an aware input/source clock, documented ordinal at least three, matching issuer/event identities, a frozen input snapshot/hash and an observe or abstain decision. Outcome fields are prohibited in enrollment inputs. The enrolled policy snapshot is the exact registered file body, not the decorated current-pointer file.

Every other record must bind to an existing enrollment and its policy. Locates require broker-approved quantity/APR and a broker reference; fills require observed/compliance attestations, execution ID, phase, quantity and price. Failed order attempts and actual cash flows can be recorded. Closure requires observed entry evidence and position/loan reconciliation.

The journal validates an entire batch before appending, rejects conflicting executions/enrollments, uses an exclusive write lock and verifies its hash chain. A hash chain protects record integrity; it does not independently authenticate a broker document or prove its economic truth. Source authenticity and reviews remain necessary.

Zero historical finalists means the current policy abstains from trade selection. No prospective observations are fabricated to populate the journal. Fifty eligible decisions across thirty issuers is a minimum review checkpoint, not an automatic trading permission or statistical proof.

## Safety and data boundaries

- No Gateway, client-ID, broker probe, scheduled session or order changes.
- No sealed execution holdout is opened.
- New market-data download budget is $0.
- Raw source extracts, per-event returns and full ledgers remain in the ignored local directory.
- Public artifacts contain aggregated research results.
- SSR-compliant execution, borrowing, live identity and actual fills remain separate evidence gates; daily prices/volume do not satisfy them.

## Saved third-plus rally-veto screen

The user-selected reusable definition is [third_plus_no_50pct_rally.v1.json](saved_screens/third_plus_no_50pct_rally.v1.json). It requires ordinal at least three and excludes any candidate with a single adjusted daily close-to-close rise of at least 50% in the five completed sessions before entry. Missing history excludes a candidate. No other fundamental filter is required by this saved definition.

Refresh its selection and fundamental coverage audit from the latest local study feature snapshots:

    node _system/scripts/third_plus_saved_screen.cjs

This writes an aggregate [screen summary](saved_screens/third_plus_no_50pct_rally.summary.json), private candidate decisions and [fundamental coverage explanation](FUNDAMENTAL_COVERAGE.md) with [machine-readable counts](fundamental_coverage.json). Every export records hashes of its feature input, study summary, definition and exporter. Run it after a new study build to refresh the export. Candidate counts do not imply executed fills.

The saved screen records the user choice for reuse. The historical study still has no validated finalist, and its abstaining forward policy is unchanged. The separate saved-screen tests cover the ordinal constraint, exact 50% boundary, missing history, completed-observation clock and absence of undeclared fundamental conditions.

## All-210 source reconciliation

The separate [reconciliation v2 report](reconciliation_v2/REPORT.md) and [coverage summary](reconciliation_v2/summary.json) supersede the old extraction-coverage counts. All 210 events now have cash and total trailing operating cash flow; 209 have exact comparable share growth and one has a proven dilution bound. Freshness, entry availability and independent financing review remain separate gates. The original backtest results above remain frozen.

Build the new source-bound event and feature overlay from the local cache:

    node _system/scripts/third_plus_reconciliation.cjs

This command also verifies recovered source hashes, checks all 210 identities and historical evidence clocks, writes the searchable local AUDIT.html and archives reports by data/code fingerprint. It makes no network or broker requests. The private reconciled_features.local.json retains signals_v1 alongside the reconciled feature values. It is not automatically imported into the original replay or forward policy.

Run the offline regression checks:

    node --test _system/scripts/third_plus_signal_study.test.cjs _system/scripts/third_plus_saved_screen.test.cjs _system/scripts/third_plus_reconciliation.test.cjs
    python -m unittest discover -s _system/scripts -p test_third_plus_reconciliation.py

The Python filing parsers require lxml (CI pins 6.1.1). The financing source classifications are explicitly single-analyst, not independent or outcome-blinded attestations; no original review requirement was silently relaxed.

## Recalculated fundamental-filter comparisons

The [v3 filter recommendation](fundamental_filters_v3/RECOMMENDATION.md) and [full recalculated report](fundamental_filters_v3/REPORT.md) use the reconciled 210-event overlay. They compare 19 additions to the saved screen in 254 registered model definitions, with matched coverage, issuer/calendar uncertainty, cost/capacity stress and chronological selection. No addition passed all research-validation gates.

    node _system/scripts/third_plus_fundamental_study.cjs

The protocol and original code/input freeze are immutable; the documented covered-control bug correction is source-hash bound in implementation_revision.json. New inputs/code require an explicit amendment. Full features and portfolio ledgers remain local; the original study and operational policy are not overwritten.

## Dashboard walkthrough

Open **Ideas → Shorts → Reverse-split backtest** (`#/ideas/short-alpha/backtest`). The view explains the research path, shows all 21 rule sets under nine declared execution cases, and keeps monthly marked P&L, costs, exclusions, source coverage and unverified trading evidence visible. Earlier studies remain in a separate collapsed section.

Refresh the aggregate, hash-verified browser publication after a completed study build:

    node _system/scripts/build_third_plus_dashboard.cjs
    node _system/scripts/build_third_plus_dashboard.cjs --check

The publication reads committed aggregate results and the hash-bound explanatory decision audit. It does not rerun the research, download market data, expose per-event licensed price outcomes, or connect to a broker. Research code tests and live strategy validation are displayed separately.

### Candidate exclusions, sizing and full dashboard guide

The dashboard now includes every one of the original 210 events for each of the 21 rules and nine cases, including failed/unknown signal gates and first execution/account rejection. A name search, reason selector and CSV downloads expose historical ticker, issuer and event date so repeated splits remain distinct. Each admitted position includes its initial modeled dollar exposure, all applied dollar ceilings, binding cap, concurrent account positions, planned exit and terminal exit state. Ten expandable guide sections explain signals, clocks, sizing, execution, costs, accounting, statistics and missing evidence.

`fundamental_filters_v3/decision_audit.json` is a separate explanatory publication, not a new optimized study. Reproduce it offline with `node _system/scripts/build_third_plus_decision_audit.cjs --source-root <checkout-with-existing-local-study-cache>`, then rebuild the dashboard with `node _system/scripts/build_third_plus_dashboard.cjs`. The generator checks frozen engine and feature fingerprints, instruments a transient copy in memory, and requires exact equality of all stored position records and daily P&L paths for all 189 displayed models. The registered engine, research ledgers and outcome definitions are unchanged. Public content is limited to historical identities, categorical states and derived modeled sizing dollars; raw prices, volumes, quantities and per-event returns remain private.

The audit explicitly identifies a material implementability gap: entry capacity depends on final entry-day volume while the assumed entry is at the opening auction. A quantity known before entry or timestamped intraday execution replay is required before live interpretation. The reference account assumes zero other-sleeve stress loss and does not replay SPX exposure.
