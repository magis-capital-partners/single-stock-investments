#!/usr/bin/env python3
"""Resolve a repo ticker from Drive intake PDF bytes / text.

Used when path/filename does not already identify a local ticker folder.
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,24}$")
MIN_TEXT_CHARS = 80
DEFAULT_MAX_PAGES = 3
BARE_SCAN_CHARS = 8000
COMPANY_SCAN_CHARS = 2000

sys.path.insert(0, str(SCRIPTS))


def repo_tickers() -> set[str]:
    out: set[str] = set()
    for child in ROOT.iterdir():
        if child.is_dir() and TICKER_RE.match(child.name) and not child.name.startswith(("_", ".")):
            out.add(child.name.upper())
    return out


def load_company_map(known: set[str] | None = None) -> dict[str, str]:
    """Map normalized company fragment -> ticker for holdings/watchlist."""
    known = known or repo_tickers()
    mapping: dict[str, str] = {}
    if not REGISTRY_PATH.exists():
        return mapping
    try:
        doc = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return mapping
    for bucket in ("holdings", "watchlist"):
        for ticker, meta in (doc.get(bucket) or {}).items():
            t = str(ticker).upper().strip()
            if t not in known:
                continue
            company = str((meta or {}).get("company") or "").strip()
            if not company or len(company) < 4:
                continue
            key = re.sub(r"[^a-z0-9]+", " ", company.lower()).strip()
            if key:
                mapping[key] = t
            words = key.split()
            if len(words) >= 2:
                short = " ".join(words[:2])
                if len(short) >= 6:
                    mapping.setdefault(short, t)
    return mapping


def extract_pdf_text(data: bytes, max_pages: int = DEFAULT_MAX_PAGES) -> tuple[str, str]:
    """Return (text, extract_method)."""
    text = _extract_pypdf(data, max_pages=max_pages)
    method = "pypdf"
    if len(text.strip()) >= MIN_TEXT_CHARS:
        return text, method
    ocr_text = _extract_pdf_ocr(data, max_pages=max_pages)
    if ocr_text is not None:
        if len(ocr_text.strip()) > len(text.strip()):
            return ocr_text, "pdf_ocr"
        if ocr_text.strip():
            return ocr_text, "pdf_ocr"
    return text, method if text.strip() else "no_text"


def _extract_pypdf(data: bytes, max_pages: int) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            return ""
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception:
        return ""
    parts: list[str] = []
    for page in reader.pages[: max(1, max_pages)]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(parts)


def _extract_pdf_ocr(data: bytes, max_pages: int) -> str | None:
    try:
        from pdf_ocr import extract_pdf_text as ocr_extract
    except ImportError:
        return None
    import tempfile

    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(data)
            path = Path(tmp.name)
        try:
            result = ocr_extract(path, max_pages=max_pages, force_ocr=False)
            text = (result.get("text") if isinstance(result, dict) else str(result or "")) or ""
            if len(text.strip()) < MIN_TEXT_CHARS:
                result = ocr_extract(path, max_pages=max_pages, force_ocr=True)
                text = (result.get("text") if isinstance(result, dict) else str(result or "")) or ""
            return text
        finally:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
    except Exception:
        return None


def _tier_a_tickers(text: str, known: set[str]) -> list[str]:
    try:
        from letter_matching import extract_explicit_symbols
    except ImportError:
        return []
    hits: list[str] = []
    seen: set[str] = set()
    for hit in extract_explicit_symbols(text):
        sym = str(hit.get("symbol") or "").upper()
        if hit.get("numeric"):
            continue
        if sym in known and sym not in seen:
            seen.add(sym)
            hits.append(sym)
        # Also try dotted variants already in known
        for k in known:
            if k == sym or k.startswith(sym + ".") or k.split(".", 1)[0] == sym:
                if k not in seen:
                    seen.add(k)
                    hits.append(k)
    return hits


def _company_tickers(text: str, company_map: dict[str, str], known: set[str]) -> list[str]:
    hay = re.sub(r"[^a-z0-9]+", " ", text[:COMPANY_SCAN_CHARS].lower())
    hits: list[str] = []
    seen: set[str] = set()
    # Longest company keys first
    for key in sorted(company_map, key=len, reverse=True):
        if len(key) < 6:
            continue
        if key in hay:
            t = company_map[key]
            if t in known and t not in seen:
                seen.add(t)
                hits.append(t)
    return hits


def _bare_tickers(text: str, known: set[str], allow_short: set[str] | None = None) -> list[str]:
    allow_short = allow_short or set()
    hay = text[:BARE_SCAN_CHARS].upper()
    hits: list[str] = []
    for ticker in sorted(known, key=len, reverse=True):
        symbol = ticker.split(".", 1)[0]
        if len(symbol) <= 2 and ticker not in allow_short:
            continue
        pattern = rf"(?<![A-Z0-9]){re.escape(ticker)}(?![A-Z0-9])"
        if re.search(pattern, hay):
            hits.append(ticker)
            continue
        if "." in ticker:
            pattern2 = rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])"
            if re.search(pattern2, hay) and len(symbol) >= 3:
                hits.append(ticker)
    return hits


def infer_ticker_from_filename(filename: str, known: set[str] | None = None) -> str | None:
    known = known or repo_tickers()
    stem = Path(filename).stem.upper()
    for token in re.split(r"[\s_\-]+", stem):
        t = token.strip().upper()
        if t in known:
            return t
    return None


def resolve_ticker_from_text(
    text: str,
    *,
    filename: str = "",
    known: set[str] | None = None,
    company_map: dict[str, str] | None = None,
) -> dict:
    known = known or repo_tickers()
    company_map = company_map if company_map is not None else load_company_map(known)
    text_chars = len((text or "").strip())

    file_hit = infer_ticker_from_filename(filename, known) if filename else None
    if file_hit:
        return {
            "ticker": file_hit,
            "method": "filename",
            "confidence": "high",
            "candidates": [file_hit],
            "text_chars": text_chars,
            "error": None,
        }

    if text_chars == 0:
        return {
            "ticker": None,
            "method": None,
            "confidence": None,
            "candidates": [],
            "text_chars": 0,
            "error": "no_text",
        }

    tier_a = _tier_a_tickers(text, known)
    if len(tier_a) == 1:
        return {
            "ticker": tier_a[0],
            "method": "tier_a_explicit",
            "confidence": "high",
            "candidates": tier_a,
            "text_chars": text_chars,
            "error": None,
        }
    if len(tier_a) > 1:
        return {
            "ticker": None,
            "method": "tier_a_explicit",
            "confidence": None,
            "candidates": tier_a,
            "text_chars": text_chars,
            "error": "ambiguous_tickers",
        }

    company_hits = _company_tickers(text, company_map, known)
    if len(company_hits) == 1:
        return {
            "ticker": company_hits[0],
            "method": "company_name",
            "confidence": "med",
            "candidates": company_hits,
            "text_chars": text_chars,
            "error": None,
        }
    if len(company_hits) > 1:
        return {
            "ticker": None,
            "method": "company_name",
            "confidence": None,
            "candidates": company_hits,
            "text_chars": text_chars,
            "error": "ambiguous_tickers",
        }

    bare = _bare_tickers(text, known, allow_short=set(tier_a))
    if len(bare) == 1:
        return {
            "ticker": bare[0],
            "method": "bare_token",
            "confidence": "med",
            "candidates": bare,
            "text_chars": text_chars,
            "error": None,
        }
    if len(bare) > 1:
        return {
            "ticker": None,
            "method": "bare_token",
            "confidence": None,
            "candidates": bare[:12],
            "text_chars": text_chars,
            "error": "ambiguous_tickers",
        }

    return {
        "ticker": None,
        "method": None,
        "confidence": None,
        "candidates": [],
        "text_chars": text_chars,
        "error": "unresolved_ticker",
    }


def resolve_ticker_from_pdf(
    data: bytes,
    *,
    filename: str = "",
    max_pages: int = DEFAULT_MAX_PAGES,
    known: set[str] | None = None,
) -> dict:
    text, extract_method = extract_pdf_text(data, max_pages=max_pages)
    result = resolve_ticker_from_text(text, filename=filename, known=known)
    result["extract_method"] = extract_method
    if result.get("error") == "no_text" and extract_method == "no_text":
        result["error"] = "no_text"
    return result
