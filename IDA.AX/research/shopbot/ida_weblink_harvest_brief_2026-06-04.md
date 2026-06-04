# Vicki brief — IDA.AX Weblink ASX announcements

**Ticker:** IDA.AX (ASX: IDA)  
**Portal:** https://wcsecure.weblink.com.au/clients/indianaresources/  
**Date:** 2026-06-04

## Goal

Harvest PDFs not reachable via static scrape of `indianaresources.com.au`:

- Annual and half-year financial reports
- Material ASX announcements (capital return, Ntaka settlement, drilling)
- Corporate governance reports

## Save to

- `IDA.AX/investor-documents/official-reports/` — annual / half-year reports
- `IDA.AX/investor-documents/asx-announcements/` — ASX releases

## After harvest

```bash
python3 _system/scripts/build_folder_indexes.py --ticker IDA.AX
python3 _system/scripts/build_filing_evidence.py IDA.AX
```
