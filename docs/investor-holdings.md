# Investor holdings archive

The Investors directory defaults to all investors and the latest available date for each source. Select a quarter to load that historical book. The source filter separates 13F filings, fund disclosures, and unresolved document identities. A missing disclosure is never interpreted as an empty portfolio or a sale.

Choose a fund vehicle to inspect its international disclosures. Holdings are searchable by company, symbol or identifier and paginated without dropping positions. Undated disclosures remain accessible under Date unavailable. Country, sector and cash allocation tables are not stock holdings. Unchanged original documents and books are retained without rewriting the archive on each refresh.

## Sources and scope

* The dated public DATAROMA roster supplies manager names, not holdings. SEC CIKs and legal names determine filing ownership; ambiguous names remain unlinked. Curated brand aliases are in `_system/reference/investors/manager_aliases.json`.
* Every eligible investor letter or fund report in the private corpus participates in the private universe. Non-filers remain in the directory. Header-confirmed managers appear normally; unverified document names remain available under Fund names to review. No public Git file records private source membership.
* Verified public brands and SEC legal names remain searchable aliases of the same manager. For example, Pabrai Investment Funds files as Dalal Street, LLC ([public adviser disclosure](https://pabraifunds.com/partnership-rules/)). Confirmed letter publishers are linked only through declared public aliases and a unique existing SEC owner; similarly named firms and distinct CIKs remain separate. The same reconciliation upgrades older pinned snapshots, including publishers retained after a corpus rotates. Fund vehicles, reporting dates and weight bases remain distinct.
* SEC 13F bulk archives supply the XML era. Every SEC submissions history page is followed without a filing-count or year limit, including older text/HTML reports, amendments, notices and legacy 13F-E forms. Availability is bounded by the SEC electronic archive; paper-only and confidential holdings cannot be manufactured.
* Principal-adviser records in all available SEC N-CEN archives discover registered fund series. Only exact legal identities link vehicles; subadvisers do not receive a whole fund portfolio. Appointment dates and the dated relationship evidence remain attached. N-CEN bulk coverage has a schema 3.1 gap disclosed by the SEC, so explicit verified sources supplement discovery.
* N-PORT supplies complete disclosed portfolios of individual registered funds, including international securities, currencies and identifiers. Letters supply only positions explicitly described as held. Historical letter tables can include issuers outside our stock universe. Mentions, benchmarks, short positions and stated exits are excluded from long holdings.

Named ownership claims and explicitly introduced numbered holdings lists do not require a ticker. PDF line wraps are rejoined within paragraphs; symbols and weights remain unknown unless disclosed. Every available eligible letter keeps its quarter and source link, including letters with no identified positions, which are explicitly labelled and never treated as empty portfolios. Deployment re-reads available authorized letter text with the current extractor and retains archived disclosures whose original text is no longer in the current corpus. This refreshes letter-derived observations alongside the pinned SEC archive without downloading historical filings again.

Raw source indexes do not always contain document classifications or canonical fund identities. The holdings pipeline inventories available text files and prepares records in memory using the letter reader's existing classification, fund/date resolution and exact-text deduplication policies. It uses the corpus's own registry and date overrides, keeps explicit exclusions, reports unavailable extracts, and never overwrites the source index. Modern classified indexes pass through unchanged. Exact archived document identities reconnect renamed publishers only when their existing owner and fund are unambiguous. Other publishers remain accessible under Fund names to review, without joining known SEC owners. Partial re-extraction retains previously disclosed positions and known weights for the same fund, document and quarter, with a source-review label.

13F weights describe reported holdings excluding options, N-PORT weights describe fund net assets, and letter weights retain their disclosed or unspecified basis. These denominators are never combined. Letters without a verified holdings date show the disclosure date and explicitly leave the holdings date unknown.

## Data integrity

The private SQLite archive preserves each accession, individual as-filed rows, reconciliation results, downloaded document bytes and checksums. New-holdings amendments add to a book; restatements replace it. An amendment with an unknown type cannot replace the original. Unrecognized legacy layouts are retained and reported. Successfully parsed rows remain available as partial data; portfolio weights stay unknown while a parser gap could change the denominator. Unreadable reports never become empty or fabricated portfolios. Coverage reports distinguish discovery, imports, source warnings and pending parser work. They do not claim complete coverage while a required source is missing.

## Refresh and recovery

Run from the repository root with the research vault available and `SEC_USER_AGENT` set to a real contact string:

```sh
python _system/scripts/refresh_investor_history.py --seconds 14400
```

The daily Investor holdings history workflow runs this same resumable refresh. It saves a verified private checkpoint even after a source-processing failure, persists the private archive first, then publishes a public checksum pointer. Subsequent runs skip completed archive imports and filings. The dashboard deployment is triggered after refresh and stages the pinned checkpoint behind the existing authentication.

For a local initial backfill, archive downloads can be completed first, followed by offline bulk imports and exhaustive accession discovery:

```sh
python _system/scripts/investor_history.py --download-only --workers 2
python _system/scripts/investor_history.py --cached-bulk --all-filings --reparse --export --seconds 43200
python _system/scripts/global_disclosures.py --public --publish
```

The private corpus can be selected with `--corpus` on the refresh or disclosure command. Original quotes and source references stay private. Private checkpoints use immutable SHA-addressed parts smaller than GitHub's object limit. Each compressed block is stored once and reused across publications. The public `archive_receipt.json` pins an exact checkpoint. Deployment fails if that checkpoint is unavailable or corrupt. The generated investor directory, yearly history and disclosure shards are restored at build time. Historical books, disclosure manifests and position shards share checksum-addressed binary bundles of at most 16 MiB. Each logical JSON body is an independent gzip member; the directory records its bundle, byte offset and compressed length. Every original byte is retained. The browser shares binary requests, retains at most four bundles, and decompresses only the requested book or position shard. Legacy by-manager and by-ticker endpoints remain directly accessible. Privacy validation also scans every decompressed logical body. Deployment validates the complete site's file count and asset sizes after company research and holdings have both been staged.

All collection is HTTPS research-data work. No Gateway socket, broker session, ThetaData terminal, or market-data subscription is involved.
