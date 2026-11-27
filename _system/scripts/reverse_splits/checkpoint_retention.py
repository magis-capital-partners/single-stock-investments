"""Archive and expire superseded RS checkpoint generations in bounded batches."""

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

ACCOUNT = "e1cac493b315c8fd7398500dd1bfd687"
BUCKET = "single-stock-reverse-splits-evidence"
DATABASE = "de0ec6d5-9619-48be-b02e-d007456517ee"
PREFIX = "collector-state/checkpoints/"
SCHEMA = "reverse_split_checkpoint_expiry.v1"
MIN_AGE = timedelta(hours=48)
KEY = re.compile(
    PREFIX
    + r"([a-f0-9]{64})-[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}\.sqlite(?:\.gz)?"
)
SLOT = re.compile(r"collector-state/slot[01]\.sqlite(?:\.gz)?")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Unexpected redirect from the Cloudflare API")


class Storage:
    def __init__(self, token):
        self.root = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}"
        self.objects = f"/r2/buckets/{BUCKET}/objects"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.opener = build_opener(NoRedirect)

    def request(self, path, *, body=None, method=None):
        headers = (
            {**self.headers, "Content-Type": "application/json"}
            if body is not None
            else self.headers
        )
        return self.opener.open(
            Request(self.root + path, data=body, headers=headers, method=method),
            timeout=35,
        )

    def query(self, path, *, body=None):
        with self.request(path, body=body) as response:
            reply = json.load(response)
        if reply.get("success") is not True:
            raise ValueError("Cloudflare did not accept the inventory request")
        return reply

    def checkpoint(self):
        body = json.dumps(
            {"sql": "SELECT value FROM rs_state WHERE key='collector_checkpoint'"}
        ).encode()
        result = self.query(f"/d1/database/{DATABASE}/query", body=body)["result"]
        return json.loads(result[0]["results"][0]["value"])

    def inventory(self, prefix=PREFIX):
        params = {"prefix": prefix, "per_page": 1000}
        seen = set()
        while True:
            page = self.query(self.objects + "?" + urlencode(params))
            for row in page["result"]:
                if not row["key"].startswith(prefix):
                    raise ValueError(
                        "R2 inventory returned an object outside its prefix"
                    )
                yield row
            info = page.get("result_info") or {}
            cursor = info.get("cursor")
            if not cursor:
                if info.get("is_truncated"):
                    raise ValueError("R2 inventory is incomplete")
                return
            if cursor in seen:
                raise ValueError("R2 inventory repeated a page")
            seen.add(cursor)
            params["cursor"] = cursor

    def get(self, key):
        return self.request(self.objects + "/" + quote(key, safe="/"))

    def delete(self, key):
        with self.request(self.objects + "/" + quote(key, safe="/"), method="DELETE"):
            pass


def recorded_time(value):
    at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if at.tzinfo is None:
        raise ValueError("Checkpoint metadata requires a time zone")
    return at


def recovery_keys(receipt):
    previous = receipt.get("previous")
    generations = [receipt] + ([previous] if previous is not None else [])
    keys = set()
    for generation in generations:
        if generation.get("format") and not generation.get("base"):
            raise ValueError("A checkpoint delta has no recovery base")
        for dependency in (generation, generation.get("base")):
            if dependency is None:
                continue
            key = (
                dependency.get("key")
                or f"collector-state/slot{dependency.get('slot')}.sqlite"
            )
            if not (KEY.fullmatch(key) or SLOT.fullmatch(key)):
                raise ValueError("Unknown recovery checkpoint identity")
            keys.add(key)
    return keys


def object_identity(row):
    key, size, etag, modified = (
        row[field] for field in ("key", "size", "etag", "last_modified")
    )
    if (
        not KEY.fullmatch(key)
        or type(size) is not int
        or size <= 0
        or not isinstance(etag, str)
        or not etag
    ):
        raise ValueError("Invalid generation object")
    recorded_time(modified)
    return {"key": key, "size": size, "etag": etag, "last_modified": modified}


def plan(store, now, max_bytes):
    protected = recovery_keys(store.checkpoint())
    cutoff = now - MIN_AGE
    candidates = [
        object_identity(row)
        for row in store.inventory()
        if KEY.fullmatch(row["key"])
        and row["key"] not in protected
        and recorded_time(row["last_modified"]) <= cutoff
    ]
    selected, size = [], 0
    for row in sorted(
        candidates, key=lambda item: recorded_time(item["last_modified"])
    ):
        if size + row["size"] <= max_bytes:
            size += row["size"]
            selected.append(row)
    return {
        "schema": SCHEMA,
        "bucket": BUCKET,
        "planned_at": now.isoformat(),
        "eligible_objects": len(candidates),
        "eligible_bytes": sum(row["size"] for row in candidates),
        "bytes": size,
        "objects": selected,
    }


