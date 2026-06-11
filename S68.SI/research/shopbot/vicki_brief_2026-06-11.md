# Vicki brief — S68.SI IR harvest

**Date:** 2026-06-11  
**Status:** dispatched (`_system/data/vicki_dispatch_queue.json`)  
**Ticker:** S68.SI (Singapore Exchange Limited)  
**IR root:** https://investorrelations.sgx.com/download-library  

## Problem

`investorrelations.sgx.com/static-files/*` URLs **time out** from cloud VM (120s). Prior successful download of FY2024 annual from `links.sgx.com` is no longer on disk.

## Priority downloads

| Label | URL | Target path |
|-------|-----|-------------|
| FY2025 annual report | `https://investorrelations.sgx.com/static-files/5d920b13-c5bb-4280-9b84-74025f006fc5` | `official-reports/annual-reports/annual_report_fy2025.pdf` |
| FY2024 financial statements | `https://investorrelations.sgx.com/static-files/634d5dd6-260a-4d66-ba38-3502fbe92587` | `official-reports/annual-reports/financial_statements_fy2025.pdf` |
| Investor presentation Jan 2025 | `https://investorrelations.sgx.com/static-files/da9d8d49-6e49-40e6-a937-1cc0b2bf4338` | `presentations-and-media/investor_presentation_jan2025_fy2024.pdf` |

Also harvest **H1 FY2026 results pack** from the download library if published.

## Browser notes

- Use SGX investor relations site with Referer `https://investorrelations.sgx.com/`.
- Alternative: browse download-library and save PDFs manually if static-file URLs fail.
- Existing HTML extract: `official-reports/annual-reports/fy2025_annual_report_ir_extract.html` (partial; upgrade to PDF).

## After harvest

```bash
python _system/scripts/build_folder_indexes.py --ticker S68.SI
python _system/scripts/build_filing_evidence.py S68.SI
python _system/scripts/update_onboard_download_status.py
```
