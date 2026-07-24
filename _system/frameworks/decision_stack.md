# Decision Stack

**Purpose:** Single pipeline for Marvin deep dives. Six orthogonal questions → triggered tools from `analysis_arsenal.md`.

**Report shape:** `deep_dive_structure.md`  
**Appendix (triggered only):** `analysis_arsenal.md`, `mental_models.md`, `lawrence_irr.md` § F  
**Valuation authority:** `proof_first_valuation.md` + `decision_authority.py` (Power Zone / contract / IC / human). Lawrence IRR is legacy/specialist only.

---

## Six orthogonal questions

| # | Question | Genius | Fields / outputs |
|---|----------|--------|------------------|
| 1 | **What is it?** | Stahl + Hohn | `archetype`, `cycle`, `lawrence_bucket`, operating snapshot |
| 2 | **Will it last?** | Munger | `moat` |
| 3 | **Is the bear bounded?** | Pabrai | `dhando`, bear case |
| 4 | **What return at this price?** | Power Zone method + contract (HK/Lawrence only if routed) | Contract `annualized_return_at_price_pct` / value per share; legacy `implied_irr` is reference-only |
| 5 | **Why mispriced?** | HK + MOI | Predictive attribute; inefficiency; catalyst if `asset`/`event` |
| 6 | **What do we do?** | Pabrai + **human owner** (IC recommends) | Actionable stance only from `human_decision.json` |

**Flow:** Q4 from routed proof-first contract · IC challenge · Q6 **approved by human**. Legacy Lawrence `stance_proposal` is not capital authority.

**Payoff lens:** tag `payoff_lens` (`operating` | `asset` | `event` | `levered`) to pick toolkit — see `analysis_arsenal.md`.

---

## Step 1 — Gate table (maps to six questions)

One table in **Payoff & return**. Do not duplicate elsewhere.

| # | Gate | Question | Fail → |
|---|------|----------|--------|
| 1 | **Understand?** | Q1 | `watch`; defer |
| 2 | **Durable cash flow?** | Q2 | Downgrade moat; cap terminal multiple |
| 3 | **Bounded bear?** | Q3 | `dhando: none`; cap stance |
| 4 | **Aligned management?** | Q2/Q3 sub-check | `[HUMAN REVIEW]` |
| 5 | **Cheap vs normalized?** | Q4 input | Drives valuation model |
| 6 | **Why mispriced?** | Q5 | Name inefficiency + predictive attribute; catalyst if `asset`/`event` |

Gate 6 for `operating` lens may be "no dated edge; own for quality + IRR at price."

---

## Step 2 — Business mechanics (Hohn)

`hohn_business_analysis.md` — under **Business & moat**:

1. Operating snapshot (or look-through for holdco)  
2. Thesis pillars — 2–4, quantified  
3. Option scan — `option_treatment.md`  
4. SOTP / catalyst bullets when `payoff_lens` is `asset` or `event`  

No IRR in this section.

---

## Step 3 — Triggered overlays (not every dive)

| Trigger | Read |
|---------|------|
| `payoff_lens: asset` or holdco / optionality | `optionality_valuation.md` (prose + § Mechanical refresh if `evidence_refresh` set) |
| `payoff_lens: event` | `special_situation_lens.md` |
| `payoff_lens: levered` | `equity_stub_valuation.md`; `irr_method: scenario` |
| Multi-segment compounder | `segment_cashflow_valuation.md` |
| AI hyperscaler | `ai_infrastructure_valuation.md` |
| Watchlist / onboard | `idea_funnel.md` |

Full index: `analysis_arsenal.md`.

---

## Step 4 — Expected return

| Trigger | `irr_method` | Tool |
|---------|--------------|------|
| Modelable FCF | `full` | `marvin_valuation.py` |
| Dated payoff | `yield_curve` | HK curve + valuation.json |
| Binary / levered | `scenario` | Bear/base/bull |
| Cannot model | `pending` | Explain why |

---

## Step 5 — Stance proposal

Script logic in `valuation.json` (unchanged). Override in `[HUMAN REVIEW]`.

---

## Step 6 — Report template

`deep_dive_template.md` + `report_prose.md`:

1. What this business is (Q1)  
2. Why the market might be wrong (Q5 prose — not a separate MOI table)  
3. Executive summary — one base return %  
4. Business & moat (Q1–2)  
5. Payoff & return — gate table (Q3–4–6)  
6. Risks — primary risk + **lens failure mode** if non-operating lens  
7. Valuation & IRR — assumption ledger last  

---

## Read order (deep dive)

1. This file  
2. `{TICKER}/research/valuation.json` + **trigger map** in `classification.md` (open only listed frameworks)  
3. `report_prose.md` + `deep_dive_structure.md`  
4. `option_treatment.md` (every dive)  
5. `hohn_business_analysis.md` when operating or mixed mechanics  
6. Triggered overlays from Step 3 only (not the full arsenal index)  
7. `{TICKER}/` primary docs  
8. `deep_dive_template.md`  
9. Mechanical close: **`marvin_cloud_refresh.py` only** (see `cloud_marvin_runbook.md` Phase 3)  

New frameworks: see `framework_governance.md`.

---

## Sync & lint

```bash
python _system/scripts/marvin_valuation.py --ticker ICE --write
python _system/scripts/sync_classification.py
python _system/scripts/lint_deep_dive.py ICE
```
