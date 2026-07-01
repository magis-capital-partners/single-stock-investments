"""Shared helpers for resolving source documents through the PDF document store."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "dashboard" / "data" / "document_registry.json"
DRIVE_AUDIT_PATH = ROOT / "_system/reference/document-store/drive_audit_latest.json"


def _clean_ref(ref: str | None) -> tuple[str | None, str]:
    if not ref:
        return None, ""
    clean = str(ref).strip()
    if not clean:
        return None, ""
    base, sep, anchor = clean.partition("#")
    return base.replace("\\", "/"), f"#{anchor}" if sep else ""


_REGISTRY_CACHE: dict | None = None
_INDEX_CACHE: dict[int, dict[str, dict[str, dict]]] = {}
_DRIVE_AUDIT_INDEX: dict[str, str] | None = None


def load_document_registry() -> dict:
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None:
        return _REGISTRY_CACHE
    if not REGISTRY_PATH.exists():
        _REGISTRY_CACHE = {}
        return _REGISTRY_CACHE
    try:
        _REGISTRY_CACHE = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        _REGISTRY_CACHE = {}
    return _REGISTRY_CACHE


def registry_indexes(registry: dict | None = None) -> dict[str, dict[str, dict]]:
    registry = registry or load_document_registry()
    key = id(registry)
    cached = _INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    docs = registry.get("documents") or []
    by_pdf: dict[str, dict] = {}
    by_text: dict[str, dict] = {}
    by_id: dict[str, dict] = {}
    for doc in docs:
        if doc.get("document_id"):
            by_id[doc["document_id"]] = doc
        if doc.get("local_pdf_path"):
            by_pdf[str(doc["local_pdf_path"]).replace("\\", "/")] = doc
        for pdf_path in doc.get("alternate_pdf_paths") or []:
            by_pdf[str(pdf_path).replace("\\", "/")] = doc
        if doc.get("text_extract_path"):
            by_text[str(doc["text_extract_path"]).replace("\\", "/")] = doc
        for text_path in doc.get("alternate_text_extract_paths") or []:
            by_text[str(text_path).replace("\\", "/")] = doc
    result = {"by_pdf": by_pdf, "by_text": by_text, "by_id": by_id}
    _INDEX_CACHE[key] = result
    return result


def document_for_ref(ref: str | None, registry: dict | None = None) -> dict | None:
    base, _anchor = _clean_ref(ref)
    if not base or base.startswith(("http://", "https://")):
        return None
    idx = registry_indexes(registry)
    if base in idx["by_pdf"]:
        return idx["by_pdf"][base]
    if base in idx["by_text"]:
        return idx["by_text"][base]
    path = ROOT / base
    if path.suffix.lower() in {".txt", ".md"}:
        pdf = str(path.with_suffix(".pdf").relative_to(ROOT)).replace("\\", "/")
        if pdf in idx["by_pdf"]:
            return idx["by_pdf"][pdf]
    if base.endswith(".pdf.txt"):
        pdf = base[: -len(".txt")]
        if pdf in idx["by_pdf"]:
            return idx["by_pdf"][pdf]
    return None


def github_blob_url(rel_path: str, github_repo: str) -> str:
    return f"https://github.com/{github_repo}/blob/main/{rel_path.replace(chr(92), '/')}"


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", Path(value).stem.lower())


def drive_audit_links() -> dict[str, str]:
    global _DRIVE_AUDIT_INDEX
    if _DRIVE_AUDIT_INDEX is not None:
        return _DRIVE_AUDIT_INDEX
    index: dict[str, str] = {}
    if DRIVE_AUDIT_PATH.exists():
        try:
            audit = json.loads(DRIVE_AUDIT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            audit = {}
        for items in audit.values():
            if not isinstance(items, list):
                continue
            for item in items:
                name = item.get("name")
                link = item.get("webViewLink") or item.get("webContentLink")
                if not name or not link or not str(name).lower().endswith(".pdf"):
                    continue
                stem = Path(str(name)).stem.lower()
                norm = _normalize_name(str(name))
                index[stem] = str(link)
                index[norm] = str(link)
    _DRIVE_AUDIT_INDEX = index
    return index


def drive_link_for_ref(base: str) -> str | None:
    links = drive_audit_links()
    stem = Path(base).stem.lower()
    norm = _normalize_name(base)
    if stem in links:
        return links[stem]
    if norm in links:
        return links[norm]
    if len(norm) >= 12:
        for key, link in links.items():
            if len(key) >= 12 and (norm in key or key in norm):
                return link
    return None


def pdf_ref_for(base: str) -> str:
    path = ROOT / base
    if path.suffix.lower() in {".txt", ".md"}:
        return str(path.with_suffix(".pdf").relative_to(ROOT)).replace("\\", "/")
    return base


def pdf_github_url(base: str, github_repo: str, anchor: str = "") -> str:
    return github_blob_url(pdf_ref_for(base), github_repo) + anchor


def best_document_url(ref: str | None, github_repo: str, registry: dict | None = None) -> str | None:
    base, anchor = _clean_ref(ref)
    if not base:
        return None
    if base.startswith(("http://", "https://")):
        return base + anchor

    doc = document_for_ref(base, registry)
    if doc:
        drive = doc.get("drive_web_view_link") or doc.get("drive_web_content_link")
        if drive:
            return str(drive) + anchor
        pdf_path = doc.get("local_pdf_path")
        if pdf_path:
            drive = drive_link_for_ref(str(pdf_path))
            if drive:
                return drive + anchor
            return github_blob_url(str(pdf_path), github_repo) + anchor

    drive = drive_link_for_ref(base) or drive_link_for_ref(pdf_ref_for(base))
    if drive:
        return drive + anchor

    path = ROOT / base
    if path.suffix.lower() in {".pdf", ".txt", ".md"} or "superinvestor-letters" in base:
        return pdf_github_url(base, github_repo, anchor)

    return github_blob_url(base, github_repo) + anchor


def best_document_label(ref: str | None, registry: dict | None = None) -> str:
    base, _anchor = _clean_ref(ref)
    if not base:
        return "source"
    if base.startswith(("http://", "https://")):
        if "drive.google.com" in base.lower():
            return "PDF"
        return "article"
    doc = document_for_ref(base, registry)
    if doc and (doc.get("drive_web_view_link") or doc.get("drive_web_content_link")):
        return "PDF"
    if drive_link_for_ref(base) or drive_link_for_ref(pdf_ref_for(base)):
        return "PDF"
    suffix = Path(pdf_ref_for(base)).suffix.lower()
    if suffix == ".pdf" or "superinvestor-letters" in base:
        return "PDF"
    if suffix in {".htm", ".html"}:
        return "HTML"
    if suffix == ".json":
        return "index"
    if doc and doc.get("text_extract_path"):
        return "Text"
    return "source"


def document_id_for_ref(ref: str | None, registry: dict | None = None) -> str | None:
    doc = document_for_ref(ref, registry)
    return doc.get("document_id") if doc else None
