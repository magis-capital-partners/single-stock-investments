# Holdings classification (Decision Stack)

Unified labels from `_system/frameworks/decision_stack.md` — layers 1–5.

Replace the old single **thesis status** (intact / weakening / strengthening / unclear) with independent axes plus Lawrence return fields.

## Fields

| Field | Lens | Values | Question answered |
|-------|------|--------|-------------------|
| **Archetype** | Stahl | `croupier`, `compounder`, `serial_acquirer`, `platform`, `holding_co`, `optionality`, `turnaround`, `infrastructure` | What *is* this business in the pecuniary economy? |
| **Moat** | Munger | `widening`, `stable`, `eroding`, `unproven`, `n/a` | Is competitive advantage durable? |
| **Dhando** | Pabrai | `full`, `partial`, `none`, `pending` | Heads I win, tails I don't lose much? |
| **Stance** | Pabrai | `core`, `accumulate`, `hold`, `watch`, `trim`, `exit` | What do we *do* with capital? |
| **Cycle** | Stahl (croupiers) | `peak`, `mid`, `trough`, `—` | Normalized earnings vs current activity |
| **Implied 7yr IRR** | Lawrence | e.g. `17% (total synthesis)`, `pending` | Blended capstone return at today's price (`total_synthesis_irr.md`) |
| **IRR method** | Lawrence | `full`, `yield_curve`, `scenario`, `pending` | How IRR was computed |
| **Lawrence bucket** | Lawrence | `pricing_power`, `multi_sided`, `low_cost`, `other` | Oakcliff business taxonomy |
| **Valuation overlay** | Speedwell / Hohn | `—`, `segment_cashflow` | Per-segment cash-flow sum + reverse DCF cross-check (`segment_cashflow_valuation.md`) |
| **Payoff lens** | Decision stack Q5 | `operating`, `asset`, `event`, `levered`, `pending` | Which toolkit applies (`analysis_arsenal.md`) |
| **MOI bucket** | Mihaljevic | optional legacy audit tag | Deprecated — map to `payoff_lens`; see `moi_lens.md` |

## valuation.json trigger map (machine + agent)

Read `{TICKER}/research/valuation.json` **before** opening optional frameworks. Open **only** the docs listed for triggers that are set (non-null / non-empty).

| JSON trigger | Open (normative) | Mechanical (do not re-list substeps) |
|--------------|------------------|--------------------------------------|
| Always | `decision_stack.md`, `deep_dive_structure.md`, `report_prose.md`, `option_treatment.md` | — |
| `classification_inputs.payoff_lens: operating` | `hohn_business_analysis.md`; Lawrence path | `marvin_valuation.py` via cloud refresh |
| `payoff_lens: asset` or `valuation_mode: optionality` | `optionality_valuation.md` (incl. mechanical refresh §) | `marvin_cloud_refresh.py` |
| `payoff_lens: event` | `special_situation_lens.md` | cloud refresh |
| `payoff_lens: levered` | `equity_stub_valuation.md` | cloud refresh |
| `segment_build` or `valuation_overlay: segment_cashflow` | `segment_cashflow_valuation.md` | cloud refresh |
| `ai_overlay` (keys present) | `ai_infrastructure_valuation.md` | cloud refresh |
| `btc_overlay` or `holdings_crypto.json` tag | `crypto_economics_valuation.md` | `fetch_crypto_panel.py` + `apply_btc_context_overlay.py` |
| `nav_overlay` or `optionality_gate` | `optionality_valuation.md` | cloud refresh |
| `evidence_refresh.type` (e.g. `commodity_nav`) | `optionality_valuation.md` § Mechanical refresh | `fetch_market_inputs` + `refresh_optionality_valuation` inside cloud refresh |
| `book_estimate_config.json` exists | `current_book_estimate.md` | `current_book_estimate.py --write` |
| HK index ticker (TPL, ICE, MSB, SJT) | `hk_cross_reference.md` | `scan_third_party_sources --with-hk` |
| Every listed ticker | `third_party_cross_reference.md` | `fill_cross_check` + `check_cross_checks` |
| `insider_signal` (US CIK ticker) | `optionality_valuation.md` § Insider conviction | `fetch_insider_transactions` + `apply_insider_signal` in cloud refresh |
| Every ticker with `valuation.json` | `persona_lens_consensus.md` | `persona_lens.py` → `{TICKER}/research/lenses.json` + `lens_consensus` block |
| `lens_consensus.lawrence_divergence` | Milly + `[HUMAN REVIEW]` | compare consensus stance vs Lawrence gate |

**Do not** read the full `analysis_arsenal.md` unless onboarding or resolving a missing trigger.

## Source of truth

- Pipeline: `_system/frameworks/decision_stack.md`
- Framework rules: `_system/frameworks/framework_governance.md`
- Portfolio map: `_system/portfolio/classification.json`
- Per-ticker copy: `{TICKER}/research/thesis.md` → `## Classification` table
- Valuation + stance proposal: `{TICKER}/research/valuation.json`
- Dashboard: parsed by `_system/scripts/build_dashboard_data.py`
- Sync check: `python _system/scripts/sync_classification.py`

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
| **Implied 7yr IRR** (Lawrence) | … |
| **IRR method** | … |
| **Lawrence bucket** | … |
| **Valuation overlay** | … |
| **Payoff lens** | … |
| **MOI bucket** | … (optional legacy) |

## [HUMAN REVIEW]
…

## [PROPOSED MEMORY]
…
```

## Terms (this report) — optional glossary

After **Classification**, add when body text still uses short codes without spelling them out on first use:

```markdown
## Terms (this report)

| Term | Meaning here |
|------|----------------|
| Dhando | Asymmetric payoff (Pabrai): … |
| Croupier | Toll on transactions (Stahl): … |
| … | … |
```

List only terms used in that report. Skip if every framework term was defined in prose per `report_prose.md`.

## Dashboard display

- **Table column:** Archetype (primary badge)
- **Detail panel:** Moat · Dhando · Stance (+ Cycle when not `—`)
