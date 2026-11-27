"""Exercise real SSI restores with a proposed object's R2 reads masked."""

import argparse
import hashlib
import json
import re
import tempfile
import time
from pathlib import Path

from private_storage import (
    HEX,
    MAX_METADATA_BYTES,
    PrivateStorage,
    StorageError,
    relative_path,
)


class MaskedObjects:
    def __init__(self, objects, digests):
        self.objects = objects
        self.digests = digests
        self.misses = set()

    def get(self, identity, size):
        if identity in self.digests:
            self.misses.add(identity)
            return None
        return self.objects.get(identity, size)


def verify_restores(storage, records, paths, digests):
    """Require each sample to encounter a masked object through both readers."""
    for path in paths:
        relative_path(path)
        entry = storage.lookup_entry(path, records)
        if not entry or not digests.intersection(c["stored_sha256"] for c in entry["chunks"]):
            raise StorageError("A requested sample does not use the proposed removal set")
    reader = PrivateStorage(
        config=storage.config, objects=MaskedObjects(storage.objects, digests), catalog=storage.catalog,
    )
    timings = []
    for path in paths:
        expected = storage.lookup_entry(path, records)
        reader.objects.misses.clear()
        start = time.monotonic()
        data = reader.restore(path, records=records)
        restore_seconds = time.monotonic() - start
        if data is None or hashlib.sha256(data).hexdigest() != expected["sha256"] or not reader.objects.misses:
            raise StorageError("Masked SSI restore failed")
        with tempfile.TemporaryDirectory(prefix="ssi-git-restore-") as tmp:
            out = Path(tmp) / "restored"
            reader.objects.misses.clear()
            start = time.monotonic()
            if not reader.restore_to(path, out, records=records) or not reader.objects.misses:
                raise StorageError("Masked SSI materialization failed")
            with out.open("rb") as materialized:
                if hashlib.file_digest(materialized, "sha256").hexdigest() != expected["sha256"]:
                    raise StorageError("Materialized SSI file hash changed")
            timings.append({"restore_seconds": round(restore_seconds, 3),
                            "materialize_seconds": round(time.monotonic() - start, 3)})
    return {"verified_restore_paths": len(paths), "masked_r2_objects": len(digests),
            "restore_timings": timings, "r2_objects_deleted": 0}


def check_live_dashboard(objects, digests):
    """Exclude the live dashboard objects whose Workers read R2 directly."""
    def pointer(key):
        raw = objects.http.request("GET", objects.base + key, limit=1024 * 1024)
        if raw is None:
            raise StorageError("A live dashboard pointer could not be checked")
        return json.loads(raw)

    research = pointer("research-explorer/v1/current.json")
    summary = pointer("stock-summary/v1/current.json")
    if research.get("schema_version") != "stock-research-live.v1" or summary.get("schema") != "stock-summary.v1":
        raise StorageError("Unexpected live dashboard pointer schema")
    receipts = [research["index"], *research["companies"].values(), summary["coverage"], *summary["bundles"].values()]
    if research.get("changes") is not None:
        receipts.append(research["changes"])
    live = {chunk["stored_sha256"] for receipt in receipts for chunk in receipt["chunks"]}
    if not live or not all(HEX.fullmatch(digest) for digest in live):
        raise StorageError("A live dashboard receipt has an invalid object identity")
    if live.intersection(digests):
        raise StorageError("A proposed removal is still referenced by a live dashboard")
    return len(live)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path, nargs="?", help="Private JSON with catalog_commit, r2_digests, and restore_paths")
    parser.add_argument("--plan-digest", help="SHA-256 of a private plan saved as an immutable object")
    parser.add_argument("--plan-size", type=int, help="Stored size of the private plan")
    args = parser.parse_args()
    remote = args.plan_digest is not None or args.plan_size is not None
    if (bool(args.plan) == remote or (remote and
            (not HEX.fullmatch(args.plan_digest or "") or not 0 < (args.plan_size or 0) <= MAX_METADATA_BYTES))):
        parser.error("Provide one private plan file or a bounded immutable digest and size")
    storage = PrivateStorage()
    raw = storage.objects.get(args.plan_digest, args.plan_size) if remote else args.plan.read_bytes()
    if raw is None:
        raise StorageError("The immutable private restore plan is absent")
    plan = json.loads(raw.decode("utf-8-sig"))
    revision, digests, paths = plan["catalog_commit"], plan["r2_digests"], plan["restore_paths"]
    if (not re.fullmatch(r"[0-9a-f]{40}", revision) or not digests or not paths
            or not all(HEX.fullmatch(digest) for digest in digests)
            or len(set(paths)) != len(paths) or len(set(digests)) != len(digests)):
        raise StorageError("Invalid or empty private restore plan")
    commit, records = storage.snapshot()
    if commit != revision:
        raise StorageError("The active catalog changed; refresh the proposed batch")
    live_count = check_live_dashboard(storage.objects, set(digests))
    print(json.dumps({"catalog_commit": commit, "live_dashboard_objects_checked": live_count,
                      **verify_restores(storage, records, paths, set(digests))}))


if __name__ == "__main__":
    main()
