import unittest
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from _system.scripts.reverse_splits import checkpoint_retention as retention

NOW = datetime(2026, 11, 27, 17, tzinfo=timezone.utc)


def file_record(body, ordinal, modified=NOW - timedelta(days=3)):
    digest = sha256(body).hexdigest()
    return {
        "key": f"{retention.PREFIX}{digest}-00000000-0000-4000-8000-{ordinal:012x}.sqlite.gz",
        "last_modified": modified.isoformat(),
        "size": len(body),
        "etag": f"etag-{ordinal}",
    }


class StorageFixture:
    def __init__(self, rows, pointer, data=None):
        self.rows = rows
        self.pointer = pointer
        self.data = data or {}
        self.deletions = []

    def inventory(self, prefix=retention.PREFIX):
        return (row for row in self.rows if row["key"].startswith(prefix))

    def checkpoint(self):
        return self.pointer

    def get(self, key):
        return BytesIO(self.data[key])

    def delete(self, key):
        self.deletions.append(key)


class CheckpointRetentionTests(unittest.TestCase):
    def test_inventory_accepts_the_final_page_without_pagination_metadata(self):
        first, last = file_record(b"first", 1), file_record(b"last", 2)
        storage = retention.Storage("fixture")
        pages = iter(
            (
                {
                    "result": [first],
                    "result_info": {"cursor": "other-page", "is_truncated": True},
                },
                {"result": [last]},
            )
        )
        storage.query = lambda path: next(pages)
        self.assertEqual(list(storage.inventory()), [first, last])

    def test_plan_keeps_both_generations_and_both_bases(self):
        current, previous, base, previous_base, orphan, fresh = (
            file_record(
                bytes([i]), i, modified=NOW - timedelta(days=1 if i == 6 else 3)
            )
            for i in range(1, 7)
        )
        pointer = {
            "key": current["key"],
            "format": "sqlite_block_delta.v2",
            "base": {"key": base["key"]},
            "previous": {
                "key": previous["key"],
                "format": "sqlite_block_delta.v1",
                "base": {"key": previous_base["key"]},
            },
        }
        legacy = {**orphan, "key": "collector-state/slot0.sqlite"}
        filing = {**orphan, "key": "documents/" + "a" * 64}
        store = StorageFixture(
            [current, previous, base, previous_base, orphan, fresh, legacy, filing],
            pointer,
        )
        plan = retention.plan(store, NOW, 1)
        self.assertEqual(plan["objects"], [orphan])
        self.assertEqual(plan["eligible_bytes"], 1)
        self.assertEqual(store.deletions, [])

    def test_archive_and_expire_require_a_full_checked_copy(self):
        body = b"an archived, superseded generation"
        orphan, current = file_record(body, 1), file_record(b"current", 2)
        store = StorageFixture(
            [orphan, current], {"key": current["key"]}, {orphan["key"]: body}
        )
        with TemporaryDirectory() as scratch:
            destination = Path(scratch)
            with self.assertRaisesRegex(ValueError, "missing or wrong size"):
                retention.expire(store, [orphan], destination)
            retention.archive(store, [orphan], destination)
            saved = retention.archive_path(destination, orphan)
            self.assertEqual(saved.read_bytes(), body)
            saved.write_bytes(b"!" + body[1:])
            with self.assertRaisesRegex(ValueError, "failed SHA-256"):
                retention.expire(store, [orphan], destination)
            self.assertEqual(store.deletions, [])
            saved.write_bytes(body)
            self.assertEqual(
                retention.expire(store, [orphan], destination)["deleted_objects"], 1
            )
            self.assertEqual(store.deletions, [orphan["key"]])
            self.assertEqual(saved.read_bytes(), body)

    def test_expire_rechecks_source_metadata_and_the_live_pointer(self):
        body = b"valid generation"
        source, current = file_record(body, 1), file_record(b"current", 2)
        expected = source.copy()
        store = StorageFixture(
            [source, current], {"key": current["key"]}, {source["key"]: body}
        )
        with TemporaryDirectory() as scratch:
            destination = Path(scratch)
            retention.archive(store, [expected], destination)
            source["etag"] = "new-etag"
            with self.assertRaisesRegex(ValueError, "Source object changed"):
                retention.expire(store, [expected], destination)
            source["etag"] = expected["etag"]
            store.pointer = {"key": current["key"], "previous": {"key": source["key"]}}
            with self.assertRaisesRegex(ValueError, "now required"):
                retention.expire(store, [expected], destination)
            self.assertEqual(store.deletions, [])


if __name__ == "__main__":
    unittest.main()
