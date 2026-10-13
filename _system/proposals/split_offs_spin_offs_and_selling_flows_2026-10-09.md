# Split-offs, spin-offs, and expected selling flows

**Date:** 2026-10-09
**Status:** implemented 2026-10-11 (phases 0-6 landed in one pass; see § Implementation record at the end). Open items: the reference-set upper limits and the Medtronic final-results 8-K still need reading into the register; Flex corporate actions are parsed but not yet ingested into the book.
**Owner:** human; Marvin implements
**Template:** `_system/prompts/architecture_review_template.md`
**Frameworks touched:** `special_situation_lens.md` (expanded, not replaced), `index_membership_lens.md` (flow primitives reused), `classification.md` (one trigger row), `analysis_arsenal.md` (one row)
**Sources already in the repo:** Stahl, *Spinoffs: Going Separate Ways* (2015); the Horizon Kinetics spin-off compendia and white paper under `investment-wisdom/horizon-kinetics/pdfs/`; Manual of Ideas Ch. 8; Greenblatt (README only, no text); `_system/reference/index-effects/SYNTHESIS.md` and the provider methodology PDFs under `index-effects/methodology/`.

Split-offs come first. They are the mechanically richer event, they create a dated and sizable selling wave that can be modelled from the filing alone, and the repo has **nothing** on them today. Spin-offs ride on the same register and the same flow model.

---

## Goal

Make corporate separations a first-class situation in the decision stack, with four things the repo does not have:

1. A **register** of separations (split-off exchange offers, spin-offs, carve-out IPOs, clean-up distributions, retained-stake sales) sourced from SEC filings, with terms source-locked.
2. A **terms engine** for split-offs: implied exchange ratio, discount, upper limit, proration, odd-lot priority, and the annualized spread that `special_situations.json` already carries as a field and always leaves `null`.
3. A **selling-flow model** that says who must sell, how much as a percent of float and in days of volume, and over which dated window. It extends `index_flow_impact.py` rather than inventing a second flow vocabulary.
4. **Valuation routing** so the parent, the stub, and the spun company each get a proof-first contract through the existing `catalyst_asset_value` zone, and the orphan window is a dated field the lint can check, not prose.

Flows never change intrinsic value. They answer decision-stack question 5 (why mispriced, who is the non-economic seller) and inform question 6 (when), and they are published `research_only` with `authority: none`, like every other flow artifact in this repo.

## What exists today (survey, 2026-10-09)

| Area | State |
|---|---|
| Split-offs | Nothing. "exchange offer" is one regex in the 10-K/10-Q sentinel (`filing_sentinel_workflow.py:55`). `SC TO-I` is in `DEAL_FORMS` of `build_special_situations.py`, but the activist feed only classifies `SC TO-T`/`SC TO-C`, so an issuer exchange offer never arrives. No odd-lot, proration, upper-limit, or valuation-period logic anywhere. |
| Spin-offs | News-only. `portfolio_news_common.py` tags `spinoff` (priority 78). `build_special_situations.py` `spinoff_rows()` groups headlines per ticker, `ends` is always null, `annualized_spread` is always null, completion is detected by the word "complet", and the bare `\bspin\b` match admits a false positive (the GEV "dips" headline). 7 ranked rows today, 0 discovery, 0 history. |
| Filings | Sentinel forms are `10-Q`, `10-K` only. `download_us_investor_docs.py` omits `10-12B`. No Form 10 in any `document_catalog.json`. 8-K Item 8.01 is parsed only for CVRs. |
| Register / linkage | No parent↔SpinCo link in `registry.json`, `security_master.json`, or `classification.json`. GEV, SOLV, VLTO, KVUE, SW, WBD, PSKY, HONA, FDXF are `price_stub` placeholders with no classification. |
| Valuation | Router profile `catalyst_asset_value` exists with method cards `probability_weighted_catalyst_nav` (present value) and `dated_future_payoff_per_share` (future payoff). It is the right home. Only APTV models a spin (`nav_overlay.versigent_spin`, `milestone_nav`). `special_situation` is referenced by the router, the economic-value trigger and `power_zones.json` but is **not** a canonical archetype (L4 violations in `INVARIANTS.md`). |
| Flows | One quantitative model: `index_flow_impact.py` (float-adjusted weight × tier AUM, both legs, `pct_of_float`, `pct_of_adv_days`, HK cliff). It covers Russell/S&P/Nasdaq-100/MSCI USA only. Known defects: % of float is a per-index constant; `next_calendar_for_indices` picks the wrong index's date; the June APLD recon boost never expires; `build_insights.py:1466` marks every add bullish, contradicting the graduation model. |
| Ownership | `overlap_holdings.json` has holder lists but no passive share. BlackRock 13F is from 2024-08. N-PORT series not isolated. No BMI per name. |
| Outcomes | Warrants have the right pattern: append-only registry, SEC events, point-in-time cohorts, matured outcomes, descriptive calibration (`_system/data/warrants/README.md`). `distribution_event_schema.json` already has a `spin_off` type with `fair_value_per_parent_share`; no ledger uses it. |
| Lens prose | `special_situation_lens.md` is 19 lines. It lists `spinoff` as an inefficiency type, demands an annualized return when the catalyst is dated, and points at a table "in git history". |

