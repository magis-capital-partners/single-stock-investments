# Drive Reorg and Insights Wiring Plan

Date: 2026-06-25

## Current Ground Truth

- The PDF registry has 5,847 documents, 5,847 uploaded, and 0 pending uploads.
- Source mix is approximately 3,467 company documents, 936 SumZero PDFs, 189 letters, 68 third-party PDFs, 6 research PDFs, and 1,181 uncategorized PDFs.
- The latest Drive audit reports 25,547 PDFs in the Shared Drive, but only 5,847 are registry-linked. It also reports 19,697 orphan PDFs and 19,700 PDFs missing `sha256` app properties.
- The latest dedupe report identified 5,586 duplicate trash candidates from 4,248 duplicate groups.
- `build_document_registry.py` has already been edited toward the intended target layout:
  - `letters/{YYYY Qn}`
  - `single-stocks/{TICKER}/company`
  - `single-stocks/{TICKER}/vic`
  - `single-stocks/{TICKER}/research`
  - `single-stocks/{TICKER}/sumzero`
  - `sumzero/{slug}` for unmatched SumZero items
- `dashboard/insights-viz.js` has already been partly rewired to restore Letters and Funds sections and build quarter tabs from both `theme_rankings_by_quarter` and `letter_index`.

The main risk is that changing `drive_folder_path` alone does not move existing Drive files. The sync script can find an existing file by sha anywhere in Drive, link it, and leave it in its old parent folder. A Drive parent migration step is required.

## Target Drive Layout

Use one Shared Drive, renamed if possible to `Single Stock Research PDF Store`.

```text
Single Stock Research PDF Store/
  Letters/
    2026 Q2/
    2026 Q1/
    2025 Q4/
  Single Stocks/
    AMZN/
      Company/
      Filings/
      VIC/
      SumZero/
      Research/
    ICE/
      Company/
      Filings/
      VIC/
      SumZero/
      Research/
  Research Sources/
    SumZero Unmatched/
    Dropbox Ingestion/
    Investment Wisdom/
    Uncategorized/
  Admin/
    Migration Reports/
    Quarantine - Review Before Delete/
```

Rules:

- No top-level `superinvestor-letters`, `company-documents`, `third-party-research`, or `sumzero-research` folders after migration.
- Keep local `_system/reference/superinvestor-letters` as the source text/index folder. Do not delete it; only remove or rename the redundant Drive folder.
- File IDs should remain stable wherever possible by moving files between parents instead of re-uploading.
- Destructive operations happen in two steps: move to quarantine/trash first, then permanently delete only after a second audit.

## Phase 0 - Freeze and Inventory

1. Stop new Drive uploads during the migration window.
2. Build a fresh registry and dashboard payload:

```text
python _system/scripts/build_sumzero_index.py
python _system/scripts/build_document_registry.py
python _system/scripts/build_insights.py
python _system/scripts/build_dashboard_data.py
```

3. Run a fresh Drive audit and dedupe dry run:

```text
python _system/scripts/audit_drive_pdf_store.py --json
python _system/scripts/dedupe_drive_pdf_store.py --dry-run --json
```

4. Produce a folder inventory, not just a PDF inventory. Add a new dry-run script:

```text
python _system/scripts/plan_drive_reorg.py --json
```

The report should list every folder, parent, child count, registry-linked PDF count, orphan PDF count, duplicate PDF count, and proposed action.

## Phase 1 - Canonical Path Mapping

Finalize the path mapping in `build_document_registry.py`:

- Letters: `_system/reference/superinvestor-letters/2026Q1/*.pdf` -> `Letters/2026 Q1`
- Company docs: `{TICKER}/investor-documents/...` -> `Single Stocks/{TICKER}/Company/...`
- VIC: `{TICKER}/third-party-analyses/vic/...` -> `Single Stocks/{TICKER}/VIC`
- Other third-party research: `{TICKER}/third-party-analyses/...` -> `Single Stocks/{TICKER}/Research/...`
- Matched SumZero: `_system/reference/sumzero-research/{TICKER}/{slug}/*.pdf` -> `Single Stocks/{TICKER}/SumZero/{slug}`
- Unmatched SumZero: `_system/reference/sumzero-research/_unmatched/{slug}/*.pdf` -> `Research Sources/SumZero Unmatched/{slug}`
- Uncategorized PDFs: `Research Sources/Uncategorized/...`

Update `google_drive_config.json` labels to match the new single-root mental model. The two logical roots can remain internally for source-type routing, but their labels should stop saying "Hedge Fund Letters PDF Hub".

## Phase 2 - SumZero Renaming

The current random SumZero folders are document IDs. Replace those with deterministic, human-readable slugs:

```text
{TICKER}/{YYYY-MM-DD}-{idea-title-slug}/
_unmatched/{YYYY-MM-DD}-{idea-title-slug}/
```

Collision rule:

```text
{YYYY-MM-DD}-{idea-title-slug}-{doc_id_prefix}
```

Implementation requirements:

