# Overlapping portfolios — holder map for the research universe

**Date:** 2026-10-07
**Status:** built 2026-10-07. Coverage page (`#/holdings`) and each ticker detail. Universe scope has no book value. Dollar stress is on the owned book, Michael's sleeve, and Drew's sleeve. Schema stays `research_only`, `in_base_irr: false`, `authority: none`.
**Sources:**

- Fabio Caccioli, Munik Shrestha, Cristopher Moore, and J. Doyne Farmer, *Stability Analysis of Financial Contagion due to Overlapping Portfolios*, SFI working paper 2012-10-018.
- Fabio Caccioli, Thomas A. Catanach, and J. Doyne Farmer, *Heterogeneity, Correlations and Financial Contagion*, SFI working paper 2011-09-044.

**Surface:** every common stock in the research universe (`_system/data/valuation_universe_tiers.json`, 846 names as of 2026-10-06: 40 tier 1, 12 tier 2, 794 tier 3). The map is a research page, not a sleeve blotter. Dollar stress uses only books that have market value. Tiers allocate research effort. They are not positions and they are not capital authority (`valuation_universe_policy.json`).

## 0. Build prompt

Build a research-only holder map for all 846 universe names. Join holders we already store before fetching anything new. Then pull the gaps listed in section 6. Do not simulate bank defaults, do not move a price, and do not write valuation, Darwin, Peters, or orders.

Questions the page answers, for every universe name and for the holder set as a whole:

> Who else reports this name, among the holders we actually have on file?
> Is the reported ownership a hub (one holder has a large share) or a crowd?
> Which holders sit in the same universe names as each other?
> Where a real book has dollars, how much of that book sits in names shared with the hub holder, compared with a typical holder?
> Which of those holders have a stated leverage figure above a published cutoff?

Schema on every payload: `research_only: true`, `in_base_irr: false`, `authority: "none"`.

## 1. What the papers contribute

2012-10-018: banks that own the same assets can pass trouble to each other when they are leveraged. A sale moves the price, the next holder is marked down, and leverage can force another sale. The spread is a branching process. If each failure causes fewer than one further failure, trouble dies out. Past that threshold, the unstable region widens as leverage rises. Most of the time nothing happens. When it does, it is large.

2011-09-044: a heavy-tailed size distribution makes "we are diversified" a sloppy description, because a few large holders dominate. A random failure is milder than the failure of a hub.

What we keep is the map of those ingredients: shared holdings, size-weighted hubs, a leverage flag where a filing states one, and a hub-versus-random comparison.

What we do not keep: a solved stability boundary, a branching-process Monte Carlo, a fire-sale price, a label of stable or unstable, a complexity score, or a complexity IRR. We do not have a liquidation rule, and we do not see hedge-fund leverage. Saying the universe is stable would be the overclaim the papers warn against.

## 2. What stays untouched

| System | Rule |
|---|---|
| `valuation.json`, the contract, IC packets, `human_decision.json` | Not an input. `decision_authority.py` does not read this artifact. |
| Legacy Lawrence IRR | No new row, no stance change. |
| Darwin weights | No feed. |
| Magis / World Model | No forecast sentence. |
| Peters time-average panel | Separate. This map does not read or write it. Peters stays on Michael's sleeve. |
| Order desk and IB Gateway | No ticket, no socket. Holdings come from files we already have and from EDGAR over HTTPS. |

Copy banned on the panel: "target weight", "fair value", "buy", "sell", "IRR", "house", "default", "cascade probability", "stable", "unstable". Allowed: "hub", "overlap", "leverage not reported", "above the threshold".

## 3. The universe, and the books that have dollars

**Name set.** All securities in `valuation_universe_tiers.json` whose instrument is a common stock. Read the tier, the ticker, and the company name from that file. Drop non-stocks (warrants, CVRs, preferred stubs, escrows, debentures) with reason `not_stock`. A name can appear even when nobody holds it for us.

**Owned books, separate from the universe.** Registry holdings are research membership, not ownership (`universe_semantics.registry_holdings`). Dollar weights come only from:

- Michael's sleeve (`GET /api/v1/sleeves/book?owner=michael`)
- Drew's sleeve, same endpoint
- The portfolio book of actual stock positions (`GET /api/v2/portfolio/book`), which is the whole account after the allocation rules

The page has a scope control: Universe, Owned book, Michael, Drew. Universe is the default and has no NAV. Owned book, Michael, and Drew compute the dollar stress in section 5.4. Switching scope does not change who the outside holders are.

