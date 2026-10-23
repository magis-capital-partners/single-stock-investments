# Short alpha strategy lab

This implements the 21 October literature-audit plan as a versioned dataset,
conditional replay engine, evidence importer and SSI dashboard. It is research;
it does not change adopted live rules, place orders or approve capital.

## Dataset and source clocks

- Import all 1,183 reverse-split and 4,720 deficiency rows from the supplied
  MicrocapLedger exports. Keep provider return statistics separate from features.
- Extract financing contexts from cached SEC reports and retain exact normalized
  text locators, original filing URLs and content hashes. This cache was selected
  around reverse-split research; it is not the full financing universe.
- Registration/ATM capacity is distinct from terms-disclosed, priced, closed,
  exercisable or terminated capital. An extraction is not a verified deal.
- Explicit previously-disclosed historical context is excluded from new financing
  entries; amendments are separate candidate states. Issuer/contract-date links
  suppress repeated same-state filings. These links are inferred, not verified
  deal identities. A source reviewer must reconcile multiple securities and deals.
- Use acceptance timestamps only with issuer/accession-bound SEC header evidence;
  otherwise use the day after the filing date in Eastern time. Split-provider
  baselines also wait until after the completed action, preventing a pre-split
  entry from conditioning on eventual completion.
- Financial features use the existing as-filed availability-filtered companyfacts
  implementation. Missing/stale facts and unknown cash runway remain unknown.
- A 100-record review panel is stratified by event type and event hash, independent
  of subsequent returns. Review and second-review statuses are evidence gaps,
  never automatically approved by keyword matching.

## Frozen comparisons

`local/profit_program/20261022_v1/protocol.json` is declared before replay. H23-H26
are a new exploratory research family; previous studies remain unchanged.

Eight opportunity groups x four holds (2/5/10/20) x two target ceilings ($25k/$50k)
x three joint cost cases x two sizing rules = 384 primary comparisons. A further
36 fixed five-session exit comparisons retain the 20% stop/target and progressive
cover alternatives. All 420 settings, including empty cases, are published.

Reconciled-saleable-supply groups require imported primary-document terms and
cash/share reconciliation. They remain empty until that evidence exists.
Gross forecasts use only matured other-issuer outcomes with a 20-session embargo
and at least 30 earlier issuers. Net sizing compares $2.5k-$50k candidates and
reserves half the forecast against estimation error; it never uses that event's
realized return or future cover depth to choose the size.

Daily execution uses conditional OHLC4 references and 5% recorded-volume caps.
Prior liquidity constrains the decision; realized volume constrains modeled fills.
Uncovered shares and fractional corporate-action obligations remain open and
marked. Stale prices are flagged. Prices and volume do not prove queue fills,
borrow availability, or access to every venue.

Nominal price paths reconcile the old, incomplete SQLite action table with the
supplied split catalogue and already-verified structured/primary action records.
Catalogue ratios are new/old, while provider ratios are old/new. Actual actions
change share units; a missing post-action quote retains the mechanically adjusted
stale mark. No action is guessed from a price jump. Action and parser repairs
were made during exploratory development; this is not an untouched validation.
Explicit vendor action records are retained for mechanical share accounting.
Additional repairs require an exact dated primary clause, a separately catalogued
matching ratio/date, and compatible nominal price continuity. Both 1-for-50 and
50-for-1 wordings are parsed. Their source clauses and hashes are published as
automatically corroborated records requiring review, not primary manual approvals.
Issuer IDs bind dated exhibits to historical action symbols, avoiding current-name
alias errors. After more than seven calendar days without a usable price, an open
short stops accepting later ticker prints or actions automatically. Its last mark
and loan obligation persist pending security-continuity/broker evidence. This
prevents a reorganized company's new shares from being treated as the old shares
one-for-one. The seven-day guard is a data-quality sensitivity, not an economic
liquidation rule; missing OTC prices and loan termination remain unresolved.

