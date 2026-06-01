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

## Popper / Deutsch — why these weights (not arbitrary)

A weighted IRR is itself a **conjecture**: “these independent lenses, combined in these proportions, best estimate ten-year return.” Without an explicit weight theory, the blend is **unfalsifiable curve-fitting** (Popper) or a **bad explanation** (Deutsch: easy to vary, no testable claim).

### Epistemic tiers (default)

| Tier | Paths | Default raw weight | Why |
|------|-------|-------------------|-----|
| **A — primary falsifiable** | Filing falsifier-adjusted | 30% | 10-K/10-Q anchor + growth mechanism + falsifier runner; highest refutation reach |
| **B — independent derivation** | Segment reverse DCF, theory-implied | 20% / 8% | Same filings, different math; cross-check, not replacement |
| **C — scenario envelope** | Bear / bull | 5% / 12% | Sensitivity probes, not competing base theories; bull > bear for optionality skew |
| **D — alternate / external** | NAV overlay, third party | 10% / 10% each | **Different question** (asset payoff) or **context tier** until human approval; capped |

**Rule:** Weights encode **evidence quality**, not a desired IRR. If reweighting would flip stance without new filing facts, the scheme is instrumentalist → **[HUMAN REVIEW]**.

### Weight-scheme falsifiers (required in dive)

Document in `#### Why these weights (Popper / Deutsch)`:

1. **Double-count:** Segment implied ≈ filing path → combined A+B weight too high
2. **Theory conflation:** NAV payoff weighted like cash-flow IRR
3. **Instrumentalist proxy:** Third-party row uses bull scenario when cross-check says no IRR upgrade
4. **Qualitative overlap:** ±pp for moat/dhando already inside segment multiples or filing growth

### Deutsch gate (synthesis block)

| Check | Requirement |
|-------|-------------|
| Hard to vary | Each weight tied to tier + source type, not “felt right” |
| Falsifiable | Each path lists observations that force weight cut |
| Not instrumentalist | No path chosen to move synthesis toward a narrative |
| Reach | Weights explain *why* beyond the single ticker price |

Spec mirrors `growth_explanation_stress_test.md` but applies to the **blend**, not growth rate alone.

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
