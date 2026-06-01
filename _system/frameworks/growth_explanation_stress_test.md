# Growth explanation stress test (Popper / Deutsch)

**Purpose:** Every **cash-flow growth rate** in a Lawrence model is a **conjecture** about how the business works. Before accepting it in the assumption ledger, Marvin must **stress-test the explanatory theory** behind the number: state it clearly, derive risky predictions, and document what would **falsify** it.

**Companions:** `irr_assumption_ledger.md` · `option_treatment.md` · `decision_stack.md` · `report_prose.md`

**Philosophy sources:** `_system/reference/philosophy/deutsch-popper/INDEX.md`

---

## Why this exists

A growth assumption such as "11% per year years 1–5" is not a fact from filings. It is a **theory** about:

- Which causal mechanisms will drive owner cash (volume, price, mix, capex normalization, segment shift)
- Over what horizon those mechanisms dominate
- What would have to be true in the world for that rate to be **approximately** right

Without an explicit theory, growth rates become **unfalsifiable curve-fitting** — the Popperian hallmark of bad science.

David Deutsch extends Popper: progress comes from **good explanations** (hard to vary, testable, reach beyond the data used to invent them). A growth rate tied only to "management guidance" or "historical CAGR" is usually a **bad explanation** unless the mechanism is spelled out and exposed to refutation.

---

## Three layers (do not conflate)

| Layer | Question | Output |
|-------|----------|--------|
| **1. Fact anchor** | What did filings show for owner cash and drivers? | FCF₀, segment revenue/OI, backlog, capex — cited paths |
| **2. Explanatory theory** | *Why* should cash grow at rate G? | Mechanism table + Deutsch "hard to vary" check |
| **3. Lawrence number** | What rate goes in the model? | Assumption ledger row with link to theory ID |

**Rule:** Layer 3 must cite Layer 2. Layer 2 must cite Layer 1. If Layer 2 is missing, growth is **[HUMAN REVIEW]** minimum; Milly flags `growth_explanation: incomplete`.

---

## Mandatory section: Growth explanation stress test

In **Valuation & IRR**, after **Assumption ledger (base case)** and **before** IRR arithmetic, add:

```markdown
### Growth explanation stress test (Popper / Deutsch)

| Field | Value |
|-------|-------|
| Growth assumption under test | Years 1–5: X%; years 6–10: Y% (base case) |
| Theory name | One-line label (e.g. "Cloud backlog conversion + Services AI yield") |

#### Explanatory theory (why this growth rate)

| # | Mechanism | Causal chain (plain English) | Filing / evidence | Hard to vary? |
|---|-----------|------------------------------|-------------------|---------------|
| 1 | … | If A then B then cash ↑ | `{TICKER}/path` | yes / partial / no |

#### Risky predictions (Popper)

Predictions that follow from the theory and would **surprise** us if false:

| # | Prediction | By when | If false → |
|---|------------|---------|------------|
| 1 | … | Q2 2026 10-Q | Revise growth down / falsify theory |

#### Falsifiers (what would refute the theory)

| # | Observation | Effect on growth assumption |
|---|-------------|----------------------------|
| 1 | Cloud rev growth <20% for 2 quarters | Cut Cloud contribution; revisit 11% consolidated |
| 2 | … | … |

#### Ad hoc rescue watch (Popper)

List adjustments we **refuse** to make without new theory:

- "Search is fine because AI" with no query/revenue bridge
- Lowering growth while raising exit multiple with no mechanism
- Using GAAP book as floor when assets are off balance sheet

#### Deutsch checks

| Check | Pass? | Notes |
|-------|-------|-------|
| **Hard to vary** — details matter; small change breaks the story | | |
| **Reach** — theory explains more than the single CAGR used to derive it | | |
| **Falsifiable** — at least one filing-observable falsifier above | | |
| **Not instrumentalist** — rate is not "what the market prices" alone | | |
```

For **segment overlays**, run one stress-test block **per segment growth rate** that moves consolidated IRR materially (or one consolidated theory with segment sub-rows).

---

## Popper framework (applied to growth)

| Popper idea | Investment translation |
|-------------|------------------------|
| **Conjecture and refutation** | Growth rate is a conjecture; filings + events refute or corroborate |
| **Falsifiability** | Name observations that would force you to **drop or cut** the rate |
| **Risky prediction** | Derive at least one **quantitative** near-term implication (not vague "AI tailwind") |
| **Ad hoc rescue** | Flag raising growth to match price, or lowering multiple to save IRR, without mechanism |
| **Corroboration ≠ proof** | One good quarter does not verify 10-year growth; note what would still falsify |
| **Problem-situation** | Start from **problem**: "Why is Lawrence IRR only 2% at $386?" not from a default CAGR |

Source: `Popper-Science-Conjectures-and-Refutations-essay.pdf`; `Popper-Science-Conjectures-Refutations-excerpt-1962.pdf`; SEP Popper extract.

---

## Deutsch framework (applied to growth)