## Constraints

- **Must keep:** framework governance (no new framework file when an arsenal row plus a `valuation.json` key plus a handler plus a lint will do); `n_a`-on-missing-inputs discipline from the index lens (never invent float, ADV, AUM, or terms); confirmed vs predicted always visually distinct; `research_only` / `authority: none` on every flow payload; only `human_decision.json` is capital-actionable.
- **Must not break:** `special_situations.json` consumers (`special-situations-viz.js`, the inbox join in `index.html`); `index_membership.json` schema; the desk's "missing inputs skip the write" rule; the ThetaData seat window and the Gateway rules (this work needs neither; all validation uses Yahoo daily bars and EDGAR).
- **Non-goals:** intraday timing of the selling wave; automated tendering or any order; options on the parent or SpinCo; non-US separations in the first release (register them, do not model flow); tax advice beyond recording whether the filing claims Section 355 treatment.

## Normative content to encode

This is the layer the index lens calls "axioms". It goes into `special_situation_lens.md` § Separations, and each line below must map to a field, a leg, or a lint.

### Split-off (exchange offer)

1. **The instrument is an offer, not a distribution.** The parent offers to exchange SpinCo shares for parent shares. Holders choose. The parent files `SC TO-I`; SpinCo files `S-4` and the prospectus `424B3`; both file 8-Ks. Tender period is at least 20 business days. Record the four dates: launch, valuation period (usually three sessions ending two before expiration), expiration, settlement.
2. **The ratio is a formula, not a number, until the valuation period closes.** `ratio = parent_vwap × (1 + discount) / spinco_vwap`, capped at an **upper limit**. The discount has been about 7% in US practice (Pfizer/Zoetis 2013, GE/Synchrony 2015, Lilly/Elanco 2019, J&J/Kenvue 2023 are the reference set). When the upper limit binds, the realized discount shrinks and can go negative; the offer then usually extends by two sessions. Both the formula and the cap are in the prospectus and must be source-locked before any spread is shown.
3. **Proration is the base case.** A discount guarantees oversubscription. The accepted fraction has been low (well under half in the reference set). The headline spread is therefore the odd-lot spread, not the holder's spread.
4. **Odd-lot priority is the retail edge.** Holders of fewer than 100 parent shares who tender all of them are not prorated. Payoff per 99 shares is the discount on 99 shares of parent, less friction. This is a per-account fact: the dashboard may flag it on a held parent; acting on it is a human ticket.
5. **Who sells, and when.** During the offer, arbitrageurs buy parent and short SpinCo; SpinCo borrow tightens and the SpinCo price is pressured. At settlement, arbitrageurs receive SpinCo and sell it to cover, and unaccepted parent shares are returned and sold. The post-settlement window is the dated selling wave: start = settlement, length = a few sessions to a few weeks, size bounded above by shares accepted.
6. **Index funds in the parent's index do not tender.** They cannot hold a non-benchmark security. So SpinCo shares pass from the parent to arbitrageurs and active holders, not to passive holders. If the parent later does a **clean-up spin** of unexchanged SpinCo shares, the passive holders receive SpinCo pro rata and face the ordinary spin-off forced sale (next section).
7. **SpinCo float jumps.** Split-offs follow a carve-out IPO, so SpinCo's float goes from a minority stake to most of the company at settlement. Index eligibility changes (S&P IWF, Russell float-adjusted weight). That is a dated **buy** leg later, and it must be modelled with the sell legs, never alone.
8. **Retained stake is overhang.** Whatever the parent keeps is a dated supply: debt-for-equity exchanges with banks who sell immediately, registered secondaries, or a clean-up spin. The 10-K/10-Q and 8-Ks state the remaining stake; the register tracks it to zero.
9. **Parent shrinks.** Accepted parent shares are retired. Parent share count falls, parent index weight falls at the next share update, and non-tendering passive holders are briefly overweight. Small, but it is a dated leg and it is negative for the parent.

