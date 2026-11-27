"""Exercise real SSI restores with a proposed object's R2 reads masked."""

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path

from private_storage import HEX, PrivateStorage, StorageError, relative_path


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
    for path in paths:
        expected = storage.lookup_entry(path, records)
        reader.objects.misses.clear()
        data = reader.restore(path, records=records)
        if data is None or hashlib.sha256(data).hexdigest() != expected["sha256"] or not reader.objects.misses:
            raise StorageError("Masked SSI restore failed")
        with tempfile.TemporaryDirectory(prefix="ssi-git-restore-") as tmp:
            out = Path(tmp) / "restored"
            reader.objects.misses.clear()
            if not reader.restore_to(path, out, records=records) or not reader.objects.misses:
                raise StorageError("Masked SSI materialization failed")
            with out.open("rb") as materialized:
                if hashlib.file_digest(materialized, "sha256").hexdigest() != expected["sha256"]:
                    raise StorageError("Materialized SSI file hash changed")
    return {"verified_restore_paths": len(paths), "masked_r2_objects": len(digests), "r2_objects_deleted": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path, help="Private JSON with catalog_commit, r2_digests, and restore_paths")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))
    revision, digests, paths = plan["catalog_commit"], plan["r2_digests"], plan["restore_paths"]
    if (not re.fullmatch(r"[0-9a-f]{40}", revision) or not digests or not paths
            or not all(HEX.fullmatch(digest) for digest in digests)
            or len(set(paths)) != len(paths) or len(set(digests)) != len(digests)):
        raise StorageError("Invalid or empty private restore plan")
    storage = PrivateStorage()
    commit, records = storage.snapshot()
    if commit != revision:
        raise StorageError("The active catalog changed; refresh the proposed batch")
    print(json.dumps({"catalog_commit": commit, **verify_restores(storage, records, paths, set(digests))}))


if __name__ == "__main__":
    main()
