# Stock research workspace

The Research coverage table opens a stock workspace with four views. The renderer is presentation only: it does not change valuation, return eligibility, committee state, owner decisions, source facts, or financial models.

## Information map

| Previous content | New location |
| --- | --- |
| Company, listing, thesis, stance, readiness, owner status, owner stance, two-phase trigger, FICO watch verdict | Persistent company header |
| Next action, main blockers, price/PV range, margin of safety, eligible forward return, model/fact/price dates, three cleared KPIs or dated operating observations, leading falsifier and three developments | Overview |
| Component ownership/value, NAV, CVR, separation terms, published scenarios or labelled research diagnostic, TCI assumptions and missing evidence, pricing, detailed earnings model | Valuation |
| Historical total returns and technical setup (kept distinct from forward returns) | Valuation disclosures |
| KPI histories, signal summaries, business quality, issuer operating drivers, company dossier, buybacks/share-count charts, FICO watch detail, two-phase monitoring, activist context | Business & KPIs |
| Report links, full deep-dive summary, essential insights | Evidence: Reports & essential insights |
| Full original decision audit (including dates, tier, proof, legacy excluded result, and gaps), owner review, complete workbench pages, investment committee | Evidence: Decision authority & valuation audit |
| Active lenses, power zones, research memory, external context, consensus | Evidence: Frameworks & research context |
| Fund holdings and overlap | Evidence: Ownership context |
| Full developments, source-library/infrastructure coverage, recent files | Evidence: History, source coverage & files |
| Research-wide summary cards and system-health data | Coverage health disclosure |
| Previous table columns | Seven default columns and optional Company & decision detail, Technicals, CVR/NAV, Ops, Insights, and Index groups |

Only the active view is mounted initially. Each other view is rendered on first selection, and retained while the stock is open. Existing specialist renderers supply the detailed content. Workbench pages become one audit document; nested disclosures are flattened into headings. Source links and data remain in the detailed views.

## Display rules

- Missing, blank, boolean, or non-finite numbers never become zero. Zero observations and negative scenario returns remain valid.
- The overview uses the published valuation decision. It does not turn a present value into a forward return.
- Research scenario diagnostics remain labelled as research, with their horizon and model date. The exact IRR and its reconciliation remain in the detailed driver table.
- Entry thresholds appear on the ruler only when upstream buy-zone status is available. The full pricing evidence remains under Valuation.
- Ruler bounds include the quote even when it is outside the value range; the quote is not silently pinned to an endpoint. Currency formatting comes from the listing's existing quote-unit helper.
- Current KPI charts obey upstream display, artifact, stale, and excluded flags. Dated issuer observations can appear without an invented trend. Other usable series are explicitly historical, with units/source gaps shown.
- Raw action instructions remain in the evidence audit; the overview gives common review tasks plain-language labels.
- FICO's watch verdict and owner stance are visible before navigating into detail.

## Navigation and verification

Stock views deep-link through `#/research/coverage/TICKER?section=overview|valuation|business|evidence`. Legacy `section=buyback` links resolve to Business & KPIs. Search/filter URL state is retained. Table and stock-list scroll positions are stored separately, and stock view/scroll/disclosure state survives a ticker rerender. Arrow keys, Home/End, Enter/Space, Escape and Back to coverage support keyboard use; mobile gives the selected stock the full width.

Run `node --test _system/scripts/tests/test_research_workspace.cjs` (also invoked by the Python suite). Browser QA covers a core compounder, an available value range, NAV, CVR, model-ready and sparse records, FICO's watch, deep links, keyboard tabs, filtering, scroll restoration, and narrow screens. The workspace never fetches the full KPI-trends dataset.
