#!/usr/bin/env python3
"""Mirror research-vault/manager-meetings/**/*.pdf to Shared Drive Manager Meetings/."""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from drive_store_common import (  # noqa: E402
    CONFIG_PATH,
    FOLDER_MIME,
    drive_quote,
    drive_service,
    ensure_folder_path,
    execute_with_retry,
    folder_id_by_parent_name,
    list_drive_items,
    load_json,
    now_iso,
    web_folder_url,
    write_json,
)
from vault_paths import research_vault_root  # noqa: E402

REPORT_PATH = ROOT / "_system" / "reference" / "document-store" / "manager_meetings_drive_sync_latest.json"
DEFAULT_DRIVE_PREFIX = "Manager Meetings"
DEFAULT_VAULT_SUBDIR = "manager-meetings"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_config() -> dict:
    return load_json(CONFIG_PATH)


def manager_meetings_config(config: dict) -> dict:
    mm = config.get("manager_meetings") or {}
    return {
        "drive_root_folder_id": mm.get("drive_root_folder_id")
        or ((config.get("drive_roots") or {}).get("general_pdfs") or {}).get("folder_id"),
        "drive_folder_prefix": mm.get("drive_folder_prefix") or DEFAULT_DRIVE_PREFIX,
        "vault_subdir": mm.get("vault_subdir") or DEFAULT_VAULT_SUBDIR,
        "label": mm.get("label") or "Magis manager meeting PDFs",
    }


def vault_meetings_root(subdir: str) -> Path:
    vault = research_vault_root()
    if vault is None:
        raise SystemExit(
            "Research vault not found. Set RESEARCH_VAULT_ROOT or clone research-vault "
            "as a sibling of single-stock-investments."
        )
    path = vault / subdir
    if not path.is_dir():
        raise SystemExit(f"Manager meetings folder missing: {path}")
    return path


def iter_local_pdfs(meetings_root: Path) -> list[dict]:
    rows: list[dict] = []
    for pdf in sorted(meetings_root.rglob("*.pdf")):
        rel = pdf.relative_to(meetings_root).as_posix()
        date_folder = pdf.parent.name if pdf.parent != meetings_root else ""
        rows.append(
            {
                "local_path": str(pdf),
                "relative_path": rel,
                "date_folder": date_folder,
                "name": pdf.name,
                "size_bytes": pdf.stat().st_size,
                "sha256": sha256_file(pdf),
            }
        )
    return rows


def find_pdf_in_folder(service, folder_id: str, name: str) -> dict | None:
    q = (
        f"'{drive_quote(folder_id)}' in parents and "
        f"name = '{drive_quote(name)}' and "
        "mimeType = 'application/pdf' and trashed = false"
    )
    res = execute_with_retry(
        service.files().list(
            q=q,
            fields="files(id,name,size,webViewLink,webContentLink,appProperties)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=10,
        )
    )
    files = res.get("files") or []
    return files[0] if files else None


def upload_pdf(service, local_path: Path, folder_id: str, sha256: str) -> dict:
    media = MediaFileUpload(str(local_path), mimetype="application/pdf", resumable=True)
    body = {
        "name": local_path.name,
        "parents": [folder_id],
        "appProperties": {
            "source_type": "manager_meeting",
            "sha256": sha256,
        },
    }
    return execute_with_retry(
        service.files().create(
            body=body,
            media_body=media,
            fields="id,name,size,webViewLink,webContentLink,appProperties",
            supportsAllDrives=True,
        )
    )


def preflight_root(service, root_id: str) -> None:
    meta = execute_with_retry(
        service.files().get(
            fileId=root_id,
            fields="id,name,mimeType,driveId,capabilities",
            supportsAllDrives=True,
        )
    )
    if not meta.get("driveId"):
        raise SystemExit(
            f"Drive root {root_id} ({meta.get('name')}) is not a Shared Drive location."
        )
    caps = meta.get("capabilities") or {}
    if caps.get("canAddChildren") is False:
        raise SystemExit(f"Drive root {root_id} is not writable by the service account.")


def sync(dry_run: bool = False) -> dict:
    config = load_config()
    mm = manager_meetings_config(config)
    root_id = mm["drive_root_folder_id"]
    if not root_id:
        raise SystemExit("No drive_root_folder_id configured for manager meetings.")

    meetings_root = vault_meetings_root(mm["vault_subdir"])
    local_docs = iter_local_pdfs(meetings_root)
    if not local_docs:
        raise SystemExit(f"No PDFs found under {meetings_root}")

    service = drive_service(readonly=False)
    preflight_root(service, root_id)

    # Warm folder cache from Shared Drive listing (best-effort).
    items = list_drive_items(service, [root_id])
    existing_folders = folder_id_by_parent_name(items)

    results: list[dict] = []
    uploaded = linked = pending = 0

    for doc in local_docs:
        date_folder = doc["date_folder"]
        folder_path = "/".join(p for p in [mm["drive_folder_prefix"], date_folder] if p)
        folder_id = ensure_folder_path(service, root_id, folder_path, dry_run, existing_folders)

        row = {
            **doc,
            "drive_folder_path": folder_path,
            "drive_folder_id": None if dry_run else folder_id,
            "drive_folder_url": None if dry_run else web_folder_url(folder_id),
        }

        if dry_run:
            row["status"] = "dry_run_pending_upload"
            pending += 1
            results.append(row)
            print(f"[dry-run] {doc['relative_path']} -> {folder_path}/", flush=True)
            continue

        existing = find_pdf_in_folder(service, folder_id, doc["name"])
        if existing:
            props = existing.get("appProperties") or {}
            same_sha = props.get("sha256") == doc["sha256"]
            same_size = str(existing.get("size") or "") == str(doc["size_bytes"])
            if same_sha or same_size:
                row.update(
                    {
                        "status": "linked_existing",
                        "drive_file_id": existing.get("id"),
                        "drive_web_view_link": existing.get("webViewLink"),
                        "drive_web_content_link": existing.get("webContentLink"),
                    }
                )
                linked += 1
                print(f"[linked]  {doc['relative_path']}", flush=True)
                results.append(row)
                continue

        created = upload_pdf(service, Path(doc["local_path"]), folder_id, doc["sha256"])
        row.update(
            {
                "status": "uploaded",
                "drive_file_id": created.get("id"),
                "drive_web_view_link": created.get("webViewLink"),
                "drive_web_content_link": created.get("webContentLink"),
            }
        )
        uploaded += 1
        print(f"[upload]  {doc['relative_path']} -> {created.get('webViewLink')}", flush=True)
        results.append(row)

    report = {
        "generated_at": now_iso(),
        "dry_run": dry_run,
        "vault_root": str(meetings_root),
        "drive_root_folder_id": root_id,
        "drive_folder_prefix": mm["drive_folder_prefix"],
        "summary": {
            "local_pdf_count": len(local_docs),
            "uploaded": uploaded,
            "linked_existing": linked,
            "pending": pending,
        },
        "files": results,
    }
    write_json(REPORT_PATH, report)
    print(
        f"\nDone. local={len(local_docs)} uploaded={uploaded} linked={linked} "
        f"pending={pending} report={REPORT_PATH}",
        flush=True,
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Resolve folders and list uploads without writing.")
    args = parser.parse_args()
    sync(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
