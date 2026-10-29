#!/usr/bin/env python3
"""Keep full audited artifacts in the private vault; redact public dashboard snapshots.

Public counterparts retain structural counts only. Full payloads stay private.
Cloudflare builds restore the exact private versions after authorization middleware
has been installed. No private payload is printed or added to the public index.
"""
from __future__ import annotations

import argparse
import hashlib
import csv
import io
import json
import shutil
import subprocess
from pathlib import Path

from audit_fund_letter_exposure import audit
from private_dashboard_assets import ROOT, digest, hydration_state, write_hydration, overlay_manifest, private_object, safe_relative
from vault_paths import research_vault_root

def public_snapshot(value):
    """Only structural metadata is published; no source-derived leaf values survive."""
    shape = "object" if isinstance(value, dict) else "array" if isinstance(value, list) else "scalar"
    public = {"private_snapshot": True, "source_shape": shape}
    if isinstance(value, (dict, list)):
        public["entry_count"] = len(value)
    if isinstance(value, dict):
        names = {"letters", "funds", "records", "rows", "items", "documents", "tickers", "positions"}
        public["collection_counts"] = {key: len(item) for key, item in value.items() if key in names and isinstance(item, (list, dict))}
    return public


def is_placeholder(value):
    return isinstance(value, dict) and value.get("private_snapshot") is True or isinstance(value, list) and len(value) == 1 and is_placeholder(value[0])


ATTRIBUTE_MARKER = "# Checksum-protected public counterparts of private Fund Letters assets."
ATTRIBUTE_END = "# End private Fund Letters asset rules."


def _attribute_outside(text: str) -> tuple[str, str]:
    """Lines before the managed block and after its end marker.

    One newline that terminates the end marker is not part of the trailer.
    Further blank lines are. They were dropped when lstrip ate every leading
    newline.
    """
    if not text or ATTRIBUTE_MARKER not in text:
        return text or "", ""
    before, rest = text.split(ATTRIBUTE_MARKER, 1)
    if ATTRIBUTE_END not in rest:
        return before, ""
    after = rest.split(ATTRIBUTE_END, 1)[1]
    if after.startswith("\r\n"):
        after = after[2:]
    elif after.startswith("\n"):
        after = after[1:]
    return before, after