### Spin-off (pro rata distribution)

1. **Form 10 (`10-12B`) is the source document.** It carries the information statement, the distribution ratio, record date, distribution date, SpinCo capitalization (including any dividend to parent funded with SpinCo debt), and management equity. Nothing is `ranked` without it.
2. **When-issued trading** (parent WI, SpinCo WI, parent regular-way) runs for roughly one to two weeks before distribution. Record the window; it is where the market first prices the stub.
3. **Index treatment is provider-specific and dated.** Encode it from the methodology PDFs already in `_system/reference/index-effects/methodology/`, not from memory. The working reading is: S&P adds a constituent's spin-off to the parent's index at the distribution and may remove or move it after at least one regular-way session if it is ineligible for that index; FTSE Russell adds eligible spin-offs of members at the time of the spin and re-ranks at the next reconstitution. The forced sale is therefore a dated provider action with an announced effective date, which `index_membership.json` already knows how to carry as a `confirmed_event`.
4. **Mandate mismatch is the second seller.** Dividend funds when SpinCo pays none, large-cap funds when SpinCo is small, sector funds when SpinCo changes sector, and holders below an odd lot. The selling runs over the first one to three months (Greenblatt, Stahl, Horizon Kinetics). It is sized from the parent's holder base in `overlap_holdings.json`, with every unclassified holder counted as `n_a`, not as passive.
5. **The stub re-rates too.** The parent after distribution is a different security. Its contract must be rebuilt, not rolled forward. SpinCo loaded with debt routes to the `levered` lens, not `event`.
6. **Insider equity in SpinCo is the quality signal** (Greenblatt). Record it from Form 10 and the first Form 4s; it is a judgment input, never a value input.
7. **Size matters inversely.** Spin-offs small relative to the parent have the largest mandate mismatch and the least analyst coverage. `spinco_value_share_of_parent` is a required field.

### What flows may and may not do

- May: set the **payoff lens** to `event`, populate `event_window_end`, rank the desk, and open a research ticket.
- May: publish `expected_forced_supply` as % of float and days of ADV, with low/base/high tiers and a dated window, beside the contract.
- May not: change `intrinsic_value`, `margin_of_safety`, or `forward_return_at_price_pct`; set a stance; or trigger committee admission. They are question-5 evidence and question-6 timing.

## Proposed change (four layers)

### Operative

**New data directory `_system/data/separations/`** (warrants pattern, append-only):

| File | Content |
|---|---|
| `separation_registry.jsonl` | One versioned record per separation. `kind ∈ {split_off, spin_off, carve_out_ipo, clean_up_spin, retained_stake_sale, reverse_morris_trust}`; `parent_ticker`, `spinco_ticker` (null until listed), CIKs, `status ∈ {announced, filed, when_issued, offer_open, valuation_period, completed, withdrawn}`, dates, `terms` (ratio or formula, discount, upper_limit, odd_lot_priority, proration_estimate, record/distribution/expiration/settlement dates, spinco_debt_to_parent, insider_equity_pct, section_355_claimed), `sources[]` with accession and locator, `lifecycle`. |
| `separation_amendments.jsonl` | Superseding versions when terms change (extensions, final ratio). |
| `separation_events.jsonl` | Accession-locked EDGAR discoveries awaiting identity and terms work. |
| `separation_flows.jsonl` | Point-in-time flow model outputs per separation per run date. Never rewritten. |
| `separation_cohorts.jsonl` / `separation_outcomes.jsonl` / `separation_calibration.json` | Entry cohorts without hindsight, matured outcomes, descriptive calibration. |
| `README.md` | Same contract as `warrants/README.md`: no `ranked` row and no spread until identity and terms gates pass; calibration never changes weights. |

