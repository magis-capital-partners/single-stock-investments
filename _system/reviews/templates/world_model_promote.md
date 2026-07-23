# World Model promotion — {{TICKER}} ({{date}})

**Status:** pending human approval  
**Hard rule:** Even after approval, promote only into listed ledger rows / falsifiers / `context_overlay` weights. **Never** silent-edit `implied_return`.

## What broke or converged

| Signal | Detail |
|--------|--------|
| KPI fails | |
| Superorg gaps | |
| Horizon convergence | |
| Industry checklist | |

## Paths allowed to edit (human fills)

- [ ] `{TICKER}/research/kpi_ledger.json` — expected gates / notes only
- [ ] `valuation.json` → `growth_explanation.falsifiers` (or equivalent)
- [ ] `valuation.json` → `context_overlay` weights / notes (`in_base_irr` stays false unless checked below)
- [ ] Assumption ledger markdown row (cite filing + World Model as context)

## Explicitly forbidden without separate review

- [ ] `inputs` growth rates used in base IRR
- [ ] `scenarios.*.payoff`
- [ ] `implied_return.base_pct`

## Approval

| Field | Value |
|-------|-------|
| Reviewer | |
| Approved at | |
| `in_base_irr` promote? | no / yes (rare) |
| Notes | |

After approval, agent sets:

```json
"world_model_context": {
  "promotion": {
    "approved_at": "YYYY-MM-DD",
    "reviewer": "name",
    "paths": ["..."]
  }
}
```
