"""Shared paths for ValueLine and Expert Calls.

Licensed PDFs and call transcripts stay in the private research vault.
This module only handles folder identity, registry membership, and the
public metadata guard.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
PRIVATE_FOLDERS_PATH = ROOT / "_system" / "reference" / "document-store" / "private_drive_folders.json"
PUBLIC_LICENSED_SOURCES = ROOT / "dashboard" / "data" / "licensed_sources.json"
PUBLIC_VALUELINE_PATH = ROOT / "dashboard" / "data" / "insights" / "valueline.json"
PUBLIC_EXPERT_CALLS_PATH = ROOT / "dashboard" / "data" / "insights" / "expert_calls.json"
VALUELINE_SUMMARY_PATH = ROOT / "_system" / "reference" / "document-store" / "valueline_sync_summary.json"
VALUELINE_UNMATCHED_PATH = ROOT / "_system" / "reference" / "document-store" / "valueline_unmatched.csv"
FILENAME_INDEX_PATH = ROOT / "_system" / "reference" / "document-store" / "drive_filename_index.json"
AUDIT_PATH = ROOT / "_system" / "reference" / "document-store" / "drive_audit_latest.json"
EXPERT_UNMATCHED_PATH = ROOT / "_system" / "reference" / "document-store" / "expert_calls_unmatched.csv"
EXPERT_PLAN_PATH = ROOT / "_system" / "reference" / "document-store" / "expert_calls_drive_plan.csv"
EXPERT_PLAN_SUMMARY_PATH = ROOT / "_system" / "reference" / "document-store" / "expert_calls_drive_plan_summary.json"
EXPERT_VIC_FLAG_PATH = ROOT / "_system" / "reference" / "document-store" / "expert_calls_misfiled_vic.json"
VALUELINE_ALIAS_PATH = ROOT / "_system" / "reference" / "document-store" / "valueline_ticker_aliases.json"
EXPERT_OVERRIDE_PATH = ROOT / "_system" / "reference" / "document-store" / "expert_call_ticker_overrides.json"
DRIVE_CONFIG_PATH = ROOT / "_system" / "reference" / "document-store" / "google_drive_config.json"

PRIVATE_PATH_PREFIXES = ("ValueLine Research", "Expert Calls")
PUBLIC_STRING_MAX = 400
FORBIDDEN_PUBLIC_KEYS = frozenset(
    {"text", "body", "transcript", "content", "extract", "markdown", "pdf_text", "snippet"}
)
DRIVE_ROOT_ID = "0AFpaOm4iTLqjUk9PVA"

# Discovered 2026-10-25. Live sync prefers the folder name and uses these
# only when the name walk fails or when stripping an index that has no paths.
KNOWN_PRIVATE_FOLDER_IDS = {
    "ValueLine Research/Company Reports/Current": "1Vkxdo3k6HqLkqR0QO6in8KMTkm3r57FJ",
    "ValueLine Research/Company Reports/Old": "1XGiU-iANX7TJyHgsXea_NRHZuJlzWESl",
    "ValueLine Research/Special Situations": "1wnqyCJLNXoLMOJcVL7czHh-1fkIizCOu",
    "ValueLine Research/Full Surveys": "1_IWMLwwMLu5VUvDzfy33GgkjqxuHrxLO",
    "Expert Calls": "1dc9SyIh2BOQKuQshldbCYk6G6W0n0pgW",
}
VALUELINE_EDITION_BY_ID = {
    "1Vkxdo3k6HqLkqR0QO6in8KMTkm3r57FJ": "current",
    "1XGiU-iANX7TJyHgsXea_NRHZuJlzWESl": "old",
    "1wnqyCJLNXoLMOJcVL7czHh-1fkIizCOu": "special_situations",
    "1_IWMLwwMLu5VUvDzfy33GgkjqxuHrxLO": "full_survey",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def drive_file_url(file_id: str | None, web_view: str | None = None) -> str:
    if web_view:
        return str(web_view)
    if not file_id:
        return ""
    return f"https://drive.google.com/file/d/{file_id}/view"


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def private_folder_ids() -> set[str]:
    ids = set(KNOWN_PRIVATE_FOLDER_IDS.values())
    doc = load_json(PRIVATE_FOLDERS_PATH, {})
    for value in (doc.get("folder_ids") or {}).values():
        if value:
            ids.add(str(value))
    for value in doc.get("extra_folder_ids") or []:
        if value:
            ids.add(str(value))
    return ids


def path_is_private(path: str | None) -> bool:
    text = str(path or "").strip().strip("/")
    if not text:
        return False
    for prefix in PRIVATE_PATH_PREFIXES:
        if text == prefix or text.startswith(prefix + "/"):
            return True
    return False


def item_is_private(item: dict, folder_paths: dict[str, str] | None = None, folder_ids: set[str] | None = None) -> bool:
    ids = folder_ids if folder_ids is not None else private_folder_ids()
    parents = [p for p in (item.get("parents") or []) if p]
    if any(parent in ids for parent in parents):
        return True
    if item.get("id") in ids and item.get("mimeType") == "application/vnd.google-apps.folder":
        return True
    if not folder_paths:
        return False
    for parent in parents:
        if path_is_private(folder_paths.get(parent, "")):
            return True
    own = folder_paths.get(item.get("id") or "", "")
    return path_is_private(own)


def load_registry_companies() -> dict[str, str]:
    """Ticker -> company name for holdings and the watchlist."""
    doc = load_json(REGISTRY_PATH, {})
    out: dict[str, str] = {}
    for section in ("holdings", "watchlist"):
        for ticker, row in (doc.get(section) or {}).items():
            symbol = str(ticker or "").strip().upper()
            if not symbol:
                continue
            company = ""
            if isinstance(row, dict):
                company = str(row.get("company") or "").strip()
            out[symbol] = company or symbol
    return out


def load_ticker_aliases() -> dict[str, str]:
    doc = load_json(VALUELINE_ALIAS_PATH, {})
    aliases = doc.get("aliases") or {}
    return {str(key).upper(): str(value).upper() for key, value in aliases.items() if key and value}


def load_expert_overrides() -> tuple[dict[str, str], dict[str, str]]:
    doc = load_json(EXPERT_OVERRIDE_PATH, {})
    by_company = {str(key): str(value).upper() for key, value in (doc.get("by_company") or {}).items() if key and value}
    by_id = {str(key): str(value).upper() for key, value in (doc.get("by_drive_id") or {}).items() if key and value}
    return by_company, by_id


def vault_subdir(name: str, *, create: bool = False) -> Path | None:
    """Return a licensed-content directory inside the research vault.

    Refuses the public repo. Licensed text is not written under dashboard/
    or _system/reference/.
    """
    from vault_paths import research_vault_root

    vault = research_vault_root(create=create)
    if vault is None:
        return None
    vault_resolved = vault.resolve()
    if vault_resolved == ROOT.resolve():
        raise RuntimeError("Refusing to write licensed research into the public repo root.")
    path = vault_resolved / name
    public_roots = (
        (ROOT / "dashboard").resolve(),
        (ROOT / "_system" / "reference").resolve(),
    )
    if any(path == root or root in path.parents for root in public_roots):
        raise RuntimeError(f"Refusing to write licensed research under {path}.")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def assert_public_metadata(payload) -> None:
    """Reject transcript-sized strings and body fields before a public write."""

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if str(key).lower() in FORBIDDEN_PUBLIC_KEYS:
                    raise ValueError(f"public metadata contains forbidden key {key}")
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str) and len(node) > PUBLIC_STRING_MAX:
            raise ValueError("public metadata string is too long to be a label or link")

    walk(payload)


def assert_public_csv_field(value: str) -> str:
    text = str(value or "")
    if len(text) > PUBLIC_STRING_MAX:
        raise ValueError("public CSV field is too long to be a filename or label")
    if re.search(r"\n\n", text):
        raise ValueError("public CSV field looks like transcript text")
    return text


def slug(text: str, limit: int = 40) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-")
    return (cleaned[:limit].strip("-") or "item")


def drop_private_rows(
    rows: list[dict],
    folder_paths: dict[str, str] | None = None,
    folder_ids: set[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Split Drive rows into public vs ValueLine / Expert Calls."""
    ids = folder_ids if folder_ids is not None else private_folder_ids()
    kept: list[dict] = []
    dropped: list[dict] = []
    for row in rows:
        if item_is_private(row, folder_paths, ids):
            dropped.append(row)
        else:
            kept.append(row)
    return kept, dropped


