# Segment cash-flow valuation (Speedwell / Hohn overlay)

**Purpose:** For **multi-segment operating compounders**, value each reportable business (and material **options**) on its own cash-flow economics, discount to present, and **sum** to an enterprise or per-share intrinsic view. Cross-check the consolidated Lawrence IRR so assumptions are explicit—not a single blended FCF growth rate hiding segment divergence.

**Philosophy sources (read before applying):**

| Source | What to borrow |
|--------|----------------|
| **Drew Cohen / Speedwell** | [Process & Philosophy](https://www.speedwellmemos.com/p/speedwell-research-process-and-philosophy) — reverse DCF: start at **today’s price**, model **explicit** cash-flow assumptions, output **business return** (implied discount rate). [Reverse DCF memo](https://speedwellresearch.com/2024/10/03/investing-is-just-answering-a-series-of-questions-explaining-the-reverse-dcf/) — hone in on **two key drivers** per segment; burden drag segments (Meta: Reality Labs losses, **zero** terminal value to that segment). |
| **Chris Hohn / TCI** | `TCI-Q2-2018-Investor-Newsletter-extract.txt` — Alphabet **segment build**: Search, YouTube, Cloud (losses → inflection), Waymo **$0 in TCI base** (explicit — not a default for all options). |
| **Marvin Lawrence** | `lawrence_irr.md` — consolidated **10yr owner-cash IRR** remains the **stance gate**; segment sum is the **assumption ledger** and sanity check. |
| **Option treatment** | `option_treatment.md` — mandatory option scan; **no auto-zero**; treatment ladder (`zero`, `embedded_in_segment`, `milestone_nav`, `probability_weighted`, `nav_floor`). |

**Not the same as:**

| Framework | Difference |
|-----------|------------|
| **Holdco SOTP** (`optionality_valuation.md`) | Marks **stakes/NAV** and catalyst payoffs—not operating segment FCF streams. |
| **Lawrence `full` alone** | One FCF₀ and one growth path for the whole company. |
| **Sell-side sum-of-parts** | Often revenue × arbitrary multiples; this framework requires **owner cash** (or defensible EBIT→cash bridge) per segment. |

---

## When to trigger

Use a **segment overlay** when **any** of:

| Trigger | Examples |
|---------|----------|
| **≥2 reportable segments** with different growth, margin, or capex intensity | GOOGL (Services / Cloud / Other Bets), AMZN (NA / Intl / AWS), MSFT, META |
| **Material option inside the company** valued separately in base vs bull | Waymo, Reality Labs, YouTube subs, Gemini consumer tier |
| **Consolidated FCF misleading** | Corp capex step-up, segment losses buried in “Other,” equity marks in GAAP EPS |
| **Human asks for segment bridge** | e.g. “value GOOGL like Speedwell / Hohn segments” |
| **AI hyperscaler with capex step-up** | Also set `ai_overlay` per `ai_infrastructure_valuation.md` |

Set in `{TICKER}/research/valuation.json`:

```json
"valuation_overlay": "segment_cashflow",
"segment_build": { ... }
```

Keep `method: "full"` (or `scenario`) for `marvin_valuation.py` consolidated IRR unless the human explicitly switches the primary gate.

---

## Speedwell reverse DCF (how it maps to segments)

Speedwell does **not** publish a single point “fair value.” They:

1. **Invert** the question: at **P₀ today**, what **return** do you earn if excess cash flows are returned and assumptions hold?
2. Model cash flows from **explicit** drivers (often revenue growth + margin, or reinvestment + ROIC)—not an opaque P/E.
3. **Sensitize** two variables that matter; table of **business returns** across scenarios.
4. For **embedded options / drag segments**, **fully burden** losses in the cash-flow path and assign terminal value per **`option_treatment.md`** — not automatic zero.

**Marvin segment overlay** applies the same discipline **per segment**, then **adds** present values (and options) to reconcile to total equity value per share.

---

## Workflow (six steps)

### 1. Map segments and options (filings first)

From latest **10-K / 10-Q segment note** (not training memory):

| Line | Source | Marvin label |
|------|--------|--------------|
| Reportable segment revenue & operating income | Segment table | `operating` row |
| Unallocated corp / Other Bets | 10-K | `corporate_drag` or `option` |
| Sub-products you must model (Search vs YouTube) | **[Assumption]** split of Services | sub-rows under parent segment |

**GOOGL (Alphabet) filing map (FY2025 / Q1 2026):**

| Segment / option | Role in model |
|------------------|---------------|
| **Google Services** | Core owner-cash engine (Search, YouTube, Play, Android distribution) |
| **Google Cloud** | High growth; capex-heavy; margin inflection |
| **Other Bets** (Waymo, etc.) | **Option**: burden losses; terminal per **`option_treatment`** — **zero** only if no filing mark / milestone |
| **Corporate / unallocated capex** | Allocate AI capex to Cloud vs Services or hold at corp—**[Assumption]**; document |
| **Undeveloped acreage** (TPL-style) | **Option** row: `nav_floor` or **probability_weighted**; operating segments for producing royalties/water |

### 2. Assign owner cash per segment (Year 0)

Prefer **segment operating income → after-tax owner cash** with explicit capex allocation:

```
OwnerCash_segment ≈ Segment OpInc × (1 − tax rate) − Segment capex attribution ± working capital
```

Rules:

- **Cite** 10-K segment op income; show ÷ consolidated shares for **$/sh** if helpful.
- If segment FCF is **not** disclosed, bridge from op income and label **[Assumption]** (capex share, SBC, D&A).
- **Do not** double-count: intersegment revenue eliminations stay in filing totals; sum of segment revenues should tie to consolidated within rounding.
- **Do not allocate consolidated owner cash by revenue share** when segment margins or capital intensity differ. Bridge from segment operating income or net income, segment D&A, working capital, taxes, and fixed-asset spending.
- Treat share-based compensation as an owner cost. If management's non-GAAP FCF adds it back, subtract it in the owner-cash bridge or demonstrate that per-share dilution fully captures it.
- Separate maintenance capital from growth capital when evidence permits. If it does not, deduct total fixed-asset spending and show the conservatism explicitly.

### 3. Project each segment (one explicit horizon)

Per segment, use the same explicitly declared horizon as the consolidated model. New seven-year models use `growth_y6_end` and `exit_pfcf_end`; do not label a year-seven terminal multiple as year ten.

| Input | Typical segment-specific |
|-------|-------------------------|
| Growth Y1–5 / Y6–10 | Cloud > Services; Other Bets N/A if valued as option |
| Exit P/FCF or EV/FCF Y10 | Higher for wide-moat Services; lower or N/A for loss-making Cloud until profitable |
| Reinvestment | Heavy capex → lower near-term owner cash, document **ROIC** narrative |

**Hohn-style qualitative checks** (TCI Alphabet): Search volume/pricing, YouTube monetization ramp, Cloud loss → profit inflection, **Waymo zero in base**.

### 4. Options within the business

Treat **material non-core bets and hidden assets** as separate rows. Complete **`#### Option scan`** first (`option_treatment.md`).

| Type | Loss drag | Overlay base terminal | Bull |
|------|-----------|----------------------|------|
| **Loss drag** (Reality Labs, Other Bets) | Burden in CF stream | **`zero`** if no mark; **`milestone_nav`** if external round/mark in filing | Full NAV or reduced drag |
| **Real option** (Waymo, autonomous) | Burden | Per scan — not default zero | External comps ÷ shares |
| **Embedded product** (Cloud backlog, Search AI) | — | **`embedded_in_segment`** — in segment growth | Higher growth / margin |
| **Undeveloped reserves** (TPL acreage) | — | **`nav_floor`** or **probability_weighted** NRA/acre comp | Full development case |
| **GAAP misstated land** | — | **`nav_floor`** SOTP line | Re-rate |

Each row requires: `option_treatment`, `base_terminal_rationale`, `evidence`, `not_in_lawrence_base: true` when overlay-only.

Store in `segment_build.options[]` and/or `nav_overlay`.

### 5. Discount and sum

**Per segment (operating):**

- Build 10-year owner-cash stream (or explicit yearly table).
- Terminal: `FCF_10 × exit_multiple` (state multiple **after** segment economics).
- Discount each segment at the **same** discount rate **or** use **reverse DCF** on the **whole equity** once summed—pick one and document.

**Sum:**

```
PV_equity = Σ PV(segment operating) + Σ PV(options) − PV(corporate drag) − net debt
Value per share = PV_equity ÷ diluted shares
```

**Reverse DCF (Speedwell):** With **P₀** fixed, solve the discount rate (business return) such that `PV_equity = market cap`. Report that rate beside Lawrence consolidated IRR.

### 6. Reconcile to consolidated Lawrence IRR

Required table in deep dive **Valuation & IRR**:

| Check | Requirement |
|-------|-------------|
| Sum of segment PV/sh | Must be shown |
| Lawrence `full` terminal / IRR | From `marvin_valuation.py` |
| **Slack** | If segment sum ≠ consolidated path, **Tie-out** row explaining (corp capex, option zeroing, timing) |

Neither path alone is “truth”—divergence forces explicit assumptions (e.g. capex normalization).

---

## `valuation.json` shape

```json
{
  "ticker": "GOOGL",
  "method": "full",
  "valuation_overlay": "segment_cashflow",
  "inputs": { "price": 386.0, "fcf_per_share": 5.85, "shares_millions": 12447 },
  "segment_build": {
    "framework": "speedwell_reverse_dcf",
    "as_of": "2026-05-26",
    "horizon_years": 10,
    "segments": [
      {
        "id": "google_services",
        "label": "Google Services",
        "type": "operating",
        "owner_cash_y0_bn": null,
        "owner_cash_y0_source": "10-K FY2025 segment operating income; capex alloc [Assumption]",
        "growth_y1_5": 0.09,
        "growth_y6_10": 0.07,
        "exit_pfcf_y10": 22,
        "notes": "Search + YouTube; AI query growth"
      },
      {
        "id": "google_cloud",
        "label": "Google Cloud",
        "type": "operating",
        "growth_y1_5": 0.25,
        "growth_y6_10": 0.12,
        "exit_pfcf_y10": 18,
        "notes": "Capex front-loaded; margin inflection"
      }
    ],
    "options": [
      {
        "id": "other_bets_waymo",
        "label": "Other Bets / Waymo",
        "option_treatment": "zero",
        "base_terminal_value_bn": 0,
        "base_terminal_rationale": "No SEC fair-value mark; explicit zero after option scan",
        "bull_terminal_value_bn": null,
        "annual_drag_bn": null,
        "evidence": "10-K segment note",
        "not_in_lawrence_base": true
      }
    ],
    "corporate_drag": {
      "unallocated_capex_bn": null,
      "notes": "FY2026 capex guide $180–190B — split Cloud vs Services"
    },
    "reconciliation": {
      "sum_pv_per_share": null,
      "implied_business_return_pct": null,
      "lawrence_base_irr_pct": 2.1,
      "slack_notes": ""
    }
  },
  "scenarios": { "bear": {}, "base": {}, "bull": {} }
}
```

Fill numbers after filing pull; `null` placeholders are valid until refresh.

---

## Report integration

### Business & moat (overview)

Add **`#### Segment map`** after Hohn mechanics when overlay applies:

| Segment / option | Revenue / op income (fact) | Economic role | Base case treatment |
|------------------|----------------------------|---------------|---------------------|

No IRR math here—only economics.

### Valuation & IRR (end) — required additions

After **Assumption ledger (base case)**, add:

```markdown
### Segment cash-flow build (Speedwell / Hohn overlay)

| # | Segment / option | Owner cash Y0 | Growth Y1–5 / Y6–10 | Exit × Y10 | PV contribution $/sh | Source |
|---|------------------|-----------------|---------------------|------------|----------------------|--------|

**Sum of segments + options (PV/sh):** $X  
**Corporate drag / tie-out:** …  
**Implied business return at P₀:** Y% (reverse DCF) · **Lawrence consolidated base IRR:** Z%

#### Segment IRR arithmetic (show your work)

**Step 1 — Segment map from filings** …  
**Step 2 — Owner cash Y0 per segment** …  
**Step 3 — Project and terminal per segment** …  
**Step 4 — Options (base zero / bull value)** …  
**Step 5 — Sum PV and reconcile to Lawrence** …
```

Rules: same as `irr_assumption_ledger.md` — one row per moving part, **[Assumption]** tagged, running sum, tie-out slack visible.

### Classification footer

| Field | Value |
|-------|-------|
| **IRR method** | `full` (unchanged) |
| **Valuation overlay** | `segment_cashflow` |
| **Implied 10yr IRR** | Lawrence consolidated % |
| **Segment-implied return** | Reverse-DCF business return % if computed |

---

## GOOGL reference (illustrative structure)

At **P₀ ≈ $386** (May 2026), consolidated Lawrence base **~2.1%** 10yr IRR on **$5.85/sh** reported FCF reflects **corp-level capex** and a single growth path. Segment overlay explains *why*:

| Piece | Base narrative |
|-------|----------------|
| **Services** | Bulk of op income; moderate growth; high terminal multiple |
| **Cloud** | 63% Q1 growth; absorbs AI capex; lower near-term owner cash, higher long-term if ROIC proves out |
| **Other Bets** | ~$2.1B Q1 op loss — **zero** in base (Speedwell/Meta pattern) |
| **Capex step-up** | $180–190B 2026 guide — unallocated drag until normalized |

Segment sum typically shows **most value in Services**, **optionality in Cloud**, **no base value in Waymo**—consistent with TCI 2018 letter and Speedwell’s explicit burdening of loss segments.

---

## Lint / tools

```bash
python _system/scripts/build_filing_evidence.py GOOGL
python _system/scripts/marvin_valuation.py --ticker GOOGL --write
# Segment PV math: spreadsheet or future segment_valuation.py — document steps in markdown until scripted
python _system/scripts/lint_deep_dive.py GOOGL
```

When `valuation_overlay` is set, `lint_deep_dive.py` should eventually require `### Segment cash-flow build`; until then, Marvin must include it by rule.

---

## Holdings map (initial)

| Ticker | Segments to model | Options |
|--------|-------------------|---------|
| **GOOGL** | Services, Cloud | Other Bets / Waymo; Cloud backlog **embedded** |
| **AMZN** | North America, International, AWS | Advertising; optional Kuiper |
| **META** | Family of Apps, Reality Labs | RL drag; messaging monetization **embedded** or separate |
| **MSFT** | Productivity, Intelligent Cloud, MPC | OpenAI stake optional |
| **TPL** | Land/Royalty, Water | Undeveloped acreage/NRA **`nav_floor`** |

---

## Maintenance

- Refresh segment op income every **10-Q**.
- Reconcile sum-of-segments to consolidated FCF when capex guidance changes.
- Promote stable segment methodology to `_system/memory/MEMORY.md` after **[HUMAN REVIEW]**.
