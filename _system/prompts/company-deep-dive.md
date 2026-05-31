# Company Deep Dive (legacy pointer)

Ticker: {{TICKER}} · Date: {{date}}

**Use the canonical cloud/local runbook instead of this file alone:**

- `_system/prompts/cloud_marvin_runbook.md` — full pipeline (evidence → narrative → `marvin_cloud_refresh.py`)
- `_system/frameworks/deep_dive_structure.md` — section order (v2)
- `_system/prompts/deep_dive_filing_grounded_refresh.md` — filing-grounded narrative rules

End state: `{{TICKER}}/research/deep_dive_{{date}}.md` + `valuation.json` + `adversarial_{{date}}.md`, synced via:

```bash
python _system/scripts/marvin_cloud_refresh.py {{TICKER}} --date {{date}}
```