def private_ids_in_filename_index(doc: dict, folder_ids: set[str] | None = None) -> set[str]:
    ids = folder_ids if folder_ids is not None else private_folder_ids()
    found: set[str] = set()
    for row in (doc.get("by_filename") or {}).values():
        if isinstance(row, dict) and item_is_private(row, None, ids) and row.get("id"):
            found.add(str(row["id"]))
    return found


def strip_filename_index(doc: dict, folder_ids: set[str] | None = None) -> tuple[dict, int]:
    """Drop licensed PDFs from the public filename index. Other rows stay."""
    ids = folder_ids if folder_ids is not None else private_folder_ids()
    kept: dict[str, dict] = {}
    removed = 0
    for key, row in (doc.get("by_filename") or {}).items():
        if isinstance(row, dict) and item_is_private(row, None, ids):
            removed += 1
            continue
        kept[key] = row
    out = dict(doc)
    out["by_filename"] = kept
    out["pdf_count"] = len(kept)
    out["private_pdfs_excluded"] = int(doc.get("private_pdfs_excluded") or 0) + removed
    return out, removed


def _audit_file_private(row: dict, extra_ids: set[str], folder_ids: set[str]) -> bool:
    file_id = str(row.get("id") or "")
    if file_id and file_id in extra_ids:
        return True
    return item_is_private(row, None, folder_ids)


