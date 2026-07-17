# Vicki brief: Pinelawn Cemetery (PLWN)

**Date:** 2026-07-17  
**Priority:** High for research unblock  
**Ticker folder:** `PLWN/`

## Why blocked

Automated US SEC/IR download returned **0 PDFs**. Pinelawn is a **501(c)(13) cemetery company** (EIN 11-1190044) trading OTC as **PLWN**. It does not file ordinary 10-K/10-Q packages. Primary financials are **IRS Form 990** returns, not EDGAR.

## Ask

1. Download latest Form 990 PDFs (last 5 years if available) from ProPublica Nonprofit Explorer or IRS Tax Exempt Organization Search for EIN **11-1190044**.
2. Capture any shareholder circulars, dividend notices, or OTC Markets disclosure pages for PLWN.
3. Save into `PLWN/investor-documents/ir-plwn/` (or `form-990/`) and append paths to `PLWN/_download_log.txt`.
4. Note latest dividend ($45.40 indicated on Yahoo as of early 2026) and any share count / book figures found.

## Company site

- Operating site: https://www.pinelawn.com (may have little investor content)
- ProPublica: https://projects.propublica.org/nonprofits/organizations/111190044

## Done when

At least one recent Form 990 PDF is local and `python _system/scripts/build_filing_evidence.py PLWN` inventories it.
