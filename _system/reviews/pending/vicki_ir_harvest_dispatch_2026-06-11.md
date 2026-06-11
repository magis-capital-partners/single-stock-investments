# Vicki IR harvest dispatch — TASE + S68.SI

**Date:** 2026-06-11  
**Queue:** `_system/data/vicki_dispatch_queue.json`  
**Workflow:** `.github/workflows/vicki-ir-harvest.yml`  
**Trigger:** push queue file to `main` (or manual `workflow_dispatch`)

## Tickers

| Ticker | Gap | Brief |
|--------|-----|-------|
| TASE | Maya PDF 403 from cloud | `TASE/research/shopbot/vicki_brief_2026-06-11.md` |
| S68.SI | SGX static-files timeout | `S68.SI/research/shopbot/vicki_brief_2026-06-11.md` |

## Expected outcome

Vicki cloud agents open PRs with:
- Official PDFs in `official-reports/` and `presentations-and-media/`
- Updated `document-index.csv`, `_download_log.txt`
- `vicki_session_2026-06-11.md` shopbot log
- `.onboard_status.json` `download_detail` → `complete` when ≥2 full-tier PDFs land

## Manual re-trigger

```bash
gh workflow run vicki-ir-harvest.yml -f tickers=TASE,S68.SI
```