def strip_audit(doc: dict, extra_ids: set[str] | None = None, folder_ids: set[str] | None = None) -> tuple[dict, int]:
    """Remove licensed PDFs from the public audit lists and fix the summary counts."""
    ids = folder_ids if folder_ids is not None else private_folder_ids()
    extra = set(extra_ids or ())
    removed_ids: set[str] = set()

    def keep(row: dict) -> bool:
        if not isinstance(row, dict):
            return True
        if _audit_file_private(row, extra, ids):
            if row.get("id"):
                removed_ids.add(str(row["id"]))
            return False
        return True

    out = dict(doc)
    for key in ("missing_sha_app_property", "orphan_drive_pdfs"):
        rows = doc.get(key) or []
        out[key] = [row for row in rows if keep(row)] if isinstance(rows, list) else rows
    duplicates: dict = {}
    for sha, rows in (doc.get("duplicate_sha") or {}).items():
        if not isinstance(rows, list):
            continue
        kept_rows = [row for row in rows if keep(row)]
        if len(kept_rows) > 1:
            duplicates[sha] = kept_rows
    out["duplicate_sha"] = duplicates
    summary = dict(doc.get("summary") or {})
    excluded = removed_ids | extra
    previous = int(summary.get("drive_pdf_count") or 0)
    summary["drive_pdf_count"] = max(0, previous - len(excluded))
    summary["private_folder_pdfs_excluded"] = len(excluded)
    summary["duplicate_sha_count"] = len(duplicates)
    summary["missing_sha_app_property_count"] = len(out.get("missing_sha_app_property") or [])
    summary["orphan_drive_pdf_count"] = len(out.get("orphan_drive_pdfs") or [])
    out["summary"] = summary
    return out, len(excluded)