| Deutsch idea | Investment translation |
|--------------|------------------------|
| **Good explanation** | Mechanism is **hard to vary**: "Cloud 25% because backlog >$460B converts at X% per year" beats "Cloud grows 25%" |
| **Bad explanation** | Easy to vary: "11% because quality compounder" (works for any ticker) |
| **Reach** | Theory should imply **other** testable claims (margin path, capex/revenue, segment mix) |
| **Fallibilism** | State what you might be wrong about; no "management will execute" without tests |
| **Conjecture source** | Theories come from **problem + creativity**, not from extrapolating one historical CAGR |
| **Instrumentalism ban** | Do not defend growth solely as "what reverse DCF requires at this price" without operating mechanism |

Source: Deutsch `Constructor-Theory-2012.pdf`; `Physics-Philosophy-Quantum-Technology.pdf`; *Beginning of Infinity* (purchase / library — see INDEX).

---

## Worked pattern: GOOGL 11% years 1–5 (illustrative)

| Step | Content |
|------|---------|
| **Fact anchor** | FY2025 FCF $5.85/sh; Cloud +63% Q1 rev; backlog >$460B (8-K) |
| **Theory** | "Cloud OI share rises; Services grows high single digits; corp capex peaks then normalizes" |
| **Hard to vary?** | Partial — must specify backlog conversion % and Services Search yield |
| **Risky prediction** | Cloud rev >50% YoY in 2026 if theory holds at 25% segment growth |
| **Falsifier** | Two consecutive quarters Cloud rev growth <30% → cut Cloud segment growth |
| **Ad hoc ban** | Do not bump to 14% bull without backlog schedule in segment build |

---

## Worked pattern: TPL 5% years 1–5 (illustrative)

| Step | Content |
|------|---------|
| **Fact anchor** | FY2025 OCF $545.9M; water +16%; royalties +10%; Q1 +21% rev |
| **Theory** | "Producing acreage toll + water infra ramp; undeveloped NRA **not** in base rate" |
| **Hard to vary?** | Yes if tied to Permian completion counts on TPL acreage |
| **Risky prediction** | Water revenue >$330M FY2026 if 5% consolidated path holds |
| **Falsifier** | Permian rig count on TPL counties down >15% YoY for 4 quarters → cut to 2% |
| **Overlay** | Undeveloped acreage option in `nav_overlay`, **not** smuggled into 5% |

---

## valuation.json shape

Add optional block (Marvin fills on refresh):

```json
"growth_explanation": {
  "as_of": "2026-06-01",
  "assumption_ids": ["growth_y1_5", "growth_y6_10"],
  "theory_label": "Cloud backlog + Services yield",
  "mechanisms": [
    {
      "id": "cloud_conversion",
      "chain": "Backlog drawdown → Cloud rev → segment OI → consolidated FCF",
      "evidence": "GOOGL/10-Q_20260430",
      "hard_to_vary": "partial"
    }
  ],
  "risky_predictions": [
    { "text": "Cloud rev >50% YoY 2026", "by": "FY2026", "falsifier_action": "cut cloud growth" }
  ],
  "falsifiers": [
    { "observation": "Cloud rev growth <30% for 2 Qs", "action": "revise segment build" }
  ],
  "ad_hoc_rescue_banned": ["Price-implied CAGR without segment bridge"],
  "deutsch_checks": {
    "hard_to_vary": true,
    "reach": true,
    "falsifiable": true,
    "not_instrumentalist": true
  }
}
```

---

## Report integration

| Location | Requirement |
|----------|-------------|
| Assumption ledger rows 3–4 (growth) | Source column: `Growth theory: {theory_label}` + filing or **[Assumption]** |
| Valuation & IRR | `### Growth explanation stress test` subsection |
| Payoff & return | One sentence: "Base growth assumes …; falsified if …" |
| Executive summary | **No** mechanism essay — one outcome % only |

---

## Milly checks

| Check | Severity |
|-------|----------|
| Growth rows in ledger without theory reference | **Inference risk** |
| No falsifiers listed when growth > historical run-rate + 300 bp | **Inference risk** |
| Theory is easy-to-vary ("quality compounder grows 10%") | **Inference risk** |
| Instrumentalist-only defense ("market prices X") | **Inference risk** |
| Ad hoc: growth and multiple both raised in same refresh without new filings | **Warn** |

YAML: `growth_explanation: complete | partial | incomplete | n/a`

---

## Anti-patterns

- **Historical CAGR as theory** — "grew 15% last 5 years so 11% forward" without mechanism
- **Guidance copy-paste** — "mgmt says mid-teens" without bridge to **owner cash per share**
- **Reverse-DCF smuggle** — growth chosen to hit 15% IRR with no operating story
- **Segment growth without segment theory** — Cloud 25% with no backlog/margin path
- **Unfalsifiable bull** — "AI changes everything" with no quarterly test

---

## Maintenance

- Re-run stress test every **10-Q** when growth assumptions change.
- When theory falsified, log in `_system/memory/daily/{date}.md` as **[PROPOSED]** — not MEMORY.md.
- Cite philosophy PDFs in `[PROPOSED MEMORY]` when promoting stable patterns after human review.
