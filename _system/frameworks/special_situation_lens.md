# Special Situation Lens

**Appendix — trigger:** `payoff_lens == event`, or a `separation` block in `valuation.json` (§ Separations below).

**Core Q5** already requires inefficiency + catalyst in prose. This doc adds event-specific tools.

## Inefficiency types

`index_deletion`, `dividend_cancellation`, `tax_loss_selling`, `spinoff`, `split_off`, `rights_offering`, `growth_disappointment`, `distressed_seller`, behavioral fear/greed.

Map to HK predictive attributes where applicable: tag list in `mental_models.md` § Predictive attribute tag; plain-English prompts in `report_prose.md` § Horizon Kinetics norms; full toolkit index in `analysis_arsenal.md`.

## Event-specific rules

- **Dated end is a field, not prose.** `payoff_lens: event` requires `classification_inputs.event_window_end` or `separation.event_window_end` (ISO date). Lint: "event lens without a dated end" (warning for dives dated before 2026-10-11, error after).
- **Annualized return** when catalyst is dated. Never annualize a present value.
- Situation **ends** — log exit in `decision_log.md`
- Cross-ref `portfolio_news` spinoff tags; a headline is never a term
- **Lens failure mode** (Risks): value trap without catalyst; stale catalyst date; for separations see § Separations

Source: MOI Ch 8; Stahl spinoffs PDF.

## Separations

Split-offs (exchange offers), spin-offs (pro rata distributions), carve-out IPOs, clean-up distributions, retained-stake sales, Reverse Morris Trusts. Register and flow model: `_system/data/separations/README.md`; proposal `_system/proposals/split_offs_spin_offs_and_selling_flows_2026-10-09.md`. Every axiom below names the field, flow leg, or lint that enforces it. Terms come from filings in `sources[]`; estimates live in `separation_flows.jsonl` with a `confidence`.

### Split-off axioms (exchange offer)

1. **An offer, not a distribution.** Parent offers SpinCo shares for parent shares; holders choose. Forms: parent `SC TO-I`, SpinCo `S-4` + `424B3`, 8-Ks both sides. Tender period at least 20 business days. Record four dates. Fields: `dates.offer_launch`, `dates.valuation_period_start/end`, `dates.expiration`, `dates.settlement`.
2. **The ratio is a formula until the valuation period closes.** `ratio = parent_vwap x (1 + discount) / spinco_vwap`, capped at the upper limit. US practice: about 7% discount (Pfizer/Zoetis 2013, GE/Synchrony 2015, Lilly/Elanco 2019, J&J/Kenvue 2023). When the cap binds the realized discount shrinks or goes negative and the offer usually extends two sessions. Fields: `terms.exchange.discount_pct`, `terms.exchange.upper_limit_ratio`, `terms.exchange.final_ratio`; `spread.basis in {filing_formula, final_filed}`. Lint: "spread without a filed formula".
3. **Proration is the base case.** A discount guarantees oversubscription; accepted fractions in the reference set were well under half. The headline spread is the odd-lot spread, not the holder's. Fields: `terms.exchange.proration_factor`, `spread.proration.{low,base,high}` (`basis: reference_set` until the final count is filed).
4. **Odd-lot priority is the retail edge.** Holders of fewer than 100 parent shares who tender all are not prorated. Payoff per 99 = discount on 99 parent shares less friction. Per-account fact: dashboard flags a held parent (`odd_lot_alerts`); acting is a human ticket. Fields: `terms.exchange.odd_lot_priority`, `odd_lot_max_shares`, `spread.odd_lot_payoff_per_99`.
5. **Who sells, and when.** During the offer arbs buy parent and short SpinCo (borrow tightens, SpinCo pressured). At settlement arbs receive SpinCo and sell to cover; unaccepted parent shares return and are sold. Dated wave: start = settlement, length a few sessions to a few weeks, size bounded above by shares accepted. Legs: `arb_unwind_sale` (SpinCo), `unaccepted_parent_return` (parent).
6. **Index funds in the parent's index do not tender.** They cannot hold a non-benchmark security, so SpinCo passes to arbs and active holders. A later clean-up spin hands passive holders SpinCo pro rata and triggers the ordinary spin-off forced sale. Leg: `clean_up_distribution`; field `dates.clean_up_distribution`.
7. **SpinCo float jumps.** Split-offs follow a carve-out IPO; float goes from a minority stake to most of the company at settlement, and index eligibility changes. A dated **buy** leg, modelled with the sell legs, never alone. Leg: `index_add_buy`; field `terms.spinco_index_eligibility_after[]`.
8. **Retained stake is overhang.** Whatever the parent keeps is dated supply (debt-for-equity exchanges, registered secondaries, clean-up spin). Track to zero from 10-K/10-Q/8-K. Leg: `retained_stake_overhang`; fields `terms.retained_stake_pct`, `terms.retained_stake_disposal_deadline`.
9. **Parent shrinks.** Accepted shares are retired; parent weight falls at the next share update; non-tendering passive holders are briefly overweight. Small, dated, negative for the parent. Leg: `parent_share_retirement`; field `terms.exchange.parent_shares_accepted`.

