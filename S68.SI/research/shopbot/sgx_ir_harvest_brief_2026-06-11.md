# S68.SI — Vicki IR harvest brief

**Date:** 2026-06-11  
**Ticker:** S68.SI (Singapore Exchange Limited)  
**IR root:** https://investorrelations.sgx.com/download-library

## Problem

Cloud agent downloaded `annual_report_fy2024.pdf` (3.3 MB) from links.sgx.com. Downloads from `investorrelations.sgx.com/static-files/*` time out from the cloud VM (FY2025 annual, Jan 2025 investor deck).

## Priority downloads

1. **FY2025 annual report** — `https://investorrelations.sgx.com/static-files/5d920b13-c5bb-4280-9b84-74025f006fc5` → `official-reports/annual-reports/annual_report_fy2025.pdf`
2. **Investor presentation (Jan 2025, FY2024 results)** — `https://investorrelations.sgx.com/static-files/da9d8d49-6e49-40e6-a937-1cc0b2bf4338` → `presentations-and-media/investor_presentation_jan2025_fy2024.pdf`
3. **H1 FY2026 results pack** — from download library (press release, financial results, presentation)

## After harvest

```bash
python _system/scripts/build_folder_indexes.py --ticker S68.SI
python _system/scripts/build_filing_evidence.py S68.SI
make milly-repass TICKER=S68.SI
```
