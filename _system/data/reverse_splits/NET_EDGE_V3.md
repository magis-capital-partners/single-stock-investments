# RSI-3.0 inputs and reproduction

Research only. The published dashboard uses a frozen 2026-10-13 source run. It does not connect to a broker or ThetaData. Account sizes, fees and fallback APRs are sensitivity assumptions; edit `net_edge_profiles.json` before rerunning for an intended account. Every profile retains explicit risk budgets.

From the repository root:

```powershell
$env:PYTHONPATH = "_system/scripts"
python -m reverse_splits.net_edge_study --source-root PATH_TO_REVERSE_SPLITS_DATA --publish
python _system/scripts/build_reverse_splits_dashboard.py
```

The source root must contain the existing frozen `local/expansion/expansion_v2/runs/20261013T224003582762Z/` manifest, event shards and nominal `prices.sqlite`; cached SEC companyfacts; the RSI-2.0 snapshots; and both the primary and repair folders of `local/portfolio_research/20261013T224003582762Z__portfolio_v1/`. The study checks event shard hashes, reads SQLite immutable/read-only, and hashes the original books/points/status inputs and borrow vintages. `--prepare-only` extracts source-rated snapshots without portfolio runs. `--fetch-missing --fetch-limit 20` tries a bounded batch of missing companyfacts in the original sample, rejects identity mismatches and stops on denial/rate limiting. It never opens a market-data terminal. Fetch results are retained in ignored `local/net_edge_v3/sec_downloads.json`.

The full local event catalogue and blinded review queue retain missing/unverified names. Published source copies are `net_edge_research_v3.json`, `net_edge_manifest_v3.json` and `net_edge_audits_v3/*.json`. The dashboard builder copies the derived summary and audits and embeds a small hashed summary reference; it does not rerun historical prices in CI. Audit hashes detect stale deployment mixtures. Raw market observations and private broker evidence are not published.

