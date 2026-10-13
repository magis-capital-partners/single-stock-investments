"""The committed JSONL ledger: paths, loaders, schemas and the decision hash chain.

SQLite is a local build artifact; these files are the truth that travels with
the repository (``_system/data/reverse_splits/``). Every writer here sorts
rows and keys so a re-export of unchanged data produces no diff.

Files
-----
``events.jsonl``                 completed or candidate splits with an ex date
``announcements.jsonl``          8-K/6-K phrase hits that did not become a split
``finra_short_interest.jsonl``   FINRA short interest / synthetic ADV rows
``book_runs.jsonl``              one row per persisted book run (config, analysis, funnel)
``book_source_manifests.jsonl``  deduplicated source manifests referenced by sha256
``decisions.jsonl``              append-only, hash-chained RSI-1.0 decisions
``ledger_manifest.json``         export stamp, row counts, byte sizes, caps applied
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

from .config import DATA_DIR

SCHEMA_VERSION = "reverse_splits_ledger.v1"
MANIFEST_NAME = "ledger_manifest.json"
FILES = (
    "events",
    "announcements",
    "finra_short_interest",
    "book_runs",
    "book_source_manifests",
    "decisions",
)
# Nothing over this enters git; larger files are capped to a recent window.
MAX_FILE_BYTES = 10 * 1024 * 1024
CAP_YEARS = 3

EVENT_KEY = ("ticker", "ex_date", "split_from", "split_to")
EXCHANGE_CLASSES = {"listed", "otc", "unknown"}
COHORTS = {"first", "second", "third_plus"}
EVENT_OUTCOMES = {"effective"}
ANNOUNCEMENT_OUTCOMES = {"announced_only", "mention", "cancelled"}
DATE_QUALITIES = {"search_hit", "acceptance_time", "filing_text"}
DECISION_STATES = {"review", "pass", "paper_ready"}

EVENT_FIELDS = (
    "ticker", "cik", "company", "exchange", "exchange_class",
    "split_from", "split_to", "ratio",
    "first_proxy_date", "announce_date", "vote_date", "ratio_set_date", "effective_date", "ex_date",
    "prior_rs_count", "cohort", "status", "confidence", "needs_review", "source", "outcome",
    "vote_path", "accept_time", "announced_ex_date", "announced_ratio", "jump_status", "jump_observed",
    "date_quality", "accession", "form", "created_at", "updated_at",
)
# Announcement rows are written sparse (null keys omitted). ``ex_date`` always equals
# ``announce_date`` for these rows and ``source``/``confidence``/``needs_review`` are the
# collector constants (edgar_search / 0.4 / 1); the importer restores all four.
ANNOUNCEMENT_FIELDS = (
    "ticker", "cik", "company", "exchange", "exchange_class",
    "announce_date", "first_proxy_date", "announced_ex_date", "announced_ratio",
    "outcome", "date_quality", "vote_path", "accept_time", "accession", "form",
)
ANNOUNCEMENT_DEFAULTS = {"source": "edgar_search", "confidence": 0.4, "needs_review": 1}
FINRA_FIELDS = ("ticker", "settlement_date", "short_interest", "avg_daily_volume", "days_to_cover", "source_file")


# --------------------------------------------------------------------------- io
def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return date.today().isoformat()


def parse_stamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def ledger_paths(ledger_dir: Path | None = None) -> dict[str, Path]:
    base = Path(ledger_dir) if ledger_dir is not None else DATA_DIR
    paths = {name: base / f"{name}.jsonl" for name in FILES}
    paths["manifest"] = base / MANIFEST_NAME
    return paths


def read_json(path: Path, default=None):
    if not Path(path).exists():
        return default
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, value, *, sort_keys: bool = False) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=sort_keys, allow_nan=False) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False, newline="\n") as handle:
        handle.write(text)
        tmp = Path(handle.name)
    tmp.replace(path)


def load_jsonl(path: Path) -> list[dict]:
    """Rows of a JSONL file; raises ``ValueError`` naming the bad line."""
    rows: list[dict] = []
    path = Path(path)
    if not path.exists():
        return rows
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path.name}:{line_number}: row must be an object")
        rows.append(value)
    return rows


def dumps_row(row: dict, *, sparse: bool = False) -> str:
    body = {k: v for k, v in row.items() if v is not None} if sparse else row
    return json.dumps(_finite(body), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def write_jsonl(path: Path, rows: Iterable[dict], *, sparse: bool = False) -> tuple[int, int]:
    """Write rows deterministically (one object per line); returns (rows, bytes).

    ``sparse`` omits null-valued keys; readers use ``.get`` so absent means null.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [dumps_row(row, sparse=sparse) for row in rows]
    text = "\n".join(lines) + ("\n" if lines else "")
    data = text.encode("utf-8")
    with tempfile.NamedTemporaryFile("wb", dir=str(path.parent), delete=False) as handle:
        handle.write(data)
        tmp = Path(handle.name)
    tmp.replace(path)
    return len(lines), len(data)


