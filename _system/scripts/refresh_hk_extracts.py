#!/usr/bin/env python3
"""Refresh in-repo HK text extracts from the full vault when available.

Copies newer/changed files from {HK_PDFS_ROOT}/book/build/text/ into
_system/reference/investment-wisdom/horizon-kinetics/ per hk_extract_manifest.json.

Runs automatically from marvin_cloud_refresh.py and scan_third_party_sources.py --with-hk.
Safe no-op when vault is unavailable (Windows path, HK_PDFS_ROOT, or cloud default).

Usage:
  python _system/scripts/refresh_hk_extracts.py
  python _system/scripts/refresh_hk_extracts.py --dry-run
  python _system/scripts/refresh_hk_extracts.py --strict   # exit 1 if vault missing
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WISDOM = ROOT / "_system" / "reference" / "investment-wisdom"
MANIFEST_PATH = WISDOM / "hk_extract_manifest.json"
STATUS_PATH = WISDOM / "horizon-kinetics" / "extract_refresh_status.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hk_vault_paths import in_repo_extracts_dir, load_paths_cfg, resolve_vault_root, vault_text_dir  # noqa: E402


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def match_vault_source(text_dir: Path, globs: list[str]) -> Path | None:
    if not text_dir.is_dir():
        return None
    candidates: list[Path] = []
    for f in sorted(text_dir.glob("*.txt")):
        name = f.name
        if any(fnmatch.fnmatch(name, pat) for pat in globs):
            candidates.append(f)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def refresh_extracts(*, dry_run: bool = False) -> dict:
    paths_cfg = load_paths_cfg()
    vault = resolve_vault_root(paths_cfg)
    dest_dir = in_repo_extracts_dir(paths_cfg)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    result: dict = {
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "vault_root": str(vault) if vault else None,
        "vault_available": vault is not None,
        "dest_dir": str(dest_dir.relative_to(ROOT)).replace("\\", "/"),
        "updated": [],
        "skipped": [],
        "missing_vault_source": [],
    }

    if not vault:
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not dry_run:
            STATUS_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result

    text_dir = vault_text_dir(vault, paths_cfg)
    dest_dir.mkdir(parents=True, exist_ok=True)

    for entry in manifest.get("extracts", []):
        dest_name = entry["dest"]
        dest_path = dest_dir / dest_name
        source = match_vault_source(text_dir, entry.get("vault_globs", []))
        if not source:
            result["missing_vault_source"].append(dest_name)
            continue

        source_hash = file_sha256(source)
        dest_hash = file_sha256(dest_path) if dest_path.exists() else None
        if dest_hash == source_hash:
            result["skipped"].append({"dest": dest_name, "source": str(source), "reason": "unchanged"})
            continue

        if dry_run:
            result["updated"].append({"dest": dest_name, "source": str(source), "dry_run": True})
            continue

        dest_path.write_bytes(source.read_bytes())
        result["updated"].append(
            {
                "dest": dest_name,
                "source": str(source),
                "source_mtime": datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
        )

    if not dry_run:
        STATUS_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh HK text extracts from vault")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    parser.add_argument("--strict", action="store_true", help="Exit 1 if vault unavailable")
    args = parser.parse_args()

    result = refresh_extracts(dry_run=args.dry_run)
    vault = result.get("vault_root") or "(none)"
    updated = len(result.get("updated", []))
    skipped = len(result.get("skipped", []))
    missing = len(result.get("missing_vault_source", []))

    print(f"HK extract refresh — vault: {vault}")
    print(f"  updated: {updated}  skipped (unchanged): {skipped}  missing source: {missing}")

    if result.get("updated"):
        for row in result["updated"]:
            print(f"  + {row['dest']} <- {row.get('source', '?')}")

    if not result.get("vault_available"):
        msg = "Vault not found — set HK_PDFS_ROOT or use Windows hk_pdfs path"
        if args.strict:
            print(f"ERROR: {msg}", file=sys.stderr)
            return 1
        print(f"WARN: {msg}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
