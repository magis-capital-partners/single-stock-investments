# Separations data

Split-offs, spin-offs, carve-out IPOs, clean-up distributions, retained-stake
sales and Reverse Morris Trusts. Proposal:
`_system/proposals/split_offs_spin_offs_and_selling_flows_2026-10-09.md`.
Shared code: `_system/scripts/separation_common.py`.

This directory separates immutable filing terms from mutable model output,
the way `_system/data/warrants/` does.

| File | Content | Mutability |
|---|---|---|
| `separation_registry.jsonl` | One versioned record per separation (schema below). | Append-only |
| `separation_amendments.jsonl` | Superseding versions (`version` + 1) when terms change: extensions, the final ratio, the accepted share count. | Append-only |
| `separation_events.jsonl` | Accession-locked EDGAR discoveries awaiting identity and terms work. | Append-only; `status` may move `unreviewed -> linked / dismissed` through a new row |
| `separation_flows.jsonl` | Flow-model output per separation, per side, per run date. | Append-only, point in time |
| `separation_cohorts.jsonl` | Entry cohorts captured at settlement or distribution without hindsight. | Append-only |
| `separation_outcomes.jsonl` | Matured 5/21/63/126/252-session outcomes. | Append-only |
| `separation_calibration.json` | Descriptive calibration. Changes no weight. | Rewritten by `resolve_separation_outcomes.py` |
| `discovery_state.json` | EDGAR collector health and consecutive-failure streak. | Rewritten by `refresh_separation_universe.py` |

No row is `ranked` and no spread is shown until the identity gate and the terms
gate pass (`separation_common.gate_state`). A headline is never a term.

## Registry record

```json
{
  "separation_id": "sep:jnj-kvue-2023",
  "version": 1,
  "recorded_at": "2026-10-11T00:00:00Z",
  "kind": "split_off",
  "market": "US",
  "parent_ticker": "JNJ", "parent_cik": "0000200406",
  "spinco_ticker": "KVUE", "spinco_cik": "0001944048", "spinco_name": "Kenvue Inc.",
  "status": "completed",
  "lifecycle": "closed",
  "dates": {
    "announced": null, "filed": null, "record": null, "when_issued_start": null,
    "distribution": null, "offer_launch": null,
    "valuation_period_start": null, "valuation_period_end": null,
    "expiration": null, "settlement": null, "clean_up_distribution": null
  },
  "terms": {
    "distribution_ratio": null,
    "exchange": {
      "discount_pct": 7.0, "upper_limit_ratio": 8.0525,
      "odd_lot_priority": true, "odd_lot_max_shares": 99,
      "valuation_sessions": 3,
      "final_ratio": null, "parent_shares_tendered": null,
      "parent_shares_accepted": null, "proration_factor": null,
      "spinco_shares_offered": null
    },
    "spinco_value_share_of_parent_pct": null,
    "spinco_debt_to_parent_usd": null,
    "insider_equity_pct": null,
    "section_355_claimed": null,
    "retained_stake_pct": null,
    "retained_stake_disposal_deadline": null,
    "spinco_index_eligibility_after": [],
    "mandate_mismatch_pct_override": null
  },
  "sources": [
    {"form": "SC TO-I", "accession": "0001193125-23-000000", "url": "https://www.sec.gov/...",
     "filed": "2023-07-24", "locator": "Exchange ratio formula and upper limit"}
  ],
  "notes": ""
}
```

Enums: `kind` in `split_off | spin_off | carve_out_ipo | clean_up_spin |
retained_stake_sale | reverse_morris_trust`; `status` in `announced | filed |
when_issued | offer_open | valuation_period | completed | withdrawn`;
`lifecycle` in `candidate | active | closed`.

Every number in `terms` comes from a filing named in `sources`. Estimates live
in the flow file with a `confidence`, never in the registry.

## Event record (discovery)

```json
{"event_id": "sepev:...", "discovered_at": "...", "cik": "0000200406", "entity_name": "...",
 "ticker": "JNJ", "form": "SC TO-I", "accession": "...", "filed": "2023-07-24", "url": "...",
 "query_family": "split_off_exchange", "kind_hint": "split_off",
 "status": "unreviewed", "separation_id": null}
```

## Flow record

