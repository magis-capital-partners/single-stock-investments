# Growth explanation (internal JSON — not in deep dives)

**Status:** Optional enrichment in `valuation.json` only. **Do not** render Popper/Deutsch subsections, Deutsch check tables, weight-scheme falsifier tables, or valuation-bridge overlay rows in `{TICKER}/research/deep_dive_*.md`.

**Where growth reasoning lives in reports:**
- **Business & moat** — operating mechanism in plain English
- **Assumption ledger** — growth rows with filing path or **[Assumption]**
- **Payoff & return** — one sentence on what would break the growth path

**Primary IRR:** Lawrence `scenarios.base` → `implied_return.base_pct` (same as executive summary).

**Companions:** `irr_assumption_ledger.md` · `decision_stack.md` · `report_prose.md`

---

## Optional `valuation.json` block

When Marvin runs `marvin_valuation.py --write`, `growth_explanation` may be populated for segment-derived growth checks and falsifier scripts. This stays in JSON; it is **not** copied into markdown.

```bash
python3 _system/scripts/check_growth_falsifiers.py --ticker {TICKER} --write
```

---

## Removed from reports (2026-06-01)

The following are **deprecated in deep-dive markdown** (refresh script no longer generates them):

| Removed block | Reason |
|---------------|--------|
| `### Valuation bridge` with Theory-implied, Falsifier-adjusted, Lawrence legacy, Segment sum, Segment implied | Duplicate of ledger + JSON scenarios |
| `### Growth explanation stress test (Popper / Deutsch)` | Bloat; mechanism belongs in Business & moat |
| Risky predictions / Falsifiers / Ad hoc rescue tables | Same |
| Deutsch checks (Hard to vary, Reach, Falsifiable, Not instrumentalist) | Same |
| Weight-scheme falsifiers (Popper) / Why these weights | Same |

Philosophy references remain in `_system/reference/philosophy/deutsch-popper/` for human study — not mandatory report sections.

---

## Milly (light touch)

| Check | Severity |
|-------|----------|
| Growth rows in ledger with no filing or **[Assumption]** cite | **Inference risk** |
| Growth > filing run-rate + 300 bp with no mechanism in Business & moat | **Inference risk** |
| Instrumentalist-only defense ("market prices X") with no operating story | **Inference risk** |

YAML: `growth_explanation: n/a` (default for new dives; JSON block optional).

---

## Anti-patterns

- Historical CAGR as sole justification — state mechanism in Business & moat
- Reverse-DCF smuggle — growth chosen to hit 15% IRR with no operating story
- Re-adding valuation bridge overlay rows or Popper/Deutsch subsections after refresh
