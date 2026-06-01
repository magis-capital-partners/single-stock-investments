# Deep dive structure (single source of truth)

**Purpose:** One place for *what sections exist* and *what not to repeat*. Voice lives in `report_prose.md`; pipeline in `decision_stack.md`; IRR detail in `irr_assumption_ledger.md` + `lawrence_irr.md`.

**Template:** `_system/prompts/deep_dive_template.md`  
**Lint:** `python _system/scripts/lint_deep_dive.py {TICKER}`

---

## Where rules live (no duplication)

| Question | Read this only |
|----------|----------------|
| What sections, what order | **This file** |
| IRR assumption ledger (repeatable) | `irr_assumption_ledger.md` |
| Analysis order | `decision_stack.md` |
| Voice / plain English | `report_prose.md` |
| Valuation readable by archetype | `archetype_valuation_prose.md` |
| IRR formulas | `lawrence_irr.md` § F |
| Third-party approval | `third_party_sources.md` |
| Approved Substacks | `approved_substacks.md` |
| Option treatment ladder | `option_treatment.md` |
| MOI idea lens | `analysis_arsenal.md` (tools); `moi_lens.md` (legacy map) |
| Cursor pointers | `.cursor/rules/investment-frameworks.mdc` + `marvin-core.mdc` + `optionality-valuation.mdc` |

---

## Report outline (required order)

| # | Section | Say once |
|---|---------|----------|
| 1 | Header links | date, prior dive, `valuation.json`, evidence digest, third-party index, **`adversarial_{date}.md` (Milly, required)** |
| 2 | **What this business is** | ≤5 sentences — **company overview starts here** |
| 3 | **Why the market might be wrong** | Q5 in prose — predictive attribute; inefficiency; catalyst when `asset`/`event` |
| 4 | **Executive summary** | 120–180 words; **one** base IRR % — **no formulas** |
| 5 | **Primary sources reviewed** | Inventory table only (10-K, 10-Q, IR, approved/pending third party) |
| 6 | **Business & moat** | Stahl, mental models, Hohn mechanics — **no IRR, no valuation tables** |
| 7 | **Approved Substack** | Only if ticker in `approved_substacks.md` |
| 8 | **Blended estimate** | Only if approved/pending external view cited |
| 9 | **Payoff & return** | Gates, dhando, stance — **points to Valuation & IRR** |
| 10 | **Risks & inversion** | Primary risk + ≤3 bullets + **lens failure mode** if non-`operating` payoff lens |
| 11 | **Valuation & IRR (assumption ledger)** | **End of analysis** — ledger + segment build (if any) + IRR arithmetic |
| 12 | Footer | Classification, Terms, [HUMAN REVIEW], [PROPOSED MEMORY] |

---

## Business & moat (overview body)

| Subsection | Required | Do not include here |
|------------|----------|---------------------|
| What (Stahl + Lawrence bucket) | Yes | IRR %, payoff $ |
| Mental models | Yes | Duplicate Tier 2 + plain English |
| Business mechanics (Hohn) | Yes | snapshot, pillars, fieldwork, disruption |
| Moat (Munger) | Yes | Assumption ledger, IRR arithmetic |
| **Segment map** (multi-segment compounder) | If `segment_cashflow` overlay | Segment PV math — that lives in §11 |
| **Option scan** (all tickers) | **Yes** — `option_treatment.md` | Option PV math — that lives in §11 or overlay |
| Look-through / catalyst (holdco only) | If needed | Full SOTP math — that lives in §11 |

---

## Valuation & IRR (assumption ledger) — end of report

| Subsection | Required |
|------------|----------|
| Price today + method tag | Yes |
| **Assumption ledger (base case)** | Table: every input + source or **[Assumption]** |
| **IRR arithmetic (show your work)** | Numbered steps; no unexplained payoffs |
| **Upside / downside from price** | One line |
| **Returns statement** | One sentence; = exec summary % |
| SOTP / look-through tables | If `holding_co` / `optionality` |
| **Segment cash-flow build** | If `valuation_overlay: segment_cashflow` (GOOGL-style) |
| **Option scan table** | **Every dive** — in §6; options sized in §11 or `nav_overlay` |
| **Optionality overlay** | If `valuation_mode: optionality` or material options in scan |

**Removed from deep dives (do not regenerate):** `### Valuation bridge` tables with overlay rows; `### Growth explanation stress test (Popper / Deutsch)`; Deutsch checks; weight-scheme falsifier tables.

Spec: `irr_assumption_ledger.md`. JSON: `valuation.json` + `sotp_build` when SOTP; + `segment_build` when segment overlay.

---

## Deduplication rules

| Redundant pattern | Fix |
|-------------------|-----|
| IRR in Business & moat + at end | **End only** |
| Exec summary shows full math | One % in exec; math in §11 |
| Tier 2 + Mental models | **Mental models** only |
| Pending third party in base IRR | **[PENDING APPROVAL]**; not in `valuation.json` base |
| Bear/bull bridge table + scenarios in JSON | **JSON only** for sensitivity; one sentence in Payoff |

---

## Refresh workflow (all holdings)

```bash
python _system/scripts/build_filing_evidence.py {TICKER}
python _system/scripts/marvin_valuation.py --ticker {TICKER} --write
python _system/scripts/refresh_deep_dive_v2.py {TICKER}
python _system/scripts/lint_deep_dive.py {TICKER}
python _system/scripts/lint_adversarial.py {TICKER}
```

Milly adversarial pass after narrative: `{TICKER}/research/adversarial_{date}.md`.
