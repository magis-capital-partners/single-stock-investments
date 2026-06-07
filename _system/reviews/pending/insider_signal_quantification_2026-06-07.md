# Insider signal — quantification recommendations (Marvin)

**Date:** 2026-06-07  
**Status:** Approved approach for implementation  
**North star:** Insider buying is a **qualitative confidence** input for scenario weighting and narrative. It does **not** auto-change Lawrence base IRR.

---

## What Marvin should quantify (three layers)

| Layer | Field | Changes base IRR? | Purpose |
|-------|-------|-------------------|---------|
| **1. Conviction score** | `insider_signal.ics` (0–10) | No | Single explainable score from Form 4 math |
| **2. Scenario confidence tilt** | `insider_signal.scenario_confidence` | No | Shifts **weight** toward bull/base vs bear for human stance |
| **3. Payoff narrative hint** | `insider_signal.bull_case_support` | No | Flags when optimistic scenario deserves more attention |

Lawrence **base** stays `scenarios.base` → `implied_return.base_pct`. Bull/bear payoffs in `valuation.json` stay filing-backed unless **[HUMAN REVIEW]** promotes an overlay.

---

## Recommended ICS → scenario tilt mapping

Default prior weights (asset/optionality names):

| Scenario | Default weight |
|----------|----------------|
| Bear | 20% |
| Base | 55% |
| Bull | 25% |

**Tilt formula** (Marvin script, capped):

```
bull_delta   = min(0.15, 0.025 × max(0, ics − 4))
bear_delta   = min(0.10, 0.02  × max(0, 4 − ics))   # only when net selling dominates
base_delta   = −(bull_delta + bear_delta)              # conserve mass
```

| ICS band | Bull Δ | Bear Δ | Interpretation |
|----------|--------|--------|----------------|
| 0–2 Negligible | 0 | +0.05 | Routine sales or no signal |
| 2–4 Weak | +0.02 | 0 | Footnote only |
| 4–6 Moderate | +0.05 | 0 | Bull case more plausible |
| 6–8 Strong | +0.10 | −0.03 | Domain-expert cluster (LMNR pattern) |
| 8–10 Exceptional | +0.15 | −0.05 | Rare; human accumulate review |

**Domain expert multiplier** (e.g. Slater ×2.5 on water): applies to ICS computation, not a second tilt — avoids double-counting.

---

## Bull case support enum (qualitative, not payoff math)

| Level | Trigger | Marvin narrative |
|-------|---------|------------------|
| `none` | ICS < 4 | No insider corroboration |
| `moderate` | ICS 4–6, any open-market buy cluster | "Insiders bought; bull is sensitivity only" |
| `strong` | ICS ≥ 6 + cluster + domain match | "Qualified insider buying supports water/land bull path" |
| `exceptional` | ICS ≥ 8 + material % increase + underwater | **[HUMAN REVIEW]** accumulate tilt |

Does **not** auto-set `scenarios.bull.payoff` to $160M water case. Marvin cites bull payoff already in JSON and explains why insider activity increases **confidence**, not the number itself.

---

## LMNR application (worked example)

| Input | Value |
|-------|-------|
| Nolan | ~$255k buys Jan 2–5; low % of 1.1M shares |
| Slater | 5,000 @ $12.85; ~7.8% of holdings; water domain ×2.5 |
| Hamm | 1k/month sales → capped noise |
| Spot | $11.83 vs insider avg ~$12.75 (underwater) |

**Expected ICS:** ~6.5–7.2 (Strong)  
**Scenario tilt:** bear 17% / base 53% / bull 30%  
**Bull case support:** `strong`  
**Base IRR:** unchanged at 5.3%  
**Narrative:** Insider cluster corroborates $50–$160M water optionality in **bull** scenario; base still haircuts development guide.

---

## What Marvin must not do

- Add ICS to assumption ledger or IRR arithmetic
- Set `in_base_irr: true` without human
- Auto-upgrade `stance_proposal` from watch → accumulate (flag only)
- Treat CFO 10b5-1 dribble sales as bearish signal

---

## Human promotion path

Under **[HUMAN REVIEW]** only:

1. Set `insider_signal.promote_bull_weight: true` to persist tilt in stance discussion
2. Optional `synthesis.qualitative_pp` max +0.3pp per `total_synthesis_irr.md` (separate gate)
3. Update `scenarios.bull.payoff` with filing + insider corroboration note
