# Cloud Vicki — IR harvest runbook

**Ticker:** {{TICKER}} · **Date:** {{date}} · **Reason:** {{PICK_REASON}}

You are **Vicki** (browser / shopbot analyst). Read `_system/agents/VICKI.md`.

## Mission

Complete the IR PDF harvest for **{{TICKER}}** where Marvin's curl/urllib pipeline failed (`download_detail: ir_gap`). Use interactive browser navigation when IR sites are JavaScript-rendered or block datacenter IPs.

## Before you start

1. Read `{TICKER}/README.md` and `{TICKER}/research/shopbot/` (latest `*brief*.md` or `vicki_brief_*.md`).
2. Read `{TICKER}/.onboard_status.json` — confirm `download_detail` is `ir_gap`.
3. Do **not** overwrite or delete existing official PDFs.

## Harvest steps

1. Open the IR root URL from the shopbot brief (browser required for JS sites).
2. Download priority PDFs into the paths specified in the brief:
   - EU scaffold: `official-reports/annual-reports/`, `presentations-and-media/`
   - Or `investor-documents/ir-{ticker}/` per US template
3. Verify each file is a real PDF (`%PDF` magic bytes, size > 5 KB).
4. Append every attempt to `{TICKER}/_download_log.txt` with ISO timestamp.
5. Update `{TICKER}/document-index.csv` (and `INDEX.csv` if present).
6. Write `{TICKER}/research/shopbot/vicki_session_{{date}}.md` with URLs, timestamps, and any blockers.

## After harvest (mechanical)

```bash
python _system/scripts/build_folder_indexes.py --ticker {{TICKER}}
python _system/scripts/build_filing_evidence.py {{TICKER}}
python _system/scripts/update_onboard_download_status.py
```

If at least one full-tier PDF landed, set `{TICKER}/.onboard_status.json`:
- `download_detail`: `complete` (or `partial` with note if only 1 of 3 targets)
- `vicki_completed`: `{{date}}`

## Success criteria

- At least **2 full-tier** filing extracts for `build_filing_evidence.py`, **or**
- Document in shopbot session why the site blocks automation and what human step is needed.

## Output

Open a PR with downloaded PDFs, updated indexes, shopbot session log, and onboard status. Do **not** rewrite Marvin deep dives unless filing evidence materially changes owner cash.
