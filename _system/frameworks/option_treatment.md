# Option treatment — when to zero, when to size, when to overlay

**Purpose:** Stop **automatic $0 terminal** on every option. Separate **Lawrence consolidated IRR** (conservative stance gate) from **overlay math** that must **identify, document, and partially value** hidden assets, undeveloped reserves, in-business bets, and GAAP misstatements.

**Companions:** `optionality_valuation.md` · `segment_cashflow_valuation.md` · `ai_infrastructure_valuation.md` · `decision_stack.md`

---

## Three valuation layers (do not conflate)

| Layer | Role | Option treatment |
|-------|------|------------------|
| **1. Lawrence consolidated `full`** | **Stance gate** — filing-based owner cash, bear/base/bull | Conservative; **no silent heroics** in base growth or FCF₀ |
| **2. Overlay base case** | Segment sum, NAV/SOTP, yield curve, AI inflection | **Size options with evidence**; probability-weight or milestone NAV where filings/comps support |
| **3. Bull sensitivity** | Upside case | Full option value, faster conversion, higher terminal |

**Rule:** Low Lawrence IRR + rich overlay base is **valid** (e.g. capex-cycle compounder, land with GAAP book at zero). Do not “fix” low IRR by stuffing options into Lawrence FCF₀ without human approval.

---

## Mandatory option scan (every deep dive)

Before finalizing valuation, complete this scan in **Business & moat** → **`#### Option scan`** (or **`#### Hidden assets & options`**). One row per line; cite filing or **[Assumption]**.

| # | Question | If yes → |
|---|----------|----------|
| 1 | **GAAP book misstates core assets?** (land at cost/zero, stakes at cost, trust assets unmarked) | `nav_overlay` + fair-value floor; **never** cite GAAP book as dhando floor |
| 2 | **Undeveloped reserves / acreage / dormant royalty?** | Segment or `nav_overlay`; undeveloped row with **zero in Lawrence**, partial in overlay base |
| 3 | **In-business loss segment?** (Other Bets, Reality Labs, corp R&D drag) | Segment `options[]`; burden losses; see treatment ladder below |
| 4 | **Backlog / RPO / contracted revenue not in FCF path?** | `ai_overlay` or segment growth bridge; schedule conversion |
| 5 | **Private or illiquid stakes below fair value?** | Holdco SOTP (`optionality_valuation.md` A) |
| 6 | **Transitory distribution / legal recovery?** | HK yield curve (`optionality_valuation.md` C) |
| 7 | **Embedded product option already in revenue?** (Cloud AI, water ramp) | `embedded_in_segment` — do not double-count separate terminal |

If **all rows are no**, document “no material options identified” and proceed with Lawrence `full` only.

---

## Treatment ladder (per option line)

Use **`option_treatment`** in `valuation.json` (`segment_build.options[]`, `nav_overlay`, or `optionality_gate`).

| Code | Label | Base overlay terminal / value | When to use | Evidence required |
|------|-------|----------------------------|-------------|-------------------|
| **`zero`** | Explicit zero | **$0** terminal; burden losses in CF | Pre-revenue binary; no asset floor; no external marks; Speedwell loss-drag only | One-line why zero |
| **`embedded_in_segment`** | Inside segment growth | No separate terminal row | Cash flows already in segment revenue/margin path (Cloud backlog → Cloud growth) | Segment growth assumption cites driver |
| **`milestone_nav`** | Dated partial NAV | Partial PV of milestone value | External transaction, funding round, disclosed mark, acquisition comp | Filing, 8-K, or audited comp |
| **`probability_weighted`** | P × payoff | `P_base × NAV_terminal` | Credible path but uncertain timing; multiple outcomes | State **P_base** + source; bull uses higher P or full NAV |
| **`nav_floor`** | Fair-value asset floor | SOTP line(s) summed | Land/mineral/holdco where GAAP ≠ fair value | Per-acre, per-NRA, or stake marks with comps |
| **`yield_curve`** | Dated payoff | Cumulative distributions + terminal | Royalty trusts, litigation recovery, catalyst stack | HK curve or dated payoff table |

**Anti-pattern (forbidden):** Setting `zero` because “Speedwell says so” **without** completing the option scan and evidence column.

**Anti-pattern (forbidden):** Using GAAP **book per share** as floor when filings state assigned assets carry **no value** on the balance sheet.

---

## Segment options (`segment_build.options[]`)

Required fields per option row:

```json
{
  "id": "other_bets_waymo",
  "label": "Other Bets / Waymo",
  "option_treatment": "zero | milestone_nav | probability_weighted | embedded_in_segment",
  "annual_drag_per_share": 0.6,
  "base_terminal_value_bn": 0,
  "base_terminal_rationale": "No SEC mark; pre-profit at scale — explicit zero after scan",
  "overlay_base_terminal_bn": null,
  "bull_terminal_value_bn": null,
  "evidence": "10-K FY2025 op loss $7.5B; no disclosed fair value",
  "not_in_lawrence_base": true
}
```

