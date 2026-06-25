#!/usr/bin/env python3
"""Audit the local PDF document registry before and after Drive sync."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "dashboard" / "data" / "document_registry.json"
SKIP_PARTS = {".git", ".cursor", "_external", "__pycache__", "node_modules"}


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def load_registry(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Missing registry: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def iter_local_pdfs() -> set[str]:
    out: set[str] = set()
    for path in ROOT.rglob("*.pdf"):
        parts = path.relative_to(ROOT).parts
        if any(part in SKIP_PARTS for part in parts):
            continue
        if path.is_file():
            out.add(rel(path))
    return out


def build_audit(registry: dict) -> dict:
    docs = registry.get("documents") or []
    registry_pdf_paths: set[str] = set()
    registry_sha: defaultdict[str, list[str]] = defaultdict(list)
    missing_local: list[str] = []
    dry_run_folder_ids: list[dict] = []

    for doc in docs:
        local_pdf = str(doc.get("local_pdf_path") or "").replace("\\", "/")
        if local_pdf:
            registry_pdf_paths.add(local_pdf)
            registry_sha[str(doc.get("sha256") or "")].append(local_pdf)
            if not (ROOT / local_pdf).exists():
                missing_local.append(local_pdf)
        for alt in doc.get("alternate_pdf_paths") or []:
            registry_pdf_paths.add(str(alt).replace("\\", "/"))
        folder_id = str(doc.get("drive_folder_id") or "")
        if folder_id.startswith("dry-run-folder:"):
            dry_run_folder_ids.append(
                {
                    "local_pdf_path": local_pdf,
                    "drive_folder_id": folder_id,
                }
            )

    local_pdfs = iter_local_pdfs()
    unregistered_local = sorted(local_pdfs - registry_pdf_paths)
    source_counts = Counter(str(doc.get("source_type") or "unknown") for doc in docs)
    root_counts = Counter(str(doc.get("drive_root_key") or "unknown") for doc in docs)
    duplicate_sha_docs = {
        sha: paths
        for sha, paths in registry_sha.items()
        if sha and len(paths) > 1
    }

    return {
        "summary": {
            "document_count": len(docs),
            "local_pdf_count": len(local_pdfs),
            "uploaded_count": sum(1 for doc in docs if doc.get("drive_web_view_link")),
            "pending_upload_count": sum(1 for doc in docs if not doc.get("drive_web_view_link")),
            "missing_local_count": len(missing_local),
            "unregistered_local_count": len(unregistered_local),
            "dry_run_folder_id_count": len(dry_run_folder_ids),
            "duplicate_sha_doc_count": len(duplicate_sha_docs),
            "source_counts": dict(sorted(source_counts.items())),
            "root_counts": dict(sorted(root_counts.items())),
        },
        "missing_local": sorted(missing_local),
        "unregistered_local": unregistered_local,
        "dry_run_folder_ids": dry_run_folder_ids,
        "duplicate_sha_docs": duplicate_sha_docs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit dashboard/data/document_registry.json")
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when actionable issues are present")
    args = parser.parse_args()

    audit = build_audit(load_registry(args.registry))
    if args.json:
        print(json.dumps(audit, indent=2, sort_keys=True))
    else:
        summary = audit["summary"]
        print("Document registry audit")
        for key, value in summary.items():
            print(f"  {key}: {value}")
        for key in ("missing_local", "unregistered_local", "dry_run_folder_ids"):
            rows = audit[key]
            if rows:
                print(f"\n{key} (first 20):")
                for row in rows[:20]:
                    print(f"  {row}")

    actionable = (
        audit["summary"]["missing_local_count"]
        or audit["summary"]["unregistered_local_count"]
        or audit["summary"]["dry_run_folder_id_count"]
    )
    return 1 if args.strict and actionable else 0


if __name__ == "__main__":
    raise SystemExit(main())