### Spin-off axioms (pro rata distribution)

1. **Form 10 (`10-12B`) is the source document.** Distribution ratio, record and distribution dates, SpinCo capitalization (including any dividend to parent funded with SpinCo debt), management equity. Nothing is `ranked` without it. Fields: `terms.distribution_ratio`, `dates.record`, `dates.distribution`, `terms.spinco_debt_to_parent_usd`; gate `separation_common.gate_state`.
2. **When-issued trading** (parent WI, SpinCo WI, parent regular-way) runs one to two weeks before distribution and is where the market first prices the stub. Field: `dates.when_issued_start`.
3. **Index treatment is provider-specific and dated.** Encode from `_system/reference/index-effects/methodology/`, not memory. Working reading: S&P adds a member's spin-off at distribution and may remove or move it after at least one regular-way session if ineligible; FTSE Russell adds eligible spin-offs at the spin and re-ranks at the next reconstitution. Leg: `index_exclusion_sale`, which requires an `index_rules.json` `separation_policy` entry; the provider action is a `confirmed_event` in `index_membership.json`.
4. **Mandate mismatch is the second seller.** Dividend funds (SpinCo pays none), large-cap funds (SpinCo is small), sector funds (sector changes), sub-odd-lot holders. Runs over the first one to three months (Greenblatt, Stahl, HK). Sized from the parent's holder base in `overlap_holdings.json`; every unclassified holder is `n_a`, never passive. Leg: `mandate_mismatch_sale`; override `terms.mandate_mismatch_pct_override`.
5. **The stub re-rates too.** The parent after distribution is a different security: rebuild its contract, do not roll it forward. SpinCo loaded with distribution-funded debt routes to `payoff_lens: levered`, not `event`. Routing: `role: stub`; `terms.spinco_debt_to_parent_usd`.
6. **Insider equity in SpinCo is the quality signal** (Greenblatt). From Form 10 and the first Form 4s. Judgment input, never a value input. Field: `terms.insider_equity_pct`.
7. **Size matters inversely.** Small spins relative to the parent carry the largest mandate mismatch and the least coverage. Required field: `terms.spinco_value_share_of_parent_pct`.

### Field map: `valuation.json` `separation` block

```json
"separation": {
  "separation_id": "sep:jnj-kvue-2023",
  "role": "parent | spinco | stub",
  "kind": "split_off | spin_off | carve_out_ipo | clean_up_spin | retained_stake_sale | reverse_morris_trust",
  "event_window_end": "2023-09-15",
  "flow_ref": "_system/data/separations/separation_flows.jsonl#<flow_id>",
  "spread_basis": "filing_formula | final_filed | null",
  "research_only": true, "in_base_irr": false, "authority": "none"
}
```

| Field | Meaning |
|-------|---------|
| `separation_id` | Key into `separation_registry.jsonl`; one block per role the ticker plays |
| `role` | `parent` before completion; `spinco` from listing through the orphan window; `stub` for the parent after distribution or settlement |
| `kind` | Registry enum; drives which axioms and legs apply |
| `event_window_end` | Settlement (split-off) or modelled orphan-window end (spin-off). The dated end the event lens needs; lint reads it here or in `classification_inputs` |
| `flow_ref` | Point-in-time flow record behind the Who-must-sell table |
| `spread_basis` | Required before any annualized spread appears in prose; `null` means no spread may be shown |
| `research_only` / `in_base_irr` / `authority` | Always `true` / `false` / `none`. Flows are question-5 evidence and question-6 timing, never value |

### Routing

| Role and state | Zone | Method | Note |
|----------------|------|--------|------|
| `parent`, pre-completion | `catalyst_asset_value` | `probability_weighted_catalyst_nav` | Event tree: completion, delay, withdrawal. Break value = parent as is |
| `spinco`, orphan window | `catalyst_asset_value` | `dated_future_payoff_per_share`, `payoff_date = event_window_end` | Payoff basis = SpinCo's own operating contract once Form 10 facts are locked. Before that `evidence_blocked`; a `price_stub` is never read as value |
| `stub`, post-event | Rebuilt contract | Per the stub's own archetype | Never rolled forward from the parent |
| `spinco` with distribution-funded debt | `levered` lens | `equity_stub_valuation.md` scenarios | Not `event` |