Settlement dates exclude the bank-only Columbus/Veterans holidays, following [FINRA's settlement schedule](https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-extension-holiday-schedule). Friday stays open when Veterans Day falls on Saturday ([DTCC 19155-23](https://www.dtcc.com/Globals/PDFs/2023/October/11/19155-23)). Settlement remained open on the Bush/Carter mourning dates ([OCC 44143](https://infomemo.theocc.com/infomemos?number=44143), [DTCC 0275](https://www.dtcc.com/-/media/Files/pdf/2024/12/30/0275.pdf)); the trading and settlement calendars therefore differ in both directions. Cost plans do not assume an emergency exchange closure before its announcement became available. Broker-specific settlement failures or other exceptional terms require actual charge records; the default is a regular-way settlement scenario.

## Import contracts

Use JSONL for nested reviews/financing; flat evidence also supports CSV. A whole batch validates before append, and exact duplicates are idempotent. Records require issuer/event identity, original source availability (`known_at`), `source_url` and a precise `locator`. Source date-only fields become usable on the following Eastern calendar day. Creation/ingestion time is separate and must not be backdated.

```powershell
python -m reverse_splits.net_edge_evidence import --kind facts --input financial_overrides.jsonl
python -m reverse_splits.net_edge_evidence import --kind reviews --input blinded_reviews.jsonl
python -m reverse_splits.net_edge_evidence import --kind capitalization --input financing.jsonl
python -m reverse_splits.net_edge_evidence import --kind borrow --input borrow_history.jsonl
python -m reverse_splits.net_edge_evidence import --kind executions --input execution_evidence.jsonl
python -m reverse_splits.net_edge_evidence import --kind cashflows --input cash_adjustments.jsonl
```

Inputs append under ignored `local/edge_inputs/`; rerun the study after import. An import validates structure and availability, not the truth of a citation or the completeness of a research review.

| Kind | Additional required fields / meaning |
|---|---|
| `facts` | `issuer` (`cik/123`), `metric` from `ALIASES` in `net_edge_evidence.py`, numeric `value`, `unit`, period `end`, fiscal `start` for flows; optional accession. A source-cited override fills an observed amount, never a guessed zero. |
| `reviews` | `event_id`, aware `review_created_at`, `review_mode` (`prospective` or `blinded_historical_reconstruction`), `outcome_blinded=true` for reconstructions, `selected_mechanisms`, `frameworks`. Each framework row needs framework key, status (`supported`, `contradicted`, `unresolved`, `not_applicable`), source availability, citation, mechanism, contrary evidence and falsifier. Use the exact 27 keys in `net_edge.FRAMEWORKS`. Optional reasoned `conviction_rating` is 0–100, separate from numerical deterioration. |
| Review identity/profile | `identity_reconciled=true`, a dated cited `identity` object, `operating_profile="operating"`, dated cited `profile`. Dated cited `valuation` and `catalyst` objects remain independent required propositions. `vetoes` require cited dates and one of `HARD_VETOES`. |
| `capitalization` | `event_id`, positive `shares_before` and `common_equity_value_before`, `basis="same_split_basis_claims_and_proceeds_reconciled"`, `scenarios` whose probabilities sum to one. Each has `probability`, nonnegative `incremental_shares`, and `net_proceeds_to_common`; reconcile mutually exclusive claims and proceeds in the source locator. A no-issuance case is explicit, not inferred from a split. |
| `borrow` | `issuer`, aware `known_at`, `kind` (`indication`, `approval`, `accrual`, `recall`). Rates use annual fractions: 0.50 = 50%. Non-recalls require `annual_rate`, nonnegative `shares`. Approval additionally requires `approved=true`, positive shares and broker `reference`. Accrual requires `value_date`; optional `fee_per_share` overrides modeled daily collateral charges. Public FTP rows remain indications. A recall invalidates older indications and produces a next-open conditional cover. |
| `executions` quotes/trades | `issuer`, aware `known_at`, UTC epoch `timestamp`. Quotes require `kind="quote"`, `bid`, `ask`, `nbbo_verified=true` and trading status. Trades require `kind="trade"`, `price`, `size`, `aggressor`, `regular_trade`. SSR replay is an explicit queue/timeout scenario; quote files alone do not establish fills. |
| `executions` fills | `kind="fill"`, `event_id`, `issuer`, `phase` (`entry`, `cover`), `policy_hash` from `StudyPolicy.fingerprint()`, positive nominal `shares` and nominal `price`, `observed=true`, `compliance_verified=true`, `order_reference`, UTC epoch `timestamp`, original aware `known_at`. Reports bind to an actual policy and day; a future cover report never gates entry. |
| `cashflows` | `event_id`, `kind` (`dividend`, `fractional_settlement_adjustment`), payment `value_date`, signed `cost_per_entry_share`, `basis="incremental_to_continuous_split_adjusted_liability"`. Supply `entitlement_date` when a dividend is paid after cover; it determines whether the held position incurred the liability. A positive amount is a cost; a credit is negative. Reconcile incremental adjustments to the continuous split-adjusted benchmark to avoid double counting. |

The complete-evidence case remains excluded until its required review, financing, announcement indication, fresh entry approval and observed entry evidence exist. A cover without observed evidence leaves performance unresolved. Numerical-screen scenarios explicitly assume borrowing and execution access and use conditional daily-bar returns.

## Prospective archive

The weekday public disclosure/borrow workflow collects recent discovery records, public availability and actual archive times. It freezes explicit abstentions when there is no verified announcement snapshot/model output. Source or approval failure stops the job; an incomplete archive is not called a complete universe. A filing first archived after its scheduled entry is historical backfill, not a prospective prediction. Cancelled and unpriced discoveries remain observations.

```powershell
python -m reverse_splits.net_edge_evidence capture
python -m reverse_splits.net_edge_evidence freeze --input frozen_forecasts.jsonl
python -m reverse_splits.net_edge_evidence outcomes --input observed_outcomes.jsonl
```

A frozen forecast needs `event_id`, `known_at`, `entry_at`, the full `policy`, `input_hashes`, and `forecast` with status `estimated` or `abstain`. An estimate additionally includes the frozen announcement `snapshot`, `code_sha256`, and gross forecast fields. Run `freeze` before entry, after the source was available; records are hash-chained and cannot be replaced under the same event/policy. This command archives supplied model output; it does not generate an estimate from a discovery phrase hit.

An outcome references `forecast_sha256`, has aware `exit_at`, finite `gross_return` and `net_return`, and dated source evidence. It appends separately and cannot rewrite the forecast. `prospective_status()` reports frozen estimates, abstentions, evaluated forecasts and gross calibration. All older calibration remains diagnostic. The archived abstention denominator must be retained when assessing prospective selection.

## Checks

```powershell
python -m pytest -q _system/scripts/tests/reverse_splits
python -m ruff check --select F821 _system/scripts/reverse_splits/net_edge_v3.py _system/scripts/reverse_splits/net_edge_evidence.py _system/scripts/reverse_splits/net_edge_study.py
node --check dashboard/shorts-edge-v3-viz.js
```

Tests cover source-time leakage, fiscal/YTD reconciliation, missing financial values, financing proceeds, framework contradictions/N/A, locate versus indication, settlement/weekend carry, nominal rounding and quantities, whole-share joint cost sizing, SSR queue/price tests, unresolved admitted liabilities, observed fills, funding failure and immutable prospective archives.

## Free public evidence backfill

The free collector uses cached SEC financials and issuer-bound filings, and optionally downloads only public SEC resources. It has no credentials, paid feed endpoints, model API calls, subscriptions or free trials. A shared rate limiter caps traffic at two requests per second across four workers; a request budget bounds each run. Access denial/rate limiting stops new requests to that host. Cached responses bind URL and SHA256; reruns reuse them.

```powershell
python -m _system.scripts.reverse_splits.free_evidence --source-root PATH_TO_REVERSE_SPLITS_DATA --fetch --max-requests 3000 --publish
python -m _system.scripts.reverse_splits.free_borrow_history --fetch --max-requests 350 --publish
python _system/scripts/build_reverse_splits_dashboard.py
```

Omit `--fetch` for an entirely local run. The source root is the same frozen run and cache described above. Collection processes the complete original 691-event cohort. A 30-event pilot is selected by the smallest SHA256 event identities, independently of ratings and outcomes. All 27 framework routes receive an explicit assessment; cash-runway and reported margin deterioration can be supported by financial facts, while other unresolved judgments remain unresolved. Keyword passages route research and never establish fraud, completed issuance, fully diluted capitalization or full conviction. Current issuer metadata is not used as an historical operating-profile determination.

`free_evidence.json` and `free_packets/` publish the derived evidence. Raw responses and the network audit stay in ignored `local/free_evidence/`. Original source availability, later reconstruction time and content hashes are separate. SEC acceptance clocks take precedence; an unclocked filing waits until the following Eastern date. Future filings and future amendments cannot enter a packet. The input to assessment contains no subsequent prices, returns, realized charges or donor forecasts. The backfill does not change the frozen strategy's returns or promote incomplete research into strict eligibility.

Exact SEC metadata can recover a same-day financial disclosure that the date-only screen excluded. It must have been accepted at least one minute before the announcement cutoff; later amendments and unclocked records remain excluded. Each refinement retains the original accession, financial fact, exact availability bound, metadata URL and metadata hash. Packet creation time records the actual reconstruction, separately from the historical source clock.

The dashboard links financial facts, financing passages, all framework routes and filing citations for each original-cohort event. It also solves for the annual borrowing fee that consumes the frozen announcement plan's expected edge at its proposed size, and the analogous threshold using the model's lower-bound edge. Fee sensitivities hold the size fixed and retain expected billed calendar days, settlement, commission and slippage assumptions. These are cost ceilings, not quotes, approvals, or overrides of margin/thesis/stress constraints. Zero modeled billing days is reported explicitly. The ceiling is suppressed when a fixed pre-borrow charge has not been separated.

The public borrow archive continues to capture actual current observations. Its first saved vintages are in October 2026. [IBorrowDesk's FAQ](https://www.iborrowdesk.com/faq) limits free history to one year and places older history/CSV exports behind paid access. Its freely accessible chart was verified in the browser with the 1Y range selected and the paid ranges disabled. The collector uses only the chart's unauthenticated public ticker response, excludes records older than the free window, and never requests login, paid history or CSV exports. Raw responses remain local. Completed daily records wait until the following Eastern date; only a prior record within 24 hours of the announcement becomes a displayed rate proxy. An incomplete current day is excluded.

These proxies remain outside strict evidence: symbol links and the provider's current CUSIP do not reconcile historical security identity, indicated inventory is not an account approval, and quoted rates are not actual charges. The dashboard shows the constant-rate cost sensitivity at the frozen announcement size without resizing positions or rewriting portfolio returns. Free source gaps remain explicit. Future fee observations never enter an earlier prediction, and account approvals or historical fills are never inferred from advertised shares.

## Calmar parameter research

`calmar_research` performs an offline search using the frozen snapshots, price database and hash-checked cost inputs. No provider requests or broker connections are made. Its plan is saved before the first new trial. The fixed $50,000 account uses the original commission, risk limits, 50% fallback annual borrow, 90% uncertainty setting and prior-issuer rules. The 640 trials vary two entry timings; 1/5/10/20-session holds; time exits or 5/10/20% profit targets paired with 10/20/30% stops; 40/60/80/90 financial-rating floors; and fundamental-only versus net-edge selection. Account size and borrowing rates are not optimized as sources of alpha.

```powershell
python -m _system.scripts.reverse_splits.calmar_research --source-root PATH_TO_REVERSE_SPLITS_DATA
python -m _system.scripts.reverse_splits.calmar_validation --source-root PATH_TO_REVERSE_SPLITS_DATA --publish
python -m _system.scripts.reverse_splits.calmar_extension --source-root PATH_TO_REVERSE_SPLITS_DATA --workers 2 --publish
python _system/scripts/build_reverse_splits_dashboard.py
```

Calmar uses calendar-time CAGR divided by the absolute maximum daily drawdown over the complete May 2018–October 2026 interval, including idle capital. Incurred settlement charges after the final trading date are reserved in the terminal account value. Cash/no-trade and zero-drawdown paths receive no ratio, rather than an infinite score. Unresolved liabilities and funding breaches prevent ranking. A sample-qualified row needs at least 30 closed trades, 20 issuers and three active entry years; this is an evidence minimum, not statistical confidence. Raw sparse winners remain visible separately. All 32 applicable original $50,000 comparison cases must reproduce before the search completes.

Validation examines the top ten sample-qualified results, the two raw leaders, a sample-qualified net-edge leader when available, and the frozen default. It tests doubled/sixfold borrow, doubled slippage, minimum-one-day borrowing charges, other account sizes, and three separate periods starting flat. Earlier periods stop new entries before their final maximum holding window, independently of later realized outcomes. Adjacent parameter settings, calendar-year results and the trailing three years remain available in the complete result artifact. Only a candidate passing the declared sample, recent-return, neighborhood, cost and separate-period checks is labelled a paper research candidate. The production policy is never changed automatically.

After inspection of the first grid, a separately timestamped extension tests 1% and 2% per-name squeeze-loss budgets alongside the original 0.5%, keeping the aggregate sleeve budget at 2%, commissions, confidence and fallback borrow fixed. The 1,920 parameter sets are replayed over both the full history and a fresh-cash trailing-three-year window: 3,840 account replays. The extension's adaptive context is explicit. It ranks the periods separately and checks leaders from each. These larger per-name budgets change concentration and fee efficiency without increasing the total allowed modeled squeeze loss. The dashboard loads the full research only when its Calmar button is opened.

All history was already explored. These diagnostics are not an untouched holdout or prospective success, and optimization adds multiple-testing risk. Historical borrow approval, complete underwriting and execution evidence remain separate requirements. Calmar's definition follows [PerformanceAnalytics](https://search.r-project.org/CRAN/refmans/PerformanceAnalytics/html/CalmarRatio.html); research validation and overfitting concerns are discussed in [CFA Institute's Investment Model Validation](https://rpc.cfainstitute.org/-/media/documents/article/rf-brief/investment-model-validation.pdf).
