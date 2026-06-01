# Cross-Check Workflow (universe-wide)

Ticker: {{TICKER}}  
Date: {{date}}

You are Marvin. Cross-check **all** third-party sources against primary filings.

## Before writing

1. Run: `python _system/scripts/scan_third_party_sources.py {{TICKER}} --with-hk --date {{date}}`
2. Read: `{{TICKER}}/third-party-analyses/source_inventory_{{date}}.md`
3. Read every source listed (Substacks, PDFs, HK extracts, pending notes)
4. Read latest deep dive and filing digest

## Rules

- Do NOT anchor to external docs — re-derive from {{TICKER}}/ primary PDFs + frameworks/
- List: agreements, disagreements, missing data, **Synthesis (best estimate)**
- **Approved** sources: may inform blend per `external_view_blend.md`
- **Pending** sources: cite with **[PENDING APPROVAL]** only; not in base IRR
- If zero third-party sources: document Marvin floor only

## Output

Save to `{{TICKER}}/research/cross_check_third_party_{{date}}.md` (or `cross_check_{source}_{{date}}.md` when single-source).

Framework: `_system/frameworks/third_party_cross_reference.md`

Verify: `python _system/scripts/check_cross_checks.py {{TICKER}}`
