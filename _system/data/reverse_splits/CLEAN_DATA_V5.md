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
