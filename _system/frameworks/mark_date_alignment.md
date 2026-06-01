# Mark date alignment (fair value vs market quotes)

**Purpose:** When a filing reports **fair value** for a listed stake, crypto treasury, or fund look-through slice, every comparison to a **market price** must use the **same measurement date** as the filing (or the last exchange session on or before `period_end`). Using a **later** quote to back into share counts or to claim "already marked" is a **factual error**.

**Applies to:** `current_book_estimate.py`, holdco SOTP (`yield_curve`), MIAX/MIH uplift tables, crypto treasury marks, any `filing_price` in `valuation.json`.

---

## Two dates (never conflate)

| Label | Meaning | Example (FRMO Q3 FY2026) |
|-------|---------|----------------------------|
| **Filing measurement date** | Last trading session on or before `period_end` used for GAAP fair value | **2026-02-27** (Feb 28, 2026 was Saturday) |
| **Current / price-today date** | Quote used for roll-forward or `price today` in IRR | Stooq/Yahoo close on report refresh date |

**Rule:** `filing_price` and `filing_value` are a **pair** as of measurement date. `current_price` is as of `as_of`. Deltas = same share count × (current − filing).

---

## Forbidden pattern (FRMO MIAX example)

**Wrong:** FRMO fair value **$13,917,000** (Feb 28, 2026 quarterly) ÷ MIAX **$51.42** (Stooq **2026-05-22**) → 270,563 shares.

**Why wrong:** $51.42 is ~**three months after** quarter-end. MIAX last sale before period-end was **~$42.60** (2026-02-27). Implied shares at filing � **326,700**, not 270,563.

**Correct for filing tie-out:**

```
filing_measurement_date = 2026-02-27
MIAX close on measurement date     ≈ $42.60
implied_shares = 13,917,000 ÷ 42.60 ≈ 326,690
filing_fair_value_check = 326,690 × 42.60 ≈ $13.9M  ✓
```

**Correct for current book roll-forward:**

```
delta_m = 326,690 × (current_MIAX − 42.60) ÷ 1e6
```

**Correct for SOTP uplift (Year-5 path):** Sub-piece A uses **326,690 shares** (or filing value directly), filing reference **$42.60 on 2026-02-27**, Year-5 price **$60** as **[Assumption]** — not May-22 as "today's mark."

---

## Measurement date rules

1. **`period_end` from filing** → compute `measurement_date` = last US equity session on or before that calendar date (NYSE calendar; skip weekends + listed holidays when script has calendar).
2. **`filing_price`** = official close (or fund NAV) on `measurement_date`. Source: Yahoo chart API, exchange close, or filing text — cite in ledger.
3. **`price today`** for parent stock (FRMO OTC) is **independent** — always label with its own date.
4. **Crypto (CMSG):** use coin USD price on `period_end` (or filing table fair value ÷ units). CoinGecko historical or filing table.
5. **Implied shares:** only compute `filing_value ÷ filing_price` when both are on **measurement_date**. Flag if implied shares disagree with disclosed count >5%.

---

## JSON / config fields

In `book_estimate_config.json` and `valuation.json` sotp lines:

| Field | Required |
|-------|----------|
| `filing_anchor.period_end` | Yes |
| `filing_anchor.measurement_date` | Yes (auto or manual) |
| `filing_price` | Close on measurement_date |
| `filing_price_source` | e.g. `Yahoo MIAX 2026-02-27` |
| `current_price` / `current_price_date` | Set by script on refresh |

---

## Deep dive / IRR ledger requirements

When a row cites **fair value** and a **listed price**:

| # | Assumption | Value | Source |
|---|------------|-------|--------|
| … | MIAX price at filing measurement date | **$42.60** | Yahoo MIAX 2026-02-27; FRMO `2026-02-28_Quarterly_Report.pdf` Note 4 |
| … | MIAX implied shares (check) | **~326,700** | $13,917,000 ÷ $42.60 |
| … | MIAX price today (sensitivity only) | **$XX** | Stooq/Yahoo {refresh date} |

**Do not** label a post-quarter quote as "filing" or "fair value at quarter-end."

---

## Script enforcement

`current_book_estimate.py`:

- Resolves `measurement_date` from `period_end`
- Fetches `filing_price` on measurement date when `filing_price_auto: true` or validates manual price
- Emits `price_alignment[]` warnings when manual `filing_price` differs >2% from fetched
- Stores `filing_price_date` and `current_price_date` on every line in `book_estimate.json`

**Never** use a quote dated **after** `period_end` as the filing mark (see MIAX example in this file).

`lint_deep_dive.py` (when `book_estimate_config.json` exists):

- Requires `### Current book value estimate` section
- Warns if dive cites MIAX/TPL `filing_price` with a date after `period_end`

---

## Milly

| Check | Severity |
|-------|----------|
| Share count derived from fair value using price dated **after** `period_end` | **Factual error** |
| "Already marked to market" claim using wrong measurement date | **Factual error** |
| Missing measurement date on fair-value / listed-stake row | Warning |

---

## Related

- `current_book_estimate.md` — roll-forward model
- `irr_assumption_ledger.md` — source column must include quote date
- `lawrence_irr.md` § F — holdco SOTP arithmetic
