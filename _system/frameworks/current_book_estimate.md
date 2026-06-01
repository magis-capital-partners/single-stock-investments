# Current book value estimate (mark-to-market roll-forward)

**Purpose:** For **holding companies** and **treasury-heavy optionality** names where reports cite **premium or discount to book value per share**, maintain a **current best estimate of book value** that rolls forward from the last official quarterly filing. Compare that estimate to **filed GAAP book** and to **price today**.

**Separate from:** Lawrence IRR, SOTP catalyst payoffs (`yield_curve`), and fair-value NAV overlays (`nav_overlay`). This model answers: *"If we re-marked the balance sheet today, what would book per share be?"*

**Canonical tickers today:** FRMO, CMSG (extend to other holdcos / BTC treasuries as needed).

---

## When to use

| Trigger | Examples |
|---------|----------|
| Stance uses **price vs book** discount | FRMO ~22% below $8.55 filed book |
| **Mark-to-market** assets dominate equity | CMSG crypto treasury; FRMO Investment A |
| **Nested listed holdings** moved since quarter-end | FRMO → Investment A → TPL; FRMO → MIAX, HKHC |
| **`optionality_gate.floor_metric` = book_per_share** | FRMO pattern |

Do **not** replace `nav_overlay` fair-value floors (TPL assigned land at $0) with this model. Use **filed book** as anchor here; economic SOTP stays in catalyst / overlay layers.

---

## Two book numbers (always show both)

| Field | Meaning |
|-------|---------|
| **Filed book per share** | GAAP stockholders' equity ÷ shares from **last official quarterly or annual** report |
| **Current book estimate per share** | Filed book **plus** sum of line-item mark adjustments through **today** |

Reports must state both and the **delta**:

- `delta_per_share = current_estimate − filed_book`
- `delta_pct = delta_per_share ÷ filed_book`
- `price_vs_filed_book_discount_pct = (filed_book − price) ÷ filed_book`
- `price_vs_current_book_discount_pct = (current_estimate − price) ÷ current_estimate`

Use **current book estimate** for "where are we trading vs economic book **today**"; use **filed book** when citing the official filing anchor.

---

## Roll-forward math

**Anchor (from filing):**

```
filed_book_equity = stockholders' equity (correct scope: parent-only vs consolidated)
filed_book_per_share = filed_book_equity ÷ shares_outstanding
```

**Adjustments (disjoint markable lines only — no double count):**

For each line `i` in `book_estimate_config.json`:

| Method | Filing value | Current value | Delta |
|--------|--------------|---------------|-------|
| `static` | `filing_value_m` | same | 0 |
| `listed_shares` | `shares × filing_price` | `shares × current_price` | current − filing |
| `crypto_units` | `units × filing_unit_price` | `units × current_unit_price` | current − filing |
| `fund_weight_proxy` | `parent_fv × weight × 1` | `parent_fv × weight × (current_price ÷ filing_price)` | per holding, summed |
| `ownership_market_value` | carrying or `pct × mcap_filing` | `pct × mcap_current` | current − filing carrying |
| `manual_price` | `shares × filing_price` | `shares × manual_current_price` | current − filing |

**Best estimate:**

```
current_book_equity_m = filed_book_equity_m + Σ line_delta_m
current_book_per_share = current_book_equity_m × 1e6 ÷ shares
```

**Static remainder:** Lines not explicitly marked stay at filing value. Config should tie out: markable lines + documented static bucket ≈ total equity.

---

## File layout

| File | Role |
|------|------|
| `{TICKER}/research/book_estimate_config.json` | Human-maintained: filing anchor, line items, look-through weights, `[HUMAN REVIEW]` notes |
| `{TICKER}/research/book_estimate.json` | Script output: live prices, deltas, discount table |
| `{TICKER}/research/valuation.json` → `book_estimate` | Optional mirror of summary fields after `--write` |

**Refresh:**

```bash
python _system/scripts/current_book_estimate.py FRMO --write
python _system/scripts/current_book_estimate.py CMSG --write
make book-estimate TICKER=FRMO
```

Runs automatically in `marvin_cloud_refresh.py` when config exists.

---

## Config schema (summary)

```json
{
  "ticker": "FRMO",
  "enabled": true,
  "filing_anchor": {
    "period_end": "2026-02-28",
    "source": "investor-documents/ir-frmo/2026-02-28_Quarterly_Report.pdf",
    "scope": "frmo_attributable",
    "book_equity_m": 376.704,
    "shares": 44022781
  },
  "lines": [
    {
      "id": "mih_miax",
      "label": "MIH / MIAX direct stake",
      "method": "listed_shares",
      "symbol": "MIAX.US",
      "shares": 270563,
      "filing_price": 51.42,
      "filing_value_m": 13.917,
      "source": "2026-02-28_Quarterly_Report.pdf Note 4"
    },
    {
      "id": "investment_a_tpl",
      "label": "Investment A — TPL look-through (weight proxy)",
      "method": "fund_weight_proxy",
      "parent_filing_value_m": 308.984,
      "weight_pct": 35,
      "symbol": "TPL.US",
      "filing_price": 380.0,
      "source": "[HUMAN REVIEW] LCI/Stahl concentration; confirm when Investment A table filed"
    }
  ]
}
```

---

## Deep dive prose (required section when config exists)

In **Valuation & IRR**, after the assumption ledger bridge, add:

### Current book value estimate (mark-to-market)

1. **Filed book** — period, source PDF, $/sh.
2. **Adjustment table** — each line: filing $, current $, delta $, delta $/sh, price source.
3. **Current best estimate** — $/sh and change vs filing.
4. **Price comparison** — discount to filed book **and** discount to current estimate.
5. **Staleness / gaps** — any `[HUMAN REVIEW]` line, missing quotes, or opaque fund residual.

Do not bury this inside SOTP catalyst math; it is a **parallel cross-check** for holdco discount framing.

---

## Nested holdings (FRMO → TPL example)

When parent holds a fund (Investment A) that holds a listed stock:

1. Record **parent fund filing fair value** (`parent_filing_value_m`).
2. For each known look-through name, set **`weight_pct`** of that fund (must document source or `[HUMAN REVIEW]`).
3. Script applies `fund_weight_proxy`: only the weighted slice moves with the child quote.
4. **Residual weight** stays at filing marks until look-through table is filed.

When `{CHILD}/research/book_estimate.json` exists, cite child current book in parent footnotes; do not chain-compute automatically unless config references `lookthrough_ticker`.

---

## Milly checks

| Check | Severity |
|-------|----------|
| Report cites book discount but no `book_estimate.json` refresh within 14 days | Warning |
| Filed book in dive ≠ `filing_anchor` in config | Factual error |
| Markable lines double-count Investment A total **and** look-through slices | Factual error |
| `price_vs_current_book_discount_pct` used in exec summary but estimate stale | Warning |

---

## Related frameworks

- `optionality_valuation.md` — holdco flywheel (FRMO); floor vs SOTP
- `archetype_valuation_prose.md` — `holding_co` discount framing
- `option_treatment.md` — do not confuse GAAP book floor with fair NAV (TPL land)
