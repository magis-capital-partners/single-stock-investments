# Filing-grounded deep dive refresh

Use when `build_filing_evidence.py` has run for the ticker.

## Required inputs (read in order)

1. `{TICKER}/research/evidence/filing_digest_{date}.md`
2. `{TICKER}/research/evidence/document_inventory.json`
3. `{TICKER}/research/evidence/_text/*.txt` for every **full**-tier document
4. `{TICKER}/research/valuation.json`
5. Prior `deep_dive_2026-05-26.md` (stance, blends, approved Substacks — carry forward unless filings contradict)
6. `_system/prompts/deep_dive_template.md`, `_system/frameworks/report_prose.md`, `decision_stack.md`

## Output

- Write **`{TICKER}/research/deep_dive_2026-05-27.md`** (do not delete prior dive; set **Prior dive:** link)
- Update **`{TICKER}/research/thesis.md`** if metrics/stance change

## Mandatory section: Primary sources reviewed

```markdown
## Primary sources reviewed

All documents in `{TICKER}/INDEX.csv` are inventoried in `research/evidence/document_inventory.json` ({N} files).

| Tier | Period / type | Path | Role in this report |
|------|---------------|------|---------------------|
| full | FY2025 annual | `investor-documents/...` | Balance sheet, related-party lease, Investment A % |
| full | Q3 FY2026 quarterly | `...` | Latest assets, equity, MIH fair value |
| partial | ... | ... | Trend / cross-check |
| inventory | ... | ... | Listed; not extracted (certification only) |

**Fieldwork / management** must cite **full-tier** paths for lease, compensation, governance — not “public narrative” alone.
```

## Rules

- **[Fact]** = from full or partial tier extract with path in same sentence or table Evidence column
- **[Inference]** = your conclusion; still anchor to a filing when possible
- Numbers: prefer **latest full-tier quarterly** for flow; **latest annual** for governance/related-party
- If digest shows **late filing** or restatement, mention in risks
- Japan tickers (3905.T, 8697.T): note if PDF text extract failed; use available partial/scan snippets + INDEX
- After write: `python _system/scripts/lint_deep_dive.py {TICKER}`
- If owner cash / price changed: `python _system/scripts/marvin_valuation.py --ticker {TICKER} --write`
