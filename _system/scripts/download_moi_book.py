#!/usr/bin/env python3
"""Install Manual of Ideas PDF into investment-wisdom/mihaljevic/.

Priority:
  1. MOI_PDF_SOURCE env (path to purchased Wiley PDF)
  2. mihaljevic/.source/Manual-of-Ideas*.pdf (human drop folder)
  3. Build Manual-of-Ideas-Marvin-Reference.pdf from chapter extract (fallback)

Usage:
  MOI_PDF_SOURCE=/path/to/book.pdf python _system/scripts/download_moi_book.py
  python _system/scripts/download_moi_book.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEST_DIR = ROOT / "_system/reference/investment-wisdom/mihaljevic"
TARGET = DEST_DIR / "Manual-of-Ideas-2nd-Edition.pdf"
REFERENCE_PDF = DEST_DIR / "Manual-of-Ideas-Marvin-Reference.pdf"
EXTRACT = DEST_DIR / "Manual-of-Ideas-chapter-reference.txt"
LOG = DEST_DIR / "_download_log.txt"
DROP_DIR = DEST_DIR / ".source"


def log(msg: str) -> None:
    line = f"{datetime.now().isoformat()} {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def find_source() -> Path | None:
    env = os.environ.get("MOI_PDF_SOURCE", "").strip()
    if env:
        p = Path(env).expanduser()
        if p.is_file() and p.stat().st_size > 100_000:
            return p
        log(f"WARN MOI_PDF_SOURCE set but not a valid file: {env}")

    if DROP_DIR.is_dir():
        for pattern in ("Manual-of-Ideas*.pdf", "*.pdf"):
            for candidate in sorted(DROP_DIR.glob(pattern)):
                if candidate.stat().st_size > 100_000:
                    return candidate
    return None


def build_reference_pdf() -> bool:
    """Build a readable reference PDF from the chapter extract."""
    if not EXTRACT.is_file():
        log(f"FAIL missing extract {EXTRACT}")
        return False
    try:
        from fpdf import FPDF
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "fpdf2", "-q"])
        from fpdf import FPDF

    text = EXTRACT.read_text(encoding="utf-8")
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=9)
    width = pdf.epw
    for line in text.splitlines():
        safe = line.encode("latin-1", errors="replace").decode("latin-1")
        if not safe.strip():
            pdf.ln(3)
            continue
        pdf.multi_cell(width, 5, safe)
    pdf.output(str(REFERENCE_PDF))
    log(f"OK built reference PDF {REFERENCE_PDF.name} ({REFERENCE_PDF.stat().st_size} bytes)")
    return True


def main() -> int:
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    DROP_DIR.mkdir(parents=True, exist_ok=True)

    source = find_source()
    if source:
        shutil.copy2(source, TARGET)
        log(f"OK copied licensed PDF -> {TARGET.relative_to(ROOT)} ({TARGET.stat().st_size} bytes)")
        return 0

    if TARGET.is_file() and TARGET.stat().st_size > 100_000:
        log(f"SKIP licensed PDF already present {TARGET.name}")
        return 0

    log("No licensed PDF found — building Marvin reference PDF from chapter extract")
    log("Purchase Wiley ISBN 978-1-119-27032-4 and set MOI_PDF_SOURCE or drop in .source/")
    if build_reference_pdf():
        if not TARGET.exists():
            shutil.copy2(REFERENCE_PDF, TARGET)
            log(f"OK symlinked reference as {TARGET.name} until licensed copy installed")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
