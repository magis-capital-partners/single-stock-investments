#!/usr/bin/env python3
"""One-shot: resolve conflicts and squash-merge open contract-backfill agent PRs."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Easier first (historically no classification.json), then remaining ascending.
ORDER = [
    527,
    532,
    547,
    584,
    585,
    586,
    513,
    516,
    523,
    524,
    528,
    533,
    534,
    535,
    537,
    538,
    540,
    542,
    548,
    561,
    564,
    571,
    575,
    579,
    588,
]


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if proc.stdout:
        sys.stdout.write(proc.stdout if proc.stdout.endswith("\n") else proc.stdout + "\n")
    if proc.stderr:
        sys.stderr.write(proc.stderr if proc.stderr.endswith("\n") else proc.stderr + "\n")
    if check and proc.returncode != 0:
        raise SystemExit(proc.returncode)
    return proc


def pr_json(pr: int, fields: str) -> dict:
    return json.loads(run(["gh", "pr", "view", str(pr), "--json", fields]).stdout)


def wait_mergeable(pr: int, attempts: int = 12) -> str:
    mergeable = "UNKNOWN"
    for _ in range(attempts):
        time.sleep(5)
        mergeable = pr_json(pr, "mergeable")["mergeable"]
        print(f"  mergeable={mergeable}", flush=True)
        if mergeable in {"MERGEABLE", "CONFLICTING"}:
            break
    return mergeable


def main() -> None:
    results: list[tuple[int, str]] = []
    for pr in ORDER:
        meta = pr_json(pr, "state,mergeable,title")
        if meta["state"] != "OPEN":
            results.append((pr, f"already_{meta['state'].lower()}"))
            print(f"PR #{pr} already {meta['state']}", flush=True)
            continue

        title = (meta.get("title") or "")[:70]
        print(
            f"\n==== PR #{pr} {title} mergeable={meta['mergeable']} ====",
            flush=True,
        )

        mergeable = meta["mergeable"]
        if mergeable != "MERGEABLE":
            resolved = run(
                ["python", "_system/scripts/resolve_marvin_pr_conflicts.py", str(pr)],
                check=False,
            )
            if resolved.returncode != 0:
                results.append((pr, "resolve_failed"))
                print(f"RESOLVE FAILED #{pr}", flush=True)
                continue
            mergeable = wait_mergeable(pr)
            if mergeable != "MERGEABLE":
                results.append((pr, f"not_mergeable_{mergeable}"))
                continue

        merged = run(
            ["gh", "pr", "merge", str(pr), "--squash", "--delete-branch"],
            check=False,
        )
        if merged.returncode == 0:
            results.append((pr, "merged"))
            time.sleep(3)
        else:
            results.append((pr, "merge_failed"))

    print("\n==== SUMMARY ====", flush=True)
    for pr, status in results:
        print(f"{pr}: {status}", flush=True)

    open_left = json.loads(
        run(["gh", "pr", "list", "--state", "open", "--limit", "50", "--json", "number,title"]).stdout
    )
    print(f"Open PRs remaining: {len(open_left)}", flush=True)
    for row in open_left:
        print(f"  #{row['number']} {row['title'][:80]}", flush=True)


if __name__ == "__main__":
    main()
