# Clean-data recovery under the original 46-trade rules

This study reproduces `post_split_next_open_10_p20_s20_f60_fundamental_risk200`
before changing any input. That is 46 closed trades from October 2023 through
October 13, 2026, and 83 across the full history. It holds the entry, exits,
score threshold, $100 minimum, 0.1% share-volume limit, costs and account fixed.
The original minimum billed borrow days also stays at zero for this comparison;
that legacy cost assumption does not establish actual broker charges.

The dashboard entry is **Short Alpha → Backtest → Open clean-data recovery ·
original rules**. This is separate from RSI-4's estimates and its changed
conviction/cost assumptions. New source data can add or remove trades. Both
admitted and closed positions are shown; unresolved admitted exits suppress
performance rather than being discarded.

## Data acquisition and acceptance

1. The official SEC cumulative CIK/name index supplies candidates. A current
   ticker or a unique name-index match alone cannot confirm a historical link.
2. A dated SEC submission must have an issuer-bound header and either an
   explicit matching DEI security/ticker cover, or an exact legal-name match
   to a dated FINRA common-stock action ID. Ambiguous CIKs, warrants, preferred
   securities, unsupported classes and future filing clocks remain unresolved.
3. Full SEC submissions include exhibits omitted from older primary snippets.
   The existing bounded action classifier must identify the same effective
   date and an exact reverse ratio. Proposals, conflicting schedules and
   unrelated historical mentions do not establish a scheduled action.
4. Financial retrieval reuses hash-bound Company Facts and extracts exact
   standard-taxonomy XBRL contexts from dated full submissions. Only whole-entity
   contexts, supported monetary/share units and explicit periods are accepted.
   Custom-tag guesses, segment totals and inconsistent repeated values stay out.
   Values are scaled using the XBRL scale/sign/format fields, never table appearance.
5. The original scoring algorithm still requires three usable signals and the
   same fresh-period and matched fiscal TTM rules. New contexts supplement gaps;
   they do not replace an already available canonical raw fact with a weaker alias.
   Every financial fact retains its period, filing/public clock, accession and source.
   A submission accepted before its official SEC filing day is held until the
   following Eastern calendar day; the earlier acceptance timestamp is retained
   separately. Cached financing passages inherit that rechecked public clock.
6. Supplemental prices require three overlapping original nominal closes in
   each split segment, median discrepancy at most 2%, and 90th percentile at
   most 5%. Unmatched or conflicting segments stay out of the main replay.
   Original prices retain priority. No missing price, exit or delisting return
   is invented. A public daily open does not establish an auction execution.
7. Public historical volume units remain unverified. The main replay retains
   original volumes and does not use public-volume estimates to enlarge sizing.
   A separate labeled sensitivity substitutes the public proxy for explicitly
   partial venue counts. It is not included in clean-data recovery.

Source requests use free unauthenticated SEC HTTPS GETs, configured identification,
at most two requests per second, durable caches and an explicit per-run limit.
The cumulative index has its own 128 MiB bound; individual responses retain the
30 MiB bound. An SEC denial/rate limit stops requests, rather than changing
identity or trying another host to bypass it. Failed lookups and pending work
remain recorded. No ThetaData, brokerage API, paid endpoint, order or purchase
is used.

## Fixed-policy replay and remaining-work queue

The waterfall shows the original data, scope/duplicate cleanup, validated prices,
reported financial repairs, and confirmed action/identity repairs. The last row
is a separate volume-proxy sensitivity. Every row has the same policy/account
signature. Exact additions and removals identify the preceding exclusion.
Changes in donor eligibility, overlapping positions and portfolio capacity can
also affect other names; a source-record recovery is not automatically an extra
independent trade.

The queue retains all 7,069 catalogue records, including policy exclusions and
duplicates. It puts existing scores at least 60 with one data gate first, then
identified issuers with prices, recent events and repeated issuers. Later returns,
profit and loss, and optimized parameters never set acquisition priority.

The source packets include financing passages and financial facts for subsequent
underwriting. A passage is not a reconciled warrant, convertible, ATM or issuance
conclusion. Completed underwriting needs sourced mechanisms, contrary evidence,
falsifiers, valuation and catalysts. Financing scenarios need exclusive claims,
consistent split units and net common proceeds. The evidence interfaces in
`net_edge_evidence.py` validate reviewed `facts`, `reviews`, `capitalization`,
`borrow` and `executions` records; no source lead is promoted into an approval.

