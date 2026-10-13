#!/usr/bin/env python3
"""Validate every desk brief under ``_system/data/desk_briefs/``.

Each ``<desk>/<YYYY-MM-DD>.json`` is checked against ``schema.json`` (JSON Schema
2020-12) and then against what a schema cannot see: the ticker is in the portfolio
registry (or is the literal ``unresolved``), ``as_of`` matches the file name, the
directory matches ``desk``, every ``inputs_read`` path exists, and the stated
``confidence`` is backed by evidence of at least that kind.

Exit 1 on any error. ``--warn-only`` reports and exits 0 (the nightly rebuild lane
does not own these files; the PR check does).

    python _system/scripts/check_desk_briefs.py
    python _system/scripts/check_desk_briefs.py --warn-only
    python _system/scripts/check_desk_briefs.py path/to/one/brief.json

Contract: ``_system/data/desk_briefs/README.md``.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, timedelta
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:  # the rebuild lane may lack jsonschema; main() degrades in --warn-only
    Draft202012Validator = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[2]
BRIEFS_DIR = ROOT / "_system" / "data" / "desk_briefs"
SCHEMA_PATH = BRIEFS_DIR / "schema.json"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"

DESKS = (
    "special_situations",
    "activism",
    "fundamentals",
    "nol_tax_assets",
    "tape_index",
    "stahl",
    "short_selling",
)
DESK_LABELS = {
    "special_situations": "Special Situations",
    "activism": "Activism",
    "fundamentals": "Fundamentals",
    "nol_tax_assets": "NOL and Tax Assets",
    "tape_index": "Index, forced flow and tape",
    "stahl": "Murray Stahl",
    "short_selling": "Short Selling",
}
OWNERS = ("drew", "michael")
UNRESOLVED = "unresolved"
# Files that may sit directly under the briefs directory.
DIRECTORY_FILES = {"schema.json", "README.md"}
NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Evidence kinds that can back each confidence level. News and web are unconstrained:
# they are already the weakest claims.
CONFIDENCE_BACKING = {
    "filing": {"filing"},
    "provider": {"filing", "provider", "dashboard"},
}
FUTURE_GRACE_DAYS = 1


def load_schema(path: Path = SCHEMA_PATH) -> dict:
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def make_validator(schema: dict) -> Draft202012Validator:
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def _ticker_keys(block: object) -> set[str]:
    """Holdings and watchlist are dicts keyed by ticker today; accept a list of rows too."""
    if isinstance(block, dict):
        return {str(key) for key in block}
    if isinstance(block, list):
        out: set[str] = set()
        for row in block:
            if isinstance(row, dict) and row.get("ticker"):
                out.add(str(row["ticker"]))
            elif isinstance(row, str):
                out.add(row)
        return out
    return set()


def registry_tickers(path: Path = REGISTRY_PATH) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _ticker_keys(payload.get("holdings")) | _ticker_keys(payload.get("watchlist"))


def brief_files(briefs_dir: Path = BRIEFS_DIR) -> list[Path]:
    """Every file under the briefs directory except the two directory files, sorted."""
    if not briefs_dir.is_dir():
        return []
    files = [p for p in briefs_dir.rglob("*") if p.is_file()]
    return sorted(p for p in files if not (p.parent == briefs_dir and p.name in DIRECTORY_FILES))


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _repo_path_ok(rel: str) -> bool:
    if not rel or rel.startswith(("/", "\\")) or "\\" in rel or ":" in rel:
        return False
    return ".." not in Path(rel).parts


def _schema_errors(validator: Draft202012Validator, payload: object) -> list[str]:
    errors = []
    for err in sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path)):
        where = "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in err.absolute_path)
        errors.append(f"{where}: {err.message}")
    return errors


def check_payload(
    payload: object,
    *,
    validator: Draft202012Validator,
    tickers: set[str],
    root: Path = ROOT,
    expected_desk: str | None = None,
    expected_as_of: str | None = None,
    today: date | None = None,
) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for one parsed brief."""
    errors = _schema_errors(validator, payload)
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return errors, warnings
    today = today or date.today()

    desk = payload.get("desk")
    if expected_desk is not None and desk != expected_desk:
        errors.append(f"desk {desk!r} does not match its directory {expected_desk!r}")
    as_of = payload.get("as_of")
    if expected_as_of is not None and as_of != expected_as_of:
        errors.append(f"as_of {as_of!r} does not match the file name {expected_as_of!r}")
    if isinstance(as_of, str) and NAME_RE.match(as_of):
        try:
            when = date.fromisoformat(as_of)
        except ValueError:
            errors.append(f"as_of {as_of!r} is not a calendar date")
        else:
            if when > today + timedelta(days=FUTURE_GRACE_DAYS):
                errors.append(f"as_of {as_of} is in the future (today {today.isoformat()})")

    for index, entry in enumerate(payload.get("inputs_read") or []):
        if not isinstance(entry, dict):
            continue
        rel = entry.get("path")
        if isinstance(rel, str):
            if not _repo_path_ok(rel):
                errors.append(f"inputs_read[{index}].path must be a relative repo path: {rel}")
            elif not (root / rel).exists():
                errors.append(f"inputs_read[{index}].path does not exist: {rel}")
        if entry.get("generated_at") in (None, ""):
            warnings.append(f"inputs_read[{index}] ({rel}) carries no stamp")

    for index, item in enumerate(payload.get("items") or []):
        if not isinstance(item, dict):
            continue
        ticker = item.get("ticker")
        if isinstance(ticker, str) and ticker != UNRESOLVED and ticker not in tickers:
            errors.append(f"items[{index}].ticker {ticker!r} is not in the registry holdings or watchlist (or 'unresolved')")
        kinds = {e.get("kind") for e in item.get("evidence") or [] if isinstance(e, dict)}
        confidence = item.get("confidence")
        needed = CONFIDENCE_BACKING.get(confidence)
        if needed and kinds and not (kinds & needed):
            errors.append(
                f"items[{index}] ({ticker}): confidence {confidence!r} needs evidence of kind "
                f"{sorted(needed)}; found {sorted(k for k in kinds if k)}"
            )
        if item.get("handoff") and item.get("handoff") == desk:
            errors.append(f"items[{index}] ({ticker}): handoff to the desk's own id {desk!r}")
        for e_index, evidence in enumerate(item.get("evidence") or []):
            if isinstance(evidence, dict) and evidence.get("kind") == "filing" and not evidence.get("url"):
                warnings.append(f"items[{index}].evidence[{e_index}] ({ticker}): filing without a URL")
    return errors, warnings


