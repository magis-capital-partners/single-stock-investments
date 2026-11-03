"""Select only current-manifest archive parts without removing vault history."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

PREFIX = '/dashboard-private/company-source-backfill-v2/'


def part_patterns(manifest: dict) -> list[str]:
    if not isinstance(manifest, dict) or not isinstance(manifest.get('parts'), list):
        raise ValueError('Source archive manifest must contain a parts list')
    result = []
    seen = set()
    for part in manifest['parts']:
        if not isinstance(part, dict):
            raise ValueError('Invalid source archive part')
        sha, name = part.get('sha256'), part.get('file')
        if not isinstance(sha, str) or not re.fullmatch('[a-f0-9]{64}', sha) or name != sha + '.zip':
            raise ValueError('Invalid immutable source archive part')
        if name in seen:
            raise ValueError('Duplicate source archive part')
        seen.add(name)
        result.append(PREFIX + name)
    return result


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: vault_source_archive_sparse.py archive/manifest.json')
    print('\n'.join(part_patterns(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))))
