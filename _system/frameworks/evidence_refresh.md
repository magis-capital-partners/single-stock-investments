# Evidence refresh (`valuation.json`)

Mechanical post-`marvin_valuation.py` overlays driven by config (not ticker-specific scripts).

## When to use

| Situation | Set in `valuation.json` |
|-----------|-------------------------|
| Mineral / land optionality with commodity-linked royalty | `evidence_refresh.type: commodity_nav` |
| Fresh spot required within 7 days | `market_inputs` + `fetch_market_inputs.py` |
| Economic floor ≠ GAAP book | `nav_overlay` + `optionality_gate.floor_metric: nav_per_share` |

## `commodity_nav` schema (example: KEWL)

```json
"evidence_refresh": {
  "type": "commodity_nav",
  "commodity": "copper",
  "royalty_usd_at_ref_lb": {"amount": 7700000, "ref_lb": 4.0, "source": "SSI"},
  "probability_pct": 35,
  "lease_annual_usd": 365000,
  "lease_cap_multiple": 10,
  "acreage_uplift_per_share": 1.0,
  "cash_floor_per_share": 3.6,
  "base_payoff": 30,
  "bear_payoff": 14,
  "horizon_years": 7,
  "payoff_lens": "asset"
}
```

## Pipeline order

1. `fetch_market_inputs.py {TICKER} --merge`
2. `marvin_valuation.py --write`
3. `refresh_optionality_valuation.py {TICKER}` (reads `evidence_refresh`)
4. `refresh_deep_dive_v2.py`
5. `check_evidence_completeness.py` (strict when config present)

Unified entry: `marvin_cloud_refresh.py` · batch: `batch_portfolio_refresh.py`.

## OTC filing facts

When XBRL/IX tags are absent, `filing_facts.py` runs `parse_otc_prose_metrics()` on full-tier `_text/` extracts (shares, acres, lease income regex). Preserves prior metrics if parse returns empty.
