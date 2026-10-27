# Dashboard data recovery — October 27, 2026

The dashboard now separates refreshed source data, missing disclosures and unfinished research. Rebuilding a file no longer marks incomplete rows as complete.

## Aggregates

- All 11 active companies have sourced, period-aligned annual financials. Nine have operating disclosures, and nine have EV/EBITDA comparisons.
- Latest-quarter and TTM operating views retain the explicitly labeled annual valuation basis. Gross profit and cash gross profit have separate columns.
- Extraction now handles annual property tables, cumulative interim disclosures, separate currency cells, thousands of tons and reported organic shipment changes. Every observation retains its source, period, scope and locator.
- Published company details retain six years of financial observations in compact JSON; full SEC responses remain cached for reproducibility.
- ROAD's cover share count combines its two classes only after verifying their identical economic rights in Note 9. Amrize's debt includes its separately disclosed short-term borrowings. IFRS financials are supported when reported in USD.
- Titan America joins the active screen. Its annual external aggregate shipments and selling prices retain their stated scope; the price is not labeled freight-adjusted.
- Arcosa leaves the active comparison after CRH completed its acquisition on October 23. Historical evidence remains in the ledger and detail snapshots.
- Breedon, Heidelberg Materials, Holcim, SigmaRoc and Wagners are research candidates. NRP and Weyerhaeuser are royalty candidates, kept separate from quarry operators.

Primary completion and identity references: [CRH / Arcosa](https://www.crh.com/media/press-releases/2026/crh-completes-8-5b-acquisition-of-arcosa/), [ROAD's June 2026 filing](https://www.sec.gov/Archives/edgar/data/1718227/000162828026054661/road-20260630.htm), [Titan America's annual filing](https://www.sec.gov/Archives/edgar/data/2035304/000203530426000047/ttam-20251231.htm).

## Other tabs

| Surface | Implemented recovery |
|---|---|
| Banks | Added Westamerica and Esquire; rebuilt the 11-company screen. Missing deposit and valuation inputs remain explicit. |
| NOL | Rebuilt 89 companies; added a dated USD market-cap fallback. Missing market caps fell from 21 to 14. |
| Index Watch | Fixed discarded market caps and prioritized current observations over saved model prices. Missing market caps fell from 637 to 81. |
| Separations | Recorded seven sourced completion amendments. All 15 registered historical separations are now closed; an empty active list is valid. |
| Market Risk | Refreshed public upstream snapshots, repaired local source discovery and prevented older inputs from replacing newer observations. Fourteen of 15 components are current. |
| Activism | Completed the SEC pass over 865 tickers. Added bounded concurrent reads, a shared request throttle, incremental filing windows and resilient checkpoints. |
| Insights | Rebuilt the Insights sections. Podcast recovery retains historical episode identities while admitting current summaries and episodes. |
| Research memory | Rebuilt the derived claim/source index; human-owned memory and approvals remain separate. |
| Buybacks | Refreshed 972 companies; 713 verified and 259 still require evidence reconciliation. |
| Shorts | Refreshed the dated public borrow file and rebuilt the candidate view. Borrow availability and research completeness remain separate. |
| Darwin | Refreshed delayed option chains and the earnings calendar; 446 of 503 companies scored. Eligibility exclusions remain intact. |
| Technicals and warrants | Refreshed snapshots and discovery. Used the newer validated technical snapshot already on main when it superseded the local run. |

## Source questions still open

- CX and TTAM need sufficiently recent, confirmed outstanding share counts for current equity-based valuation. Weighted-average EPS shares do not substitute for outstanding shares.
- Undisclosed cash gross profit, organic growth, reserve life and maintenance capital spending remain unavailable. Reserves/resources, production/shipments and corporate/segment profit are not interchangeable.
- Foreign candidates need currency, listing-unit, tonne and business-perimeter reconciliation before numeric admission.
- The observed volatility-target flow component has no connected source. Estimated leveraged ETF flows remain a separate measure.
- Some NOL securities lack current quotes or filing detail. Some bank inputs require issuer-specific or non-USD extraction.
- Podcast transcript/model queues, video caption pacing, investment-model gaps and human review queues remain visible. Refreshing source data does not approve an investment or complete its research.

## Validation and publication

The broad Python suite and targeted regression tests passed. Browser checks covered the quarterly aggregates view, annual valuation visibility and source-status presentation. The separation register passed its strict validation, and aggregate detail references passed publication checks.

Changes are prepared for pull-request review under CONTRIBUTING.md. The working dashboard and private research snapshots were rebuilt locally; source-linked private artifacts remain in the configured private archive.

## Follow-up request for Grok

Find additional listed aggregates, cement, lime and aggregate-royalty candidates beyond VMC, MLM, CRH, AMRZ, EXP, KNF, TTAM, USLM, GVA, ROAD, CX, BREE.L, HEI.DE, HOLN.SW, SRC.L, WGN.AX, NRP and WY. Check acquisitions, delistings, renamings and duplicate parent/subsidiary exposure first. Use issuer filings and official exchange records. Return ticker, exchange, issuer identifier, reporting currency, listing/ADS ratio, peer category, latest annual/interim period, aggregate shipments, selling-price definition, segment profit, reserves, production and outstanding shares. Give an exact source URL and table/page locator for every number. Distinguish short tons from metric tonnes, external from internal volumes, freight-adjusted prices from reported prices, and reserves from resources. Leave undisclosed fields null. Rank research priority separately from investment attractiveness; do not infer missing financials or treat acquired companies as current listed peers.