No historical broker exports were present in the local archive when this work
started. Actual locates, loan rates/recalls/fees and fills require dated archived
records. Public borrow indications and daily bars cannot manufacture them.
Private brokerage identifiers and files must stay local/ignored; only aggregate
counts are published. The existing strict gate retains all these requirements.

## Reproduce

From the repository root, with `SOURCE` pointing to the original frozen data:

This replay also needs the existing ignored RSI-3 frozen snapshots at
`local/net_edge_v3/frozen_snapshots.json`, matching `net_edge_manifest_v3.json`,
and RSI-4's `local/coverage_v4/inputs.json` plus its hash-bound `price_cache`.
Keep these local inputs when moving checkouts. They are prerequisites, not
downloaded by the replay. [COVERAGE_V4.md](COVERAGE_V4.md) describes acquiring
the earlier public inputs; no new parameter search is required here.

```powershell
python -m _system.scripts.reverse_splits.clean_data_sources --source-root SOURCE --fetch --maximum 5000
python -m _system.scripts.reverse_splits.clean_data_research --source-root SOURCE --publish
python _system/scripts/build_reverse_splits_dashboard.py
python -m pytest -q _system/scripts/tests/reverse_splits
```

Omit `--fetch` to use only cached responses. The collector resumes existing
downloads. Original frozen inputs are opened read-only. Raw source caches,
complete filings, extracted facts and full local simulation cases remain ignored.
Published summaries, source-cited queue parts and trade changes have checksums;
LF checkout rules preserve those hashes on Windows.

The SEC documents its [Company Facts and submissions APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
and [free EDGAR access and cumulative CIK index](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).

## Validated run — October 17, 2026

The fixed fundamentals-only comparison produces:

| Data stage | Recent closed trades | Full-history closed trades |
| --- | ---: | ---: |
| Original frozen data | 46 | 83 |
| Scope and duplicates | 46 | 83 |
| Validated prices | 42 | 71 |
| Reported financial repairs | 42 | 71 |
| Verified historical identities and actions | **49** | **89** |

The final clean rows cover 45 recent companies and 81 full-history companies;
all admitted positions have resolved modeled exits. The recent decision funnel
is 556 scored events, minus 112 missing entry prices, 282 below the financial
floor and 113 sizing exclusions, leaving 49 trades. The enlarged denominator
means the final missing-price count includes newly scorable events. Within the
original cohort, price validation alone resolves 18 full-history and four recent
entry-price exclusions. Recovered price days can displace older observations in
the lookback window while still lacking accepted volume. Their unknown volume
cannot increase capacity, so admissions can also fall during a price repair.

Across the catalogue, 1,140 records now have reported financial scores, versus
847 originally. There are 1,126 scored decisions in the full-history entry
window and 556 recently. Source work confirms 412 previously absent CIK links,
1,062 dated identity records in total and 385 primary scheduled-action records.
The extractor accepts 28,021 facts from 1,274 filings across 516 issuers.
Nominal-price validation retains 36,689 bars across 570 symbols. These are
coverage counts, not independent trades or completed underwriting.

The separate public-volume sensitivity gives 71 recent / 119 full-history closed
trades, with 72 / 120 admissions and one unresolved position in each replay.
Its performance is suppressed. These counts are not clean recovery and are not
included in the 49 / 89 result.

The bounded acquisition log records 6,991 free SEC requests: 6,803 downloads,
134 not-found responses and 54 unavailable responses. The final snapshot has
4,681 accepted filing documents and 2,907 uncached source requests still pending.
All 7,069 catalogue records remain in 48 source-cited queue parts. Full
underwriting, reconciled financing, actual locates and observed fills remain
zero, and the strict recent case remains zero. Historical broker exports are
unavailable. No source passage is treated as a completed assessment.

The next price-repair targets are 48 recent / 144 full-history records already
scoring at least 60 whose first recorded exclusion is a missing entry price.
The next sizing targets need verified volume units and full-market volume:
112 of 113 recent sizing exclusions have a recorded volume cap below $100
(165 of 175 over full history). These are data priorities, not promised trades;
other gates can remain after a single repair. The $100 / 0.1% policy stays fixed.

Validation: 1,024 broader repository tests passed with six skipped; the final
reverse-split suite passed 323 tests. Source and implementation hashes, queue
counts, decision funnels and every trade-count transition reconcile.
