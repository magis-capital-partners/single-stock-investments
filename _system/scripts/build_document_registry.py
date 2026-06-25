#!/usr/bin/env python3
"""Build the local PDF document registry used by dashboard source links."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "dashboard" / "data" / "document_registry.json"
CONFIG_PATH = ROOT / "_system" / "reference" / "document-store" / "google_drive_config.json"
DEFAULT_LETTERS_DRIVE_FOLDER_ID = "0AFpaOm4iTLqjUk9PVA"
DEFAULT_GENERAL_DRIVE_FOLDER_ID = "0AFpaOm4iTLqjUk9PVA"
SKIP_PARTS = {".git", ".cursor", "_external", "__pycache__", "node_modules"}


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def source_type_for(path: Path) -> str:
    r = rel(path)
    parts = path.parts
    if "_system" in parts and "superinvestor-letters" in parts:
        return "superinvestor_letter"
    if "_system" in parts and "sumzero-research" in parts:
        return "sumzero_research"
    if "third-party-analyses" in parts:
        return "third_party"
    if "investor-documents" in parts:
        return "company_document"
    if "research" in parts:
        return "research"
    if "_system" in parts and "dropbox_ingestion" in parts:
        return "dropbox_ingestion"
    return "pdf"


def drive_roots(config: dict) -> dict:
    roots = config.get("drive_roots") or {}
    if roots:
        return roots
    root_id = config.get("drive_root_folder_id") or DEFAULT_LETTERS_DRIVE_FOLDER_ID
    return {
        "hedge_fund_letters": {
            "folder_id": root_id,
            "label": config.get("drive_root_label") or "Hedge Fund Letters PDF Hub",
            "source_types": ["superinvestor_letter"],
        },
        "general_pdfs": {
            "folder_id": DEFAULT_GENERAL_DRIVE_FOLDER_ID,
            "label": "General Investment PDFs Hub",
            "source_types": ["third_party", "company_document", "research", "dropbox_ingestion", "sumzero_research", "pdf"],
        },
    }


def drive_root_for_source(source_type: str, config: dict) -> tuple[str, dict]:
    roots = drive_roots(config)
    for key, root in roots.items():
        if source_type in (root.get("source_types") or []):
            return key, root
    default_key = config.get("default_drive_root") or "general_pdfs"
    return default_key, roots.get(default_key) or next(iter(roots.items()))[1]


def drive_folder_path_for(path: Path) -> str:
    parts = list(path.relative_to(ROOT).parts[:-1])
    if parts[:3] == ["_system", "reference", "superinvestor-letters"]:
        return "/".join(["superinvestor-letters", *parts[3:]])
    if parts[:3] == ["_system", "reference", "sumzero-research"]:
        return "/".join(["sumzero-research", *parts[3:]])
    if len(parts) >= 2 and parts[1] == "third-party-analyses":
        return "/".join(["third-party-research", parts[0], *parts[2:]])
    if len(parts) >= 2 and parts[1] == "investor-documents":
        return "/".join(["company-documents", parts[0], *parts[2:]])
    if parts[:3] == ["_system", "dropbox_ingestion", "00_sources"]:
        return "/".join(["dropbox-ingestion", *parts[3:]])
    return "/".join(parts) or "uncategorized"


def text_extract_for(pdf: Path) -> str | None:
    candidates = [
        pdf.with_suffix(".txt"),
        Path(str(pdf) + ".txt"),
        pdf.with_suffix(".md"),
    ]
    for c in candidates:
        if c.exists():
            return rel(c)
    return None


def title_for(path: Path) -> str:
    return path.stem.replace("_", " ").replace("-", " ").strip()


def existing_by_sha(existing: dict) -> dict[str, dict]:
    return {d.get("sha256"): d for d in existing.get("documents") or [] if d.get("sha256")}


def existing_by_path(existing: dict) -> dict[str, dict]:
    return {d.get("local_pdf_path"): d for d in existing.get("documents") or [] if d.get("local_pdf_path")}


def prior_upload_status(prior: dict) -> str:
    status = prior.get("upload_status") or "pending_upload"
    if str(status).startswith("dry_run"):
        return "pending_upload"
    return status


def prior_drive_folder_id(prior: dict) -> str | None:
    folder_id = prior.get("drive_folder_id")
    if str(folder_id or "").startswith("dry-run-folder:"):
        return None
    return folder_id


def iter_pdfs() -> list[Path]:
    out = []
    for path in ROOT.rglob("*.pdf"):
        if any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts):
            continue
        if path.is_file():
            out.append(path)
    return sorted(out, key=lambda p: rel(p).lower())


def build() -> dict:
    config = load_json(CONFIG_PATH, {})
    existing = load_json(OUTPUT, {})
    existing_sha = existing_by_sha(existing)
    existing_path = existing_by_path(existing)
    docs = []
    seen_sha: set[str] = set()
    current_by_sha: dict[str, dict] = {}
    for path in iter_pdfs():
        path_rel = rel(path)
        stat = path.stat()
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        path_prior = existing_path.get(path_rel) or {}
        if (
            path_prior.get("sha256")
            and path_prior.get("size_bytes") == stat.st_size
            and path_prior.get("modified_at") == modified_at
        ):
            digest = path_prior["sha256"]
        else:
            digest = sha256_file(path)
        if digest in seen_sha:
            doc = current_by_sha[digest]
            doc.setdefault("alternate_pdf_paths", [])
            if path_rel not in doc["alternate_pdf_paths"] and path_rel != doc.get("local_pdf_path"):
                doc["alternate_pdf_paths"].append(path_rel)
            text_path = text_extract_for(path)
            if text_path and text_path != doc.get("text_extract_path"):
                doc.setdefault("alternate_text_extract_paths", [])
                if text_path not in doc["alternate_text_extract_paths"]:
                    doc["alternate_text_extract_paths"].append(text_path)
            continue
        seen_sha.add(digest)
        prior = existing_sha.get(digest) or path_prior
        drive_folder_path = drive_folder_path_for(path)
        source_type = source_type_for(path)
        drive_root_key, drive_root = drive_root_for_source(source_type, config)
        doc = {
            "document_id": f"sha256:{digest}",
            "title": prior.get("title") or title_for(path),
            "source_type": source_type,
            "local_pdf_path": path_rel,
            "text_extract_path": text_extract_for(path),
            "alternate_pdf_paths": prior.get("alternate_pdf_paths") or [],
            "alternate_text_extract_paths": prior.get("alternate_text_extract_paths") or [],
            "sha256": digest,
            "size_bytes": stat.st_size,
            "modified_at": modified_at,
            "mime_type": mimetypes.guess_type(path.name)[0] or "application/pdf",
            "drive_root_key": drive_root_key,
            "drive_root_label": drive_root.get("label"),
            "drive_root_folder_id": drive_root.get("folder_id"),
            "drive_folder_path": prior.get("drive_folder_path") or drive_folder_path,
            "drive_folder_id": prior_drive_folder_id(prior),
            "drive_file_id": prior.get("drive_file_id"),
            "drive_web_view_link": prior.get("drive_web_view_link"),
            "drive_web_content_link": prior.get("drive_web_content_link"),
            "upload_status": prior_upload_status(prior),
        }
        docs.append(doc)
        current_by_sha[digest] = doc
    uploaded = sum(1 for d in docs if d.get("drive_web_view_link"))
    return {
        "generated_at": now_iso(),
        "schema_version": 1,
        "config": {
            "drive_roots": drive_roots(config),
            "default_drive_root": config.get("default_drive_root") or "general_pdfs",
            "service_account_email": config.get("service_account_email"),
            "folder_strategy": config.get("folder_strategy") or "mirror_source_path",
            "access_model": config.get("access_model") or "shared_drive_permissions",
        },
        "summary": {
            "document_count": len(docs),
            "uploaded_count": uploaded,
            "pending_upload_count": len(docs) - uploaded,
            "text_extract_count": sum(1 for d in docs if d.get("text_extract_path")),
            "total_size_bytes": sum(int(d.get("size_bytes") or 0) for d in docs),
            "hedge_fund_letter_count": sum(1 for d in docs if d.get("drive_root_key") == "hedge_fund_letters"),
            "general_pdf_count": sum(1 for d in docs if d.get("drive_root_key") == "general_pdfs"),
        },
        "documents": docs,
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = build()
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    s = payload["summary"]
    print(
        f"Wrote {OUTPUT.relative_to(ROOT)} "
        f"({s['document_count']} PDFs, {s['uploaded_count']} uploaded, {s['pending_upload_count']} pending)"
    )


if __name__ == "__main__":
    main()
