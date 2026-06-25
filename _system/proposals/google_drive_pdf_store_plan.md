# Google Drive PDF Store Plan

## Goal

Use one Google Shared Drive as the canonical store for raw PDFs, while Git remains the canonical store for metadata, text extracts, indexes, and dashboard data.

Shared Drive root:

```text
0AFpaOm4iTLqjUk9PVA
```

Service account:

```text
pdf-store-uploader@single-stock-pdf-store.iam.gserviceaccount.com
```

## Routing Policy

The registry keeps two logical roots for clarity, but both point to the same Shared Drive:

- `hedge_fund_letters` for `_system/reference/superinvestor-letters/**/*.pdf`
- `general_pdfs` for company documents, third-party research, VIC, SumZero extracts, Dropbox ingestion, research PDFs, and uncategorized PDFs

The generated registry records either logical key with:

```json
{
  "drive_root_folder_id": "0AFpaOm4iTLqjUk9PVA"
}
```

## Link Resolution Policy

Dashboard source links resolve in this order:

1. Google Drive PDF viewer link from `dashboard/data/document_registry.json`.
2. GitHub text extract, when the PDF has not been uploaded yet.
3. Original article URL for web-native sources.
4. GitHub source/index file for non-PDF evidence.
5. No PDF link when the local PDF is missing and no text fallback exists.

This prevents GitHub 404s for ignored local-only PDFs and makes Drive the user-facing PDF destination once sync is complete.

## Upload Behavior

The sync script:

1. Loads `dashboard/data/document_registry.json`.
2. Preflights each configured root and confirms it is a writable Shared Drive location.
3. Mirrors the local source path inside the Shared Drive.
4. Searches the expected Drive folder for an existing matching PDF.
5. If not found there, searches accessible Drive files for the same filename and matching document ID or size.
6. Links the existing Drive file when found.
7. Uploads only when no match exists.
8. Writes `drive_file_id`, `drive_web_view_link`, `drive_web_content_link`, and `upload_status` back into the registry.

## Storage Layout

```text
0AFpaOm4iTLqjUk9PVA/
  superinvestor-letters/
    2026Q1/
    2026Q2/
  third-party-research/{TICKER}/...
  company-documents/{TICKER}/...
  dropbox-ingestion/...
  sumzero-research/{DOCUMENT_ID}/...
  uncategorized/...
```

## SumZero Intake

`build_sumzero_index.py` extracts PDF members from the local `SumZero Ideas.zip` archive into:

```text
_system/reference/sumzero-research/{DOCUMENT_ID}/{filename}.pdf
```

That folder is gitignored. The compact SumZero index stores `local_pdf_path` for each extracted PDF, and dashboard insights use that PDF path as evidence when available. The registry then uploads these PDFs under `sumzero-research/` in the Shared Drive.

## Operational Flow

1. Set `GOOGLE_APPLICATION_CREDENTIALS` to the service-account JSON file.
2. Refresh SumZero staging and index:

```text
python _system/scripts/build_sumzero_index.py
```

3. Build the PDF registry:

```text
python _system/scripts/build_document_registry.py
python _system/scripts/audit_document_registry.py
```

4. Sync PDFs to Drive:

```text
python _system/scripts/sync_pdf_store_google_drive.py --root-key hedge_fund_letters
python _system/scripts/sync_pdf_store_google_drive.py --root-key general_pdfs
```

5. Rebuild dashboard links:

```text
python _system/scripts/build_insights.py
python _system/scripts/build_research_memory.py
python _system/scripts/build_dashboard_data.py
```

6. Audit Drive after upload:

```text
python _system/scripts/audit_drive_pdf_store.py
```

7. Remove duplicate uploads (keep registry-linked canonical files):

```text
python _system/scripts/dedupe_drive_pdf_store.py --dry-run
python _system/scripts/dedupe_drive_pdf_store.py
python _system/scripts/audit_drive_pdf_store.py --strict
```

## Git Policy

Commit:

- text extracts
- document registry
- generated dashboard data
- Drive config
- routing, sync, audit, and dedupe scripts
- SumZero compact index

Do not commit:

- raw PDFs
- OAuth tokens
- service-account credentials