def sha256_file(path: Path) -> str | None:
    path = Path(path)
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite(value):
    """NaN/inf become ``None`` so ``allow_nan=False`` never raises on vendor data."""
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else None
    if isinstance(value, dict):
        return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(v) for v in value]
    return value


# ------------------------------------------------------------------ event keys
def event_key(row: dict) -> tuple:
    return (
        str(row.get("ticker") or ""),
        str(row.get("ex_date") or "")[:10],
        _num(row.get("split_from")),
        _num(row.get("split_to")),
    )


def _num(value) -> float | None:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


# -------------------------------------------------------------- notes <-> ids
def parse_notes(notes: str | None) -> tuple[str | None, str | None]:
    """``accession=... form=...`` (either order) -> (accession, form)."""
    accession = form = None
    for token in str(notes or "").split():
        if token.startswith("accession="):
            accession = token[len("accession="):] or None
        elif token.startswith("form="):
            form = token[len("form="):] or None
    return accession, form


def make_notes(status: str | None, accession: str | None, form: str | None) -> str | None:
    """Rebuild the SQLite ``notes`` text the collectors wrote, in their field order."""
    if not accession and not form:
        return None
    if status == "announced_only":
        return f"accession={accession} form={form}"
    return f"form={form} accession={accession}"


# ------------------------------------------------------------- decision chain
def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def record_hash(record: dict) -> str:
    """Hash of a decision record without its own ``record_hash`` (strategy.record_decision)."""
    body = {k: v for k, v in record.items() if k != "record_hash"}
    return hashlib.sha256(canonical(body).encode()).hexdigest()


def verify_decision_chain(rows: list[dict]) -> list[str]:
    """Structural errors in a decisions ledger: hash, link, order and identity."""
    errors: list[str] = []
    previous = ""
    seen: set[str] = set()
    for index, row in enumerate(rows):
        prefix = f"decisions[{index}]"
        record = row.get("record")
        if not isinstance(record, dict):
            errors.append(f"{prefix}: record object required")
            continue
        for field in ("id", "recorded_at", "ticker", "previous_hash", "record_hash"):
            if row.get(field) != record.get(field):
                errors.append(f"{prefix}: {field} differs between row and record")
        if row.get("id") in seen:
            errors.append(f"{prefix}: duplicate decision id {row.get('id')}")
        seen.add(str(row.get("id")))
        if record.get("decision") not in DECISION_STATES:
            errors.append(f"{prefix}: decision must be one of {sorted(DECISION_STATES)}")
        expected = record_hash(record)
        if record.get("record_hash") != expected:
            errors.append(f"{prefix}: record_hash does not match the canonical record")
        if record.get("previous_hash", "") != previous:
            errors.append(f"{prefix}: previous_hash does not link to the prior record")
        previous = str(record.get("record_hash") or "")
    return errors


def latest_manifest(ledger_dir: Path | None = None) -> dict:
    return read_json(ledger_paths(ledger_dir)["manifest"], {}) or {}