**New scripts** (all under `_system/scripts/`, each with a `test_*.py`):

- `separation_common.py`: schema, load/validate, gate state (`identity`, `terms`, `market`), date helpers.
- `refresh_separation_universe.py`: EDGAR full-text discovery modelled on `refresh_cvr_universe.py` `discover_sec_cvrs`. Forms `10-12B, 10-12B/A, S-4, S-4/A, 424B3, SC TO-I, SC TO-I/A, 8-K, 425`. Queries: `"exchange offer" AND ("split-off" OR "shares of common stock of")`, `"distribution ratio"`, `"information statement" AND "spin-off"`, `"when-issued"`. CIK → ticker through the existing resolver. Fail-soft, daily cap, consecutive-failure state like `discovery_state.json`.
- `split_off_terms.py`: pure arithmetic, no I/O. Inputs: formula terms plus parent and SpinCo closes. Outputs: `implied_ratio`, `upper_limit_binding`, `realized_discount_pct`, `odd_lot_payoff_per_99`, `annualized_spread_pct` (to settlement), `proration_scenarios` (low/base/high accepted fraction from the reference set until the final count is filed). Every output carries `basis: "filing_formula" | "final_filed"`.
- `separation_flow_impact.py`: legs, reusing `index_flow_impact.load_aum_registry`, float/ADV from `index_market_inputs.py`, and the same `n_a` discipline. Legs: `index_exclusion_sale`, `index_add_buy`, `mandate_mismatch_sale`, `arb_unwind_sale`, `unaccepted_parent_return`, `retained_stake_overhang`, `clean_up_distribution`, `parent_share_retirement`. Each leg has `window_start`, `window_end`, `shares_low/base/high`, `confidence`, `source`. Outputs per separation and per side (parent, SpinCo): `pct_of_float_{low,base,high}`, `pct_of_adv_days`, `window`, `legs[]`, `status`, `reason`. Pre-listing SpinCo ADV is `n_a`; a proxy from parent ADV × ratio × value share may be shown only with the asterisk convention the index lens already uses.
- `build_separations_dashboard.py` → `dashboard/data/separations.json` (lazy shard like `index_membership.json`). Also writes the `spin_off` / `split_off` rows into `{PARENT}/research/distribution_events.json` when `fair_value_per_parent_share` can be locked, so the total-return panel stops silently dropping them.
- `resolve_separation_outcomes.py`: at 5/21/63/126/252 sessions after distribution or settlement, SpinCo and parent returns vs SPY and vs each other, realized turnover in the window vs modelled supply, realized discount and proration for split-offs, odd-lot payoff realized.

**Changed scripts:**

- `build_special_situations.py`: add lane `{"id": "split_offs", "label": "Split-offs and exchange offers", "source": "Greenblatt"}`. `spinoff_rows()` and the new `split_off_rows()` read `separations.json` first; headline rows survive only as `discovery` with "Terms are not extracted". `ends` = settlement or distribution date; `annualized_spread` filled from `split_off_terms`; `forced_sellers` lane gains rows from `separation_flows` with the dated window and days of ADV. Fix the `\bspin\b` false positive: require an explicit spin-off cue and an entity match. Post-distribution rows must read "Orphan window" and carry `ends` = modelled window end.
- `build_index_membership.py` / `index_rules.json`: add `separation_policy` per index family (from the methodology PDFs, dated), consumed by `separation_flow_impact.index_exclusion_sale`. Fix the three defects found in the survey: per-index calendar event, expiring recon boost, and the `add` direction in `build_insights.py`.
- `download_us_investor_docs.py`: add `10-12B`, `10-12B/A`, `SC TO-I`, `424B3` to the forms list for tickers in the register.
- `filing_sentinel_taxonomy.json`: `transaction` category gains tags `separation_announced`, `exchange_offer`, `distribution_ratio`, `retained_stake`; `always_human_review_tags` unchanged.
- `onboard_ticker.py`: accept `--parent TICKER --separation-id ID` so a newly listed SpinCo is scaffolded with `registry.json` fields `parent_ticker`, `separation_id`, and `classification_inputs.payoff_lens: event` plus `event_window_end`.
- `ci_rebuild_profile.py`, `build_feed_status.py`, `graph_sources.json` (P6 feed window), and the lane declaration for the supervisor. An undeclared lane is invisible (see memory); declare it on day one.

