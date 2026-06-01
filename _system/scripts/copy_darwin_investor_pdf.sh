#!/usr/bin/env bash
# Copy Darwin 1Q26 PDF into research vault (Linux/macOS/CI).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export PYTHONPATH="${ROOT}/_system/scripts${PYTHONPATH:+:$PYTHONPATH}"
python3 - <<'PY'
from darwin_pdf_paths import DEST, ensure_vault_copy, find_darwin_pdf

src = find_darwin_pdf()
if src is None:
    raise SystemExit(
        "ERROR: Darwin PDF not found.\n"
        "  Drop at: _system/frameworks/Darwin AI Investments - 1Q26.pdf\n"
        "  Or: _system/reference/quant-evolution/INCOMING/\n"
        "  Or: export DARWIN_PDF_SOURCE=/path/to/file.pdf"
    )
dest = ensure_vault_copy()
if src.resolve() == dest.resolve():
    print(f"Already at vault: {dest}")
else:
    print(f"Copied {src} → {dest}")
PY
