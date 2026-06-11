# TASE — IR harvest brief (Vicki)

**Date:** 2026-06-11  
**Ticker:** TASE  
**IR root:** https://www.tase.co.il/en/investor_relations  
**Financial reports:** https://www.tase.co.il/en/content/kne/financial_reports  

## Goal

Download FY2024 annual report PDF, FY2025 quarterly presentations, and latest investor presentation into:

```
TASE/official-reports/annual-reports/
TASE/presentations-and-media/
```

Update `TASE/document-index.csv` and append `TASE/_download_log.txt`.

## Context

Marvin first deep dive uses the company earnings press release (PR Newswire, 2025-03-04) because batch onboard skipped IR downloads. Cloud curl found zero PDF links on the financial reports page (likely JavaScript-rendered).

## Priority documents

1. Annual report FY2024 (Hebrew or English)
2. Q1 2025 / latest quarterly financial statements
3. Latest investor presentation deck

## After harvest

Re-run `python _system/scripts/build_filing_evidence.py TASE` and refresh owner cash from filed statements.
