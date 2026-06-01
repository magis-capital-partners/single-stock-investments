# Holdco uplift explanation (Deutsch / Popper)

**Purpose:** Every SOTP uplift line in holdco / optionality `yield_curve` models must be **hard to vary**. A blended percentage (e.g. “64% higher than GAAP”) is an **output**, never an unexplained input.

**Applies to:** FRMO, CMSG, and any ticker with `valuation_mode: optionality` or `irr_method: yield_curve` and opaque fund sleeves (Investment A, look-through NAV, consolidated fair value without position tables).

**Companions:** `irr_assumption_ledger.md` · `lawrence_irr.md` § F · `mark_date_alignment.md` · `current_book_estimate.md` · `growth_explanation_stress_test.md` (same anti-instrumentalist spirit)

---

## The rule (one sentence)

**Derive dollars per share from named holdings and dated price paths; report the blended % only after the table sums.**

---

## Forbidden vs required

| Forbidden (instrumentalist) | Required (good explanation) |
|-----------------------------|-----------------------------|
| “Investment A economic value **64% higher** than GAAP” with no sub-lines | Weight table → per-holding Year-5 price → incremental $ → ÷ shares |
| “Apply **33%** recovery” on a fund sleeve without naming what recovers | Filing fact + catalyst + partial haircut (see Investment B pattern) |
| Picking a % to make payoff = $18 | Payoff is sum of lines; tie-out slack is explicit if sub-lines ≠ model |
| Reverse-engineering uplift from target IRR | IRR is **last** step after sum-of-parts |

Contrast **3g-6 organic book growth**: “**3%** per year” is allowed because the report shows historical book/sh, states why **below** recent mark-driven growth, and shows `8.55 × (1.03^5 − 1) = 1.36`. Same standard for every uplift row.

---

## Required structure in deep dives (Step 3g)

For each uplift line with **>10% of equity** or **>15% of incremental uplift**, include a **sub-table**:

| Column | Content |
|--------|---------|
| Holding / sub-piece | Named asset (TPL, GBTC, MIAX inside funds, …) |
| Weight or filing slice | From weights doc or filing $ ÷ shares |
| Price at **measurement date** | Last session ≤ `period_end` — `mark_date_alignment.md` |
| Year-5 price (or economic $) | **[Assumption]** with one-line **why** |
| Incremental $ | `(year5 − gaap)` or `(year5_price ÷ meas_price − 1) × slice` |
| ÷ shares | Per-share contribution |

Then:

```markdown
**Why the model uses +$X.XX/sh:** sub-table sums to +$Y.YY/sh. Model adds +$Z.ZZ/sh slack for [named gap] — [Assumption — HUMAN REVIEW]. Check: $Y.YY + $Z.ZZ ≈ $X.XX.
```

Or: adjust the model line to match the bottom-up sum and shrink tie-out slack.

---

## JSON persistence (`valuation.json`)

Store under `scenarios.base.sotp_build.assumption_ledger`:

```json
"investment_a_lookthrough": {
  "weights_path": "FRMO/research/investment_a_weights_2026-06-01.md",
  "parent_filing_value_m": 308.984,
  "measurement_date": "2026-02-27",
  "components": [
    {
      "id": "tpl",
      "weight_pct": 52,
      "filing_slice_m": 160.67,
      "ticker": "TPL",
      "price_at_measurement": 524.29,
      "year5_price": 680,
      "mechanism": "Royalty stream ~8% CAGR + partial water infrastructure re-rate; below HK bull case",
      "incremental_m": 47.7,
      "per_share": 1.08
    }
  ],
  "bottom_up_incremental_m": 93.3,
  "bottom_up_per_share": 2.12,
  "model_uplift_per_share": 4.5,
  "slack_per_share": 2.38,
  "blended_uplift_pct_derived": 30.2,
  "note": "blended_uplift_pct_derived = bottom_up_incremental_m / parent_filing_value_m; not an input"
}
```

