"""Recover an already approved immutable handoff, without another judgment call."""
from __future__ import annotations

import argparse
import io
import json
import os
import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from private_storage import ROOT, PrivateStorage, StorageError, encoded_json, load_config, relative_path, sha


def validate_archive(raw, approved, *, validate=None):
    if sha(raw) != approved["archive_sha256"]:
        raise StorageError("Approved recovery archive identity changed")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        names = [relative_path(item.filename) for item in infos]
        if len(names) != len(set(names)) or any(stat.S_ISLNK(item.external_attr >> 16) for item in infos):
            raise StorageError("Duplicate or linked recovery archive member")
        if sum(item.file_size for item in infos) > 512 * 1024 * 1024:
            raise StorageError("Recovery archive exceeds its complete bounded transport")
        manifest = json.loads(archive.read("manifest.json"))
        if (manifest.get("schema_version") != "underwriting-private-recovery/1"
                or manifest.get("ticker") != "V" or manifest.get("limit") != 1
                or manifest.get("handoff_hash") != approved["handoff_hash"]
                or manifest.get("contract_hash") != approved["contract_hash"]
                or manifest.get("review_verdict") != "approve"):
            raise StorageError("Approved recovery manifest binding changed")
        files, expected = {}, {"manifest.json"}
        for section in ("materialize", "historical"):
            records = manifest.get(section)
            if not isinstance(records, list):
                raise StorageError("Incomplete recovery manifest")
            for entry in records:
                path = relative_path(entry["path"])
                name = "materialize/" + path if section == "materialize" else path
                if name in expected:
                    raise StorageError("Duplicate recovery manifest member")
                expected.add(name)
                value = archive.read(name)
                if len(value) != entry["bytes"] or sha(value) != entry["sha256"]:
                    raise StorageError("Complete recovery member changed")
                if section == "materialize":
                    if not path.startswith("valuation-underwriting/"):
                        raise StorageError("Recovery escaped the approved underwriting namespace")
                    files[path] = value
        if expected != set(names):
            raise StorageError("Recovery archive is incomplete or has unlisted members")
        handoff_path = "valuation-underwriting/handoffs/" + approved["handoff_hash"] + ".json"
        payload = json.loads(files[handoff_path])
        if validate is None:
            from underwriting_contract import digest
            from underwriting_pipeline import validate_handoff
            canonical = validate_handoff(ROOT, payload, approved["handoff_hash"])
            if digest(canonical) != manifest["canonical_hash"] or digest(payload["contract"]) != approved["contract_hash"]:
                raise StorageError("Approved canonical model changed during recovery")
        else:
            validate(payload, approved, manifest)
        ledger = files["valuation-underwriting/local-runtime/ledger.jsonl"]
        actual = [json.loads(line) for line in ledger.splitlines() if line.strip()]
        original = [json.loads(line) for line in archive.read("preserved_prelaunch/ledger-original.jsonl").splitlines() if line.strip()]
        if (len(actual) != manifest["actual_ledger_rows"] or len(original) != manifest["original_ledger_rows"]
                or actual[:len(original)] != original):
            raise StorageError("Recovery admission ledger history changed")
        pointer = json.loads(files["valuation-underwriting/handoffs/latest/V.json"])
        if pointer.get("contract_hash") != approved["contract_hash"] or pointer.get("handoff_hash") != approved["handoff_hash"]:
            raise StorageError("Approved handoff pointer changed")
        return manifest, files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("register", "prepare", "check"))
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--ticker", required=True, choices=("V",))
    parser.add_argument("--limit", type=int, required=True, choices=(1,))
    parser.add_argument("--proof", type=Path)
    args = parser.parse_args()
    config = load_config(ROOT)
    approved = config["approved_recovery"][args.ticker]
    storage = PrivateStorage(config=config)
    if args.action == "register":
        if args.archive is None:
            parser.error("register requires the exact approved local archive")
        raw = args.archive.read_bytes()
    else:
        raw = storage.restore(approved["archive_path"])
        if raw is None:
            raise StorageError("The complete approved private recovery archive is unavailable")
    manifest, files = validate_archive(raw, approved)
    if args.action == "register":
        commit = storage.publish({approved["archive_path"]: raw})
    elif args.action == "prepare":
        commit = storage.publish(files)
    else:
        run = os.environ.get("GITHUB_RUN_ID", "local")
        receipt = {"schema_version": "private-storage-preflight/1", "run_id": run,
                   "checked_at": datetime.now(timezone.utc).isoformat(), "ticker": "V", "limit": 1,
                   "approved_archive_sha256": approved["archive_sha256"], "model_calls": 0,
                   "all_complete_members_verified": len(files), "ledger_rows": manifest["actual_ledger_rows"]}
        commit = storage.publish({"audit/storage-preflight/" + str(run) + ".json": encoded_json(receipt)})
    proof = {"action": args.action, "ticker": "V", "limit": 1, "catalog_commit": commit,
             "archive_sha256": approved["archive_sha256"], "contract_hash": approved["contract_hash"],
             "handoff_hash": approved["handoff_hash"], "complete_members_verified": len(files),
             "actual_ledger_rows": manifest["actual_ledger_rows"], "model_calls": 0,
             "economic_or_compiler_checks_changed": False, "private_archive_verified": True}
    if args.proof:
        args.proof.write_text(json.dumps(proof, indent=2) + "\n")
    print(json.dumps(proof))


if __name__ == "__main__":
    main()