def load_plan(path):
    batch = json.loads(path.read_text(encoding="utf-8-sig"))
    if batch.get("schema") != SCHEMA or batch.get("bucket") != BUCKET:
        raise ValueError("This is not an RS checkpoint expiration plan")
    cutoff = recorded_time(batch["planned_at"]) - MIN_AGE
    rows = [object_identity(row) for row in batch["objects"]]
    if (
        len({row["key"] for row in rows}) != len(rows)
        or sum(row["size"] for row in rows) != batch["bytes"]
        or any(recorded_time(row["last_modified"]) > cutoff for row in rows)
    ):
        raise ValueError("The expiration batch identity or age changed")
    return rows


def archive_path(directory, row):
    path = directory / Path(row["key"]).name
    if path.is_symlink():
        raise ValueError("Archive generation must be a regular file on the destination")
    return path


def verify_file(path, row):
    expected = KEY.fullmatch(row["key"])[1]
    if not path.is_file() or path.stat().st_size != row["size"]:
        raise ValueError(f"Archive copy missing or wrong size: {path.name}")
    with path.open("rb") as saved:
        if hashlib.file_digest(saved, "sha256").hexdigest() != expected:
            raise ValueError(f"Archive copy failed SHA-256: {path.name}")


def archive(store, rows, directory):
    bytes_needed = sum(
        row["size"] for row in rows if not archive_path(directory, row).exists()
    )
    if bytes_needed > shutil.disk_usage(directory).free:
        raise ValueError("The batch exceeds the available archive space")
    for row in rows:
        target = archive_path(directory, row)
        if target.exists():
            verify_file(target, row)
            continue
        partial = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=directory, prefix=".rs-checkpoint-", delete=False
            ) as out:
                partial = Path(out.name)
                with store.get(row["key"]) as source:
                    remaining = row["size"]
                    while data := source.read(min(1024 * 1024, remaining + 1)):
                        remaining -= len(data)
                        if remaining < 0:
                            raise ValueError("Checkpoint exceeds the planned length")
                        out.write(data)
                out.flush()
                os.fsync(out.fileno())
            verify_file(partial, row)
            partial.replace(target)
        finally:
            if partial is not None:
                partial.unlink(missing_ok=True)


def verify(rows, directory):
    for row in rows:
        verify_file(archive_path(directory, row), row)


def expire(store, rows, directory):
    # Read every archived byte before the first deletion. An old, verified
    # generation is the only permitted target; the live pointer is read last.
    verify(rows, directory)
    deleted, missing = 0, 0
    for row in rows:
        key = row["key"]
        current = next(
            (item for item in store.inventory(key) if item["key"] == key), None
        )
        if current is None:
            missing += 1
            continue
        if (
            object_identity(current) != row
            or recorded_time(row["last_modified"])
            > datetime.now(timezone.utc) - MIN_AGE
        ):
            raise ValueError("Source object changed; rebuild the expiration plan")
        if key in recovery_keys(store.checkpoint()):
            raise ValueError(
                "A planned generation is now required for checkpoint recovery"
            )
        store.delete(key)
        deleted += 1
    return {"deleted_objects": deleted, "already_absent": missing}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    plan_parser = actions.add_parser(
        "plan", help="Read R2 and D1 metadata and write a JSON batch to stdout"
    )
    plan_parser.add_argument(
        "--max-bytes",
        required=True,
        type=int,
        help="Limit selected bytes to the archive space allocated for this batch",
    )
    for action in ("archive", "verify", "expire"):
        command = actions.add_parser(action)
        command.add_argument("--plan", type=Path, required=True)
        command.add_argument(
            "--destination",
            type=Path,
            required=True,
            help="Existing private archive outside R2",
        )
    args = parser.parse_args()
    store = (
        None if args.action == "verify" else Storage(os.environ["CLOUDFLARE_API_TOKEN"])
    )
    if args.action == "plan":
        if args.max_bytes <= 0:
            parser.error("--max-bytes must be positive")
        print(json.dumps(plan(store, datetime.now(timezone.utc), args.max_bytes)))
        return
    rows = load_plan(args.plan)
    directory = args.destination.resolve(strict=True)
    if not directory.is_dir():
        parser.error("--destination must be an existing directory")
    if args.action == "archive":
        archive(store, rows, directory)
    if args.action == "expire":
        print(json.dumps(expire(store, rows, directory)))
    else:
        verify(rows, directory)
        print(
            json.dumps(
                {
                    "verified_objects": len(rows),
                    "verified_bytes": sum(row["size"] for row in rows),
                }
            )
        )


if __name__ == "__main__":
    main()
