#!/usr/bin/env python3
"""Object paths for a publication-only research-vault checkout.

Canonical Memory Triage, the Epistemic Falsifier Loop, and the Committee
Outcome Loop do not read letters, transcripts, investor history, the
company-research cache, or the extraction archive. Their vault checkout exists
so private dashboard snapshots can be hydrated for the run and redacted before
anything is pushed. Each receipt in dashboard/private-assets.json names one
content-addressed object under dashboard-private/objects/.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_SHA = re.compile(r"[0-9a-f]{64}")


def publication_entries(manifest: dict, workspace: Path | None = None):
    """Sparse-checkout patterns for every private object the manifest names."""
    if not isinstance(manifest, dict):
        raise ValueError("private-assets manifest must be an object")
    ordered = []
    for section in ("assets", "repository_assets"):
        entries = manifest.get(section) or {}
        if not isinstance(entries, dict):
            raise ValueError(f"{section} must be an object")
        for relative, entry in entries.items():
            if not isinstance(relative, str) or not relative:
                raise ValueError(f"{section} has an empty path")
            if not isinstance(entry, dict):
                raise ValueError(f"{section} receipt for {relative} must be an object")
            sha = entry.get("private_sha256")
            if not isinstance(sha, str) or _SHA.fullmatch(sha) is None:
                raise ValueError(f"{section} receipt for {relative} has no private object id")
            path = Path(relative)
            if path.is_absolute() or ".." in path.parts or "\\" in relative or ":" in relative:
                raise ValueError("Unsafe publication path")
            if workspace is not None:
                root = Path(workspace).resolve()
                candidate = root / "dashboard" / path if section == "assets" else root / path
                if not candidate.resolve().is_relative_to(root):
                    raise ValueError("Publication path escaped the workspace")
                if not candidate.is_file():
                    continue
            ordered.append((section, relative, entry))
    return ordered


def object_patterns(manifest: dict, workspace: Path | None = None) -> list[str]:
    seen = set()
    ordered = []
    for _, _, entry in publication_entries(manifest, workspace):
        identity = entry["private_sha256"]
        if identity not in seen:
            seen.add(identity)
            ordered.append("/dashboard-private/objects/" + identity)
    return ordered


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 4) or len(argv) == 4 and argv[2] != "--workspace":
        print("usage: vault_publication_sparse.py dashboard/private-assets.json", file=sys.stderr)
        return 2
    manifest = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    workspace = Path(argv[3]) if len(argv) == 4 else None
    for line in object_patterns(manifest, workspace):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
