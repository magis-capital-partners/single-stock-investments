# Company research library

The owner website opens on **Stock Research**, followed by **Ideas** and
**Insights**. Explicit links to other workspaces still work. Each company has
three tabs: **Overview**, **Sources**, and **Models & KPIs**. Older evidence,
business, valuation and buyback links resolve to the corresponding new tab.

The overview contains the company thesis, three operating metrics, two recent
developments, the main open question, source counts and essential reading.
Research status and the existing valuation, KPI and decision records remain
available through disclosures. Source filters never depend on the capped
Insights feeds.

## Inventory and relevance

`_system/scripts/build_company_research.py` joins both document catalogs, the
configured Drive research roots, the private research-vault collections,
company originals and filing manifests, the Git tree, and shared industry,
commodity and model research. Drive discovery follows every page and folder;
it includes native Docs, Sheets and Slides, expert interviews, fund letters,
presentations, spreadsheets, PDFs and media. A document can belong to several
companies, with company-specific passages and reproducible text locators.

Matching uses issuer collections, company names, the existing security master
and exchange-identity checks. Bare ticker collisions, incidental holdings-table
mentions and weak matches go to the private review inventory. Shared research
uses explicit company lists and economic explanations in
`company_research_themes.json` and `_system/portfolio/holdings_themes.json`.
Portfolio-wide wildcard relationships are not company evidence. The old
linkage graph is not an authority for issuer relevance. Adding a driver is a
reviewed configuration change; it does not change valuation assumptions.
Existing natural-gas forecasts, Bitcoin mining and electricity-cost models are
included with their assumptions and references. Methodology files are read as
source text, never executed by this library.

Exact byte hashes, original Drive identity and explicit original/extract
relationships combine duplicate copies. Equal filenames alone never do.
Original locations remain attached to the combined record. Historical revisions
remain accessible using **All versions & history**. The default lists the latest
version of each source family.

## Search and completeness

All inventory pages participate in filtering; 25 displayed rows are a page,
not an ingestion limit. Search covers all extracted text, titles and authors.
Large text, metadata and search indexes are split into bounded assets. PDFs are
read across all text-bearing pages and Office files across sheets/slides.
Scanned PDFs and recordings without transcripts remain listed with their
original links and an explicit processing state. This implementation does not
claim OCR or transcription has completed for those files.

Each company reports when its library was checked, pending text processing,
possible matches awaiting review and unavailable collections. Missing inputs
never imply an empty, complete library. A failed refresh preserves the last
known source records; successful absence is labelled removed or unavailable.
A corrupt individual file does not stop discovery of the rest of its collection.

Text extraction caches are keyed by content or original revision. Drive and
sparse-Git extraction have a bounded work budget per build; **inventory has no
result limit**. Later builds reuse completed work and advance through missing
text. Failed Drive extraction has a retry delay so one unsupported original
cannot monopolize the queue. The private review inventory records weak matches
for later reconciliation; they are not mixed into a company's accepted sources.

## Private deployment

The deploy action builds the library under `_private/company-research/site`.
Its incremental cache is stored only under the private vault's
`dashboard-private/company-research-cache`, using the existing private-vault
preservation action. Do not commit generated library data to this public
repository, upload it to public Actions artifacts, or use public workflow caches.

`stage_company_research.py` requires authentication on every site path, validates
all referenced assets, and copies only reachable library assets into the Pages
artifact. The existing middleware denies source text, search indexes and
metadata to anonymous users and restricted fund-letter readers. Owner responses
use private, no-store caching. Document content is always displayed as escaped
text; document instructions and embedded scripts are never executed.

The existing dashboard deployment performs the refresh. It needs the existing
Drive service-account secret and private-vault token. No broker connection,
ThetaData session, live market-data request or trade operation is involved.

## Local verification

Run focused tests:

```text
python -m pytest _system/scripts/tests/test_company_research.py _system/scripts/tests/test_research_workspace.py
node --test dashboard/cloudflare/test-fund-letters.mjs
```

To verify real sources, set `RESEARCH_VAULT_ROOT` and the existing read-only Drive
credentials, then run the builder. `--tickers CME NEM WPM CLSK MSTR` limits a
verification run; omit it for the entire coverage universe. Use a separate cache
and output directory for scoped runs. `--download-budget-seconds 0` removes the
Drive extraction work budget, while ordinary deployments use an incremental
budget. A coverage report, unresolved-match inventory and each ticker's manifest
are written alongside the private assets.