**`valuation.json` block** (trigger, no new framework file):

```json
"separation": {
  "separation_id": "sep:jnj-kvue-2023",
  "role": "parent | spinco | stub",
  "kind": "split_off",
  "event_window_end": "2023-09-15",
  "flow_ref": "_system/data/separations/separation_flows.jsonl#<id>",
  "research_only": true, "in_base_irr": false, "authority": "none"
}
```

### Normative

Expand `_system/frameworks/special_situation_lens.md` with § Separations containing the axioms above, the field map, and three worked templates: parent pre-separation (event tree), SpinCo orphan window (dated payoff), split-off participant and odd-lot (dated payoff with proration case). No new file; the appendix is already the `payoff_lens: event` target.

`classification.md` trigger map gains one row: `separation` block present → `special_situation_lens.md § Separations`; mechanical `build_separations_dashboard.py` inside cloud refresh. `analysis_arsenal.md` Events & structure table gains one row (below). `.cursor/rules/investment-frameworks.mdc` mirrors the row.

Archetype vocabulary: add `special_situation` to the canonical list in `classification.md` and `graph_sources.json` `classification_vocab`. The router, the economic-value trigger and two power zones already use it; closing the gap removes the L4 violations instead of adding to them. Alternative if the owner prefers a closed list unchanged: map `special_situation` → `holding_co` in the router and drop it from `power_zones.json`. Decide before Phase 4.

Routing: `separation.role: parent` pre-completion → `catalyst_asset_value`, primary `probability_weighted_catalyst_nav` (completion, delay, withdrawal cases; break value = parent as is). `role: spinco` in the orphan window → `dated_future_payoff_per_share` with `payoff_date = event_window_end` and the SpinCo's own operating contract as the payoff basis once Form 10 financials are locked; `evidence_blocked` before that, never `price_stub` read as value. `role: stub` → rebuilt contract, not rolled forward. SpinCo with distribution-funded debt → `payoff_lens: levered`.

### Narrative

`deep_dive_structure.md`: when `separation` is set, section 2 (why the market might be wrong) must contain a **Who must sell** table: seller class, shares or % float, window, source, confidence. Section 6 risks must name the lens failure mode for separations: "orphan window mistaken for value; forced seller already done; stub re-rated on parent's old multiple." `report_prose.md` adds the three dates (record, distribution or expiration, settlement) to the exec summary when within 90 days.

### Adversarial

- `lint_deep_dive.py`: `payoff_lens: event` requires `event_window_end`; a `separation` block requires the Who-must-sell table; no `annualized_spread` in prose unless `split_off_terms.basis == filing_formula | final_filed`.
- `test_special_situations.py`: a split-off row never ranks without `terms.discount` and `terms.upper_limit`; a headline-only spin row stays in discovery; the GEV-class false positive is a regression test.
- `test_separation_flow_impact.py`: both sides modelled; pre-listing ADV is `n_a`; index exclusion leg requires a `separation_policy` entry; sum of legs reconciles to shares accepted or distributed.
- Graph: register `separations` as a P6 feed with its freshness window; typed falsifier kinds `separation_completes_by` and `flow_window_exhausted` in `falsifier_specs.py` so E1/E2 can score them.
- Milly prompt line: "A spread without a filed formula is a headline."

## Dashboard

