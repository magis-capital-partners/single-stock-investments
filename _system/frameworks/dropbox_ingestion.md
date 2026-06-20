# Dropbox Research Ingestion

This pipeline ingests the two Dropbox research folders into a source-preserving local library:

- `stahl_private` - password-protected Stahl/Horizon Kinetics folder.
- `sumzero_ideas` - shared SumZero Ideas folder.

Run:

```powershell
python _system/scripts/dropbox_ingest.py --stahl-password stahl
```

If Dropbox blocks direct archive download for a password-protected folder, download the folder zip manually in the browser and point the ingest script at it:

```powershell
python _system/scripts/dropbox_ingest.py --archive stahl_private=C:\path\to\stahl.zip
```

## Storage Contract

Raw Dropbox files are kept immutable and local only:

```text
_system/dropbox_ingestion/00_sources/dropbox/<source>/archive/
_system/dropbox_ingestion/00_sources/dropbox/<source>/raw/
```

Regenerable retrieval artifacts are committed:

```text
_system/dropbox_ingestion/01_library/
_system/dropbox_ingestion/02_processed/
_system/dropbox_ingestion/03_index/
_system/dropbox_ingestion/04_summaries/
```

## Retrieval Model

The manifest is the audit spine:

```text
_system/dropbox_ingestion/03_index/manifest.jsonl
```

Each row records source folder, original Dropbox path, local raw path, file metadata, SHA-256 hash, parse status, document type, guessed ticker/company, guessed date, theme tags, and derived text/table paths.

The SQLite index includes:

- `documents` - metadata table.
- `document_fts` - full-text search over extracted text.

Useful query example:

```powershell
python - <<'PY'
import sqlite3
db = sqlite3.connect("_system/dropbox_ingestion/03_index/documents.sqlite")
for row in db.execute("select title, sha256 from document_fts where document_fts match 'catalyst NEAR valuation' limit 20"):
    print(row)
PY
```

## Summary Layers

The script writes:

- document summaries in `04_summaries/by_document/`;
- ticker/company summaries in `04_summaries/by_company/`;
- theme summaries in `04_summaries/by_theme/`;
- ingestion coverage reports in `04_summaries/ingestion_reports/`.

The summaries are heuristic, not final investment conclusions. They are meant to make the corpus navigable and to surface thesis, valuation, catalyst, and risk language for deeper research.
