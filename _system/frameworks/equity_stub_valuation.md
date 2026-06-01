# Equity Stub Valuation (MOI Ch 9)

**Trigger:** `moi_bucket == equity_stub` OR net debt / market cap > 2, debt/equity > 2–3, interest coverage weak.

**Source:** Mihaljevic, *Manual of Ideas* Ch 9.

High judgment. Win rate on any single name may be **<50%** with lopsided payoffs.

---

## Do not use Lawrence `full` 10yr FCF

Force `irr_method: scenario` in `valuation.json`. Probability-weighted bear / base / bull.

---

## Required fields

| Field | Question |
|-------|----------|
| Leverage nature | Recourse vs **non-recourse** — market often ignores non-recourse |
| Debt ownership | **Who owns the debt?** |
| Distress type | Prefer **industry-wide** selloff vs idiosyncratic failure |
| Management alignment | Common equity vesting |
| Range of outcomes | Distribution, not point IRR |
| Position size | De minimis until thesis tested |

---

## Stance

Default **`watch`** unless `dhando` is `partial` with explicit asset floor and named recovery path.

Cap stance at `accumulate` without human override in `[HUMAN REVIEW]`.

---

## Uses & misuses

| Uses | Misuses |
|------|---------|
| Industry depression; non-recourse debt mispriced | Company-specific terminal failure |
| Management aligned via equity | Overconfidence after one win |
| Asymmetric payoff vs price | Point estimate ignores tail risk |

---

## Process

Commit thesis to paper; review in `decision_log.md`. Focus on **process**, not single outcomes (MOI Ch 9).
