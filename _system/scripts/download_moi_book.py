#!/usr/bin/env python3
"""Install Manual of Ideas (PDF or EPUB) into investment-wisdom/mihaljevic/.

Priority:
  1. MOI_PDF_SOURCE / MOI_EPUB_SOURCE env (path to licensed file)
  2. mihaljevic/.source/Manual-of-Ideas*.{epub,pdf} (human drop folder)
  3. Build Manual-of-Ideas-Marvin-Reference.pdf from chapter extract (fallback)

On EPUB install, also writes Manual-of-Ideas-full-text.txt for agent full-text read.

Usage:
  MOI_EPUB_SOURCE=/path/to/book.epub python _system/scripts/download_moi_book.py
  MOI_PDF_SOURCE=/path/to/book.pdf python _system/scripts/download_moi_book.py
  python _system/scripts/download_moi_book.py
"""
from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEST_DIR = ROOT / "_system/reference/investment-wisdom/mihaljevic"
TARGET_PDF = DEST_DIR / "Manual-of-Ideas-2nd-Edition.pdf"
TARGET_EPUB = DEST_DIR / "Manual-of-Ideas-1st-Edition-2013.epub"
FULL_TEXT = DEST_DIR / "Manual-of-Ideas-full-text.txt"
REFERENCE_PDF = DEST_DIR / "Manual-of-Ideas-Marvin-Reference.pdf"
EXTRACT = DEST_DIR / "Manual-of-Ideas-chapter-reference.txt"
LOG = DEST_DIR / "_download_log.txt"
DROP_DIR = DEST_DIR / ".source"

MIN_BYTES = 100_000


def log(msg: str) -> None:
    line = f"{datetime.now().isoformat()} {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _valid(path: Path) -> bool:
    return path.is_file() and path.stat().st_size >= MIN_BYTES


def find_epub_source() -> Path | None:
    env = os.environ.get("MOI_EPUB_SOURCE", "").strip()
    if env:
        p = Path(env).expanduser()
        if _valid(p) and p.suffix.lower() == ".epub":
            return p
        log(f"WARN MOI_EPUB_SOURCE set but not a valid epub: {env}")

    if DROP_DIR.is_dir():
        for pattern in ("Manual-of-Ideas*.epub", "*.epub"):
            for candidate in sorted(DROP_DIR.glob(pattern)):
                if _valid(candidate):
                    return candidate
    return None


def find_pdf_source() -> Path | None:
    env = os.environ.get("MOI_PDF_SOURCE", "").strip()
    if env:
        p = Path(env).expanduser()
        if _valid(p):
            return p
        log(f"WARN MOI_PDF_SOURCE set but not a valid file: {env}")

    if DROP_DIR.is_dir():
        for pattern in ("Manual-of-Ideas*.pdf", "*.pdf"):
            for candidate in sorted(DROP_DIR.glob(pattern)):
                if _valid(candidate):
                    return candidate
    return None


def _strip_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</p\s*>", "\n\n", raw)
    raw = re.sub(r"(?i)</h[1-6]\s*>", "\n\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = html.unescape(raw)
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_epub_text(epub_path: Path) -> str:
    """Extract plain text from EPUB (zip of XHTML)."""
    parts: list[str] = []
    with zipfile.ZipFile(epub_path) as zf:
        names = sorted(
            n
            for n in zf.namelist()
            if n.lower().endswith((".xhtml", ".html", ".htm"))
            and "nav" not in n.lower()
        )
        for name in names:
            try:
                raw = zf.read(name).decode("utf-8", errors="replace")
            except KeyError:
                continue
            cleaned = _strip_html(raw)
            if cleaned:
                parts.append(cleaned)
    return "\n\n".join(parts)


def install_epub(source: Path) -> int:
    shutil.copy2(source, TARGET_EPUB)
    log(f"OK copied EPUB -> {TARGET_EPUB.relative_to(ROOT)} ({TARGET_EPUB.stat().st_size} bytes)")
    try:
        text = extract_epub_text(TARGET_EPUB)
        if len(text) < 10_000:
            log(f"WARN EPUB text extraction short ({len(text)} chars) — check file integrity")
        header = (
            "Manual of Ideas — full text extract\n"
            f"Source: {TARGET_EPUB.name}\n"
            f"Extracted: {datetime.now().date().isoformat()}\n"
            "=" * 72 + "\n\n"
        )
        FULL_TEXT.write_text(header + text, encoding="utf-8")
        log(f"OK wrote full text {FULL_TEXT.name} ({len(text):,} chars)")
    except Exception as exc:
        log(f"FAIL EPUB text extraction: {exc}")
        return 1
    return 0


def install_pdf(source: Path) -> int:
    shutil.copy2(source, TARGET_PDF)
    log(f"OK copied PDF -> {TARGET_PDF.relative_to(ROOT)} ({TARGET_PDF.stat().st_size} bytes)")
    return 0


def build_reference_pdf() -> bool:
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

    epub = find_epub_source()
    if epub:
        return install_epub(epub)

    pdf = find_pdf_source()
    if pdf:
        return install_pdf(pdf)

    if TARGET_EPUB.is_file() and _valid(TARGET_EPUB):
        log(f"SKIP EPUB already present {TARGET_EPUB.name}")
        if not FULL_TEXT.is_file():
            return install_epub(TARGET_EPUB)
        return 0

    if TARGET_PDF.is_file() and TARGET_PDF.stat().st_size > MIN_BYTES:
        log(f"SKIP PDF already present {TARGET_PDF.name}")
        return 0

    log("No licensed PDF/EPUB found — building Marvin reference PDF from chapter extract")
    log("Drop licensed file in mihaljevic/.source/ or set MOI_EPUB_SOURCE / MOI_PDF_SOURCE")
    if build_reference_pdf():
        if not TARGET_PDF.exists():
            shutil.copy2(REFERENCE_PDF, TARGET_PDF)
            log(f"OK copied reference as {TARGET_PDF.name} until licensed copy installed")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
