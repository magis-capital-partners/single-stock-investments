"""Shared helpers for resolving source documents through the PDF document store."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "dashboard" / "data" / "document_registry.json"


def _clean_ref(ref: str | None) -> tuple[str | None, str]:
    if not ref:
        return None, ""
    clean = str(ref).strip()
    if not clean:
        return None, ""
    base, sep, anchor = clean.partition("#")
    return base.replace("\\", "/"), f"#{anchor}" if sep else ""


def load_document_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {}
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def registry_indexes(registry: dict | None = None) -> dict[str, dict[str, dict]]:
    registry = registry or load_document_registry()
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
    return {"by_pdf": by_pdf, "by_text": by_text, "by_id": by_id}


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
            return str(drive)
        text_path = doc.get("text_extract_path")
        if text_path:
            return github_blob_url(str(text_path), github_repo) + anchor
    path = ROOT / base
    if path.suffix.lower() == ".pdf" and not path.exists():
        for candidate in (path.with_suffix(".txt"), Path(str(path) + ".txt")):
            if candidate.exists():
                return github_blob_url(str(candidate.relative_to(ROOT)).replace("\\", "/"), github_repo) + anchor
        return None
    return github_blob_url(base, github_repo) + anchor


def best_document_label(ref: str | None, registry: dict | None = None) -> str:
    base, _anchor = _clean_ref(ref)
    if not base:
        return "source"
    if base.startswith(("http://", "https://")):
        return "article"
    doc = document_for_ref(base, registry)
    if doc:
        if doc.get("drive_web_view_link") or doc.get("drive_web_content_link"):
            return "PDF"
        if doc.get("text_extract_path"):
            return "Text"
    path = ROOT / base
    if path.suffix.lower() == ".pdf" and not path.exists():
        for candidate in (path.with_suffix(".txt"), Path(str(path) + ".txt")):
            if candidate.exists():
                return "Text"
        return "missing"
    suffix = Path(base).suffix.lower()
    if suffix == ".pdf":
        return "PDF"
    if suffix in {".htm", ".html"}:
        return "HTML"
    if suffix == ".json":
        return "index"
    return "source"


def document_id_for_ref(ref: str | None, registry: dict | None = None) -> str | None:
    doc = document_for_ref(ref, registry)
    return doc.get("document_id") if doc else None
