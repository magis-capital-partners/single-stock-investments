# Superinvestor letters

Structured hedge-fund letter corpus for Insights ? Letters / Funds / Consensus.

## Canonical source: Google Drive

All letter PDFs live in the shared PDF store under `Letters/{YYYY Qn}/` (folder id in `google_drive_config.json` ? `hedge_fund_letters`).

Import into this repo:

```powershell
# Preview counts by quarter
python _system/scripts/import_drive_letter_orphans.py --all --dry-run

# Full import + text extract + insights build
make letter-import-drive

# Or since a given year only
python _system/scripts/import_drive_letter_orphans.py --since-year 2023 --all --build
```

Requires `GOOGLE_APPLICATION_CREDENTIALS` for `pdf-store-uploader@single-stock-pdf-store.iam.gserviceaccount.com`, or place the key at `_secrets/google-service-account.json`.

## Local layout

| Path | Committed | Role |
|------|-----------|------|
| `{YYYY}Q{n}/*.pdf` | No (gitignored) | Raw letter PDFs |
| `{YYYY}Q{n}/*.txt` | Yes | Text extracts for matching |
| `insights.json` | Yes | Parsed letter records |
| `letters_index.json` | Yes | Compact index |
| `drive_import_manifest.json` | Yes | Drive file id ? local path map |
| `funds.json` | Yes | Curated fund identity overrides |
| `sources.json` | Yes | Optional Dropbox zip URLs for new quarters |

## Build pipeline

```powershell
python _system/scripts/build_superinvestor_insights.py
python _system/scripts/build_insights.py
python _system/scripts/build_document_registry.py
python _system/scripts/build_dashboard_data.py
```

Or: `make letter-backfill` (import + full rebuild + Drive link refresh).

## Optional: Dropbox fetch

If a new quarter arrives as a Dropbox zip, add an entry to `sources.json` and run:

```powershell
make persona-fetch-letters
```
