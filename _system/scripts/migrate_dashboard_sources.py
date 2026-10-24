#!/usr/bin/env python3
"""Keep full audited artifacts in the private vault; redact public dashboard snapshots.

The source tree retains all counts, identities, dates and other non-source data.
Cloudflare builds restore the exact private versions after authorization middleware
has been installed. No private payload is printed or added to the public index.
"""
from __future__ import annotations

import argparse
import hashlib
import csv
import io
import json
import re
import shutil
from pathlib import Path

from audit_fund_letter_exposure import audit
from private_dashboard_assets import ROOT, digest, overlay_manifest, private_object, safe_relative
from vault_paths import research_vault_root

PRIVATE_FIELDS = {
    "source_file", "source_document", "raw_extract", "evidence_quote", "raw_text", "extracted_text",
    "lead_summary", "commentary", "thesis", "quote", "evidence", "evidence_url", "evidence_label",
    "source_url", "drive_url", "drive_id", "drive_file_id", "drive_pdf_id", "download_token",
    "duplicate_sources", "alternate_sources", "source_ref",
}
PRIVATE_VALUE = re.compile(r"https?://drive\.google\.com/|_system[/\\]reference[/\\]superinvestor-letters", re.I)


def redact(value, *, letter_context=False):
    if isinstance(value, dict):
        # A letter record can contain extracts under generic text/claim/summary names.
        letter = letter_context or value.get("source_type") in {"superinvestor_letter", "superinvestor-letters", "fund_letter", "letter"} or any(isinstance(v, str) and "superinvestor-letters/" in v for v in value.values())
        clean = {}
        for key, item in value.items():
            normalized_key = re.sub(r"[^a-z]", "", key.lower())
            if key in PRIVATE_FIELDS or (key.lower().startswith("drive_") or normalized_key.startswith(("drivefile", "drivefolder", "driveroot", "driveweb", "gdrive"))) or normalized_key in {"driveid", "fileid", "folderid", "localpdfpath", "textextractpath", "alternatetextextractpaths", "alternatepdfpaths", "links"} or (letter and key in {"text", "claim", "summary", "description", "snippet", "excerpt", "text_excerpt"}):
                continue
            if PRIVATE_VALUE.search(key):
                # Some link indexes use private paths as keys and bare Drive IDs as values.
                clean["restricted-" + hashlib.sha256(key.encode()).hexdigest()[:24]] = None
            else:
                clean[key] = redact(item, letter_context=letter)
        return clean
    if isinstance(value, list):
        return [redact(v, letter_context=letter_context) for v in value]
    if isinstance(value, str) and PRIVATE_VALUE.search(value):
        return ""
    return value


def write_public_attributes(root: Path, manifest: dict) -> None:
    attributes = root / ".gitattributes"
    prior = attributes.read_text(encoding="utf-8") if attributes.exists() else ""
    marker = "# Checksum-protected public counterparts of private Fund Letters assets."
    end_marker = "# End private Fund Letters asset rules."
    rules = ["/dashboard/private-assets.json text eol=lf"] + [json.dumps("/dashboard/" + p) + " text eol=lf" for p in sorted(manifest.get("assets", {}))] + [json.dumps("/" + p) + " text eol=lf" for p in sorted(manifest.get("repository_assets", {}))]
    section = marker + "\n" + "\n".join(rules) + "\n" + end_marker + "\n"
    if marker in prior:
        before, old = prior.split(marker, 1)
        after = old.split(end_marker, 1)[1].lstrip("\r\n") if end_marker in old else ""
        updated = before + section + after
    else:
        updated = prior.rstrip() + "\n" + section
    attributes.write_text(updated, encoding="utf-8")


def migrate(root: Path = ROOT, *, paths: list[str] | None = None) -> dict:
    vault = research_vault_root()
    source = root / "dashboard"
    manifest = overlay_manifest(source)
    entries = manifest.setdefault("assets", {})
    repository_entries = manifest.setdefault("repository_assets", {})
    prior_originals = manifest.pop("originals_migrated", [])
    # The append-only journal recovers a crash between redaction and manifest commit.
    # Content-addressed objects retain old versions used by concurrent builds.
    journal = vault / "dashboard-private/migration-journal.jsonl" if vault else None
    recovered = bool(prior_originals)
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
    pending = [p for p in candidates if (root / p).is_file() and ((root / p).suffix.lower() in {".json", ".jsonl", ".csv", ".pdf", ".txt", ".md"}) and (p not in managed or digest(root / p) != managed[p]["public_sha256"])]
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
        if existing and digest(path) == existing["public_sha256"]:
            continue  # Never replace the full private copy with its redacted public counterpart.
        if path.suffix.lower() in {".json", ".jsonl"}:
            lines = path.suffix.lower() == ".jsonl"
            doc = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if lines else json.loads(path.read_text(encoding="utf-8"))
            redacted = redact(doc)
            if existing and redacted == doc and digest(path) != existing["private_sha256"]:
                raise RuntimeError(f"Hydrate the managed private snapshot before rebuilding: {key}")
            if redacted == doc and not existing:
                continue
            text = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in redacted) if lines else json.dumps(redacted, ensure_ascii=False, separators=(",", ":")) + "\n"
        elif path.suffix.lower() == ".md":
            text = "This source-linked research document is available in the private research archive.\n"
            if existing and path.read_text(encoding="utf-8") == text:
                raise RuntimeError(f"Hydrate the managed private snapshot before rebuilding: {key}")
        else:
            rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))
            clean = [redact(row) for row in rows]
            if existing and clean == rows and digest(path) != existing["private_sha256"]:
                raise RuntimeError(f"Hydrate the managed private snapshot before rebuilding: {key}")
            if clean == rows and not existing:
                continue
            stream = io.StringIO()
            writer = csv.DictWriter(stream, fieldnames=list(clean[0]) if clean else [], lineterminator="\n")
            writer.writeheader(); writer.writerows(clean)
            text = stream.getvalue()
        private_hash = digest(path)
        private = private_object(vault, private_hash)
        private.parent.mkdir(parents=True, exist_ok=True)
        if not private.exists():
            shutil.copy2(path, private)
        if private_hash != digest(private) or private_hash != digest(path):
            raise RuntimeError(f"Private copy failed verification: {key}")
        # Journal the recovery mapping before redacting the local public copy.
        entry = {"private_sha256": private_hash, "public_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        with journal.open("a", encoding="utf-8") as log:
            log.write(json.dumps({"path": key, "scope": "dashboard" if dashboard else "repository", "entry": entry}) + "\n")
        collection[key] = entry
        temporary = path.with_name(path.name + ".private-redaction.tmp")
        temporary.write_bytes(text.encode("utf-8"))
        if digest(path) != private_hash:
            raise RuntimeError(f"Input changed during migration; retry without overwriting it: {key}")
        temporary.replace(path)
        changed += 1
    manifest["schema_version"] = 1
    manifest["originals_migrated_count"] = max(manifest.get("originals_migrated_count", 0), len(set(prior_originals) | set(originals)))
    manifest_text = json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
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
