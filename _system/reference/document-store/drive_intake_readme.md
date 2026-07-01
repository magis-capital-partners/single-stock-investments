# Drive Intake

Use this Shared Drive folder as the repo drop zone:

- Folder: https://drive.google.com/drive/folders/1wWZpAvlH5AANn76nRoklTK8IXf5gyPnR
- Label: Single Stock Research PDF Store
- Service account: `pdf-store-uploader@single-stock-pdf-store.iam.gserviceaccount.com`
- Workflow: `Drive Intake Sync` runs hourly at minute 20 UTC and can also be run manually.

The current Drive layout is flat by intake type:

```text
Admin/
  VIC/
    TPL.pdf
    FRMO.pdf
  Research/
    TPL.pdf
  Company/
    TPL.pdf
```

## Where To Drop PDFs

Ticker subfolders are also accepted:

```text
Admin/
  VIC/
    TPL/
      VIC writeup.pdf
  Research/
    TPL/
      outside report.pdf
  Company/
    TPL/
      company presentation.pdf
  Activist/
    Long/
      DIS/
        elliott-proxy-letter.pdf
    Short/
      APLD/
        hindenburg-report.pdf
```

Use the exact repo ticker folder name, for example `TPL`, `FRMO`, `0388.HK`, or `TEQ.ST`.

For the flat layout, put the ticker as the filename or as the first clear filename token, such as `TPL.pdf` or `TPL - outside report.pdf`.

## Routing

- `Admin/VIC/{TICKER}.pdf` imports to `{TICKER}/third-party-analyses/vic/`
- `Admin/Research/{TICKER}.pdf` imports to `{TICKER}/third-party-analyses/drive-intake/`
- `Admin/Company/{TICKER}.pdf` imports to `{TICKER}/investor-documents/drive-intake/`
- `Admin/Activist/Long/{TICKER}/*.pdf` imports to `{TICKER}/third-party-analyses/activist_reports/long/`
- `Admin/Activist/Short/{TICKER}/*.pdf` imports to `{TICKER}/third-party-analyses/activist_reports/short/`

The legacy `Admin/Intake/{VIC,Research,Company}/{TICKER}/*.pdf` layout is still accepted.

After local import, the normal registry/upload step links the PDFs back into the PDF store folders used by the dashboard:

- VIC: `Single Stocks/{TICKER}/VIC/`
- Research: `Single Stocks/{TICKER}/Research/drive-intake/`
- Company: `Single Stocks/{TICKER}/Company/drive-intake/`
- Activist long: `Single Stocks/{TICKER}/Activist/long/`
- Activist short: `Single Stocks/{TICKER}/Activist/short/`

## Automation Flow

1. Drop PDFs into the appropriate Drive intake folder.
2. `Drive Intake Sync` scans the configured intake folder/root, creates missing intake folders, and imports new PDFs.
3. Each imported PDF gets a `.source.json` sidecar with Drive source metadata.
4. `_system/data/drive_intake_manifest.json` records Drive file IDs so the same file is not imported again.
5. The workflow rebuilds the third-party source inventory, document registry, Drive PDF links, insights, research memory, and dashboard data.
6. Letter source links use `_system/reference/document-store/drive_filename_index.json` (full Shared Drive PDF scan) and `_system/reference/document-store/letter_drive_links.json` (maps `letters_index.json` paths to Drive file URLs). These refresh during Drive Intake Sync when credentials are present.
7. The workflow commits the imported documents and rebuilt dashboard artifacts back to `main`.

## Required GitHub Secret

Drive folder access alone is not enough for GitHub Actions. The repo also needs an Actions secret named `GOOGLE_APPLICATION_CREDENTIALS_JSON` containing the full JSON key for `pdf-store-uploader@single-stock-pdf-store.iam.gserviceaccount.com`.

## Rules

- Upload PDFs only.
- Leave files in Drive after upload; the manifest prevents duplicate imports.
- Use existing repo tickers. Unknown ticker folders or filenames are reported in `_system/reference/document-store/drive_intake_latest.json`.
- Use `VIC` only for Value Investors Club writeups; use `Research` for other outside research PDFs; use `Company` for company presentations or manually collected company PDFs; use `Activist/Long` or `Activist/Short` for activist letters, proxy fights, and forensic short reports.