Foreign listings stay in the universe table. They join a holder only when a US CUSIP is already mapped. Otherwise the row says `not_on_13f`. Do not guess a US share class.

## 4. Data we already have

Use these before any new download. Each row is a fact about a file that exists in this repo or in a sibling the market-risk builder already reads.

| Source | Path | What it actually contains | How the map uses it |
|---|---|---|---|
| Research universe | `_system/data/valuation_universe_tiers.json` | 846 names, tiers, as of 2026-10-06 | The name set. Tier is a column, not a weight. |
| Specialist 13F books | `_system/reference/market-data/ownership/records/full/{fund}/2026Q2.json` and `latest.json` | Full reported books for 29 biotech and healthcare advisers (Baker Bros, RA Capital, OrbiMed, and the rest). Quarter 2026Q2. Fields include CIK, CUSIP, issuer, market value, ticker, fund id. Shares are often null. | Direct holder rows for any universe name those funds report. This is the right source for tier-3 biotech. It is the wrong source for Garrett Motion or J.P. Morgan. |
| Specialist overlays | `.../ownership/overlays/{TICKER}.json` | Per-ticker rollup already built for names those specialists hold | Read-through for the biotech footnote. Do not treat an empty overlay as "no holders." |
| Tracked-fund 13F cache | `.../ownership/tracked_funds/cache/*.xml` | The raw 13F information tables for six advisers, downloaded 2026-07-09: Ruane Cunniff, Dodge & Cox, Harris Associates, First Eagle, Tweedy Browne, Capital Research Global Investors. The XML is the full filing. | Reparse with `ownership_common.parse_13f_info_table_xml`. This is free. No EDGAR call. |
| Tracked-fund published records | `.../tracked_funds/records/2026Q2.json` | 100 rows. The file's own note says "Portfolio/watchlist overlay only." | Do not use this as the holder book. It dropped every holding that was not on the old research list, and it has matched at least one CUSIP onto the wrong ticker (`478160104` stored as `ABMD.CVR` while the issuer string is Johnson & Johnson). Reparse the XML and join by CUSIP. |
| CUSIP map | `.../ownership/cusip_ticker_map.json` | Mappings built by the biotech ingest. Incomplete for the 846. | First join key. Measure coverage in phase A and print the gap. Do not name-match issuers onto tickers. The J&J / ABMD.CVR row is why. |
| Parser and fetch | `_system/scripts/ownership_common.py` | `sec_fetch_bytes`, `latest_13f_filings`, `parse_13f_info_table_xml`, `match_holding_to_ticker`, User-Agent, sleep | Reuse. Do not write a second EDGAR client. |
| Float, shares, short interest | `_system/reference/market-data/fundamentals/index_float_adv.json` | Per ticker: `shares_outstanding`, `float_shares`, `short_percent_float`, ADV. As of 2026-08-11. Stale after 90 days, so on 2026-10-07 it is still inside the window. The file says omit when unknown. | Top holder's shares, once we have them, divided by `float_shares`. Short interest is a separate column, not a 13F holder. |
| Index membership | `dashboard/data/index_membership.json` | Current index memberships and boundary scorecards, as of 2026-10-01 | A tag ("in the S&P 500"), which explains why a broad ETF might hold the name. Membership is not a share count and is not an ETF holding. |
| Insider scores | `.../ownership/biotech_insider_scores.json` | Biotech insiders only | Footnote on a biotech name. Not part of the overlap graph. |
| Leveraged-ETF holdings | Sibling repo `etf-dashboard/data/etf_holdings_latest.json`, already read by `_system/scripts/build_market_risk_components.py` (`by_symbol`, `as_of_date`, `source`, `security_type`) | Issuer holdings for leveraged and inverse wrappers, including swaps and futures. The file is not in this repo. The market-risk builder treats it as optional. | If the file is present, map wrapper to underlying and carry the fund's stated multiple when the sibling publishes one. If the file is absent, the leveraged-ETF rows say "holdings file not on this machine." Do not invent the basket. |
| Insights extracts | `specialist_13f` and `tracked_fund_13f` rows inside the insights archive | A few dozen extracted mentions, not holdings | Ignore for this map. The filings above are the primary source. |

Phase A is a local rebuild. It does not call EDGAR. It reparses the six cached XMLs, loads the 29 specialist books, joins on the CUSIP map, attaches float and index tags, and writes a coverage report: how many of the 846 have at least one holder, how many CUSIPs are missing, how many specialist rows failed the ticker join, and which of the six XML caches parsed.