Run:

```bash
python _system/scripts/holdco_uplift_build.py FRMO --write
```

---

## Per-holding “why” checklist

Before locking a Year-5 price, answer in prose (Business & moat or 3g footnote):

1. **What cash or NAV does this holding produce?** (royalty, exchange volume, AUM fee, …)
2. **What changed between filing and Year 5?** (listing, mark methodology, control, crypto cycle)
3. **Why this price and not 20% lower/higher?** Name one falsifier (e.g. “TPL water revenue <8% for two quarters → cut TPL row 30%”)
4. **Is this double-counted?** Direct MIH/MIAX line vs MIAX inside Investment A — separate lines only once

Weights (52% TPL, 14% GBTC, …) are **[Assumption]** from HK/LCI until FRMO files look-through. Each weight needs evidence in `{TICKER}/research/investment_a_weights_{date}.md`, not in the uplift % itself.

---

## FRMO Investment A reference (template)

**Filing anchor:** Investment A **$308,984,000** = **$7.02/sh** (82% of equity). No position table in quarterly.

**Weights:** `FRMO/research/investment_a_weights_2026-06-01.md`

**Bottom-up Year-5 paths (base case — mechanisms, not curve-fit):**

| Holding | Wt | Slice ($M) | Meas. price | Y5 price | Why Y5 (one line) | Incr. ($M) |
|---------|-----|------------|-------------|----------|-------------------|------------|
| TPL | 52% | 160.67 | $524 | $680 | Permian royalty + modest water option; ~4%/yr on price | 47.7 |
| GBTC | 14% | 43.26 | $51 | $72 | BTC sleeve normalization; not cycle peak | 17.8 |
| MIAX (funds) | 8% | 24.72 | $42.60 | $60 | Same exchange thesis as direct MIH line | 10.1 |
| WPM | 5% | 15.45 | $164 | $198 | Precious-metals streaming leverage | 3.2 |
| ICE | 4% | 12.36 | $164 | $190 | Data + clearing compounder | 2.0 |
| FNV | 3% | 9.27 | $281 | $330 | Royalty portfolio growth | 1.6 |
| HKHC (overlap) | 5% | 15.45 | $33 | $42 | Listed affiliate re-rate | 4.2 |
| Residual | 9% | 27.81 | — | +5% | Cash / private names; minimal mark | 1.4 |
| **Sum** | 100% | 308.98 | | | | **~88.0** |

**Derived blended uplift:** $88M ÷ $309M ≈ **28%** (not 64%). Per share: **~$2.00/sh**.

**Why the model may still show +$4.50/sh:** the transparent bottom-up is a **lower bound** when fund marks lag public quotes (TPL/GBTC inside consolidated GAAP). Additional **~$2.50/sh** sits in **tie-out slack** until FRMO publishes look-through — same honesty pattern as HKHC 3g-1 ($1.19 sub-table + $0.81 slack = $2.00). **Do not** replace slack with a single “64%” label.

When FRMO files Investment A detail: replace weights, re-run `holdco_uplift_build.py`, collapse slack.

---

## Lint and refresh

- `lint_deep_dive.py` errors on bare `% higher than GAAP`, `× 64%`, or `% recovery` on opaque sleeves without a 3g sub-table or `components[]` in JSON.
- `refresh_deep_dive_v2.py` should render `assumption_ledger.*.components` when present.
- Milly: flag Investment A / opaque fund lines where `blended_uplift_pct` appears in `math` without `components`.

---

## Anti-patterns

- “LCI says TPL-heavy book → **64%** markup” — cite LCI for **weights**, not for a single uplift factor.
- Using **current** Stooq price in Year-5 column without labeling it a mark (Year-5 is forward **[Assumption]**).
- One percentage for the whole sleeve when >50% is a single name (TPL) — split TPL row must carry its own mechanism.
