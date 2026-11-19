# Stock research presentation inputs

Every covered stock receives the six-tab brief. `universe.json` is a small index of bounded private input parts. Each part has a checksum-protected public counterpart and restores through the existing authorized publication process. It holds financial histories, dated model inputs, risks and shareholder-return series; it is never part of the startup core. The small original reference-stock caches remain as explicit overrides.

To refresh the snapshot, restore the current core and ticker shards into a disposable local folder and run:

```powershell
python _system/scripts/build_stock_research_history.py --core <restored-core.json> --shards <restored-tickers-folder> --output <temporary-universe.json> --refresh-performance
```

Partition the generated output before private preservation:

```powershell
python _system/scripts/partition_stock_research_history.py --input <temporary-universe.json> --output <temporary-part-folder>
```

Publish the parts through the existing private snapshot preservation and storage process, verify the private bytes, then commit only the small index, structural public counterparts and their receipts. Do not commit the full snapshot. Prices come from rate-limited Yahoo HTTPS requests; this tool has no broker or terminal connection. Without `--refresh-performance`, it uses previously collected checkpoints and existing source caches.

Financial periods and currencies retain their source basis. Quarterly caches support TTM. Annual sums require four consecutive quarters ending at an explicitly derived annual-minus-nine-month observation; fiscal boundaries are never guessed from filing-year labels. Raw filings support actual annuals, explicit YTD differences and 52/53-week fiscal years. Incomplete evidence remains a visible gap. Historical financials and newer prices do not upgrade model eligibility or revise a valuation.

Returns exclude the current exchange day, use the listing currency and reinvest discovered distributions. Distribution verification remains explicitly incomplete unless independently established. SPY is compared only in the same currency and on matching observed dates. Unavailable and delisted listings retain the layout and a clear history gap.

Publication verifies that every stock in the core has a brief and that the core remains below 6,000,000 bytes. Full histories stay in the stock shards. Table badges, valuation gates and freshness dates remain in the core.


Cash-distribution basis is explicit. Yahoo's historical dividend amounts already reflect subsequent stock splits; they must not be divided by those splits again. Primary amounts declared on an original share basis are normalized once. The regression fixture uses Apple's [July 2020 dividend and split announcement](https://www.apple.com/newsroom/2020/07/apple-reports-third-quarter-results/) and the vendor's adjusted historical amount. Events before the observation window are excluded. Completed exchange sessions before 1970 are supported.

Captured provider inputs are retained in the refresh's temporary `performance-inputs` folder so return calculations can be reproduced without another download. A separate adjusted-close consistency check flags materially conflicting vendor-only histories for source review. Those histories are withheld rather than substituted with an older curve.