## 5. The objects

Computed in `dashboard/functions/_lib/overlap_map.js`. No prices. No I/O. Python only writes the holdings file.

### 5.1 Holders of a name

For each universe name, every on-file holder that reports it.

Per holder, store: fund id, display name, kind (`specialist_13f`, `tracked_13f`, `large_13f`, `etf`), quarter, filing date, accession or source URL, CUSIP, market value, shares if the filing has them, and the leverage field from section 5.3.

Per name, store:

- Holder count, size-weighted. An unweighted count is the sloppy statistic the 2011 paper warns about, so the headline is the top holder's share of reported market value, not the count.
- Top holder name and that share.
- Herfindahl of holder market-value weights. Lineage only.
- Top holder as a percent of float, when both `shares` and `float_shares` exist. Otherwise "shares not on the filing" or "float not on file."
- Short percent of float from the float file, labeled with its date, as context beside the holder bar.

### 5.2 Hubs

**Hub name.** The largest holder's share of reported market value in that name is at least 25%. The cutoff is printed on the page. It is our round number, not the paper's critical value. A name held in equal size by many advisers is not a hub, even if the count is high.

**Hub holder of a scope.** Only when the scope has dollars (Owned book, Michael, Drew). Rank holders by the absolute market value of our positions in names that holder also reports. The top holder is the hub holder for that scope. Ties break on the holder's reported market value, then CIK. A famous name is not a hub because it is famous.

On the Universe scope there is no hub holder, because the universe has no NAV. The page still ranks holders by how many universe names they report and by the sum of their reported dollars in those names. That ranking is "who is large inside our research list," and the caption says so.

### 5.3 Leverage flag

Flag only a figure a filing or a prospectus states. Silence is "not reported," which is not a pass and is not the word "unlevered."

| Kind | Figure | Above the threshold when |
|---|---|---|
| ETF on the stated-multiple list | Prospectus daily multiple, signed | Absolute multiple ≥ 2 |
| Fund with N-PORT borrowings and total assets | Borrowings / total assets | Ratio ≥ 0.10 |
| 13F adviser with neither | Not reported | Never flagged |

The cutoffs 2× and 10% are constants in the formula module, with a test. They are not the paper's critical lambda.

A name is "held above the threshold" when at least one flagged holder reports it. The cell shows the count and the largest absolute multiple. A name whose holders are all "not reported" shows that phrase.

### 5.4 Dollar stress, owned scopes only

One stress, two removals, no prices. Same definition as before, now parameterized by scope.

**Hub removal.** Delete the scope's hub holder. Report the share of that scope's NAV sitting in names the hub holder also reports, and the names that then have no remaining on-file holder.

**Random removal.** Delete one other holder who shares at least one name with the scope. Seed is the scope's as-of date plus the holdings quarter, so the row does not flicker. Report the same two numbers.

The page prints hub overlap, random overlap, and the difference in NAV points. The sentence under the numbers: "This is how much of this book sits in names that holder also reports. It is not a loss."

If only one holder overlaps the scope, the random column says "only one overlapping holder" and the difference is withheld.

### 5.5 Holder-versus-holder overlap

This is the paper's object, and it does not need our NAV. For every pair of holders who both report at least one universe name:

- Shared universe names.
- Overlap dollars: the sum, across shared names, of the smaller of the two reported market values.
- Each holder's reported dollars in the shared names, divided by that holder's total reported dollars in the universe. That is how alike the two books are inside the names we study. It is a lower bound on how alike the full books are whenever we do not have a full book (the overlay file was that mistake; full XML and full specialist books fix it for the holders we already fetched).

The page shows the top 25 pairs by overlap dollars, not a matrix. A pair of specialists who both own the same thin biotech book will rank here. That is a feature. The row names the kind of each holder so a BlackRock-Vanguard pair and a Baker-RA pair are not read as the same fact.

### 5.6 Diversification pair, owned scopes only

- Our concentration: the largest position as a share of that scope's NAV.
- Crowd concentration: the share of that scope's NAV sitting in names the hub holder also reports.

One sentence: "The largest position is X% of this book. Names also reported by {hub} are Y% of this book."

## 6. New data we still have to pull

Phase A will show the holes. These pulls fill them, in this order. Each pull reuses `ownership_common` and the existing SEC User-Agent and sleep. None of them touch the Gateway.

### 6.1 Fix the join we already paid for

