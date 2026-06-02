#!/usr/bin/env python3
"""PDF text extraction with OCR fallback for scanned transcripts."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

LOGGER = logging.getLogger("pdf_ocr")

MIN_TEXT_CHARS = int(__import__("os").getenv("PDF_OCR_MIN_TEXT_CHARS", "200"))
OCR_MAX_PAGES = int(__import__("os").getenv("PDF_OCR_MAX_PAGES", "25"))


def _pypdf_extract(path: Path, max_pages: int) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = reader.pages[:max_pages]
    return "\n".join((p.extract_text() or "") for p in pages)


def _ocr_extract(path: Path, max_pages: int) -> tuple[str, bool]:
    """OCR via tesseract + pdf2image. Returns (text, ocr_used)."""
    if not shutil.which("tesseract"):
        LOGGER.debug("tesseract not installed; skipping OCR for %s", path)
        return "", False
    try:
        import pytesseract  # type: ignore
        from pdf2image import convert_from_path  # type: ignore
    except ImportError:
        LOGGER.debug("pytesseract/pdf2image not installed; skipping OCR for %s", path)
        return "", False

    try:
        images = convert_from_path(str(path), first_page=1, last_page=max_pages, dpi=200)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("pdf2image failed for %s: %s", path, exc)
        return "", False

    chunks: list[str] = []
    for img in images:
        try:
            chunks.append(pytesseract.image_to_string(img))
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("OCR page failed for %s: %s", path, exc)
    text = "\n".join(chunks)
    return text, bool(text.strip())


def extract_pdf_text(path: Path, *, max_pages: int = 15, force_ocr: bool = False) -> dict:
    """Extract text from PDF; OCR when native text is sparse."""
    result = {"text": "", "method": "none", "ocr_used": False, "error": None}
    try:
        native = _pypdf_extract(path, max_pages)
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
        native = ""

    native_clean = (native or "").strip()
    if not force_ocr and len(native_clean) >= MIN_TEXT_CHARS:
        result["text"] = native
        result["method"] = "pypdf"
        return result

    ocr_text, ocr_used = _ocr_extract(path, min(max_pages, OCR_MAX_PAGES))
    if ocr_used and len(ocr_text.strip()) > len(native_clean):
        result["text"] = ocr_text
        result["method"] = "ocr"
        result["ocr_used"] = True
        return result

    if native_clean:
        result["text"] = native
        result["method"] = "pypdf_sparse"
        return result

    if ocr_text.strip():
        result["text"] = ocr_text
        result["method"] = "ocr"
        result["ocr_used"] = True
        return result

    result["method"] = "failed"
    return result
