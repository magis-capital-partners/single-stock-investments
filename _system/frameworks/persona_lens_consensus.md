# Persona lens consensus

**Purpose:** Deterministic multi-investor lens layer over the **same shared data** (`valuation.json`). Each persona reads facts; personas never restate numbers. Outputs `{TICKER}/research/lenses.json` + `valuation.json` → `lens_consensus`.

**Normative companion:** `_system/lenses/personas.json` (criteria, bars, return functions).

---

## Architecture

| Layer | Role |
|-------|------|
| Shared data | `valuation.json`, macro/insider/themes, filings |
| Persona lenses | `persona_lens.py` → per-persona relevance, return, verdict |
| Valuation blend | Relevance-weighted mean of annualized returns + band + weighted median |
| Stance consensus | Downstream of blend; dissent ledger preserved |
| Insights (context) | `build_insights.py` — letters, macro, insider, third-party; `in_base_irr: false` |

---

## Relevance (hard-to-vary)

Relevance ∈ {1.0 high, 0.5 medium, 0.0 silent} from **published criteria** in `personas.json`:

- **High:** all criteria met  
- **Medium:** at least one met, not all  
- **Silent:** none met  

**Sparsity:** max 3 personas at high relevance per ticker (extras demoted to 0.5).

**Calibration:** `relevance_calibration_check.py` compares high-relevance names vs superinvestor letter holdings.

---

## Valuation blend (precision over accuracy)

```
blended_return = Σ(relevance × return) / Σ(relevance)
```

Report: central mean, `[min,max]` band, weighted median. Mean–median divergence > 3pp → flag.

**Common unit:** expected annualized return at today's price (persona-specific return_fn over shared scenarios).

---

## Horizon / metric compression

```
valuation_richness from low base IRR and/or low FCF yield
horizon = round(horizon_base × (1 - 0.5 × richness))
metric_count = 3 / 2 / 1 by richness tertiles
```

---

## Mechanical pipeline

```bash
python _system/scripts/fetch_superinvestor_letters.py --all --build
python _system/scripts/persona_lens.py --all
python _system/scripts/build_insights.py
python _system/scripts/relevance_calibration_check.py
python _system/scripts/lint_persona_lens.py --portfolio
python _system/scripts/append_persona_memory.py --date YYYY-MM-DD
```

Wired into `marvin_cloud_refresh.py` after valuation write.

---

## Adversarial

- `lint_persona_lens.py` — determinism (re-run diff)  
- Milly: flag `lens_consensus.lawrence_divergence` on core holdings  
- Insights never auto-inflate base IRR (`in_base_irr: false`)

---

## Dashboard

- Ticker detail: persona sub-tabs + consensus strip  
- Top-level **Insights** tab: theme rankings + fund cards + per-ticker "who discusses"

See `_system/proposals/persona_lens_consensus_2026-06-08.md`.