- Special Situations desk: new `split_offs` lane; spinoff rows gain real end dates; forced-sellers rows gain days of ADV and a window bar. The detail row shows the legs the way Index Watch shows the flow bridge (`index-viz.js` L208-257), reused rather than redrawn.
- Holdings: if a held parent has an open exchange offer and any sleeve holds fewer than 100 shares, show an **odd-lot** badge with the payoff per 99 shares and the expiration. The badge opens a human ticket text; it never prefills an order.
- Ticker detail: a Separation card (role, kind, dates, window, expected supply) under the existing Index Watch cell; hidden when no `separation` block.
- Caption (required, like the index lens): "Forced selling is a research trigger and a timing input. It does not change intrinsic value, and the average post-spin excess return has compressed as the trade became known."

## Phases

| Phase | Scope | Exit check |
|---|---|---|
| 0. Hygiene (1 day) | Fix `\bspin\b` false positive and orphan-window labels; fix index calendar per index, expiring APLD boost, and the add direction in insights. | `special_situations.json` has no GEV row; APLD shows the S&P 400 date; tests green. |
| 1. Register and discovery (split-offs first) | `separations/` directory, `separation_common.py`, `refresh_separation_universe.py`, forms added to the downloader, sentinel tags, lane declaration, P6 feed. Backfill the reference set (Zoetis 2013, Synchrony 2015, Elanco 2019, Kenvue 2023) and the repo's own spin set (GEV, SOLV, VLTO, KVUE, SW, WBD, PSKY, HONA, FDXF, Ralliant, Vylor, Millrose, Versigent) by hand with accessions. | Every record has at least one accession; EDGAR search runs fail-soft in CI; `python _system/scripts/check_ib_gateway_registry.py --skip-mirrors --scan-ssi` unchanged. |
| 2. Split-off terms engine and lane | `split_off_terms.py`, `split_off_rows()`, odd-lot badge on held parents, `annualized_spread` filled. | Kenvue 2023 replays to the filed final ratio within rounding; odd-lot payoff matches the prospectus example; no spread shown without a formula. |
| 3. Flow model | `separation_flow_impact.py`, `separation_policy` in `index_rules.json` from the methodology PDFs, forced-sellers rows with windows, `separation_flows.jsonl`. | For each backfilled spin, modelled supply vs realized 20-session turnover is within the low/high band or carries a stated reason; Kenvue settlement-window SpinCo volume lies inside the arb-unwind band. |
| 4. Valuation and lens | § Separations in `special_situation_lens.md`; `separation` block; trigger rows; archetype decision; onboarding linkage; lint and deep-dive requirements; route one live parent and one live SpinCo through the pipeline. | `run_security_decision_pipeline.py --ticker <parent>` yields a `catalyst_asset_value` contract with an event tree; the SpinCo contract is `evidence_blocked` until Form 10 facts are locked; `lint_deep_dive.py` fails a dive that lacks the Who-must-sell table. |
| 5. Book integration | Flex corporate-action rows (spin receipts, exchange acceptances) parsed into the hub book; `distribution_events.json` `spin_off` rows for held parents; cost-basis allocation shown, human-reviewed. | A held parent that spins shows the SpinCo line with allocated basis; the total-return panel no longer drops the distribution. No Gateway contact; Flex over HTTPS only. |
| 6. Outcomes and calibration | Cohorts, `resolve_separation_outcomes.py`, calibration page, typed falsifiers. | First matured cohort graded; calibration is descriptive and changes no weight. |

Phases 0 to 3 are independent of the valuation work and can land first. Phase 5 depends on the Flex corporate-actions section being present in the report; confirm on NY4 before building.

## Risks of simplification

- Treating a split-off as a merger row (where it would land today through `SC TO-I`) gives the wrong next action and no spread. The separate lane is not duplication.
- Reusing index AUM tiers for mandate-mismatch legs overstates confidence; passive share per name does not exist. Every mandate leg is `estimate` or `n_a` until the 13F classification work lands, and the UI says so.
- % of float being a per-index constant in the index model carries over to the `index_exclusion_sale` leg. Rank by dollars and days of ADV, as the index lens already instructs.

## Redundancy we keep on purpose

