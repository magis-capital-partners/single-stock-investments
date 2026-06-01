# Total synthesis IRR (capstone)

**Purpose:** The **last analytical block** in every deep dive combines **all** evidence into one weighted return estimate. Filings, growth theory, segment/NAV overlays, third-party cross-checks, competition, and qualitative moat/dhando judgments feed a single **Total synthesis IRR** and **Returns statement (synthesis)**.

**Placement:** `## Valuation & IRR (assumption ledger)` → **`### Total synthesis IRR (all sources)`** after growth stress test + segment build + IRR arithmetic; **before** Classification footer.

**Companions:** `external_view_blend.md` · `third_party_cross_reference.md` · `growth_explanation_stress_test.md` · `irr_assumption_ledger.md`

---

## What gets combined

| Input type | Typical source | Synthesis row |
|------------|----------------|---------------|
| **Filings (10-K/10-Q)** | Falsifier-adjusted Lawrence path | Primary cash-flow return |
| **Segment build** | `segment_build` reverse DCF | Segment-implied return |
| **Bear / bull** | `scenarios` | Downside / upside stress |
| **NAV / optionality** | `nav_overlay`, option scan | Dated-payoff or option-weighted path |
| **Third party (HK, Substacks, PDFs)** | `cross_check_*.md`, inventory | Numeric proxy or qualitative adjustment |
| **Competition / moat** | Business & moat section | Qualitative ±pp adjustment |
| **Governance / cycle** | Risks, proxy, LCI notes | Qualitative ±pp adjustment |

**Rule:** Nothing cited in the dive's source inventory may be ignored. If a source has no numeric return, it appears as a **qualitative adjustment** with explicit ± basis points and rationale.

---

## Weighting (default heuristics)

| Path | Default weight | Notes |
|------|----------------|-------|
| Filing falsifier-adjusted | 30% | Marvin floor from primary docs |
| Segment implied | 20% | When `segment_build` exists |
| Bull scenario | 12% | Upside stress |
| Bear scenario | 5% | Downside stress |
| HK / approved third party | 10% | Use cross-check synthesis or bull proxy |
| Substacks (SSI/LCI) | 8% | Topic-weighted qualitative |
| NAV / optionality overlay | 10% | When `nav_overlay` complete |
| Competition / moat | 5% | Qualitative only |

Weights renormalize to 100%. Override per ticker in `valuation.json` → `synthesis.paths[]`.

---

## Formula

1. **Numeric paths:** weighted average of all rows with `return_pct` (10-year comparable).
2. **Qualitative adjustments:** sum of documented ±pp (cap **±3pp** total without **[HUMAN REVIEW]**).
3. **Total synthesis IRR** = numeric weighted average + qualitative adjustments.

Store in `valuation.json`:

```json
"synthesis": {
  "status": "complete",
  "paths": [ { "id", "label", "source", "return_pct", "weight", "type" } ],
  "qualitative_adjustments": [ { "factor", "pp", "rationale", "sources" } ],
  "numeric_weighted_pct": -0.9,
  "qualitative_pp": 0.4,
  "total_synthesis_pct": -0.5,
  "human_approval": "pending"
}
```

When `synthesis.status === complete`, **`implied_return.base_pct`** and executive summary use **`total_synthesis_pct`**. Filing-only falsifier-adjusted remains in `implied_return.falsifier_adjusted_pct` for audit.

---

## Human approval

You promote third-party **approved** status in `third_party_sources.md`. Synthesis still **includes** context-tier HK/Substacks with documented weights; mark `synthesis.human_approval: pending` until you sign off on weights and qualitative pp.

---

## Report template (required)

```markdown
### Total synthesis IRR (all sources)

| # | Source / lens | Type | Return (10yr) | Weight | Role in synthesis |
|---|---------------|------|---------------|--------|-------------------|

#### Qualitative adjustments (competition, moat, governance)

| Factor | ±pp | Rationale | Sources |

#### Synthesis arithmetic

1. Numeric weighted return: …
2. Qualitative adjustments: …
3. **Total synthesis IRR: X% per year**

**Returns statement (synthesis):** …
```

This block is the **authoritative** return for Classification stance when synthesis is complete.
