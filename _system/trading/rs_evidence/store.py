"""The one evidence file the RS executor reads, written by three section owners.

``rs_paper_reviewed_evidence.v1`` (see ``rs_paper_executor/evidence.example.json``)
has three sections. Each producer owns exactly one and never touches another:

* ``identities`` - the identity producer (keyed by ticker);
* ``borrow`` - the borrow producer (keyed by str(conid));
* ``eligibility`` - the halt/SSR producer (keyed by str(conid)).

Writes take an OS lock on ``<file>.lock``, re-read the current file, replace one
section, then write a temp file, fsync it and ``os.replace`` it over the target.
The executor reads without the lock: a reader sees the old file or the new
one, never a torn one. ``producers.<section>`` records who wrote what, when;
the executor ignores it.

A row is evidence, not permission: every consumer still checks freshness,
contract identity and its own policy. A producer that cannot verify a value
writes ``None``/``False`` and says why, it never writes a guess.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import time

from _system.trading.rs_paper_executor.safety import SafetyError

SCHEMA = "rs_paper_reviewed_evidence.v1"
SECTIONS = ("identities", "borrow", "eligibility")
MAX_BYTES = 4_000_000  # the executor re-reads this file several times a cycle


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def empty():
    return {"schema": SCHEMA, **{name: {} for name in SECTIONS}, "producers": {}}


def validate(data):
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise SafetyError("evidence schema mismatch")
    for name in SECTIONS:
        if not isinstance(data.get(name), dict):
            raise SafetyError("evidence section missing: " + name)
    return data


@contextlib.contextmanager
def _locked(path, wait_seconds=10.0):
    lock = Path(str(path) + ".lock").open("a+b")
    deadline = time.monotonic() + wait_seconds
    try:
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    lock.seek(0)
                    if not lock.read(1):
                        lock.write(b"0")
                        lock.flush()
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (OSError, BlockingIOError) as exc:
                if time.monotonic() >= deadline:
                    raise SafetyError("evidence file lock not acquired") from exc
                time.sleep(0.05)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                lock.seek(0)
                with contextlib.suppress(OSError):
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            lock.close()


def atomic_write(path, data):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp-" + str(os.getpid()))
    with tmp.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            break
        except PermissionError:
            # Windows refuses a replace while a reader holds the file open.
            if attempt == 19:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.05)
    if os.name != "nt":
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class EvidenceStore:
    """Section-owning writer for the executor's evidence file."""

    def __init__(self, path, archive_dir=None):
        self.path = Path(path)
        self.archive_dir = Path(archive_dir) if archive_dir else None

    def read(self):
        if not self.path.exists():
            return empty()
        data = self.path.read_bytes()
        if len(data) > MAX_BYTES:
            raise SafetyError("evidence file exceeds its size limit")
        loaded = json.loads(data)
        validate(loaded)
        loaded.setdefault("producers", {})
        return loaded

    def write_section(self, section, rows, meta):
        """Replace one section (whole) and its producer record, atomically."""
        if section not in SECTIONS:
            raise SafetyError("unknown evidence section")
        if not isinstance(rows, dict):
            raise SafetyError("evidence rows must be an object")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _locked(self.path):
            try:
                current = self.read()
            except (SafetyError, ValueError):
                # A corrupt file is replaced section by section; the other
                # sections start empty, which every consumer reads as missing.
                current = empty()
            current[section] = rows
            current["producers"][section] = meta
            data = json.dumps(current, sort_keys=True, indent=1).encode()
            if len(data) > MAX_BYTES:
                raise SafetyError("evidence file would exceed its size limit")
            atomic_write(self.path, data)
        return current

    def archive(self, payload):
        """Store a proof document by its sha256 so a row's hash is resolvable."""
        data = payload if isinstance(payload, bytes) else canonical(payload).encode()
        digest = sha256_bytes(data)
        if self.archive_dir is not None:
            self.archive_dir.mkdir(parents=True, exist_ok=True)
            target = self.archive_dir / digest
            if not target.exists():
                atomic_write(target, data)
        return digest