Milly and lint on the Who-must-sell table; the 7-day staleness convention on quotes used in the spread; confirmed vs predicted distinction; "missing inputs skip the write" on the desk; human ticket for odd-lot action.

## Open questions for [HUMAN REVIEW]

1. Add `special_situation` to the canonical archetype list, or map it away? (Recommendation: add.)
2. Which live separations should seed the register first? The EDGAR search will find them, but a hand-picked set gets Phase 2 and 3 validation faster.
3. Odd-lot badge: show per sleeve (Drew, Michael) or book-wide? Per sleeve is the useful answer; it means the hub reads sleeve share counts from Flex, which it already does.
4. Is a Reverse Morris Trust (split-off plus merger) in scope for Phase 2 or deferred? It needs the merger lane's CVR-style terms work as well.

## Success criteria

- Agent read list for an `event` dive grows by one section of one existing file, not by a file.
- Zero flow numbers displayed without float, ADV, and a dated window; zero spreads displayed without a filed formula.
- Every row in the spinoffs and split-offs lanes has an end date or the label "Terms are not extracted" and sits in discovery.
- The register, the flows file, and the outcomes file are append-only and point-in-time; a re-run never rewrites a published row.
- The reference set replays: four split-offs to their filed ratios, the spin set to realized turnover inside the band or with a stated reason.

## Implementation scope

- [x] Docs (`special_situation_lens.md` § Separations, trigger rows, arsenal row, Cursor mirror)
- [x] Scripts (listed above, each with tests)
- [x] Data (`_system/data/separations/`, `index_rules.json` `separation_policy`, sentinel tags)
- [x] Dashboard (`special-situations-viz.js` lane, ticker card, odd-lot badge)
- [x] CI (lane declaration, P6 feed, rebuild profile, feed status)

## Arsenal row

| Tool | Trigger | Doc |
|------|---------|-----|
| Separations: split-off terms, spin-off orphan window, who-must-sell flow | `valuation.json` `separation` block, or `payoff_lens: event` with a parent or SpinCo role | `special_situation_lens.md` § Separations; `split_off_terms.py`, `separation_flow_impact.py`, `build_separations_dashboard.py` |

## Implementation record (2026-10-11)

| Piece | Where |
|---|---|
| Register, events, flows, cohorts, outcomes, calibration | `_system/data/separations/` (schema in its README); `separation_common.py` |
| Split-off terms engine | `split_off_terms.py` (+ `test_split_off_terms.py`) |
| Flow legs | `separation_flow_impact.py` (+ test); policy in `index_rules.json` `separation_policy` |
| EDGAR discovery (fail-soft) | `refresh_separation_universe.py`; health in `check_separation_universe.py` |
| Builders | `build_separation_flows.py`, `build_separations_dashboard.py` (quotes, odd-lot alerts, forced rows, per-ticker attach, distribution events), `resolve_separation_outcomes.py` |
| Desk | `build_special_situations.py`: `split_offs` lane, register-backed spinoffs, forced-seller rows from flows, headline-only rows demoted to discovery, bare "spin" false positive fixed |
| Dashboard | `separations-viz.js`, `special-situations-viz.js`, `index.html` (lane, route, ticker card, odd-lot badge) |
| Index hygiene | per-index calendar event, expiring recon boost, insight direction from modelled flow |
| Docs and lint | `special_situation_lens.md` § Separations; trigger rows in `classification.md` and the Cursor mirror; `special_situation` archetype canonical; `lint_deep_dive.py` separation checks |
| Plumbing | `separation-discover` job, lane and P6 feed registry, rebuild profile, feed status, downloader forms, sentinel tags, onboarding flags, router hint, Flex `corporate_actions`, falsifier adapter |

Seeded: Medtronic/MiniMed 2026 (live), Pfizer/Zoetis 2013, GE/Synchrony 2015, Lilly/Elanco 2019, J&J/Kenvue 2023, and ten Form 10 spin-offs (GEV, SOLV, VLTO, HONA, FDXF, RAL, VYLR, Versigent, MFP, ADIG). First matured outcomes: split-off SpinCo median excess return about -7% at 21 sessions and -13% at 63 (n=4), realized volume in the first 21 sessions about half the modelled arb unwind.