Archetype `special_situation` is canonical (`classification.md`, `graph_sources.json` L4); a dive carrying it needs `#### Catalyst path`.

### What flows may and may not do

- May: set `payoff_lens: event`, populate `event_window_end`, rank the desk, open a research ticket.
- May: publish `expected_forced_supply` as % of float and days of ADV, low/base/high, with a dated window, beside the contract.
- May not: change `intrinsic_value`, `margin_of_safety`, or `forward_return_at_price_pct`; set a stance; trigger committee admission.
- Never invent float, ADV, AUM, or terms. Missing inputs give `n_a` and a `reason`, and the UI says so. Pre-listing SpinCo ADV is `n_a`; a parent-ADV proxy carries the asterisk convention from the index lens.

### Who must sell (required table)

When `separation` is set, `## Why the market might be wrong` carries a `#### Who must sell` table. One row per leg, both sides of the event. Confidence is `filed`, `estimate`, or `n_a`; `n_a` rows stay in the table with the reason in the source column.

```markdown
#### Who must sell

| Seller class | Shares or % float | Window | Source | Confidence |
|--------------|-------------------|--------|--------|------------|
| Arbitrageurs unwinding (SpinCo) | 3.4% of float / 1.8 days ADV | 2023-08-23 to 2023-09-08 | parent_shares_accepted x final_ratio x arb share (flow sepflow:...) | estimate |
| Index funds, S&P 500 exclusion (SpinCo) | n_a | after first regular-way session | no separation_policy entry yet | n_a |
```

### Worked templates

**1. Parent, pre-separation (event tree).** Route `catalyst_asset_value` / `probability_weighted_catalyst_nav`. Branches: completes on schedule (parent ex-SpinCo plus SpinCo value per parent share at the filed ratio); delays (same payoff, later date, carry cost); withdrawn (break value = parent as is, less announcement premium). Probabilities from the filing stage (`status`): announced < filed < when_issued or offer_open. Dates from the register; `event_window_end` = distribution or settlement. Who-must-sell: `parent_share_retirement`, `unaccepted_parent_return`. Lens failure mode: break value assumed equal to today's price.

**2. SpinCo, orphan window (dated payoff).** Route `catalyst_asset_value` / `dated_future_payoff_per_share`, `payoff_date = event_window_end` (modelled window end from `separation_flows`). Payoff basis = SpinCo operating contract from Form 10 financials; until those facts are locked the contract is `evidence_blocked` and the dive says so. Who-must-sell: `index_exclusion_sale` (dated provider action), `mandate_mismatch_sale` (one to three months), `retained_stake_overhang`, `index_add_buy` when eligibility arrives. Insider equity and `spinco_value_share_of_parent_pct` in Business & moat. Lens failure mode: orphan window mistaken for value; the forced seller already done.

**3. Split-off participant and odd-lot (dated payoff with proration).** Route `dated_future_payoff_per_share`, `payoff_date = settlement`. Inputs: filed formula, upper limit, valuation period, `spread_basis`. Holder payoff = discount x accepted fraction (low/base/high from `spread.proration`) less SpinCo price risk between valuation period and settlement. Odd-lot payoff = `odd_lot_payoff_per_99` with no proration case. Show the annualized spread only with `spread_basis` set; label the holder's spread and the odd-lot spread separately. Who-must-sell: `arb_unwind_sale`, `unaccepted_parent_return`, later `clean_up_distribution`. Any tender is a human ticket. Lens failure mode: upper limit binds and the discount vanishes; spread quoted off a headline ratio.

### Separation lens failure modes (Risks section)

Name at least one: orphan window mistaken for value; forced seller already done; stub re-rated on the parent's old multiple; upper limit binding; spread without a filed formula.

### Lint (`lint_deep_dive.py`)

| Check | Severity |
|-------|----------|
| `payoff_lens: event` without `event_window_end` (either location) | warning before 2026-10-11, error after |
| `separation` block without `#### Who must sell` | error |
| Annualized spread with a percent in prose and no `separation.spread_basis in {filing_formula, final_filed}` | error |
| Archetype `special_situation` without `#### Catalyst path` | error |

Milly line: a spread without a filed formula is a headline.

Sources: Stahl, *Spinoffs: Going Separate Ways*; Horizon Kinetics spin-off compendia (`investment-wisdom/horizon-kinetics/pdfs/`); MOI Ch 8; Greenblatt; `_system/reference/index-effects/SYNTHESIS.md` and the provider methodology PDFs.