def check_file(
    path: Path,
    *,
    validator: Draft202012Validator,
    tickers: set[str],
    root: Path = ROOT,
    briefs_dir: Path = BRIEFS_DIR,
    today: date | None = None,
) -> dict:
    """Check one file. Returns {path, desk, as_of, payload, errors, warnings}."""
    rel = _rel(path, root)
    record = {"path": rel, "desk": None, "as_of": None, "payload": None, "errors": [], "warnings": []}
    try:
        parent_rel = path.resolve().relative_to(briefs_dir.resolve())
    except ValueError:
        parent_rel = None
    expected_desk = expected_as_of = None
    if parent_rel is None or len(parent_rel.parts) != 2:
        record["errors"].append("brief files live at <desk>/<YYYY-MM-DD>.json under the briefs directory")
    else:
        expected_desk = parent_rel.parts[0]
        stem, suffix = path.stem, path.suffix
        if expected_desk not in DESKS:
            record["errors"].append(f"unknown desk directory {expected_desk!r}; desks are {', '.join(DESKS)}")
            expected_desk = None
        if suffix != ".json" or not NAME_RE.match(stem):
            record["errors"].append("file name must be <YYYY-MM-DD>.json")
        else:
            expected_as_of = stem
    record["desk"] = expected_desk
    record["as_of"] = expected_as_of
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        record["errors"].append(f"unreadable JSON: {exc}")
        return record
    record["payload"] = payload
    errors, warnings = check_payload(
        payload,
        validator=validator,
        tickers=tickers,
        root=root,
        expected_desk=expected_desk,
        expected_as_of=expected_as_of,
        today=today,
    )
    record["errors"].extend(errors)
    record["warnings"].extend(warnings)
    if not record["errors"] and isinstance(payload, dict):
        record["desk"] = payload.get("desk")
        record["as_of"] = payload.get("as_of")
    return record


def check_all(
    *,
    paths: list[Path] | None = None,
    briefs_dir: Path = BRIEFS_DIR,
    registry_path: Path = REGISTRY_PATH,
    schema_path: Path = SCHEMA_PATH,
    root: Path = ROOT,
    today: date | None = None,
) -> dict:
    """Check every brief (or the given paths). Returns {briefs, errors, warnings, files}."""
    validator = make_validator(load_schema(schema_path))
    tickers = registry_tickers(registry_path)
    files = paths if paths is not None else brief_files(briefs_dir)
    briefs = [
        check_file(path, validator=validator, tickers=tickers, root=root, briefs_dir=briefs_dir, today=today)
        for path in files
    ]
    errors = [f"{b['path']}: {e}" for b in briefs for e in b["errors"]]
    warnings = [f"{b['path']}: {w}" for b in briefs for w in b["warnings"]]
    return {"briefs": briefs, "errors": errors, "warnings": warnings, "files": len(files)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path, help="brief files to check (default: every file under the briefs directory)")
    parser.add_argument("--warn-only", action="store_true", help="report and exit 0")
    parser.add_argument("--briefs-dir", type=Path, default=BRIEFS_DIR)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--schema", type=Path, default=SCHEMA_PATH)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--today", type=date.fromisoformat, default=None, help="override today's date (tests)")
    args = parser.parse_args(argv)
    if Draft202012Validator is None:
        print("check_desk_briefs.py: jsonschema is not installed; briefs were not validated"
              " (pip install jsonschema). Exiting 0 under --warn-only, 1 otherwise.")
        return 0 if args.warn_only else 1
    report = check_all(
        paths=args.paths or None,
        briefs_dir=args.briefs_dir,
        registry_path=args.registry,
        schema_path=args.schema,
        root=args.root,
        today=args.today,
    )
    for line in report["errors"]:
        print(f"ERROR {line}")
    for line in report["warnings"]:
        print(f"WARN  {line}")
    valid = sum(1 for b in report["briefs"] if not b["errors"])
    print(f"desk_briefs: files={report['files']} valid={valid} errors={len(report['errors'])} warnings={len(report['warnings'])}")
    if report["errors"] and not args.warn_only:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
