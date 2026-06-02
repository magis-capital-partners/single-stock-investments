# Market inputs freshness

See `_system/proposals/valuation_evidence_pipeline_plan_2026-06-02.md`. Mandatory: refresh commodity spot within **7 days** via `fetch_market_inputs.py`; store `as_of`, `source`, `fetched_at` in `market_inputs.json`. Milly checks `market_inputs_freshness` per `MILLY.md` §2f.
