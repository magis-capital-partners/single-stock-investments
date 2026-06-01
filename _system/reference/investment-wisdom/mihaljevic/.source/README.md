# Drop licensed Manual of Ideas here

Copy your purchased or licensed copy to this folder, then run:

```bash
python _system/scripts/download_moi_book.py
python _system/scripts/build_wisdom_manifest.py
```

**Supported formats:** `.epub`, `.pdf`

**Environment variables (alternative):**

```bash
MOI_EPUB_SOURCE="/path/to/Manual-of-Ideas.epub" python _system/scripts/download_moi_book.py
MOI_PDF_SOURCE="/path/to/Manual-of-Ideas.pdf" python _system/scripts/download_moi_book.py
```

**Outputs after install:**

| File | Purpose |
|------|---------|
| `Manual-of-Ideas-1st-Edition-2013.epub` | Archived source (epub path) |
| `Manual-of-Ideas-full-text.txt` | Full-text extract for Marvin agents |
| `Manual-of-Ideas-2nd-Edition.pdf` | PDF archive (pdf path) |

**Evaluation rules:** `_system/frameworks/moi_company_evaluation.md`