- Keep the SumZero document ID in `sumzero_ideas_index.json`.
- Keep `sha256` as the stable identity for dedupe and Drive linking.
- Rebuild `document_registry.json` after paths change.
- Generate a local rename manifest before moving any files:

```text
_system/reference/document-store/sumzero_rename_manifest.json
```

The manifest should include old local path, new local path, old Drive parent, target Drive parent, document ID, sha256, title, ticker match, and confidence.

## Phase 3 - Drive Migration Script

Add a migration script that moves existing files and folders into the canonical layout:

```text
python _system/scripts/migrate_drive_pdf_store_layout.py --dry-run
python _system/scripts/migrate_drive_pdf_store_layout.py --apply
```

Required behavior:

- Read `dashboard/data/document_registry.json`.
- Resolve or create each target folder.
- For each registry-linked file, compare actual Drive parents to target folder.
- If the file is in the wrong folder, call Drive `files.update` with `addParents` and `removeParents`.
- Preserve `drive_file_id`, `drive_web_view_link`, `sha256`, and `document_id`.
- Write a migration report under `_system/reference/document-store/drive_layout_migration_report.json`.
- Never delete files in the same pass that moves files.

After `--apply`, rerun:

```text
python _system/scripts/audit_drive_pdf_store.py --json
python _system/scripts/build_document_registry.py
```

## Phase 4 - Redundant Folder Cleanup

Only after Phase 3 passes:

1. Mark top-level legacy folders as cleanup candidates:
   - `superinvestor-letters`
   - `company-documents`
   - `third-party-research`
   - `sumzero-research`
   - duplicate copied folders with the same subtree content
2. Empty folders can be trashed immediately in dry-run/apply form.
3. Non-empty folders go to `Admin/Quarantine - Review Before Delete` unless every child file is both:
   - registry-linked somewhere else by the same sha, and
   - present under the canonical target path.
4. Run dedupe only after folder migration:

```text
python _system/scripts/dedupe_drive_pdf_store.py --dry-run
python _system/scripts/dedupe_drive_pdf_store.py
python _system/scripts/audit_drive_pdf_store.py --strict
```

Do not permanently delete the `superinvestor-letters` Drive folder until the audit shows zero registry-linked files and zero unique orphan files under it.

## Phase 5 - Website and Dashboard Rewiring

The static website should not live-query Drive folders. It should read the generated JSON catalog, because that keeps the dashboard fast and avoids auth problems.

Data changes:

- Add a slim `document_catalog` to dashboard data or lazy-load `dashboard/data/document_catalog.json`.
- Fields: `document_id`, `title`, `ticker`, `source_type`, `quarter`, `drive_folder_path`, `drive_web_view_link`, `modified_at`, `size_bytes`.
- Do not embed the full registry in `dashboard_data.json`; keep the heavy registry as a separate file.
- Add `pdf_store` to `source_health` with document count, uploaded count, orphan count, duplicate count, and latest audit timestamp.

Insights UI changes:

- Keep the restored Letters and Funds sections.
- Default the quarter filter to the latest populated quarter, but visibly warn if that quarter has fewer than a threshold number of letters.
- Add a `PDF Library` section grouped by:
  - Letters
  - Single Stocks
  - Company
  - VIC
  - SumZero
  - Research Sources
- In ticker detail, use fixed context pills in this order:
  - Letters
  - Company
  - VIC
  - SumZero
  - Research
  - News
- Add a portfolio table PDF count/link column that opens `Single Stocks/{TICKER}` in Drive when available.

## Phase 6 - Letter Freshness

Fix stale quarters before relying on the new Letters UI:

```text
python _system/scripts/fetch_superinvestor_letters.py --quarter 2026Q2 --build
python _system/scripts/build_document_registry.py
python _system/scripts/sync_pdf_store_google_drive.py --root-key hedge_fund_letters
python _system/scripts/build_insights.py
python _system/scripts/build_dashboard_data.py
```

When the 2026 Q3 Dropbox source exists, add it to `_system/reference/superinvestor-letters/sources.json` and repeat the same flow.

## Acceptance Criteria

- `document_registry.summary.pending_upload_count == 0`.
- Every registry-linked PDF has exactly one canonical Drive parent.
- No registry-linked PDFs remain under legacy top-level folders.
- `audit_drive_pdf_store.py --strict` has no duplicate-sha groups and no registry-linked orphan problems.
- Legacy folders are empty or quarantined with a manifest.
- SumZero folders are readable by ticker/title, not random IDs.
- Insights shows Letters, Funds, PDF Library, and PDF Store source health.
- Q2 2026 letter count is no longer misleadingly low after the fetch/build flow.

## Recommended Execution Order

1. Finish and commit the local registry/SumZero path mapping already started.
2. Add `plan_drive_reorg.py` and `migrate_drive_pdf_store_layout.py` with dry-run reports.
3. Rebuild local data and generate migration manifests.
4. Review the dry-run reports manually.
5. Apply Drive file moves.
6. Re-audit.
7. Quarantine/trash redundant folders and duplicate PDFs.
8. Rebuild dashboard data.
9. Implement PDF Library and source-health UI polish.
10. Run final link checks from the dashboard.
