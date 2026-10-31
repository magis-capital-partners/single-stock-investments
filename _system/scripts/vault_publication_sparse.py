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


def object_patterns(manifest: dict) -> list[str]:
    """Sparse-checkout patterns for every private object the manifest names."""
    if not isinstance(manifest, dict):
        raise ValueError("private-assets manifest must be an object")
    ordered: list[str] = []
    seen: set[str] = set()
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
            if sha in seen:
                continue
            seen.add(sha)
            ordered.append(f"/dashboard-private/objects/{sha}")
    return ordered


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: vault_publication_sparse.py dashboard/private-assets.json", file=sys.stderr)
        return 2
    manifest = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    for line in object_patterns(manifest):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
