# Stock research presentation inputs

Every covered stock receives the six-tab brief. `universe.json` is a checksum-protected public receipt for a private input snapshot, restored by the existing authorized publication process. It holds financial histories, dated model inputs, risks and shareholder-return series; it is never part of the startup core. The small original reference-stock caches remain as explicit overrides.

To refresh the snapshot, restore the current core and ticker shards into a disposable local folder and run:

```powershell
python _system/scripts/build_stock_research_history.py --core <restored-core.json> --shards <restored-tickers-folder> --output <temporary-universe.json> --refresh-performance
```

Publish the exact output through the existing private snapshot preservation and storage process, verify the private bytes, then commit only the structural public counterpart and its receipt. Do not commit the full snapshot. Prices come from rate-limited Yahoo HTTPS requests; this tool has no broker or terminal connection. Without `--refresh-performance`, it uses previously collected checkpoints and existing source caches.

Financial periods and currencies retain their source basis. Quarterly caches support TTM. Annual sums require four consecutive quarters ending at an explicitly derived annual-minus-nine-month observation; fiscal boundaries are never guessed from filing-year labels. Raw filings support actual annuals, explicit YTD differences and 52/53-week fiscal years. Incomplete evidence remains a visible gap. Historical financials and newer prices do not upgrade model eligibility or revise a valuation.

Returns exclude the current exchange day, use the listing currency and reinvest discovered distributions. Distribution verification remains explicitly incomplete unless independently established. SPY is compared only in the same currency and on matching observed dates. Unavailable and delisted listings retain the layout and a clear history gap.

Publication verifies that every stock in the core has a brief and that the core remains below 6,000,000 bytes. Full histories stay in the stock shards. Table badges, valuation gates and freshness dates remain in the core.
