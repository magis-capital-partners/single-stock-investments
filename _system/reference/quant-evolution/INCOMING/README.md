# Drop Darwin PDF here (or in `_system/frameworks/`)

Copy or save:

`Darwin AI Investments - 1Q26.pdf`

**Also accepted:** `_system/frameworks/Darwin AI Investments - 1Q26.pdf` (or any `*Darwin*.pdf` in frameworks).

Then from repo root:

```bash
bash _system/scripts/copy_darwin_investor_pdf.sh
pip install pypdf
python3 _system/scripts/ingest_darwin_investor_pdf.py
```

Or set `DARWIN_PDF_SOURCE=/full/path/to/file.pdf` before running the shell script.
