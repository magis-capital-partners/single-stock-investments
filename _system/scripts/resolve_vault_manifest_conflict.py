"""Merge only the private receipt index during a vault rebase.

Immutable objects carry every snapshot. Preserve the newer upstream pointer
when two producers changed the same receipt, and retain independent additions.
Never resolve source contents or recovery manifest conflicts automatically.
"""
import json
from pathlib import Path
import subprocess
import sys

MISSING = object()


def reconcile(base, upstream, incoming):
    if upstream == incoming or incoming == base:
        return upstream
    if upstream == base:
        return incoming
    if isinstance(upstream, dict) and isinstance(incoming, dict) and (isinstance(base, dict) or base is MISSING):
        # A receipt's private/public hashes are one pair. Mixing fields from
        # two snapshots could point at an object with the wrong public receipt.
        if "private_sha256" in upstream or "private_sha256" in incoming:
            return upstream
        base = {} if base is MISSING else base
        result = {}
        for key in sorted(set(base) | set(upstream) | set(incoming)):
            value = reconcile(base.get(key, MISSING), upstream.get(key, MISSING), incoming.get(key, MISSING))
            if value is not MISSING:
                result[key] = value
        return result
    return upstream


def resolve(vault):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(vault), *args])
    path = "dashboard-private/manifest.json"
    conflicts = git("diff", "--name-only", "--diff-filter=U").decode().splitlines()
    if conflicts != [path]:
        raise RuntimeError("Vault conflict includes source data; refusing automatic resolution")
    versions = [json.loads(git("show", f":{stage}:{path}")) for stage in (1, 2, 3)]
    (Path(vault) / path).write_text(json.dumps(reconcile(*versions), sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    git("add", "--", path)


if __name__ == "__main__":
    resolve(Path(sys.argv[1]))
