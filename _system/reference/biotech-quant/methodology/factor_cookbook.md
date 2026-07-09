# Biotech quant factor cookbook (Marvin)

Operational notes for builders. Source of truth for weights: `../FACTOR_SPEC.json`.

## Universe gate

A ticker enters biotech quant UI / composite only if
`memory_common.is_biotech_quant_universe_ticker()` is true:

1. ≥1 specialist 13F record, and
2. biotech sleeve / watchlist / company name **or** biotech-like 13F issuer name.

Portfolio megacaps (AMZN, GOOGL, NVDA, …) stay out unless explicitly classified.

## Live factors

| Factor | Builder | Output keys |
|--------|---------|-------------|
| specialist_consensus | `build_specialist_13f_signals.py` | consensus_score, specialist_holder_count, consensus_quintile, convergence_flag |
| spend_value | `build_biotech_spend_value.py` | spend_value, spend_value_quintile |
| insider_non_ceo | `build_biotech_insider_scores.py` | insider_score, insider_buy_count_90d |
| composite | `build_biotech_composite.py` | composite_score → valuation.json `biotech_overlay` |

## Stub factors

| Factor | Status | Notes |
|--------|--------|-------|
| peer_momentum | stub | Needs ClinicalTrials.gov profiles |
| short_interest | stub | Needs approved SI/borrow feed |

## Rebuild

```bash
make biotech-quant-lib
make specialist-13f-ingest   # or biotech-spend / biotech-insider
make research-memory
```
