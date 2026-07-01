"""Shared helpers for resolving source documents through the PDF document store."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "dashboard" / "data" / "document_registry.json"
DRIVE_AUDIT_PATH = ROOT / "_system/reference/document-store/drive_audit_latest.json"
DRIVE_FILENAME_INDEX_PATH = ROOT / "_system/reference/document-store/drive_filename_index.json"
DRIVE_FOLDER_INDEX_PATH = ROOT / "_system/reference/document-store/drive_folder_index.json"
LETTER_DRIVE_LINKS_PATH = ROOT / "_system/reference/document-store/letter_drive_links.json"
LETTERS_INDEX_PATH = ROOT / "_system/reference/superinvestor-letters/letters_index.json"


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
_DRIVE_AUDIT_BY_FILENAME: dict[str, str] | None = None
_DRIVE_FILENAME_INDEX: dict[str, str] | None = None
_DRIVE_FOLDER_INDEX: dict[str, str] | None = None
_LETTER_DRIVE_LINKS: dict[str, str] | None = None
_LETTER_SOURCE_INDEX: dict[str, dict] | None = None
_REGISTRY_BY_FILENAME: dict[str, str] | None = None


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


def _load_drive_audit() -> dict:
    if not DRIVE_AUDIT_PATH.exists():
        return {}
    try:
        return json.loads(DRIVE_AUDIT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def drive_audit_links() -> dict[str, str]:
    global _DRIVE_AUDIT_INDEX
    if _DRIVE_AUDIT_INDEX is not None:
        return _DRIVE_AUDIT_INDEX
    index: dict[str, str] = {}
    audit = _load_drive_audit()
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


def drive_filename_links() -> dict[str, str]:
    global _DRIVE_FILENAME_INDEX
    if _DRIVE_FILENAME_INDEX is not None:
        return _DRIVE_FILENAME_INDEX
    index: dict[str, str] = {}
    if DRIVE_FILENAME_INDEX_PATH.exists():
        try:
            payload = json.loads(DRIVE_FILENAME_INDEX_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        for key, row in (payload.get("by_filename") or {}).items():
            link = (row or {}).get("webViewLink")
            if link:
                index[str(key).lower()] = str(link)
    _DRIVE_FILENAME_INDEX = index
    return index


def letter_drive_links() -> dict[str, str]:
    global _LETTER_DRIVE_LINKS
    if _LETTER_DRIVE_LINKS is not None:
        return _LETTER_DRIVE_LINKS
    index: dict[str, str] = {}
    if LETTER_DRIVE_LINKS_PATH.exists():
        try:
            payload = json.loads(LETTER_DRIVE_LINKS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        for key, link in (payload.get("links") or {}).items():
            if link:
                index[str(key).replace("\\", "/").lower()] = str(link)
    _LETTER_DRIVE_LINKS = index
    return index


def registry_filename_links() -> dict[str, str]:
    global _REGISTRY_BY_FILENAME
    if _REGISTRY_BY_FILENAME is not None:
        return _REGISTRY_BY_FILENAME
    index: dict[str, str] = {}
    for doc in load_document_registry().get("documents") or []:
        link = doc.get("drive_web_view_link") or doc.get("drive_web_content_link")
        if not link:
            continue
        for path in [doc.get("local_pdf_path"), *(doc.get("alternate_pdf_paths") or [])]:
            if path:
                index[Path(str(path)).name.lower()] = str(link)
    _REGISTRY_BY_FILENAME = index
    return index


def drive_audit_by_filename() -> dict[str, str]:
    global _DRIVE_AUDIT_BY_FILENAME
    if _DRIVE_AUDIT_BY_FILENAME is not None:
        return _DRIVE_AUDIT_BY_FILENAME
    index: dict[str, str] = {}
    audit = _load_drive_audit()
    for items in audit.values():
        if not isinstance(items, list):
            continue
        for item in items:
            name = item.get("name")
            link = item.get("webViewLink") or item.get("webContentLink")
            if not name or not link:
                continue
            index[str(name).lower()] = str(link)
    _DRIVE_AUDIT_BY_FILENAME = index
    return index


def drive_folder_links() -> dict[str, str]:
    global _DRIVE_FOLDER_INDEX
    if _DRIVE_FOLDER_INDEX is not None:
        return _DRIVE_FOLDER_INDEX
    index: dict[str, str] = {}
    if DRIVE_FOLDER_INDEX_PATH.exists():
        try:
            payload = json.loads(DRIVE_FOLDER_INDEX_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        for path, meta in (payload.get("folders") or {}).items():
            link = (meta or {}).get("webViewLink")
            if link:
                index[str(path)] = str(link)
    _DRIVE_FOLDER_INDEX = index
    return index


def letter_source_index() -> dict[str, dict]:
    global _LETTER_SOURCE_INDEX
    if _LETTER_SOURCE_INDEX is not None:
        return _LETTER_SOURCE_INDEX
    index: dict[str, dict] = {}
    if LETTERS_INDEX_PATH.exists():
        try:
            rows = json.loads(LETTERS_INDEX_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            rows = []
        if isinstance(rows, list):
            for row in rows:
                for key in ("source_document", "source_file"):
                    ref = row.get(key)
                    if ref:
                        index[str(ref).replace("\\", "/")] = row
                        index[Path(str(ref)).name.lower()] = row
    _LETTER_SOURCE_INDEX = index
    return index


def quarter_folder_path(quarter: str | None) -> str | None:
    paths = quarter_folder_paths(quarter)
    return paths[0] if paths else None


def quarter_folder_paths(quarter: str | None) -> list[str]:
    text = str(quarter or "").strip().upper()
    m = re.match(r"^(20\d{2})Q([1-4])$", text)
    if not m:
        return []
    label = f"{m.group(1)} Q{m.group(2)}"
    return [
        f"Letters/{label}",
        f"Letters/Letters/{label}",
        f"superinvestor-letters/{text}",
    ]


def quarter_from_ref(ref: str | None) -> str | None:
    base, _anchor = _clean_ref(ref)
    if not base:
        return None
    m = re.search(r"superinvestor-letters/(20\d{2})Q([1-4])/", base, re.I)
    if m:
        return f"{m.group(1)}Q{m.group(2)}".upper()
    return None


def drive_link_for_ref(base: str) -> str | None:
    clean = str(base).replace("\\", "/").lower()
    letter_links = letter_drive_links()
    if clean in letter_links:
        return letter_links[clean]

    filename = Path(base).name.lower()
    if filename in letter_links:
        return letter_links[filename]

    by_name = drive_filename_links()
    if filename in by_name:
        return by_name[filename]

    registry_links = registry_filename_links()
    if filename in registry_links:
        return registry_links[filename]

    audit_by_name = drive_audit_by_filename()
    if filename in audit_by_name:
        return audit_by_name[filename]

    links = drive_audit_links()
    stem = Path(base).stem.lower()
    norm = _normalize_name(base)
    if stem in links:
        return links[stem]
    if norm in links:
        return links[norm]
    return None


def drive_link_for_letter(
    *,
    source_ref: str | None,
    quarter: str | None = None,
    fund: str | None = None,
) -> str | None:
    base, _anchor = _clean_ref(source_ref)
    if not base:
        return None

    clean = base.replace("\\", "/").lower()
    letter_links = letter_drive_links()
    if clean in letter_links:
        return letter_links[clean]
    filename = Path(base).name.lower()
    if filename in letter_links:
        return letter_links[filename]

    doc = document_for_ref(base)
    if doc:
        drive = doc.get("drive_web_view_link") or doc.get("drive_web_content_link")
        if drive:
            return str(drive)

    pdf_ref = pdf_ref_for(base)
    for candidate in (base, pdf_ref, Path(base).name, Path(pdf_ref).name):
        link = drive_link_for_ref(str(candidate))
        if link:
            return link

    q = quarter or quarter_from_ref(base)
    folders = drive_folder_links()
    for folder in quarter_folder_paths(q):
        folder_link = folders.get(folder)
        if folder_link:
            return folder_link

    if fund and q:
        year = q[:4]
        qnum = q[-1]
        tokens = [t for t in re.split(r"[^a-z0-9]+", fund.lower()) if len(t) >= 4]
        best_score = 0
        best_link = None
        for name, link in drive_audit_by_filename().items():
            if not name.endswith(".pdf"):
                continue
            if year not in name:
                continue
            if f"q{qnum}" not in name and f"{qnum}q" not in name and f" {qnum} " not in f" {name} ":
                if f"first quarter" not in name and f"1q" not in name.replace(" ", "") and qnum != "1":
                    continue
            score = sum(1 for token in tokens if token in name)
            if score > best_score:
                best_score = score
                best_link = link
        if best_link and best_score >= 2:
            return best_link

    return None


def pdf_ref_for(base: str) -> str:
    path = ROOT / base
    if path.suffix.lower() in {".txt", ".md"}:
        return str(path.with_suffix(".pdf").relative_to(ROOT)).replace("\\", "/")
    return base


def pdf_github_url(base: str, github_repo: str, anchor: str = "") -> str:
    return github_blob_url(pdf_ref_for(base), github_repo) + anchor


def letter_evidence_url(
    letter: dict | None,
    github_repo: str,
    source_ref: str | None = None,
    registry: dict | None = None,
) -> str | None:
    ref = source_ref or (letter or {}).get("source_document") or (letter or {}).get("source_file")
    base, anchor = _clean_ref(ref)
    if not base:
        return None
    if base.startswith(("http://", "https://")):
        return base + anchor

    drive = drive_link_for_letter(
        source_ref=base,
        quarter=(letter or {}).get("quarter") or quarter_from_ref(base),
        fund=(letter or {}).get("fund"),
    )
    if drive:
        return drive + anchor

    doc = document_for_ref(base, registry)
    if doc:
        pdf_path = doc.get("local_pdf_path")
        if pdf_path and Path(ROOT / pdf_path).exists():
            return github_blob_url(str(pdf_path), github_repo) + anchor

    if "superinvestor-letters" in base:
        return pdf_github_url(base, github_repo, anchor)
    return best_document_url(base, github_repo, registry)


def letter_evidence_label(url: str | None, source_ref: str | None = None) -> str:
    if not url:
        return "source"
    if "drive.google.com/drive/folders/" in url.lower():
        return "Drive folder"
    if "drive.google.com" in url.lower():
        return "PDF"
    return best_document_label(source_ref)


def best_document_url(ref: str | None, github_repo: str, registry: dict | None = None) -> str | None:
    base, anchor = _clean_ref(ref)
    if not base:
        return None
    if base.startswith(("http://", "https://")):
        return base + anchor

    if "superinvestor-letters" in base:
        meta = letter_source_index().get(base) or letter_source_index().get(Path(base).name.lower())
        return letter_evidence_url(meta, github_repo, base, registry)

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
            if Path(ROOT / pdf_path).exists():
                return github_blob_url(str(pdf_path), github_repo) + anchor

    drive = drive_link_for_ref(base) or drive_link_for_ref(pdf_ref_for(base))
    if drive:
        return drive + anchor

    path = ROOT / base
    if path.suffix.lower() in {".pdf", ".txt", ".md"}:
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
