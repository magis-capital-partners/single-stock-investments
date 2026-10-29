"""Live Drive listings for ValueLine and Expert Calls.

Imported only when a command actually talks to Drive, so unit tests can
import the planners without the Google client.
"""
from __future__ import annotations

from licensed_drive_common import (
    DRIVE_ROOT_ID,
    KNOWN_PRIVATE_FOLDER_IDS,
    VALUELINE_EDITION_BY_ID,
)

FOLDER_MIME = "application/vnd.google-apps.folder"
EXPERT_CALLS_NAME = "Expert Calls"
EXPERT_CALLS_FALLBACK = KNOWN_PRIVATE_FOLDER_IDS["Expert Calls"]


def _service(readonly: bool):
    from drive_store_common import drive_service

    return drive_service(readonly=readonly)


def _configured_roots() -> list[str]:
    from drive_store_common import CONFIG_PATH, configured_root_ids, load_json

    roots = configured_root_ids(load_json(CONFIG_PATH))
    return roots or [DRIVE_ROOT_ID]


def find_named_folder(service, name: str, fallback_id: str) -> str:
    """Prefer the folder with this name. The saved id is the fallback."""
    from drive_store_common import drive_quote, execute_with_retry

    query = (
        f"name = '{drive_quote(name)}' and mimeType = '{FOLDER_MIME}' and trashed = false"
    )
    try:
        found = execute_with_retry(
            service.files().list(
                q=query,
                fields="files(id,name,parents)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora="allDrives",
                pageSize=25,
            )
        )
    except Exception:
        return fallback_id
    files = found.get("files") or []
    for item in files:
        if item.get("id") == fallback_id:
            return fallback_id
    if len(files) == 1 and files[0].get("id"):
        return str(files[0]["id"])
    return fallback_id


def list_children(service, folder_id: str) -> list[dict]:
    from drive_store_common import drive_quote, execute_with_retry

    rows: list[dict] = []
    page_token = None
    query = f"'{drive_quote(folder_id)}' in parents and trashed = false"
    while True:
        found = execute_with_retry(
            service.files().list(
                q=query,
                fields=(
                    "nextPageToken,files(id,name,size,mimeType,parents,webViewLink,md5Checksum)"
                ),
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageSize=1000,
                pageToken=page_token,
            )
        )
        rows.extend(found.get("files") or [])
        page_token = found.get("nextPageToken")
        if not page_token:
            return rows


def child_folder(service, parent_id: str, name: str, cache: dict[tuple[str, str], str]) -> str:
    """Return the child folder id, creating it only when it is missing."""
    from drive_store_common import ensure_folder

    key = (parent_id, name)
    if key in cache:
        return cache[key]
    for item in list_children(service, parent_id):
        if item.get("mimeType") == FOLDER_MIME and item.get("name") == name and item.get("id"):
            cache[key] = str(item["id"])
            return cache[key]
    return ensure_folder(service, parent_id, name, False, cache)


def list_valueline_pdfs(service=None) -> list[dict]:
    from drive_store_common import build_folder_paths, list_drive_items

    service = service or _service(readonly=True)
    root_ids = _configured_roots()
    items = list_drive_items(service, root_ids)
    folder_paths = build_folder_paths(items, root_ids)
    rows: list[dict] = []
    for item in items:
        if item.get("mimeType") != "application/pdf":
            continue
        parents = item.get("parents") or []
        parent_path = folder_paths.get(parents[0], "") if parents else ""
        in_tree = parent_path == "ValueLine Research" or parent_path.startswith("ValueLine Research/")
        in_known = any(parent in VALUELINE_EDITION_BY_ID for parent in parents)
        if not in_tree and not in_known:
            continue
        rows.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "parents": parents,
                "webViewLink": item.get("webViewLink"),
                "path": parent_path,
                "size": item.get("size"),
                "md5Checksum": item.get("md5Checksum"),
            }
        )
    return rows


def list_expert_call_files(service=None) -> tuple[list[dict], str]:
    """Files in Expert Calls.

    Direct children are new flat uploads (parent_name ``Expert Calls``).
    Files already inside a subfolder keep that folder name so the planner
    leaves them alone.
    """
    service = service or _service(readonly=True)
    folder_id = find_named_folder(service, EXPERT_CALLS_NAME, EXPERT_CALLS_FALLBACK)
    rows: list[dict] = []
    for item in list_children(service, folder_id):
        if item.get("mimeType") == FOLDER_MIME:
            folder_name = item.get("name") or ""
            for child in list_children(service, item["id"]):
                if child.get("mimeType") == FOLDER_MIME:
                    continue
                rows.append(_expert_row(child, folder_name))
            continue
        rows.append(_expert_row(item, EXPERT_CALLS_NAME))
    return rows, folder_id


def _expert_row(item: dict, parent_name: str) -> dict:
    return {
        "name": item.get("name") or "",
        "Name": item.get("name") or "",
        "size": item.get("size") or 0,
        "Size": item.get("size") or 0,
        "id": item.get("id") or "",
        "ID": item.get("id") or "",
        "parents": item.get("parents") or [],
        "parent_name": parent_name,
        "webViewLink": item.get("webViewLink") or "",
        "mimeType": item.get("mimeType") or "",
        "md5Checksum": item.get("md5Checksum") or "",
    }
