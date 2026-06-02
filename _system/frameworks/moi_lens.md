# Manual of Ideas — pointer

**MOI content lives in three places:**

1. **Required core:** `_system/frameworks/decision_stack.md` — six orthogonal questions (Q5 = why mispriced)  
2. **Comprehensive evaluation rules:** `_system/frameworks/moi_company_evaluation.md` — full Ch 1–10 checklist  
3. **Triggered toolkit:** `_system/frameworks/analysis_arsenal.md` — MOI chapters as triggered tools  

**Wisdom:** `_system/reference/investment-wisdom/mihaljevic/` (`Manual-of-Ideas-full-text.txt` after EPUB install)

Do not read this file for a separate MOI workflow. Use it for legacy field mapping and MOI-specific failure-mode examples.

---

## Payoff lens (use this, not 10 moi_buckets)

| `payoff_lens` | Legacy `moi_bucket` examples |
|---------------|------------------------------|
| `operating` | `compounder_core`, `good_cheap`, `jockey` |
| `asset` | `sotp_hidden`, `deep_value` |
| `event` | `special_situation`, `small_cap_inflection` |
| `levered` | `equity_stub` |
| `pending` | unset |

Set `classification_inputs.payoff_lens` in `valuation.json`. Sync writes Classification footer.

`moi_bucket` remains optional for portfolio audit; prefer `payoff_lens` for new work.

---

## Q5 sub-answers (when lens ≠ operating)

| Sub-question | When required |
|--------------|---------------|
| Inefficiency source | `asset` or `event` |
| Catalyst + timeline | `asset` or `event` |
| Annualized return | `event` with dated catalyst |
| Discount vs price | `asset` with NAV/SOTP |

Margin of safety = Q3 (dhando + floor). Do not restate as a third MOI table.

---

## Lens failure mode — examples by lens

| Lens | Example failure mode |
|------|----------------------|
| `asset` | Over-sliced SOTP; smart-money crowding; buy-ten-get-one-free discount |
| `event` | No mechanical seller; niche crowded; ignoring time in return |
| `levered` | Idiosyncratic failure; point IRR; wrong-side of debt structure |
| `operating` | Transitory ROC; no reinvestment runway (good+cheap misuse) |

Discovery-only: clone without verify, illiquid micro-cap — log in `decision_log.md`.

---

## Appendix docs (triggered — not mandatory reads)

| Doc | Open when |
|-----|-----------|
| `idea_funnel.md` | Onboard / watchlist |
| `special_situation_lens.md` | `payoff_lens == event` |
| `equity_stub_valuation.md` | `payoff_lens == levered` |