```json
{"flow_id": "sepflow:...", "separation_id": "sep:...", "run_date": "2026-10-11",
 "model_version": "separation-flow-v1", "side": "spinco", "ticker": "KVUE",
 "status": "ok", "reason": null, "float_flag": "float_adj",
 "pct_of_float_low": -2.1, "pct_of_float_base": -3.4, "pct_of_float_high": -4.9,
 "pct_of_adv_days": 1.8, "net_shares_base": -51000000, "net_flow_usd_base": -1.1e9,
 "window_start": "2023-08-23", "window_end": "2023-09-08",
 "legs": [
   {"leg": "arb_unwind_sale", "direction": "sell", "shares_low": 0, "shares_base": 0, "shares_high": 0,
    "pct_of_float_base": -3.4, "window_start": "...", "window_end": "...",
    "confidence": "estimate", "source": "parent_shares_accepted x final_ratio x arb_share", "reason": null}
 ],
 "research_only": true, "in_base_irr": false, "authority": "none"}
```

Legs: `index_exclusion_sale`, `index_add_buy`, `mandate_mismatch_sale`,
`arb_unwind_sale`, `unaccepted_parent_return`, `retained_stake_overhang`,
`clean_up_distribution`, `parent_share_retirement`. Sell legs are negative.
A leg whose inputs are missing is emitted with `confidence: "n_a"` and a
`reason`, never with an invented share count. Both sides of every event are
modelled.

## Dashboard payload (`dashboard/data/separations.json`)

```json
{"schema_version": "separations.v1", "generated_at": "...", "caption": "...",
 "research_only": true, "in_base_irr": false, "authority": "none",
 "counts": {"ranked": 0, "discovery": 0, "closed": 0, "by_kind": {}},
 "rows": [{
   "separation_id": "...", "kind": "split_off", "status": "offer_open", "lifecycle": "active",
   "parent_ticker": "JNJ", "spinco_ticker": "KVUE", "spinco_name": "Kenvue Inc.",
   "dates": {}, "ends": "2023-08-23", "ends_label": "Settlement 2023-08-23",
   "gates": {"identity": {"pass": true, "missing": []}, "terms": {"pass": true, "missing": []}, "status": "ranked"},
   "terms_summary": "Exchange at a 7% discount, upper limit 8.0525, odd-lot priority, three-session valuation period.",
   "spread": null,
   "flows": {"parent": null, "spinco": null},
   "sources": [], "next": "...", "notes": ""
 }],
 "by_ticker": {"JNJ": ["sep:..."]},
 "odd_lot_alerts": [{"separation_id": "...", "parent_ticker": "JNJ", "owner": "drew", "qty": 60,
                     "eligible": true, "max_shares": 99, "gain_usd": 0.0, "gain_pct": 0.0, "expiration": "..."}],
 "forced_seller_rows": [{"separation_id": "...", "ticker": "KVUE", "side": "spinco", "what": "...",
                         "window_start": "...", "window_end": "...", "pct_of_float_base": -3.4,
                         "pct_of_adv_days": 1.8, "confidence": "estimate"}],
 "discovery_events": [{"event_id": "sepev:...", "entity_name": "...", "ticker": null, "form": "10-12B/A",
                       "accession": "...", "filed": "...", "url": "...", "kind_hint": "spin_off"}],
 "ticker_attach": {"JNJ": {"roles": [], "odd_lot": {"eligible_owners": [], "expiration": null}}},
 "outcomes_summary": {"matured": 0, "by_horizon": {}},
 "health": {"status": "healthy", "structural_errors": [], "problems": [], "stale_terms": []}}
```

`health.status` is never `unhealthy` when the feed is fine; the P6 feed registry
asserts `health.status not_in [unhealthy]` and `health.structural_errors` empty.

`spread` (split-offs only, when quotes exist):

```json
{"basis": "filing_formula", "as_of": "2026-10-11", "parent_price": 0.0, "spinco_price": 0.0,
 "implied_ratio": 0.0, "upper_limit_binding": false, "realized_discount_pct": 0.0,
 "days_to_settlement": 0, "annualized_spread_pct": 0.0,
 "odd_lot_payoff_per_99": {"gain_usd": 0.0, "gain_pct": 0.0},
 "proration": {"low": 0.15, "base": 0.25, "high": 0.40, "basis": "reference_set"},
 "holder_expected_gain_pct": {"low": 0.0, "base": 0.0, "high": 0.0}}
```

Per-ticker attach in `core.json` / ticker shards (`row.separation`):

```json
{"roles": [{"separation_id": "...", "role": "parent", "kind": "split_off", "status": "offer_open",
            "counterparty": "KVUE", "ends": "...", "ends_label": "...",
            "flow": {"pct_of_float_base": -3.4, "pct_of_adv_days": 1.8, "window_end": "..."}}],
 "odd_lot": {"eligible_owners": ["drew"], "expiration": "..."}}
```

Do not edit the JSONL files by hand except to seed the registry with filing
accessions. Run `python _system/scripts/check_separation_universe.py` after
any edit.
