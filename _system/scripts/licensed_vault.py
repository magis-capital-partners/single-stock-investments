"""Write licensed ValueLine and Expert Call text into the research vault.

PDFs and Word files are not stored here. A gitignore for those suffixes is
written before any extract. Callers pass a destination that is already outside
dashboard/ and _system/reference/.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

from licensed_drive_common import ROOT, load_json, now_iso, slug, write_json

VALUELINE_GITIGNORE = "# Licensed ValueLine PDFs stay on Drive. This tree stores extracted text only.\n*.pdf\n"
EXPERT_GITIGNORE = (
    "# Licensed call audio, Word, and PDF copies stay on Drive.\n"
    "# This tree stores the markdown transcript only.\n"
    "*.pdf\n*.docx\n"
)
MIN_EXTRACT_CHARS = 40


def assert_licensed_destination(path: Path) -> None:
    resolved = path.resolve()
    if resolved == ROOT.resolve():
        raise RuntimeError("Refusing to write licensed research into the public repo root.")
    banned = (
        (ROOT / "dashboard").resolve(),
        (ROOT / "_system" / "reference").resolve(),
    )
    if any(resolved == root or root in resolved.parents for root in banned):
        raise RuntimeError(f"Refusing to write licensed research under {resolved}.")


def prepare_tree(vault: Path, name: str) -> Path:
    """Create the vault subtree and its gitignore before any download."""
    assert_licensed_destination(vault)
    root = vault / name
    assert_licensed_destination(root)
    root.mkdir(parents=True, exist_ok=True)
    ignore = root / ".gitignore"
    body = VALUELINE_GITIGNORE if name == "valueline" else EXPERT_GITIGNORE
    if not ignore.exists():
        ignore.write_text(body, encoding="utf-8")
    return root


def load_manifest(root: Path) -> dict:
    doc = load_json(root / "manifest.json", {})
    doc.setdefault("files", {})
    doc.setdefault("by_sha", {})
    return doc


def save_manifest(root: Path, manifest: dict) -> None:
    manifest["updated_at"] = now_iso()
    write_json(root / "manifest.json", manifest)


def file_in_shard(file_id: str, shard_index: int, shard_count: int) -> bool:
    if shard_count <= 1:
        return True
    if shard_index < 0 or shard_index >= shard_count:
        raise ValueError(f"shard_index {shard_index} is outside 0..{shard_count - 1}")
    digest = hashlib.sha256(str(file_id).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % shard_count == shard_index


def valueline_relative(row: dict) -> str | None:
    """Vault path relative to valueline/. Unmatched company reports stay out."""
    status = row.get("status")
    date = row.get("report_date") or "undated"
    if status == "matched" and row.get("ticker"):
        edition = {
            "current": "current",
            "old": "old",
            "special_situations": "special-situations",
        }.get(row.get("edition") or "", "unknown")
        return f"{row['ticker']}/{edition}/{date}.txt"
    if status == "survey":
        return f"_full-surveys/{date}_{slug(row.get('company') or 'survey', 40)}.txt"
    if status == "special_situation_issue":
        return f"_special-situation-issues/{date}_{slug(row.get('company') or 'issue', 40)}.txt"
    return None


def expert_relative(row: dict) -> str | None:
    if row.get("bucket") != "ticker" or row.get("extension") != "md":
        return None
    ticker = row.get("ticker") or ""
    name = row.get("new_name") or ""
    if not ticker or not name.endswith(".md"):
        return None
    return f"{ticker}/{Path(name).name}"


def _text_of(result) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return str(result.get("text") or "")
    return ""


def _refuse_pdf_bytes(text: str) -> None:
    if text.startswith("%PDF"):
        raise RuntimeError("Refusing to write PDF bytes into the vault.")


def download_drive_bytes(service, file_id: str) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload

    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
        if status is None and not done:
            continue
    return buffer.getvalue()


def extract_pdf_bytes(data: bytes) -> str:
    import tempfile

    from pdf_ocr import extract_pdf_text

    with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
        handle.write(data)
        handle.flush()
        return _text_of(extract_pdf_text(Path(handle.name), max_pages=15))


def import_documents(
    *,
    root: Path,
    jobs: list[dict],
    download,
    decode,
    dry_run: bool,
) -> dict:
    """Import jobs of {file_id, relative, meta, sha256?}.

    ``decode`` turns downloaded bytes into text. Existing manifest entries and
    identical sha256 values are skipped. Nothing is removed.
    """
    assert_licensed_destination(root)
    manifest = load_manifest(root)
    counts = {"written": 0, "skipped": 0, "aliased": 0, "empty": 0, "dry_run": 0, "errors": 0}
    for job in jobs:
        file_id = str(job.get("file_id") or "")
        relative = str(job.get("relative") or "")
        if not file_id or not relative:
            counts["errors"] += 1
            continue
        if dry_run:
            counts["dry_run"] += 1
            continue
        existing = manifest["files"].get(file_id)
        if existing:
            target = root / str(existing.get("text_path") or relative)
            if target.exists() and target.stat().st_size > 0:
                counts["skipped"] += 1
                continue
        known_sha = str(job.get("sha256") or "")
        if known_sha and known_sha in manifest["by_sha"]:
            _alias(manifest, file_id, known_sha, job.get("meta") or {})
            counts["aliased"] += 1
            continue
        try:
            data = download(file_id)
            text = _text_of(decode(data))
            _refuse_pdf_bytes(text)
        except Exception as exc:  # noqa: BLE001 — recorded, shard continues
            counts["errors"] += 1
            manifest["files"][file_id] = {
                "error": str(exc)[:300],
                "updated_at": now_iso(),
                **(job.get("meta") or {}),
            }
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest in manifest["by_sha"]:
            _alias(manifest, file_id, digest, job.get("meta") or {})
            counts["aliased"] += 1
            continue
        if len(text.strip()) < MIN_EXTRACT_CHARS:
            counts["empty"] += 1
            manifest["files"][file_id] = {
                "sha256": digest,
                "empty_extract": True,
                "updated_at": now_iso(),
                **(job.get("meta") or {}),
            }
            continue
        target = _unique_target(root, relative, file_id, manifest)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.suffix.lower() == ".pdf" or target.suffix.lower() == ".docx":
            raise RuntimeError(f"Refusing to store {target.name} in the vault.")
        target.write_text(text, encoding="utf-8")
        rel = target.relative_to(root).as_posix()
        manifest["by_sha"][digest] = rel
        manifest["files"][file_id] = {
            "sha256": digest,
            "text_path": rel,
            "updated_at": now_iso(),
            **(job.get("meta") or {}),
        }
        counts["written"] += 1
    if not dry_run:
        save_manifest(root, manifest)
    return counts


def _alias(manifest: dict, file_id: str, digest: str, meta: dict) -> None:
    manifest["files"][file_id] = {
        "sha256": digest,
        "text_path": manifest["by_sha"].get(digest) or "",
        "aliased": True,
        "updated_at": now_iso(),
        **meta,
    }


def _unique_target(root: Path, relative: str, file_id: str, _manifest: dict) -> Path:
    target = root / relative
    if not target.exists():
        return target
    # A different Drive file already occupies this date path. Keep both.
    suffix = file_id[:8] or "copy"
    return target.with_name(f"{target.stem}-{suffix}{target.suffix}")