| Segment pattern | Loss drag | Overlay base terminal |
|-----------------|-----------|------------------------|
| **Reality Labs / Other Bets** | Always burden in CF | **zero** unless external mark or milestone in filing |
| **Cloud + backlog** | Capex in segment or corp drag | **embedded_in_segment** — model conversion in Cloud growth, not separate Waymo-style zero |
| **TPU / chip sales** | — | **milestone_nav** if revenue disclosed; else **zero** + `not_in_model_requires_refresh` |
| **Undeveloped acreage (TPL)** | — | **nav_floor** row: undeveloped NRA/acres at comp; **zero** in Lawrence consolidated |

**Sum:** `PV(operating segments) + PV(options per treatment) − PV(corporate drag)`.

Report **two** implied returns when options are material:

- **Segment-implied return** (overlay base assumptions at P₀)
- **Lawrence consolidated base IRR** (stance gate)

---

## Infrastructure + land (`nav_overlay`)

**Trigger:** Permian/mineral land, royalty trusts with physical assets, any issuer disclosing **no value assigned** to historical assets on balance sheet.

**Required JSON:**

```json
"valuation_mode": "optionality",
"nav_overlay": {
  "gaap_vs_fair_value": { },
  "asset_inventory_filing": { },
  "segments_or_options": [
    { "id": "undeveloped_reserves", "option_treatment": "nav_floor", "notes": "…" }
  ],
  "not_in_model_requires_refresh": [ ]
}
```

**Segment build (when operating + asset base):**

| Segment | Type | Base treatment |
|---------|------|----------------|
| Royalties / easements ( producing ) | operating | Owner cash Y0 from filings; segment growth |
| Water / infrastructure | operating | Capex attribution; higher growth if ramping |
| **Undeveloped acreage / NRA** | option | **nav_floor** or **probability_weighted** future royalty; **$0 in Lawrence** |

**TPL reference:** Assigned 1888 land/RRA **$0** on BS → fair value via NRA comps, land-sale marks, $/acre — not GAAP book.

---

## AI hyperscaler options

Pair with `ai_infrastructure_valuation.md`:

| Theme | Lawrence base | Overlay base |
|-------|---------------|--------------|
| Capex peak | FY filing FCF₀ | `capex_stress` illustration only |
| Post-capex normalization | Unchanged in gate | `ai_inflection_bull` sensitivity |
| Cloud backlog | Not in FCF₀ | **embedded_in_segment** or backlog drawdown schedule in segment Cloud |
| Waymo / RL / Other Bets | — | **zero** or **milestone_nav** if external mark |

---

## Report integration

### Business & moat

```markdown
#### Option scan

| # | Option / hidden asset | In Lawrence base? | Overlay treatment | Evidence |
|---|----------------------|-------------------|-------------------|----------|
```

### Payoff & return

```markdown
### Optionality overlay

| Field | Value |
|-------|-------|
| Framework | holdco_sotp / mineral_floor_option / hk_royalty_curve / segment_options |
| Options identified | … |
| Zero-by-explicit-choice | … (not “by default”) |
| Partially valued in overlay | … |
| Primary metric for stance | Lawrence IRR vs overlay metric |
```

### Valuation bridge

Add overlay rows (not stance gate unless `optionality_gate` primary):

| Case | Method | Main assumptions | Annual return | Versus 15% target |
|------|--------|------------------|---------------|-------------------|
| Overlay base (segment/NAV) | segment @ 10% / NAV SOTP | … | X% or $/sh | overlay |
| Bull option | … | … | Y% | sensitivity |

---

## Stance logic

| Situation | Stance |
|-----------|--------|
| Lawrence base ≥ 15%, dhando OK | hold / core per gates |
| Lawrence base < 15%, **overlay base** ≥ 15% with filing-backed options | **watch** or **hold** — document `optionality_gate.primary_metric` |
| Lawrence base < 15%, overlay base < 15%, quality franchise | **watch** — priced in |
| Options identified but **not sized** | **watch** + `[HUMAN REVIEW]` — Milly flags `option_coverage: incomplete` |
| GAAP book used as floor when nav_overlay triggered | **Error** — fix before final |

---

## Holdings map (option treatment examples)

| Ticker | Options to model | Default overlay base (not auto-zero) |
|--------|------------------|--------------------------------------|
| **GOOGL** | Cloud backlog, Waymo, TPU, corp AI drag | Cloud **embedded**; Waymo **zero** until mark; backlog schedule |
| **META** | Reality Labs, messaging monetization | RL **zero** drag; FoA **embedded** AI yield |
| **AMZN** | AWS backlog, ads, Trainium | AWS **embedded**; ads split if material |
| **TPL** | Undeveloped acreage, GAAP land at zero | **nav_floor** + segment Land/Water; undeveloped NRA comp |
| **KEWL** | Copperwood | **zero** in overlay base; bull option yield |
| **FRMO** | HK, MIAX, CMSG stakes | **milestone_nav** / SOTP uplifts |
| **MSB / SJT** | Distribution recovery | **yield_curve** |

---

## Milly checks

See `MILLY.md` § Option coverage. Fail **inference risk** if:

- Material option in business description but no **Option scan** table
- `option_treatment: zero` with empty `base_terminal_rationale`
- GAAP book cited as floor when `nav_overlay` or filing says assets unmarked
- Segment sum gap to price > 30% with all options at zero and no `[HUMAN REVIEW]`

---

## Maintenance

- Refresh option scan every **10-Q** when segments, backlog, or asset disposals change.
- Promote stable treatment patterns to `[PROPOSED MEMORY]` after human review — not directly to `MEMORY.md`.