The base static-book cost anchor is 5.95% round trip at $25k: 1.72% spread proxy
plus 4.23% incremental size/depth. Square-root interpolation and transfer to other
dates/names are uncalibrated assumptions. Bear/base/bull combine execution and
150/50/20% borrow APR sensitivities; these rates are not measured typical loans.
The engine charges calendar-day ACT/360 on settled, dollar-rounded collateral;
current-rate IBKR Pro proceeds interest is credited incrementally above other USD
shorts' $100k threshold. Historical interest rates are not reconstructed.

SEC transaction fees use the charge-date schedule, including settlement lag;
TAF includes the Q4 2026 pause. A small other-venue/CAT allowance is explicitly a
fixed sensitivity. Actual charge files are needed for precise account costs.

One position per issuer, +200% stress reserve and shared margin constraints apply
to the hypothetical $10m portfolio. Existing Michael positions are unknown, so the
margin estimates are incremental sensitivities, not actual account availability.

## Reproduce offline

```powershell
python _system/scripts/short_profit_program.py ingest --source-root <cached-repo> --max-filings 100000
python _system/scripts/short_profit_program.py build --source-root <cached-repo>
python _system/scripts/build_reverse_splits_dashboard.py
```

Raw market data, full filings, companyfacts caches, execution files and individual
trade paths stay in ignored `local/`. Public source facts and aggregate comparisons
publish into `profit_program/`, copied to `dashboard/data/short_profit_program/`.
Per-file hashes and a dataset version detect deployment mixtures. A clean CI build
copies the committed snapshot; it does not silently redownload prices.

## Import evidence and freeze future forecasts

```powershell
python _system/scripts/short_profit_program.py import --source-root <cached-repo> --input records.jsonl
python _system/scripts/short_profit_program.py evidence --source-root <cached-repo>
python _system/scripts/short_profit_program.py collect --source-root <cached-repo> --since 2026-10-14 --max-requests 200
```

Imports validate the whole batch, append to a hash chain and deduplicate identical
records. Kinds: `terms`, `review`, `quote`, `fill`, `borrow`, `recall`, `cashflow`,
`forecast`, `outcome`. Every row requires event ID, aware known-at time, source URL
and locator. See `profit_evidence.validate` for exact fields. An import validates
structure and timing, not truth. No observed fill or approval is invented.

Forecasts must be frozen before future entry and cannot be replaced for the same
event/policy. Later outcomes reference the frozen hash. Abstentions remain in the
denominator. Execution calibration pairs observed compliant broker fills with
verified NBBO no more than five seconds before order arrival.

Each forecast includes `input_snapshot` (the dated event record),
`policy_snapshot` (the full frozen policy), and their canonical-JSON SHA-256
fingerprints. Hashes are verified before import. An outcome must match the
forecast's event and occur after its entry clock; one immutable outcome per
forecast prevents double counting. Identical reimports are idempotent. These
records calibrate evidence; they do not silently replace historical replay costs.

The optional collector uses only allowlisted public SEC HTTPS resources, the
existing research user agent, cached responses and bounded traffic. It stops on
access denial/rate limiting. It searches selected recent issuer submissions,
not a complete market or every older submission shard. New paid downloads remain
$0; no ThetaData or IB Gateway access occurs.

## Evidence gates

Software implementation is distinct from completing source reviews, calibrated
useful-size fills, sufficient independent forward outcomes and production approval.
The dashboard exposes each gate and its actual count. Ten or twenty execution
observations can diagnose the fill model but cannot establish annual return or
rare squeeze risk. The designated sealed holdout remains unread.

Monte Carlo resamples 63-session calendar blocks of the complete marked portfolio,
preserving within-block overlap/cost dependence. It cannot validate assumed fills
or represent unobserved tails. Residual-liability and squeeze stresses remain
separate, without attaching invented probabilities.

The committed 22 October snapshot uses daily prices through 13 October 2026.
Newer SEC discoveries remain visible but cannot enter a priced replay without
coverage. The build date is not the market-data date. Case labels describe joint
assumptions, not confidence bounds: changed fills can reverse return ordering.
