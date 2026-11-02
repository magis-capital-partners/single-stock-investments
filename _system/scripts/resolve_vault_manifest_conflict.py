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


MANIFEST = "dashboard-private/manifest.json"
JOURNAL = "dashboard-private/migration-journal.jsonl"
# These two files are the shared index. Object hashes are unique paths and do
# not conflict. Anything else is source or archive content.
RECEIPT_PATHS = {MANIFEST, JOURNAL}


def merge_journal(upstream: str, incoming: str) -> str:
    """Append-only union. Upstream order wins. Incoming lines not already present follow."""
    lines: list[str] = []
    seen: set[str] = set()
    for text in (upstream, incoming):
        for line in text.splitlines():
            if line and line not in seen:
                seen.add(line)
                lines.append(line)
    return ("\n".join(lines) + "\n") if lines else ""


def resolve(vault):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(vault), *args])
    conflicts = [path for path in git("diff", "--name-only", "--diff-filter=U").decode().splitlines() if path]
    if any(path not in RECEIPT_PATHS for path in conflicts):
        raise RuntimeError("Vault conflict includes source data; refusing automatic resolution")
    if MANIFEST in conflicts:
        versions = [json.loads(git("show", f":{stage}:{MANIFEST}")) for stage in (1, 2, 3)]
        target = Path(vault) / MANIFEST
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(reconcile(*versions), sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        git("add", "--sparse", "--", MANIFEST)
    if JOURNAL in conflicts:
        upstream = git("show", f":2:{JOURNAL}").decode()
        incoming = git("show", f":3:{JOURNAL}").decode()
        target = Path(vault) / JOURNAL
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(merge_journal(upstream, incoming), encoding="utf-8")
        git("add", "--sparse", "--", JOURNAL)


if __name__ == "__main__":
    resolve(Path(sys.argv[1]))
