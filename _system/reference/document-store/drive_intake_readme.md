# Drive Intake

Use this folder structure in the Single Stock Research PDF Store Shared Drive:

```text
Admin/
  Intake/
    VIC/
      TPL/
        VIC writeup.pdf
      FRMO/
        another writeup.pdf
    Research/
      TPL/
        outside report.pdf
    Company/
      TPL/
        company presentation.pdf
```

The GitHub workflow `Drive Intake Sync` imports PDFs from those folders into the repo:

- `Admin/Intake/VIC/{TICKER}` -> `{TICKER}/third-party-analyses/vic`
- `Admin/Intake/Research/{TICKER}` -> `{TICKER}/third-party-analyses/drive-intake`
- `Admin/Intake/Company/{TICKER}` -> `{TICKER}/investor-documents/drive-intake`

Rules:

- Prefer one ticker folder per upload batch.
- Use the exact repo ticker, for example `TPL`, `FRMO`, `0388.HK`, `TEQ.ST`.
- Upload PDFs only.
- Leave files in Drive after upload; `_system/data/drive_intake_manifest.json` prevents re-importing the same Drive file.
- If a file is in `Admin/Intake/VIC` without a ticker folder, the importer tries to infer the ticker from the filename. Folder naming is more reliable.

After import, existing scripts rebuild:

- third-party source inventory
- document registry
- Google Drive PDF store links
- insights
- research memory
- dashboard data
