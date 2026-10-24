#!/usr/bin/env python3
"""Report tracked source-link/extract exposures without copying their contents into logs."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATTERNS = {
    "drive_links": re.compile(r"https?://drive\.google\.com/", re.I),
    "vault_references": re.compile(r"_system[/\\]reference[/\\]superinvestor-letters"),
    "private_evidence_fields": re.compile(r'"(?:source_file|source_document|raw_extract|evidence_quote)"\s*:'),
    "drive_identifiers": re.compile(r'"(?:drive_\w*(?:id|path|link)|driveFileId|driveFolderId|fileId|folder_id)"\s*:', re.I),
}


def audit(root: Path = ROOT, *, staged=False) -> dict:
    command = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"] if staged else ["git", "ls-files", "-z"]
    tracked = subprocess.run(command + ["--"], cwd=root, check=True, capture_output=True).stdout.decode("utf-8").split("\0")
    tracked = [p for p in tracked if p and Path(p).suffix.lower() in {".json", ".jsonl", ".csv", ".js", ".html", ".md", ".pdf", ".txt"} and (p.startswith("dashboard/") or Path(p).suffix.lower() in {".json", ".jsonl", ".csv"} or (Path(p).suffix.lower() == ".md" and "/research/" in p) or p.startswith("_system/reference/superinvestor-letters/"))]
    blobs = {}
    manifest = {"assets": {}}
    if not staged and (root / "dashboard/private-assets.json").is_file():
        manifest = json.loads((root / "dashboard/private-assets.json").read_text(encoding="utf-8"))
    if staged:
        files = list(filter(None, tracked))
        process = subprocess.run(["git", "cat-file", "--batch"], input="".join(":" + p + "\n" for p in files).encode(), cwd=root, check=True, capture_output=True)
        offset = 0
        for relative in files:
            end = process.stdout.index(b"\n", offset)
            header = process.stdout[offset:end].split()
            if len(header) != 3 or header[1] != b"blob":
                raise RuntimeError("Cannot inspect staged asset")
            size = int(header[2]); offset = end + 1
            blobs[relative] = process.stdout[offset:offset + size]
            offset += size + 1
        staged_manifest = subprocess.run(["git", "show", ":dashboard/private-assets.json"], cwd=root, capture_output=True)
        if staged_manifest.returncode == 0:
            manifest = json.loads(staged_manifest.stdout)
    findings = []
    for relative in filter(None, tracked):
        path = root / relative
        if not staged and not path.is_file():
            continue
        data = blobs[relative] if staged else path.read_bytes()
        entry = manifest.get("assets", {}).get(relative.removeprefix("dashboard/")) if relative.startswith("dashboard/") else manifest.get("repository_assets", {}).get(relative)
        if staged and entry and hashlib.sha256(data).hexdigest() != entry["public_sha256"]:
            findings.append({"path": relative, "kind": "managed_private_snapshot_not_sanitized", "matches": 1})
        if relative.startswith("_system/reference/superinvestor-letters/") and path.suffix.lower() in {".pdf", ".txt", ".md"}:
            findings.append({"path": relative, "kind": "tracked_original_or_extract", "matches": 1})
        elif path.suffix.lower() in {".json", ".jsonl", ".js", ".html", ".csv", ".md"}:
            text = data.decode("utf-8", errors="replace")
            source_context = bool(PATTERNS["drive_links"].search(text) or PATTERNS["vault_references"].search(text) or 'superinvestor_letter' in text)
            if not relative.startswith("dashboard/"):
                if path.suffix.lower() in {".js", ".html"} or (not entry and not PATTERNS["vault_references"].search(text) and 'superinvestor_letter' not in text):
                    continue  # Other research collections and generic application code are outside this migration.
                if path.suffix.lower() == ".md" and "/research/" not in relative:
                    continue  # Documentation describing a corpus location is not a source artifact.
            for kind, pattern in PATTERNS.items():
                if kind == "private_evidence_fields" and not (source_context or entry):
                    continue
                if path.suffix.lower() in {".js", ".html"} and kind != "drive_links":
                    continue  # Generic code paths/field declarations are not original source artifacts.
                count = sum(1 for _ in pattern.finditer(text))
                if count:
                    findings.append({"path": relative, "kind": kind, "matches": count})
    return {"scope": "Current tracked dashboard assets, letter-related repository data/research, and legacy letter corpus. Git history, forks, caches, external mirrors, other collections and other hosting require separate review.", "source_restriction_ready": not findings, "affected_files": len({r["path"] for r in findings}), "findings": findings, "required_action": "Move restricted artifacts to the private vault/R2 and stop publishing them in the public repository. Prior public copies cannot be recalled." if findings else None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "_private/fund_letters/exposure.json")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--staged", action="store_true", help="Inspect only staged blobs, including the staged snapshot manifest")
    args = parser.parse_args()
    report = audit(staged=args.staged)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "findings"}))
    return int(args.strict and not report["source_restriction_ready"])


if __name__ == "__main__":
    raise SystemExit(main())
