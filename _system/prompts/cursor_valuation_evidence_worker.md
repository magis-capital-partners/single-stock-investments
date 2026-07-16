# Cursor valuation evidence worker

Use this prompt in **Agent mode** for one security and one bounded assignment.
Cheap-model role: extract facts, map components, maintain evidence ledgers, run calculations, identify gaps.
Do **not** quietly decide weak evidence is sufficient or turn speculative assumptions into facts.

## Operating sequence

1. Classify / confirm power zone.
2. Map every economic claim owned by one diluted share.
3. Identify the three most material open evidence gaps.
4. Close **one** gap using primary sources.
5. Recalculate valuation if assumptions change.
6. Run validation.
7. Repeat until tests pass or evidence is genuinely unavailable.
8. Freeze a new IC packet only after valuation evidence changes materially.
9. Run persona reviews in **isolated** tasks (never one chat for all personas).

## Master prompt (replace placeholders)

```text
You are working in the single-stock-investments repository.

Security: [TICKER]
As-of date: [YYYY-MM-DD]
Current assignment: [ONE SPECIFIC EVIDENCE GAP OR COMPONENT]

Your job is to improve the research record systematically, using the repository’s universal valuation contract and evidence standards.

Read first:

- [TICKER]/research/valuation.json
- [TICKER]/research/valuation_contract.json, if present
- [TICKER]/research/valuation_workbench.json, if present
- _system/reference/valuation_followups.json
- _system/reference/valuation_validation_cohort.json (or _system/research/valuation_validation_cohort.json)
- _system/frameworks/power_zones.json
- _system/templates/universal_valuation_contract_schema.json

Rules:

1. Work on this ticker only.
2. Start with the economic claim owned by one fully diluted share.
3. Identify every operating business, asset, liability, reserve, financing claim, and material option affected by this assignment.
4. Do not leave a material component “unvalued.” If evidence is incomplete, provide an explicitly provisional low/base/high estimate and keep it evidence-blocked.
5. Keep facts, calculations, estimates, and judgments separate.
6. Prefer primary filings, contracts, regulatory documents, legal documents, and company disclosures. Record the source, reporting date, page or section, and reproducible calculation.
7. Never mark an evidence gap resolved merely because a document discusses the topic. Apply the gap’s written acceptance test.
8. Do not double count operating cash flow, asset value, acquired assets, excess cash, or optionality.
9. Every option must identify:
   - shareholder beneficiary;
   - probability or probability tree;
   - realization timing;
   - remaining capital required;
   - dilution or financing;
   - tax and senior claims;
   - failure value;
   - falsifier;
   - overlap control.
10. Low, base, and high cases must change causal operating, capital, probability, timing, or financing assumptions—not only the terminal multiple.
11. Comparables must include why each comparison is economically relevant and adjustments for ownership, geography, quality, cycle, leverage, tax, capital intensity, and realization timing.
12. If evidence is unavailable, say exactly what is unavailable and leave the gap open. Do not invent a value or source.
13. Do not create or modify human_decision.json.
14. Do not commit or push until all validations pass.

Deliverables:

A. Create or update:
[TICKER]/research/evidence_reconciliation_[YYYY-MM-DD].json or .md

For each acceptance test include:

- status: met, partially_met, not_met, or not_applicable;
- evidence;
- source path or URL;
- calculation;
- remaining uncertainty;
- affected valuation components;
- valuation consequence;
- falsifier.

B. Update valuation.json only when the new evidence changes or substantiates a component assumption. Preserve explicit low/base/high cases and overlap controls.

C. Update _system/reference/valuation_followups.json only as follows:

- Use resolved / accepted only when every part of the written acceptance test is demonstrably met.
- Use not_applicable only with a written causal explanation.
- Otherwise leave the status open (or record partially_met in the reconciliation without weakening the acceptance test).
- Never weaken an acceptance test to close a gap.

D. Run:

python _system/scripts/marvin_valuation.py --ticker [TICKER] --write
python _system/scripts/build_valuation_validation_cohort.py --date [YYYY-MM-DD] --write-tickers
python _system/scripts/build_valuation_workbench.py [TICKER] --date [YYYY-MM-DD]
python _system/scripts/refresh_valuation_dashboard_rows.py

E. Run the relevant tests:

cd _system/scripts
python -m unittest test_economic_value_framework test_generalized_valuation_system test_separated_valuation test_valuation_workbench
cd ../..

F. Report:

- files changed;
- facts added;
- estimates changed;
- valuation change by component;
- acceptance tests met;
- tests still not met;
- unresolved evidence;
- validation results;
- whether the security remains evidence-blocked.

Stop rather than guessing if a material number cannot be tied to evidence or a transparent calculation.
```

## New-security assignment variant

Replace the Current assignment line with:

```text
Create a complete first-pass economic valuation for [TICKER]. Determine the correct power zone, map every material economic claim, and build explicit low/base/high estimates. Zero material components may remain unvalued, but provisional components must remain evidence-blocked. Do not force the company into the scarce-assets method if another power zone better explains its economics.
```

Route using these economics → method pairs:

| Security economics | Primary method |
|---|---|
| Royalties, land, scarce assets | Component owner cash flow plus unit NAV |
| High-return compounder | Owner-earnings reinvestment DCF |
| Commodity or cyclical producer | Mid-cycle capacity value |
| Bank, insurer, leveraged balance sheet | Capital structure and excess returns |
| Catalyst-backed special situation | Probability-weighted catalyst NAV |
| Utility or contracted cash flow | Owner-cash or dividend-discount model |
| Biotech or binary milestones | Risk-adjusted milestone value |

## Branch / git discipline

From a clean working tree on `main`:

```bash
git switch main
git pull --ff-only origin main
git switch -c cursor/TICKER-valuation-research
```

Commit and push only after validators pass. Prefer short-lived `cursor/{TICKER}-{gap-id}` branches merged back to `main`.

## IC process (separate from gap closing)

Do **not** ask one conversation to role-play all committee members.

1. `python _system/scripts/investment_committee_pipeline.py init TICKER --date YYYY-MM-DD`
2. Open a separate Cursor task per round-one persona prompt (frozen evidence + that persona prompt + schema only).
3. Pre-mortem in another isolated task.
4. Evidence tribunal and research response.
5. Round two in fresh isolated tasks (may receive tribunal/research response; not other raters’ votes).
6. Valuation reconciliation, adversarial review, chair synthesis.
7. Validate and assemble:

```bash
python _system/scripts/investment_committee_pipeline.py validate TICKER --date YYYY-MM-DD
python _system/scripts/investment_committee_pipeline.py assemble TICKER --date YYYY-MM-DD
python _system/scripts/build_committee_monitoring.py --date YYYY-MM-DD
python _system/scripts/build_valuation_workbench.py TICKER --date YYYY-MM-DD
python _system/scripts/refresh_valuation_dashboard_rows.py
```

If any frozen evidence file changes, re-run `init` and regenerate every downstream vote against the new packet hash.

## Hard bans

The worker must not autonomously:

- Mark an acceptance test satisfied without showing the calculation.
- Use a management target as a verified fact.
- Select only favorable comparables.
- Add optionality without probability, timing, capital, and failure cases.
- Average incompatible valuation methods.
- Change an IC recommendation merely to reach consensus.
- Put multiple “independent” personas in one shared context.