def _head_attributes(root: Path) -> str:
    try:
        shown = subprocess.run(
            ["git", "-C", str(root), "show", "HEAD:.gitattributes"],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return ""
    return shown.stdout if shown.returncode == 0 else ""


def _preserved_outside(worktree: str, committed: str) -> tuple[str, str]:
    """Keep every non-managed line. A sparse checkout that never had the file
    must not replace HEAD with only the managed section.
    """
    before_work, after_work = _attribute_outside(worktree)
    before_head, after_head = _attribute_outside(committed)
    work_lines = (before_work + after_work).splitlines()
    missing = [line for line in (before_head + after_head).splitlines() if line.strip() and line not in work_lines]
    if not worktree or missing:
        return before_head, after_head
    return before_work, after_work


def write_public_attributes(root: Path, manifest: dict) -> None:
    attributes = root / ".gitattributes"
    worktree = attributes.read_text(encoding="utf-8") if attributes.is_file() else ""
    before, after = _preserved_outside(worktree, _head_attributes(root))
    rules = ["/dashboard/private-assets.json text eol=lf"] + [json.dumps("/dashboard/" + p) + " text eol=lf" for p in sorted(manifest.get("assets", {}))] + [json.dumps("/" + p) + " text eol=lf" for p in sorted(manifest.get("repository_assets", {}))]
    section = ATTRIBUTE_MARKER + "\n" + "\n".join(rules) + "\n" + ATTRIBUTE_END + "\n"
    if not before and not after and worktree and ATTRIBUTE_MARKER not in worktree:
        before = worktree if worktree.endswith("\n") else worktree + "\n"
    attributes.write_text(before + section + after, encoding="utf-8")


def migrate(root: Path = ROOT, *, paths: list[str] | None = None) -> dict:
    vault = research_vault_root()
    source = root / "dashboard"
    manifest = overlay_manifest(source)
    format_changed = manifest.get("publication_format") != "metadata-only-v1"
    entries = manifest.setdefault("assets", {})
    repository_entries = manifest.setdefault("repository_assets", {})
    prior_originals = manifest.pop("originals_migrated", [])
    hydrated = hydration_state(root)
    # The append-only journal recovers a crash between redaction and manifest commit.
    # Content-addressed objects retain old versions used by concurrent builds.
    journal = vault / "dashboard-private/migration-journal.jsonl" if vault else None
    recovered = bool(prior_originals) or (format_changed and bool(entries or repository_entries))
    if journal and journal.is_file():
        for line in journal.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            safe_relative(item["path"])
            collection = repository_entries if item.get("scope") == "repository" else entries
            base = root if item.get("scope") == "repository" else source
            if item["entry"] != collection.get(item["path"]):
                # An older public checkout must keep its own matching version.
                public = base / item["path"]
                previous = collection.get(item["path"], {})
                if public.is_file() and digest(public) in item["entry"].values() and digest(public) not in previous.values():
                    collection[item["path"]] = item["entry"]
                    recovered = True
    candidates = sorted(set(paths if paths is not None else [r["path"] for r in audit(root)["findings"]]))
    # Re-export any hydrated snapshots, even if only an otherwise innocent field changed.
    candidates = sorted(set(candidates) | {"dashboard/" + p for p in entries} | set(repository_entries))
    managed = {"dashboard/" + k: v for k, v in entries.items()}
    managed.update(repository_entries)
    for relative in candidates:
        safe_relative(relative)
    pending = [p for p in candidates if (root / p).is_file() and ((root / p).suffix.lower() in {".json", ".jsonl", ".csv", ".pdf", ".txt", ".md"}) and (format_changed or p not in managed or digest(root / p) != managed[p]["public_sha256"])]
    if not pending and not recovered:
        if managed:
            write_public_attributes(root, manifest)
        return {"migrated_or_updated_assets": 0, "managed_private_assets": len(managed), "originals_migrated": 0}
    if vault is None or not (vault / ".git").exists():
        raise RuntimeError("A configured private research-vault checkout is required; public files were not changed.")
    journal.parent.mkdir(parents=True, exist_ok=True)
    (journal.parent / ".gitattributes").write_text("objects/* -text\noriginals/** -text\n", encoding="utf-8")
    changed = 0
    originals = []
    for relative in candidates:
        path = root / relative
        if not path.is_file():
            continue
        if relative.startswith("_system/reference/superinvestor-letters/") and path.suffix.lower() in {".pdf", ".txt", ".md"}:
            dest = vault / "dashboard-private/originals" / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists() and digest(dest) != digest(path):
                raise RuntimeError("An existing private original differs; preserve both editions before retrying")
            shutil.copy2(path, dest)
            if digest(path) != digest(dest):
                raise RuntimeError("Original source copy failed verification")
            path.unlink()  # Only after verified preservation, never recursive.
            originals.append(relative)
            continue
        if path.suffix.lower() not in {".json", ".jsonl", ".csv", ".md"}:
            continue
        dashboard = relative.startswith("dashboard/")
        collection = entries if dashboard else repository_entries
        key = path.relative_to(source).as_posix() if dashboard else relative
        existing = collection.get(key)
        original_hash = digest(path)
        upgrading = existing and original_hash == existing["public_sha256"] and format_changed
        payload_path = private_object(vault, existing["private_sha256"]) if upgrading else path
        if upgrading and (not payload_path.is_file() or digest(payload_path) != existing["private_sha256"]):
            raise RuntimeError(f"Private snapshot is missing or mismatched: {key}")
        if existing and original_hash == existing["public_sha256"] and not upgrading:
            continue  # Never replace the full private copy with its redacted public counterpart.
        if existing and not upgrading and original_hash != existing["private_sha256"] and hydrated.get(relative) != existing["private_sha256"]:
            raise RuntimeError(f"Hydrate the managed private snapshot before rebuilding: {key}")
        if path.suffix.lower() in {".json", ".jsonl"}:
            lines = path.suffix.lower() == ".jsonl"
            doc = [json.loads(line) for line in payload_path.read_text(encoding="utf-8").splitlines() if line.strip()] if lines else json.loads(payload_path.read_text(encoding="utf-8"))
            redacted = public_snapshot(doc)
            if existing and is_placeholder(doc) and digest(payload_path) != existing["private_sha256"]:
                raise RuntimeError(f"Hydrate the managed private snapshot before rebuilding: {key}")
            text = json.dumps(redacted, ensure_ascii=False, separators=(",", ":")) + "\n"
        elif path.suffix.lower() == ".md":
            text = "This source-linked research document is available in the private research archive.\n"
            if existing and payload_path.read_text(encoding="utf-8") == text:
                raise RuntimeError(f"Hydrate the managed private snapshot before rebuilding: {key}")
        else:
            rows = list(csv.DictReader(io.StringIO(payload_path.read_text(encoding="utf-8"))))
            if existing and rows and "private_snapshot" in rows[0] and digest(path) != existing["private_sha256"]:
                raise RuntimeError(f"Hydrate the managed private snapshot before rebuilding: {key}")
            stream = io.StringIO()
            writer = csv.DictWriter(stream, fieldnames=["private_snapshot", "entry_count"], lineterminator="\n")
            writer.writeheader(); writer.writerow({"private_snapshot": "true", "entry_count": len(rows)})
            text = stream.getvalue()
        private_hash = digest(payload_path)
        private = private_object(vault, private_hash)
        private.parent.mkdir(parents=True, exist_ok=True)
        if not private.exists():
            shutil.copy2(payload_path, private)
        if private_hash != digest(private) or private_hash != digest(payload_path):
            raise RuntimeError(f"Private copy failed verification: {key}")
        # Journal the recovery mapping before redacting the local public copy.
        entry = {"private_sha256": private_hash, "public_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        if entry != existing:
            with journal.open("a", encoding="utf-8") as log:
                log.write(json.dumps({"path": key, "scope": "dashboard" if dashboard else "repository", "entry": entry}) + "\n")
        collection[key] = entry
        temporary = path.with_name(path.name + ".private-redaction.tmp")
        temporary.write_bytes(text.encode("utf-8"))
        if digest(path) != original_hash:
            raise RuntimeError(f"Input changed during migration; retry without overwriting it: {key}")
        temporary.replace(path)
        hydrated.pop(relative, None)
        changed += 1
    manifest["schema_version"] = 1
    manifest["publication_format"] = "metadata-only-v1"
    manifest["originals_migrated_count"] = max(manifest.get("originals_migrated_count", 0), len(set(prior_originals) | set(originals)))
    manifest_text = json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    write_hydration(root, hydrated)
    write_public_attributes(root, manifest)
    for destination in (source / "private-assets.json", vault / "dashboard-private/manifest.json"):
        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(manifest_text, encoding="utf-8")
        temporary.replace(destination)
    return {"migrated_or_updated_assets": changed, "managed_private_assets": len(entries) + len(repository_entries), "originals_migrated": len(originals)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(migrate(args.root)))