Reparse the six cached XMLs to full holdings, including `sshPrnamt` (shares) if the parser currently drops it. Extend the CUSIP map from those rows plus the specialist books, by exact CUSIP only. Write the count of universe names still unmapped. This is not a new download. It is the first pull's prerequisite, because a bad join will poison every later file.

### 6.2 Large 13F advisers not in the cache

The six cached advisers are value shops plus Capital Research. They are not the crowding complexes. Add a checked-in list, `dashboard/data/overlap_holders.json`, of the next advisers, each with CIK, name, and the SEC URL used to confirm the CIK:

BlackRock, Vanguard, State Street, Fidelity, Geode, Wellington, T. Rowe Price, Invesco, Northern Trust, Norges Bank (if it files 13F), Capital World, and the other members of a top-20 by previous-quarter total 13F value. Rank them from the SEC 13F data-set summary for the latest complete quarter, once, and store the quarter on the list. Do not grow the list in code.

Fetch each adviser's latest 13F-HR information table the same way `ingest_tracked_funds_13f.py` already does. Keep the full table, not an overlay. Store it beside the existing cache so the next run can skip a filing we already have.

### 6.3 Quarterly 13F bulk, filtered to universe CUSIPs

The top-20 miss the holder who owns 40% of a tier-3 name and files 13F from outside that list. That holder is often the hub the 2011 paper is about.

Download the SEC Form 13F data set for the latest complete quarter (the quarterly zip SEC publishes for the information table). Filter to CUSIPs on the universe map. Store one row per (filer CIK, CUSIP): market value, shares, period. Drop the rest of the zip. Do not commit the unfiltered zip.

This bulk file is the holder universe for the 846. The specialist books, the six caches, and the top-20 fetches remain as richer records (accession URL, fund id, kind). Where both exist, prefer the bulk row for market value and shares, and keep the curated fund id as a label. A filer who appears only in the bulk set has kind `bulk_13f`.

Refresh in the week after each 13F deadline, about 45 days after quarter end. A filing older than two quarters stays on the page with the quarter printed.

### 6.4 CUSIPs the map still lacks

After 6.1 and 6.3, print every universe ticker with no CUSIP. Fill those from the bulk set's own issuer names only when the issuer string matches the universe company name under the same normalizer `ownership_common` already uses, and only when exactly one universe name matches. Two matches go to an exception list, unresolved, rather than a silent pick. Still no purchased CUSIP vendor.

### 6.5 ETF baskets and stated leverage

Broad ETFs are not in the six 13Fs as holdings of the ETF. The ETF is the holder.

- Read `etf-dashboard/data/etf_holdings_latest.json` when it exists. That file is the leveraged and inverse wrapper book the market-risk job already trusts. Map each underlying to a universe ticker. Carry `security_type` so a swap is not shown as a share holding.
- New pull: N-PORT-P for a fixed list in `overlap_holders.json`: SPY, IVV, VTI, ITOT, IWM, IJH, QQQ, and the sector SPDRs. Store series id, class id, CUSIP, shares, market value, and the fund's borrowings and total assets. Borrowings over total assets is the leverage field.
- New small table, hand-maintained in the same holder file: `{etf_ticker, stated_multiple, prospectus_url}` for products whose daily multiple is 2, 3, -1, -2, or -3. Copy the multiple from the prospectus URL. Do not infer it from returns. If the sibling repo already publishes that multiple, cite that field and do not retype it.

### 6.6 What we will not pull

WhaleWisdom, Fintel, and BiopharmaWatch are named in the specialist registry as places a human might look. We do not have their feeds, and v1 does not add them. Superinvestor letters and podcast extracts mention holdings in prose. They are not positions. Insider scores stay a footnote. Index membership stays a tag.

## 7. Where it appears

One research section, mounted from the coverage view, titled **Who else holds these names**. It is not on the order desk, not on LS Algo, and not inside the Peters block.

Default scope is Universe. The table lists every eligible universe name, with tier, holder count, top holder and that holder's share, hub-name flag, leverage cell, float percent when known, and index tags. Sort by top-holder share so hubs surface first. A tier filter and a search box sit above it. Tier 3 is included. Hiding it would throw away the names where a specialist hub is the whole point.

Owned book, Michael, and Drew add the dollar-stress strip and the diversification sentence above the same table, filtered to names in that scope. Names in the scope with no on-file holder still appear, as "no holder on file."

The top 25 holder pairs sit under the name table.

A ticker's research page shows that name's holder rows and the pairs that include those holders. It does not recompute the formula. It reads the same payload.

