# Coverage filter simplification

## Implemented in this change

- Remove the large Core compounders banner and its separate Research navigation item.
- Put All coverage, Quality compounders and Serial acquirers together in the Universe filter row. Keep separate company views and company links for each list.
- Retain the 46 owner-selected quality compounders. Reconcile all 141 companies from the linked M&A tracker: 111 new listings, 30 already covered. Allow membership in both lists.
- Keep established acquirers, bank consolidators and emerging acquirers as categories within the serial-acquirer view. These are research candidates, not automatic quality ratings.
- Label the existing filter rows. Keep the chosen universe while applying market, sleeve, valuation, technical, ownership and work-status criteria; show each selected filter correctly.
- Add Clear all filters and a compact indication of active criteria. Use one search field across coverage and both company views.
- Retain the existing company research, valuation evidence gates and buyback links. New listings start without financial estimates or ownership assumptions.

## Next pass: consolidate the controls

Replace the long rows of buttons with the following small set of labeled controls. Keep the Universe row as ordinary tabs; use dropdowns for longer lists.

| Control | Purpose | Existing controls to consolidate |
|---|---|---|
| Universe | Which maintained research list to browse | All coverage, quality compounders, serial acquirers |
| Market | Where the security is listed | All country/market buttons; use full market names in the dropdown |
| Strategy and industry | Which investment approach or business group to inspect | Split CVRs, NAV discounts and hard assets from industry sleeves such as software and healthcare |
| Research priority | How much research effort a company receives | Tier 1, Tier 2, Tier 3; explain their meaning beside the selection |
| Valuation readiness | Whether usable valuation research exists | Stock-specific, screening only, evidence blocked, cohort, Phase 2, provisional, decision-grade |
| Technical condition | Which price/volume condition to inspect | Panic 70+, capitulation candidates, confirmed exhaustion |
| Tracking | Ownership and outstanding research work | Owned and Needs work as independent toggles |

### Valuation readiness requires a mapping review

Priority tiers and model readiness answer different questions and must remain independent. Before collapsing the readiness buttons, inventory their actual row predicates and counts. Proposed visible choices are All models, Needs a model, Screening only, Evidence missing and Research available. Keep the precise model type and review stage on each company page and in an advanced dropdown when useful.

Do not equate a published research return with an owner-approved investment decision. Do not merge two statuses just because their labels sound similar. Document the old-to-new predicate mapping and check known examples before replacing the current buttons.

## Delivery order

1. Inventory current filter predicates, usage, result counts and links. Identify overlaps and empty choices; preserve useful niche screens.
2. Introduce a shared filter-state definition used by controls, counts, URL parameters and the results table. Move column visibility and table density into a separate Display menu.
3. Replace the long market/sleeve/valuation button lists with the reviewed controls above. Keep less-used choices in Advanced filters and expose active choices as removable chips.
4. Add saved views only after the underlying controls are consistent. Suggested views: Owned, Quality compounders, Serial acquirers and Research needs work.

## Acceptance checks

- Combine Serial acquirers + Sweden + Needs work; changing one criterion must retain the others.
- Switch between the two company views; each retains its own business-category selection and links to the correct company page.
- Direct links and reloads preserve search, universe and global filters. Old compounder and valuation links continue working.
- Result counts reflect the exact same predicates as the displayed rows. An empty result explains which filters to clear.
- Clear all resets global and list-specific filters, search and pagination.
- New companies, overlapping memberships and foreign ticker collisions appear once per listing. No imported rank changes an investment stance.
- Controls remain usable with a keyboard, at phone widths and in both themes. Column controls never look like company filters.

The next pass is a plan, not a wholesale redesign included in this change. The dated company reconciliation is in [serial-acquirer-coverage-2026-11-16.md](serial-acquirer-coverage-2026-11-16.md).
