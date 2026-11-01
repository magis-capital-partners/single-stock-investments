#!/usr/bin/env python3
"""Checksum-verified, bounded parts for durable private archive checkpoints."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import time
from contextlib import closing
from pathlib import Path

from investor_history import ARCHIVE, connect, now, quarter_from_period, write_json

PART_BYTES = 80 * 1024 * 1024
FILES = {
    "archive.sqlite",
    "universe.json",
    "disclosures.json",
    "discovered_funds.json",
    "public-cache.sqlite",
    "filer_catalog.json",
}


class PartsWriter:
    def __init__(self, folder, size=PART_BYTES):
        self.folder, self.size = folder, size
        self.stream = None
        self.used = 0
        self.parts = []
        self.hash = None

    def write(self, value):
        original = len(value)
        while value:
            if self.stream is None:
                name = f"part-{len(self.parts):05d}.bin"
                self.stream = (self.folder / name).open("wb")
                self.parts.append({"name": name})
                self.hash = hashlib.sha256()
                self.used = 0
            piece, value = (
                value[: self.size - self.used],
                value[self.size - self.used :],
            )
            self.stream.write(piece)
            self.hash.update(piece)
            self.used += len(piece)
            if self.used == self.size:
                self.finish()
        return original

    def finish(self):
        if self.stream:
            self.stream.close()
            original = self.folder / self.parts[-1]["name"]
            compressed = original.with_suffix(".gz")
            with (
                original.open("rb") as incoming,
                compressed.open("wb") as output,
                gzip.GzipFile(
                    fileobj=output, mode="wb", filename="", mtime=0, compresslevel=6
                ) as outgoing,
            ):
                shutil.copyfileobj(incoming, outgoing)
            digest = sha(compressed)
            destination = self.folder / (digest + ".gz")
            compressed.replace(destination)
            original.unlink()
            self.parts[-1].update(
                {
                    "name": "objects/" + destination.name,
                    "sha256": digest,
                    "bytes": destination.stat().st_size,
                    "uncompressed_bytes": self.used,
                }
            )
            self.stream = None


class PartsReader:
    def __init__(self, folder, parts, *, compressed=False):
        self.paths = iter([folder / part["name"] for part in parts])
        self.stream = None
        self.compressed = compressed

    def read(self, size):
        result = bytearray()
        while len(result) < size:
            if self.stream is None:
                path = next(self.paths, None)
                if path is None:
                    break
                self.stream = (
                    gzip.open(path, "rb") if self.compressed else path.open("rb")  # noqa: SIM115 -- closed at EOF and in close()
                )
            piece = self.stream.read(size - len(result))
            if not piece:
                self.stream.close()
                self.stream = None
            result.extend(piece)
        return bytes(result)

    def close(self):
        if self.stream:
            self.stream.close()


def sha(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def part_path(source, manifest, part):
    if manifest.get("schema_version") == 2:
        expected = "objects/" + part["sha256"] + ".gz"
        if (
            part["name"] != expected
            or len(part["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in part["sha256"])
        ):
            raise ValueError("Unsafe checkpoint part path")
        return source / expected
    if Path(part["name"]).name != part["name"] or not part["name"].startswith("part-"):
        raise ValueError("Unsafe checkpoint part path")
    return source / manifest["identity"] / part["name"]


def materialize(source, *, identity, additional_identities=()):
    """Select one immutable checkpoint in a sparse publication checkout."""
    identities = list(dict.fromkeys([identity, *additional_identities]))
    for selected_identity in identities:
        if len(selected_identity) != 64 or any(
            c not in "0123456789abcdef" for c in selected_identity
        ):
            raise ValueError("Unsafe checkpoint identity")
    source = Path(source).resolve()
    vault = source.parent.parent
    if source != vault / "dashboard-private/investor-history":
        raise ValueError("Expected a vault investor-history directory")

    def git(*args, **kwargs):
        for attempt in range(3):
            try:
                return subprocess.run(
                    ["git", "-C", str(vault), *args],
                    check=True,
                    capture_output=True,
                    text=True,
                    **kwargs,
                ).stdout.strip()
            except subprocess.CalledProcessError as exc:
                message = (exc.stderr or "").lower()
                transient = any(
                    term in message
                    for term in (
                        "early eof",
                        "unexpected disconnect",
                        "rpc failed",
                        "timed out",
                        "remote end hung up",
                        "index-pack failed",
                    )
                )
                if not transient or attempt == 2:
                    raise
                time.sleep(2**attempt)

    if Path(git("rev-parse", "--show-toplevel")).resolve() != vault:
        raise ValueError("Checkpoint is not in the vault checkout")
    sparse = subprocess.run(
        ["git", "-C", str(vault), "config", "--bool", "core.sparseCheckout"],
        capture_output=True,
        text=True,
        check=False,
    )
    if sparse.stdout.strip() != "true":
        return {"sparse": False}
    prefix = "/dashboard-private/investor-history/"
    previous = git("sparse-checkout", "list").splitlines()
    # Replace history selection only. The processing checkout may contain new,
    # unpublished company objects and other regenerated inputs we must retain.
    keep = [
        p
        for p in previous
        if not (
            p.lstrip("!/") == prefix.strip("/")
            or p.lstrip("!/").startswith(prefix.lstrip("/"))
        )
    ]
    selected = [
        prefix,
        "!" + prefix + "*",
        *[prefix + value + "/" for value in identities],
    ]

    def apply(patterns):
        git(
            "sparse-checkout",
            "set",
            "--no-cone",
            "--stdin",
            input="\n".join([*keep, *patterns]) + "\n",
        )

    # Fetch the small pinned manifest before selecting its immutable objects.
    apply(selected)
    manifests = [
        json.loads((source / value / "manifest.json").read_text())
        for value in identities
    ]
    if any(m.get("identity") != value for value, m in zip(identities, manifests)):
        raise ValueError("Pinned checkpoint identity mismatch")
    paths = []
    objects = {}
    for manifest in manifests:
        for part in manifest["parts"]:
            path = part_path(source, manifest, part).resolve()
            if not path.is_relative_to(source):
                raise ValueError("Unsafe checkpoint part path")
            relative = path.relative_to(vault).as_posix()
            if any(c in relative for c in "*?[]\\\r\n"):
                raise ValueError("Unsafe checkpoint selection path")
            paths.append("/" + relative)
            objects[relative] = part
    if any(m.get("schema_version") == 2 for m in manifests):
        selected.extend([prefix + "objects/", "!" + prefix + "objects/*"])
    apply([*selected, *paths])
    return {
        "sparse": True,
        "identity": identity,
        "parts": len(paths),
        "compressed_bytes": sum(part["bytes"] for part in objects.values()),
        "identities": identities,
    }


def merge_historical(
    source, destination, *, identity, manager_id, cik, first_quarter, last_quarter
):
    """Fill missing historical accessions; never replace a newer primary book."""
    with tempfile.TemporaryDirectory(
        dir=destination, prefix="historical-"
    ) as temporary:
        temporary = Path(temporary)
        if not restore(source, temporary, identity=identity):
            raise RuntimeError("Required historical filings checkpoint is missing")
        with closing(
            sqlite3.connect(
                (temporary / "archive.sqlite").resolve().as_uri() + "?mode=ro", uri=True
            )
        ) as original:
            original.row_factory = sqlite3.Row
            records = list(original.execute("SELECT * FROM filings"))
            if not records:
                raise ValueError("Historical checkpoint contains no filings")
            for row in records:
                quarter = quarter_from_period(row["period_end"])
                if (
                    str(int(row["cik"])) != str(int(cik))
                    or not quarter
                    or not first_quarter <= quarter <= last_quarter
                    or row["form"] not in {"13F-HR", "13F-HR/A", "13F-NT", "13F-NT/A"}
                ):
                    raise ValueError(
                        "Historical checkpoint exceeds its declared filer or dates"
                    )
            with closing(connect(Path(destination) / "archive.sqlite")) as db, db:
                added = 0
                columns = [
                    "accession",
                    "manager_id",
                    "cik",
                    "period_end",
                    "filed_at",
                    "form",
                    "amendment_type",
                    "status",
                    "source_url",
                    "metadata",
                    "error",
                    "updated_at",
                ]
                for source_row in records:
                    row = dict(source_row)
                    existing = db.execute(
                        "SELECT cik FROM filings WHERE accession=?", (row["accession"],)
                    ).fetchone()
                    if existing:
                        if str(int(existing["cik"])) != str(int(cik)):
                            raise ValueError(
                                "Historical accession belongs to another filer"
                            )
                        continue
                    row["manager_id"] = manager_id
                    row["metadata"] = json.dumps(
                        {**json.loads(row["metadata"]), "manager_id": manager_id}
                    )
                    db.execute(
                        "INSERT INTO filings ("
                        + ",".join(columns)
                        + ") VALUES ("
                        + ",".join("?" for _ in columns)
                        + ")",
                        [row[c] for c in columns],
                    )
                    for table, fields in (
                        ("positions", 3),
                        ("position_books", 2),
                        ("raw_documents", 4),
                    ):
                        values = original.execute(
                            f"SELECT * FROM {table} WHERE accession=?",
                            (row["accession"],),
                        ).fetchall()
                        db.executemany(
                            f"INSERT INTO {table} VALUES ("
                            + ",".join("?" for _ in range(fields))
                            + ")",
                            [tuple(v) for v in values],
                        )
                    added += 1
                db.execute(
                    "INSERT OR IGNORE INTO discovery VALUES(?,?,?,?,?,?)",
                    (str(int(cik)), manager_id, "loaded", len(records), None, now()),
                )
                return added


def pack(source, destination, *, part_bytes=PART_BYTES):
    if not (source / "archive.sqlite").is_file():
        raise ValueError("No holdings database exists; refusing an empty checkpoint")
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="investor-checkpoint-") as temporary:
        work = Path(temporary)
        for name in sorted(
            n for n in FILES if n.endswith(".sqlite") and (source / n).exists()
        ):
            source_db = source / name
            with (
                closing(
                    sqlite3.connect(source_db.resolve().as_uri() + "?mode=ro", uri=True)
                ) as original,
                closing(sqlite3.connect(work / name)) as backup,
            ):
                original.backup(backup)
        for name in (n for n in FILES if not n.endswith(".sqlite")):
            if (source / name).exists():
                shutil.copy2(source / name, work / name)
        identity = hashlib.sha256(
            "".join(
                name + sha(work / name)
                for name in sorted(FILES)
                if (work / name).exists()
            ).encode()
        ).hexdigest()
        target = destination / identity
        existing = target / "manifest.json"
        if existing.exists():
            manifest = json.loads(existing.read_text())
            for part in manifest["parts"]:
                if sha(part_path(destination, manifest, part)) != part["sha256"]:
                    raise ValueError("Existing immutable checkpoint is corrupt")
            write_json(destination / "manifest.json", manifest)
            return manifest
        staging = work / "parts"
        staging.mkdir()
        writer = PartsWriter(staging, part_bytes)
        try:
            with tarfile.open(fileobj=writer, mode="w|") as archive:
                for name in sorted(FILES):
                    if (work / name).exists():
                        info = archive.gettarinfo(str(work / name), arcname=name)
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        info.mtime = 0
                        with (work / name).open("rb") as stream:
                            archive.addfile(info, stream)
        finally:
            writer.finish()
        manifest = {
            "schema_version": 2,
            "identity": identity,
            "created_at": now(),
            "parts": writer.parts,
        }
        (destination / "objects").mkdir(exist_ok=True)
        for part in writer.parts:
            path = part_path(destination, manifest, part)
            if path.exists():
                if sha(path) != part["sha256"]:
                    raise ValueError("Existing immutable checkpoint object is corrupt")
            else:
                temporary = path.with_suffix(".tmp")
                shutil.copyfile(staging / Path(part["name"]).name, temporary)
                temporary.replace(path)
        write_json(target / "manifest.json", manifest)
        write_json(destination / "manifest.json", manifest)
        return manifest


def restore(source, destination, *, identity=None):
    if identity is not None and (
        len(identity) != 64 or any(c not in "0123456789abcdef" for c in identity)
    ):
        raise ValueError("Unsafe checkpoint identity")
    manifest_path = (
        source / identity / "manifest.json" if identity else source / "manifest.json"
    )
    if not manifest_path.exists():
        return False
    manifest = json.loads(manifest_path.read_text())
    if identity and identity != manifest["identity"]:
        raise ValueError("Pinned checkpoint identity mismatch")
    identity = manifest["identity"]
    if len(identity) != 64 or any(c not in "0123456789abcdef" for c in identity):
        raise ValueError("Unsafe checkpoint identity")
    folder = source if manifest.get("schema_version") == 2 else source / identity
    for part in manifest["parts"]:
        path = part_path(source, manifest, part)
        if path.stat().st_size != part["bytes"] or sha(path) != part["sha256"]:
            raise ValueError("Checkpoint checksum mismatch")
    destination.mkdir(parents=True, exist_ok=True)
    if any(
        (destination / (name + suffix)).exists()
        for name in FILES
        if name.endswith(".sqlite")
        for suffix in ("-wal", "-shm")
    ):
        raise ValueError(
            "Close the destination database before restoring its checkpoint"
        )
    reader = PartsReader(
        folder, manifest["parts"], compressed=manifest.get("schema_version") == 2
    )
    try:
        with tempfile.TemporaryDirectory(
            dir=destination, prefix="restore-"
        ) as temporary:
            temporary = Path(temporary)
            seen = set()
            with tarfile.open(
                fileobj=reader,
                mode="r|" if manifest.get("schema_version") == 2 else "r|gz",
            ) as archive:
                for item in archive:
                    if (
                        item.name not in FILES
                        or not item.isfile()
                        or item.size > 50 * 1024**3
                        or item.name in seen
                    ):
                        raise ValueError("Unexpected checkpoint member")
                    seen.add(item.name)
                    with (
                        archive.extractfile(item) as incoming,
                        (temporary / item.name).open("wb") as outgoing,
                    ):
                        shutil.copyfileobj(incoming, outgoing)
            actual_identity = hashlib.sha256(
                "".join(name + sha(temporary / name) for name in sorted(seen)).encode()
            ).hexdigest()
            if actual_identity != identity:
                raise ValueError("Checkpoint payload identity mismatch")
            for name in (
                n for n in FILES if n.endswith(".sqlite") and (temporary / n).exists()
            ):
                with closing(sqlite3.connect(temporary / name)) as db:
                    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise ValueError("Checkpoint database is corrupt")
            for file in temporary.iterdir():
                file.replace(destination / file.name)
    finally:
        reader.close()
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["pack", "restore", "materialize"])
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=ARCHIVE)
    parser.add_argument("--public-receipt", type=Path)
    parser.add_argument("--historical-filers", type=Path)
    args = parser.parse_args()
    if args.action == "pack":
        result = pack(args.cache, args.archive)
        if args.public_receipt:
            write_json(
                args.public_receipt,
                {"schema_version": 1, "identity": result["identity"]},
            )
        print(
            json.dumps({"identity": result["identity"], "parts": len(result["parts"])})
        )
    elif args.action == "materialize":
        if not args.public_receipt:
            parser.error("materialize requires --public-receipt")
        receipt = json.loads(args.public_receipt.read_text())
        extra = []
        if args.historical_filers:
            extra = [
                r["checkpoint_identity"]
                for r in json.loads(args.historical_filers.read_text())["filers"]
            ]
        print(
            json.dumps(
                materialize(
                    args.archive,
                    identity=receipt["identity"],
                    additional_identities=extra,
                )
            )
        )
    else:
        print(
            "Restored checkpoint"
            if restore(args.archive, args.cache)
            else "No previous checkpoint"
        )


if __name__ == "__main__":
    main()