Lineage drawer: both papers, the phase A coverage counts, the bulk quarter, the holder-list version, the threshold constants, omitted reasons (`not_stock`, `no_cusip`, `not_on_13f`, `stale_filing`, `holdings file not on this machine`), and the sentence that 13F omits shorts and omits most leverage.

## 8. Code layout

| Piece | Path | Job |
|---|---|---|
| Formula | `dashboard/functions/_lib/overlap_map.js` | Per-name stats, hub flags, leverage flag, scope stress, holder pairs. No I/O. |
| Endpoint | `dashboard/functions/api/v1/research/overlap.js` | Reads the holdings file and, when the scope has dollars, the sleeve or portfolio book. |
| Holdings file | `dashboard/data/overlap_holdings.json` | One record per universe ticker, plus the pair list and the coverage report. |
| Holder list | `dashboard/data/overlap_holders.json` | Top-20 CIKs, ETF series ids, stated multiples, prospectus URLs. |
| Phase A rebuild | `_system/scripts/build_overlap_holdings.py --local-only` | Cache XML, specialist JSON, CUSIP map, float file, index file. No network. |
| Phase B fetch | same script, without `--local-only` | Sections 6.2, 6.3, and 6.5. Stale-on-failure: a failed filer keeps the previous block. |
| Fixture | `_system/scripts/tests/fixtures/overlap_map_mini.json` | Locks the arithmetic in section 9. |
| UI | coverage view, plus a ticker holder block | Does not reimplement the formula. |
| Fence | `_system/scripts/tests/test_overlap_map_fence.py` | Valuation builders, Darwin, `decision_authority.py`, and the Peters module do not reference these files. |

## 9. Fixture

Toy universe of five names. Toy owned book, NAV $100, holds AAA $50, BBB $30, CCC $20. DDD and EEE are universe names we do not own. They still appear on the Universe scope.

| Holder | Kind | Reports | Leverage |
|---|---|---|---|
| HubCo | large_13f | AAA $1,000, BBB $100 | not reported |
| OtherCo | large_13f | BBB $100, CCC $50, DDD $80 | not reported |
| SpecCo | specialist_13f | EEE $40, and 90% of the reported EEE value | not reported |
| Levered | etf | AAA, stated multiple 3 | above threshold |

Locked:

- Owned-book overlap: HubCo 0.80 of NAV, OtherCo 0.50, Levered 0.50. Hub holder is HubCo.
- AAA is held above the threshold. BBB, CCC, DDD, EEE are not.
- EEE is a hub name. DDD is not, once the fixture values say no single holder has 25% of DDD.
- Universe scope includes DDD and EEE and does not print a NAV stress.
- A 13F row with no leverage field is "not reported" and is not labeled unlevered.
- A CUSIP that matches two tickers is omitted from the join and listed as an exception.
- Holder pair HubCo-OtherCo shares BBB. The overlap dollars equal the smaller reported BBB value.

## 10. Phases

### Phase A — local only

Coverage report from section 4. Formula and fixture. Fence test. No EDGAR. The page can render against this file, with a banner that says the holder set is the specialists plus the six cached advisers, and that the large complexes are not in it yet.

### Phase B — the new pulls, in section 6 order

CUSIP repair, then the top-20 13Fs, then one quarterly bulk zip filtered to our CUSIPs, then N-PORT for the fixed ETF list and the stated-multiple table. Each step updates the coverage report so we can see which gap closed.

### Phase C — the page

Universe table, scope switch, pair list, ticker block. Browser check: a tier-3 name with only a specialist holder still appears; Michael's scope shows the dollar stress; the combined research list does not show a fake NAV; Drew's empty book does not invent overlap.

### Phase D — stop

Do not add price impact, a branching-process simulator, a stability label, a suggested weight, a write-back into Peters, Darwin, or the contract, or a paid holder feed. Do not commit the unfiltered 13F zip.

## 11. Done when

- The coverage view lists holder stats for the universe names, all three tiers, from the files in section 4 plus the pulls in section 6.
- A hub name is the 25% top-holder test. A hub holder exists only on a scope that has NAV.
- Leverage is a stated multiple or an N-PORT borrowings ratio. Everyone else reads "not reported."
- Owned scopes show hub removal and one seeded random removal, labeled as shared NAV, not a loss.
- The top holder pairs are computed without using our NAV.
- The phase A report states how many of the 846 already had a holder before any new download.
- Valuation, IC, human decision, Darwin, and Peters do not change because this ran.
- The fixture locks HubCo at 80% of the toy owned NAV, and it locks EEE as a universe name that is not in that book.
