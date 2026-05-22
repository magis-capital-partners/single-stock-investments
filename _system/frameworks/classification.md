# Holdings classification (Munger / Pabrai / Stahl)

Replace the old single **thesis status** (intact / weakening / strengthening / unclear) with four independent axes plus an optional cycle tag for croupiers.

## Fields

| Field | Lens | Values | Question answered |
|-------|------|--------|-------------------|
| **Archetype** | Stahl | `croupier`, `compounder`, `serial_acquirer`, `platform`, `holding_co`, `optionality`, `turnaround`, `infrastructure` | What *is* this business in the pecuniary economy? |
| **Moat** | Munger | `widening`, `stable`, `eroding`, `unproven`, `n/a` | Is competitive advantage durable? |
| **Dhando** | Pabrai | `full`, `partial`, `none`, `pending` | Heads I win, tails I don't lose much? |
| **Stance** | Pabrai | `core`, `accumulate`, `hold`, `watch`, `trim`, `exit` | What do we *do* with capital? |
| **Cycle** | Stahl (croupiers) | `peak`, `mid`, `trough`, `—` | Normalized earnings vs current activity |

## Source of truth

- Portfolio map: `_system/portfolio/classification.json`
- Per-ticker copy: `{TICKER}/research/thesis.md` → `## Classification` table
- Dashboard: parsed by `_system/scripts/build_dashboard_data.py`

## Report footer (replaces thesis status)

Every deep dive and thesis update ends with:

```markdown
## Classification

| Field | Value |
|-------|-------|
| **Archetype** (Stahl) | … |
| **Moat** (Munger) | … |
| **Dhando** (Pabrai) | … |
| **Stance** | … |
| **Cycle** | … |

## [HUMAN REVIEW]
…

## [PROPOSED MEMORY]
…
```

## Dashboard display

- **Table column:** Archetype (primary badge)
- **Detail panel:** Moat · Dhando · Stance (+ Cycle when not `—`)
