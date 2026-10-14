# Short-selling research library

This directory separates **licensed/copyrighted books** from **publicly distributed research**. Do not commit unauthorized book scans. Books are catalogued for purchase, library access, or a user-supplied licensed copy; official public papers are stored under `public/` with their source URL.

## Core books — catalogue only

| Resource | Why it belongs in the process | Access |
|---|---|---|
| Kathryn F. Staley, *The Art of Short Selling* (1996) | Field cases, balance-sheet deterioration, accounting signals, and short thesis construction | ISBN 9780471146322 · purchase/library/authorized copy |
| Howard M. Schilit, Jeremy Perler, Yoni Engelhart, *Financial Shenanigans*, 4th ed. | Earnings quality, cash-flow manipulation, acquisition accounting, and KPI games | ISBN 9781260117264 · purchase/library/authorized copy |
| Thornton L. O'glove, *Quality of Earnings* | Receivables, inventories, capitalization, taxes, and reported-vs-economic earnings | ISBN 9780684863757 · purchase/library/authorized copy |
| Scott Fearon, *Dead Companies Walking* | Competitive decay, management denial, and catalyst discipline | ISBN 9781137279644 · purchase/library/authorized copy |
| Christine S. Richard, *Confidence Game* | Forensic credit work, regulatory claims, and the path/timing problem in a public short | ISBN 9781118010419 · purchase/library/authorized copy |
| Bethany McLean and Peter Elkind, *The Smartest Guys in the Room* | Related parties, incentives, off-balance-sheet structures, and narrative control | ISBN 9781591846604 · purchase/library/authorized copy |

When an authorized ebook/PDF is supplied, store it in the private research vault, not this operational repository, and add only a metadata pointer here.

## Public documents stored here

| Local file | Original source | Use |
|---|---|---|
| `public/sec_financial_reporting_manual_2026.pdf` | https://www.sec.gov/files/cf-frm.pdf | Filing and disclosure requirements; treat as non-authoritative staff guidance where the SEC says so. |
| `public/sec_short_sale_position_transaction_reporting_2014.pdf` | https://www.sec.gov/files/short-sale-position-and-transaction-reporting0.pdf | Market structure, short-position data, reporting limitations, and policy background. |
| `public/nber_w9466_efficiency_and_the_bear.pdf` | https://www.nber.org/system/files/working_papers/w9466/w9466.pdf | Short-sale constraints, market efficiency, volatility, and skew. |
| `public/nber_w20282_shorting_premium.pdf` | https://www.nber.org/system/files/working_papers/w20282/w20282.pdf | Borrow fees, anomaly interaction, and the shorting risk premium. |
| `public/nber_w16335_short_selling_market_quality.pdf` | https://www.nber.org/system/files/working_papers/w16335/w16335.pdf | Experimental evidence on lending supply, prices, and market quality. |

These five files are the local copies. The Shorts tab encodes this reading list as trackable lenses in `_system/research/short-alpha/frameworks.json`.

Public availability does not erase copyright. Preserve attribution and do not redistribute outside the terms of the source.

## Playbooks (process notes)

Michael's Short-Selling desk kept `type: playbook` entries beside its ideas. Process pages land here; framework content lands in `_system/frameworks/short_alpha_filing_furnace.md`. The entry contract they serve is in `_system/research/short-alpha/README.md`; the blank is `_system/templates/short_entry_template.md`.

| Local file | Adapted from | Use |
|---|---|---|
| `playbooks/framing_a_short.md` | Michael's Short-Selling desk playbook "Framing a short before it is a position", 2026-01-06 | What a note must contain before anyone treats it as a live idea: one arguable claim, an honest category, evidence read versus needed, the falsifier first, tradability as its own point, a truthful stage. |

## Paper notes (summaries in our words)

Michael's `type: paper` entries become original summaries with a citation and a link to the public version. No abstract, table or equation is copied. File one when a result changes how we screen, not to store an abstract.

| Local file | Paper | Use |
|---|---|---|
| `public/notes/dechow_hutton_meulbroek_sloan_2001.md` | Dechow, Hutton, Meulbroek and Sloan, "Short-sellers, fundamental analysis, and stock returns," *JFE* 61 (2001), DOI 10.1016/S0304-405X(01)00056-3 | Short interest clusters where price has run ahead of fundamentals and those names underperform afterward; a reason to do the fundamental work and to start price-versus-fundamentals ideas in the accounting lenses. |

## Live official references

- SEC Regulation SHO overview: https://www.sec.gov/investor/pubs/regsho.htm
- SEC Accounting and Auditing Enforcement Releases: https://www.sec.gov/enforcement-litigation/accounting-auditing-enforcement-releases
- SEC Financial Reporting Manual (current web edition): https://www.sec.gov/about/divisions-offices/division-corporation-finance/financial-reporting-manual
- Investor.gov leveraged/inverse ETF bulletin: https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-alerts/sec
- AQR, “Price Efficiency and Short Selling”: https://www.aqr.com/Insights/Research/Journal-Article/Price-Efficiency-and-Short-Selling
- NBER, “Go Down Fighting: Short Sellers vs. Firms”: https://www.nber.org/papers/w10659

## Reading-to-workflow map

1. **Framing:** `playbooks/framing_a_short.md` → one arguable claim, an honest category, evidence read versus needed, the falsifier before the argument, tradability as its own point. The note is written from `_system/templates/short_entry_template.md`; the row goes to `candidates.json`.
2. **Idea formation:** Staley/Fearon → define the market belief, variant view, catalyst, and falsifier.
3. **Accounting:** Schilit/O'glove + SEC FRM/AAER + `public/notes/dechow_hutton_meulbroek_sloan_2001.md` → reconcile revenue, working capital, capitalization, reserves, acquisitions, and non-GAAP claims; start a price-versus-fundamentals idea in the accounting lenses before any story category.
4. **Share supply and reverse splits:** the `share_supply` gate (lockups, ATMs, converts, insider selling, index deletions, separations) and the `reverse_split_impairment` lens with `_system/frameworks/reverse_split_short_process.md` → a pipe that can add stock is a timing gate; a reverse split is a capital-structure event, not a thesis.
5. **Tradability:** Regulation SHO + NBER/AQR → borrow, utilization, fee, recall, crowding, squeeze, and options alternatives. Borrow arrives as a Client Portal CSV through `refresh_short_alpha_borrow.py`, never through the Gateway.
6. **Instrument:** Investor.gov bulletin → daily reset, swaps, tracking, liquidity, and path dependence for ECHX-like products.
7. **Memory:** write a dated baseline and every later check-in to the Short Alpha ledger; never rewrite the original hypothesis after seeing the outcome. Move `updated_on` on every material edit of a row or its note.
