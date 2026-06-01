# Special Situation Lens (MOI Ch 8)

**Trigger:** `moi_bucket == special_situation` OR spinoff / index / dividend / rights / distressed seller in thesis.

**Source:** Mihaljevic, *Manual of Ideas* Ch 8; Stahl spinoffs (`stahl/Stahl-Spinoffs-Going-Separate-Ways-2015.pdf`).

---

## Definition

Equities whose **near- to medium-term** return is largely **independent of broad market beta** — event, mechanical selling, or bounded recovery drives price.

Not buy-and-hold forever: successful situations **end**; capital recycles.

---

## Inefficiency registry

Name the driver in "Why the market might be wrong" and Classification optional field `moi_inefficiency`:

| Inefficiency | Mechanism | HK / Marvin hook |
|--------------|-----------|------------------|
| `index_deletion` | Index funds must sell | `market_structure_discount` |
| `dividend_cancellation` | Income funds sell | `transitory_problem` |
| `tax_loss_selling` | Calendar Q4 | daily scan |
| `spinoff` | Orphan + index + complexity | Stahl; news tag `spinoff` |
| `rights_offering` | Complexity discount | — |
| `growth_disappointment` | Fear overshoot | Hohn reversion |
| `distressed_seller` | Non-fundamental flow | — |
| `high_fear` / `high_greed` | Behavioral | Munger psychology |

If **no** identifiable inefficiency, higher probability the valuation has a flaw — re-check work.

---

## Required analysis

| Item | Rule |
|------|------|
| MOI three questions | All three; **path to value creation** mandatory |
| **Annualized return** | Report alongside absolute $ upside (time matters) |
| Catalyst timeline | Dated where possible |
| Uses & misuses | Passive event-driven ≠ passive index; niche crowding lowers edge |

---

## Annualized return (plain English)

For dated catalysts:

```
Annualized return ≈ (Payoff / Price)^(1/years) − 1
```

State in Payoff & return and assumption ledger when `irr_method` is `yield_curve` or `scenario`.

---

## Portfolio news alignment

`portfolio_news_common.py` tags: `spinoff`, etc. — cross-check filing when news triggers refresh.

---

## Decision diary

Event-driven names: log entry/exit thesis in `decision_log.md` when situation resolves.
