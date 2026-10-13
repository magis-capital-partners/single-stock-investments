#!/usr/bin/env python3
"""Validate ``_system/sources.json`` and the repo paths it names.

The check is structural: required fields, allowed source types, and whether
each repo path exists. A path counts when it is on disk or committed at HEAD
(``git ls-tree``), so a sparse checkout does not have to download large
dashboard JSON blobs.

Run from the repo root::

    python _system/scripts/validate_sources.py

The unit test lives at ``_system/scripts/tests/test_validate_sources.py`` and
is collected by the Python tests workflow.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INDEX = ROOT / "_system" / "sources.json"

SCHEMA = "sources.v1"
TYPES = {"repo file", "Drive folder", "Drive file", "memory hub", "email label"}
MODES = {"read", "read-write", "append"}
PATH_KINDS = {"file", "directory"}
DRIVE_ID_POLICIES = {"find_by_name", "search_by_name"}
DRIVE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")
SOURCE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
BROKER_ACCOUNT_RE = re.compile(r"\bDU\d{6,10}\b", re.IGNORECASE)

TOP_LEVEL_KEYS = {
    "schema",
    "description",
    "github_repo",
    "ground_rules",
    "local_worktree",
    "local_memory_hub",
    "room",
    "pending_access",
    "do_not_write",
    "sources",
}
SOURCE_KEYS = {
    "id",
    "type",
    "location",
    "purpose",
    "owner_desk",
    "mode",
    "push",
    "repo_path",
    "path_kind",
    "optional_path",
    "freshness_field",
    "drive_id",
    "drive_id_policy",
    "parent_drive_id",
    "parent_title",
    "drive_path",
    "resolved_by",
    "notes",
    "labels",
    "constraints",
    "never_surface",
    "helper_repo_paths",
    "helper_repo_dirs",
    "local_path",
    "account",
    "connector",
}
FORBIDDEN_KEYS = {
    "password",
    "secret",
    "token",
    "credential",
    "credentials",
    "balance",
    "balances",
    "positions",
    "body",
    "raw_email",
    "snippet",
    "private_key",
}

REQUIRED_GROUND_RULES = (
    "Before using a dashboard data file, read its build date first. Use generated_at when the file has that field, and build_time when the file has that field.",
    "Read _system/portfolio/registry.json fresh. Do not hardcode tickers.",
    "Report ranked hits only.",
    "Stubs go to the Special Situations desk.",
    "Say nothing when nothing is new.",
    "Never post Drew's personal trades or private correspondence.",
    "Outbound messages to people need Drew's approval.",
    "Email is read-only. Use it only to cross-reference universe names. Label each item as a newsletter or a letter with its date, and treat it as a lead until a filing confirms it. Never surface personal brokerage mail, and do not store email content in this repo.",
    "Bots write only inside _system/memory-hub/research-equity/. Append at most three [PROPOSED] lessons per session. Never edit _system/memory/MEMORY.md. Never create a new hub without Drew's approval. Never write the borrow-etf, diamond-creek, or spx-0dte hubs.",
)

EMAIL_PHRASES = (
    "read-only",
    "universe names",
    "newsletter",
    "letter",
    "filing",
    "do not store email content",
)
MEMORY_PHRASES = (
    "[PROPOSED]",
    "Evidence",
    "Seen",
    "Harmful",
    "Scope",
    "Review after",
    "CONTEXT.md",
    "MEMORY.md",
    "Drew's approval",
    "borrow-etf",
    "diamond-creek",
    "spx-0dte",
)


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(_nonempty_string(item) for item in value)


def _forbidden_keys(value: object, trail: str) -> list[str]:
    failures: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                failures.append(f"forbidden field {trail}.{key}")
            failures.extend(_forbidden_keys(child, f"{trail}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            failures.extend(_forbidden_keys(child, f"{trail}[{index}]"))
    elif isinstance(value, str):
        if "BEGIN PRIVATE" in value or "BEGIN RSA" in value:
            failures.append(f"private key material in {trail}")
        if BROKER_ACCOUNT_RE.search(value):
            failures.append(f"broker account identifier in {trail}")
    return failures


def _repo_relative(value: object, label: str) -> tuple[str | None, str | None]:
    if not _nonempty_string(value):
        return None, f"{label} must be a non-empty repo-relative path"
    rel = str(value).strip()
    if rel.startswith(("/", "\\")) or "\\" in rel or ":" in rel:
        return None, f"{label} must be a relative repo path: {rel}"
    parts = Path(rel).parts
    if not parts or ".." in parts:
        return None, f"{label} must stay inside the repo: {rel}"
    return rel, None


def _git_path_kind(root: Path, rel: str) -> str | None:
    git_dir = root / ".git"
    if not git_dir.exists():
        return None
    try:
        result = subprocess.run(
            ["git", "ls-tree", "HEAD", "--", rel],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        mode = line.split(None, 1)[0] if line.strip() else ""
        if mode == "040000":
            return "directory"
        if mode.startswith("100") or mode.startswith("120"):
            return "file"
    return None


def path_exists(root: Path, rel: str, kind: str) -> bool:
    candidate = root / rel
    if kind == "directory" and candidate.is_dir():
        return True
    if kind == "file" and candidate.is_file():
        return True
    return _git_path_kind(root, rel) == kind


def _check_repo_path(root: Path, rel: str, kind: str, label: str, optional: bool) -> list[str]:
    if path_exists(root, rel, kind):
        return []
    if optional:
        return []
    return [f"missing {kind} {label}: {rel}"]


def _check_source(source: object, root: Path, seen_ids: set[str]) -> list[str]:
    if not isinstance(source, dict):
        return ["each source must be an object"]
    failures: list[str] = []
    unknown = sorted(set(source) - SOURCE_KEYS)
    if unknown:
        failures.append(f"unknown source fields: {', '.join(unknown)}")
    source_id = source.get("id")
    label = str(source_id) if _nonempty_string(source_id) else "<missing id>"
    if not _nonempty_string(source_id) or not SOURCE_ID_RE.match(str(source_id)):
        failures.append(f"{label}: id must be lowercase words separated by hyphens")
    elif str(source_id) in seen_ids:
        failures.append(f"duplicate id: {source_id}")
    else:
        seen_ids.add(str(source_id))

    for key in ("location", "purpose", "owner_desk", "push"):
        if not _nonempty_string(source.get(key)):
            failures.append(f"{label}: {key} must be a non-empty string")

    source_type = source.get("type")
    if source_type not in TYPES:
        failures.append(f"{label}: type must be one of {', '.join(sorted(TYPES))}")
    mode = source.get("mode")
    if mode not in MODES:
        failures.append(f"{label}: mode must be one of {', '.join(sorted(MODES))}")

    if source_type in {"repo file", "memory hub"}:
        rel, error = _repo_relative(source.get("repo_path"), f"{label}.repo_path")
        if error:
            failures.append(error)
        kind = source.get("path_kind")
        if kind not in PATH_KINDS:
            failures.append(f"{label}: path_kind must be file or directory")
        elif rel:
            optional = source.get("optional_path") is True
            failures.extend(_check_repo_path(root, rel, kind, f"{label}.repo_path", optional))
        if source_type == "memory hub" and mode != "append":
            failures.append(f"{label}: a memory hub is append-only")
        if source_type == "memory hub" and source.get("path_kind") != "directory":
            failures.append(f"{label}: a memory hub path is a directory")
        if source_type == "repo file" and mode == "append":
            failures.append(f"{label}: repo files are read or read-write, not append")

    if source_type in {"Drive folder", "Drive file"}:
        drive_id = source.get("drive_id")
        policy = source.get("drive_id_policy")
        if drive_id is not None and (not _nonempty_string(drive_id) or not DRIVE_ID_RE.match(str(drive_id))):
            failures.append(f"{label}: drive_id is not a Drive id")
        if policy is not None and policy not in DRIVE_ID_POLICIES:
            failures.append(f"{label}: drive_id_policy must be find_by_name or search_by_name")
        if not drive_id and policy not in DRIVE_ID_POLICIES:
            failures.append(f"{label}: a Drive source needs drive_id or drive_id_policy")
        parent_id = source.get("parent_drive_id")
        if parent_id is not None and (not _nonempty_string(parent_id) or not DRIVE_ID_RE.match(str(parent_id))):
            failures.append(f"{label}: parent_drive_id is not a Drive id")
        if mode == "append":
            failures.append(f"{label}: Drive sources are read or read-write")

    if source_type == "email label":
        if mode != "read":
            failures.append(f"{label}: email is read-only")
        if not _nonempty_string(source.get("account")):
            failures.append(f"{label}: account is required")
        if not _string_list(source.get("labels")):
            failures.append(f"{label}: labels must be a non-empty list of strings")
        blob = " ".join(source.get("constraints") or []).lower()
        for phrase in EMAIL_PHRASES:
            if phrase not in blob:
                failures.append(f"{label}: email constraints must include {phrase!r}")
        account = str(source.get("account") or "") + " " + str(source.get("location") or "")
        if "drewgoldman01@gmail.com" in account.lower():
            hidden = " ".join(source.get("never_surface") or []).lower()
            if "brokerage" not in hidden:
                failures.append(f"{label}: personal brokerage mail must be listed in never_surface")

    if source_type == "memory hub":
        blob = " ".join(
            [str(source.get("push") or ""), str(source.get("notes") or "")]
            + list(source.get("constraints") or [])
        )
        for phrase in MEMORY_PHRASES:
            if phrase not in blob:
                failures.append(f"{label}: memory hub text must include {phrase!r}")

    for key in ("helper_repo_paths", "helper_repo_dirs"):
        listed = source.get(key)
        if listed is None:
            continue
        if not _string_list(listed):
            failures.append(f"{label}: {key} must be a non-empty list of strings")
            continue
        kind = "file" if key == "helper_repo_paths" else "directory"
        for item in listed:
            rel, error = _repo_relative(item, f"{label}.{key}")
            if error:
                failures.append(error)
            elif rel:
                failures.extend(_check_repo_path(root, rel, kind, f"{label}.{key}", False))

    if "optional_path" in source and not isinstance(source.get("optional_path"), bool):
        failures.append(f"{label}: optional_path must be a boolean")
    if "freshness_field" in source and not _nonempty_string(source.get("freshness_field")):
        failures.append(f"{label}: freshness_field must be a non-empty string")
    return failures


def validate_payload(payload: object, root: Path) -> list[str]:
    if not isinstance(payload, dict):
        return ["sources index must be a JSON object"]
    failures = _forbidden_keys(payload, "$")
    unknown = sorted(set(payload) - TOP_LEVEL_KEYS)
    if unknown:
        failures.append(f"unknown top-level fields: {', '.join(unknown)}")
    if payload.get("schema") != SCHEMA:
        failures.append(f"schema must be {SCHEMA}")
    if not _nonempty_string(payload.get("description")):
        failures.append("description must be a non-empty string")
    if not _nonempty_string(payload.get("github_repo")):
        failures.append("github_repo must be a non-empty string")
    if payload.get("ground_rules") != list(REQUIRED_GROUND_RULES):
        failures.append("ground_rules must match the required source contract")
    for key in ("local_worktree", "local_memory_hub"):
        block = payload.get(key)
        if not isinstance(block, dict):
            failures.append(f"{key} must be an object")
        else:
            for field in ("path", "status"):
                if not _nonempty_string(block.get(field)):
                    failures.append(f"{key}.{field} must be a non-empty string")
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        failures.append("sources must be a non-empty list")
        return failures
    seen: set[str] = set()
    for source in sources:
        failures.extend(_check_source(source, root, seen))
    room = payload.get("room")
    if not isinstance(room, dict):
        failures.append("room must be an object")
    else:
        for key in ("name", "id", "platform", "digest"):
            if not _nonempty_string(room.get(key)):
                failures.append(f"room.{key} must be a non-empty string")
        if not _string_list(room.get("desks")):
            failures.append("room.desks must be a non-empty list of strings")
    if not _string_list(payload.get("pending_access")):
        failures.append("pending_access must be a non-empty list of strings")
    if not _string_list(payload.get("do_not_write")):
        failures.append("do_not_write must be a non-empty list of strings")
    else:
        blocked = " ".join(payload["do_not_write"])
        for name in ("MEMORY.md", "borrow-etf", "diamond-creek", "spx-0dte"):
            if name not in blocked:
                failures.append(f"do_not_write must name {name}")
    return failures


def validate_index(path: Path, root: Path | None = None) -> list[str]:
    root = (root or ROOT).resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"missing index: {path}"]
    except json.JSONDecodeError as exc:
        return [f"invalid JSON in {path}: {exc}"]
    return validate_payload(payload, root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path, nargs="?", default=DEFAULT_INDEX)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    failures = validate_index(args.path, args.root)
    if failures:
        for failure in failures:
            print(f"SOURCES INVALID: {failure}")
        return 1
    print(f"Sources index valid: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
