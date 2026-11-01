#!/usr/bin/env python3
"""Validate ``_system/data/special_situations/situations.jsonl``.

JSON Schema first, then the rules a schema cannot see: paths in ``inputs_read``
exist, a ``fact`` statement names an accession, versions of one situation id
are unique and increase with the line order, and an outcome's tag matches
``field_tags.outcome`` when that tag is set.

    python _system/scripts/check_situation_rows.py
    python _system/scripts/check_situation_rows.py --ledger path/to/situations.jsonl

Exit 1 on any error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - CI installs jsonschema
    Draft202012Validator = None  # type: ignore[assignment]

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from situation_rows import LEDGER, load_lines  # noqa: E402

SCHEMA_PATH = ROOT / "_system" / "data" / "special_situations" / "schema.json"
ACCESSION = __import__("re").compile(r"^\d{10}-\d{2}-\d{6}$")


def _where(err) -> str:
    path = "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in err.absolute_path)
    return f"{path}: {err.message}"


def check_rows(rows: list[dict], *, root: Path = ROOT, schema_path: Path = SCHEMA_PATH) -> list[str]:
    if Draft202012Validator is None:
        return ["jsonschema is not installed"]
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    errors: list[str] = []
    seen: dict[str, list[tuple[int, int]]] = {}
    for row in rows:
        line = row.get("_line")
        prefix = f"line {line}"
        payload = {key: value for key, value in row.items() if key != "_line"}
        for err in sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path)):
            errors.append(f"{prefix} {_where(err)}")
        situation_id = str(payload.get("situation_id") or "")
        version = payload.get("version")
        if situation_id and isinstance(version, int):
            seen.setdefault(situation_id, []).append((int(row.get("_line") or 0), version))
        for index, entry in enumerate(payload.get("inputs_read") or []):
            if not isinstance(entry, dict):
                continue
            rel = entry.get("path")
            if isinstance(rel, str) and rel and not (root / rel).exists():
                errors.append(f"{prefix} inputs_read[{index}].path does not exist: {rel}")
        for index, statement in enumerate(payload.get("statements") or []):
            if not isinstance(statement, dict):
                continue
            if statement.get("tag") == "fact" and not ACCESSION.match(str(statement.get("accession") or "")):
                errors.append(f"{prefix} statements[{index}] is a fact without an accession")
        outcome = payload.get("outcome")
        tags = payload.get("field_tags") if isinstance(payload.get("field_tags"), dict) else {}
        if isinstance(outcome, dict) and tags.get("outcome") and tags.get("outcome") != outcome.get("tag"):
            errors.append(f"{prefix} field_tags.outcome does not match outcome.tag")
        if isinstance(outcome, dict) and outcome.get("tag") == "fact" and not ACCESSION.match(str(outcome.get("accession") or "")):
            errors.append(f"{prefix} outcome is a fact without an accession")
        primary = payload.get("primary_filing") if isinstance(payload.get("primary_filing"), dict) else {}
        if tags.get("primary_filing") == "fact" and not ACCESSION.match(str(primary.get("accession") or "")):
            errors.append(f"{prefix} primary_filing is tagged fact without an accession")
    for situation_id, versions in seen.items():
        ordered = sorted(versions)
        numbers = [number for _, number in ordered]
        if len(numbers) != len(set(numbers)):
            errors.append(f"{situation_id} repeats a version: {numbers}")
        if numbers and numbers != list(range(1, max(numbers) + 1)):
            errors.append(f"{situation_id} versions must be 1..N in line order, found {numbers}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--schema", type=Path, default=SCHEMA_PATH)
    args = parser.parse_args(argv)
    if not args.ledger.is_file():
        print(f"ERROR {args.ledger} does not exist")
        return 1
    try:
        rows = load_lines(args.ledger)
    except ValueError as exc:
        print(f"ERROR {exc}")
        return 1
    errors = check_rows(rows, root=args.root, schema_path=args.schema)
    print(f"{args.ledger}: {len(rows)} row(s), {len(errors)} error(s)")
    for error in errors:
        print(f"ERROR {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
