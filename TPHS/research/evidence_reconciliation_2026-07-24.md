# TPHS — Evidence reconciliation (contract backfill)

**Date:** 2026-07-24  
**Agent:** Marvin (cloud contract backfill)  
**Evidence hash:** `16994b53bed24323859ebb60163d3c57a27f2f6d9f06f91b1dba48bd2619797f` // pragma: allowlist secret  
**Prior contract status:** evidence_blocked (four legacy_sensitivity components)  
**Target:** decision_grade universal valuation contract with valid calculation_proof graphs

## Summary

Closed all four universal contract blockers by attaching deterministic calculation_proof graphs to every additive component in `valuation.json`. Component ranges reconcile to primary IR press releases and the February 2025 Steel Partners stock purchase agreement. No human capital decision was introduced.

## Component proofs

| Component | Method | Proof base ($/sh) | Legacy base ($/sh) | Primary source |
|-----------|--------|-------------------|--------------------|----------------|
| cash_and_working_capital | net_asset_value@1.0 | ~0.0008 → 0.00 | 0.00 | Q1 2026 press release: cash $54k / 64.95M shares |
| ip_licensing_stub | owner_cash_or_dividend_discount@1.0 | 0.01 | 0.01 | FY2025 other income $239k capitalized on residual IP |
| nol_shell_option | probability_weighted_catalyst_nav@1.0 | 0.04 | 0.04 | Federal NOL ~$329.9M face; risked shell utility only |
| steel_note_and_deficit_reserve | net_asset_value@1.0 | -0.01 | -0.01 | Steel note $1.372M secured; stockholders' deficit $1.534M |

**Proof-backed component base sum:** ~$0.04/sh (cash rounds to zero at two decimals).  
**Market price (2026-07-17):** $0.023/sh.  
**Dated payoff stance gate:** $0.045/sh in five years (~14.4% per year), unchanged.

## Facts (filing-backed)

- Cash and cash equivalents: **$54 thousand** at March 31, 2026 (`3-31-26-TPHS-Financials-Press-Release-v5.14.26.pdf`).
- Shares outstanding: **64,947,266** at March 31, 2026 (same source).
- FY2025 other income (IP licensing): **$239 thousand** (`12-31-25-TPHS-Financials-Press-Release-BW-v3.31.26.pdf`).
- Federal NOL carryforward: **~$329.9 million** with full valuation allowance at March 31, 2026 (Q1 release).
- Steel Promissory Note to Steel Connect LLC: **$1.372 million** outstanding, secured by all assets (Q1 release).
- Stockholders' deficit: **$1.534 million** (~-$0.024/sh book) at March 31, 2026 (Q1 release).
- Steel IP Investments LLC purchased **25,862,245 shares (~40%)** for $2,586,200 on February 5, 2025 (`8-K_20250205...`).

## Inferences

- Face NOL is an option to a taxpaying acquirer, not equity NAV; the proof caps base shell utility at **$0.04/sh**, not NOL face divided by shares.
- The Steel note sits ahead of common in any wind-down; the reserve component nets senior-claim risk without double-counting the NOL option.
- Cash per share (~$0.0008) is immaterial at two-decimal rounding; G&A (~$126k/quarter) can exhaust cash before any shell transaction (falsifier).

## Open items ([HUMAN REVIEW])

- Confirm OTC Pink closing price against OTC Markets (aggregator $0.023 used).
- Download and reconcile FY2025 10-K and 2025-2026 10-Qs once filed on EDGAR.
- No disclosed Steel Partners plan to use the NOL shell; base/bull remain analyst assumptions.

## Falsifiers (monitoring)

1. Cash exhausted by G&A before any shell transaction.
2. IP income goes to zero with no replacement revenue.
3. Going-private / Form 15 / note foreclosure leaves minority common near zero.
4. Note conversion or foreclosure extinguishes common ahead of shell payoff.
