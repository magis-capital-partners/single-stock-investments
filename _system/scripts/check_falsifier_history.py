#!/usr/bin/env python3
"""Fail CI when an immutable falsifier revision is edited or deleted, or when
an approved draft could not be promoted without breaking that history."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from falsifier_specs import spec_errors, spec_payload_hash

ROOT = Path(__file__).resolve().parents[2]


def _identity(ticker: str, spec: dict) -> tuple[str, str, int] | None:
    if not spec.get("spec_id"):
        return None
    return ticker.upper(), str(spec["spec_id"]), int(spec.get("spec_revision") or 1)


def history_errors(base_docs: dict[str, dict], current_docs: dict[str, dict]) -> list[str]:
    errors = []
    base_records: dict[tuple[str, str, int], dict] = {}
    current_records: dict[tuple[str, str, int], dict] = {}
    for ticker, doc in base_docs.items():
        for spec in doc.get("specs") or []:
            identity = _identity(ticker, spec)
            if identity:
                base_records[identity] = spec
    for ticker, doc in current_docs.items():
        for spec in doc.get("specs") or []:
            identity = _identity(ticker, spec)
            if identity:
                if identity in current_records:
                    errors.append(f"duplicate immutable identity: {identity}")
                current_records[identity] = spec
    for identity, prior in sorted(base_records.items()):
        current = current_records.get(identity)
        if current is None:
            errors.append(f"immutable forecast deleted: {identity}")
        elif spec_payload_hash(current) != spec_payload_hash(prior):
            errors.append(f"immutable forecast edited: {identity}")
    known_ids = {(ticker, spec_id) for ticker, spec_id, _revision in base_records}
    for identity, spec in sorted(current_records.items()):
        if identity in base_records:
            continue
        ticker, spec_id, revision = identity
        supersedes = spec.get("supersedes_spec_id")
        if supersedes:
            if (ticker, str(supersedes)) not in known_ids:
                errors.append(f"supersedes unknown forecast: {identity} -> {supersedes}")
            prior_revisions = [prior_revision for prior_ticker, prior_id, prior_revision in base_records
                               if prior_ticker == ticker and prior_id == str(supersedes)]
            if prior_revisions and revision <= max(prior_revisions):
                errors.append(f"superseding revision must increase: {identity}")
        elif (ticker, spec_id) in known_ids:
            errors.append(f"new revision lacks supersedes_spec_id: {identity}")
    return errors


def promotion_errors(ticker: str, committed: dict, working: dict, spec: dict) -> list[str]:
    """History violations that appending ``spec`` to ``working`` would add.

    ``committed`` is the ticker's sidecar as found on disk; ``working`` is that
    sidecar plus anything promoted earlier in the same pass. Only violations
    the new spec introduces are returned, so a problem already sitting in the
    sidecar never blocks every draft for the ticker. The promoter and the
    simulation below share this function so they cannot disagree.
    """
    base = {ticker: committed}
    before = set(history_errors(base, {ticker: working}))
    candidate = {**working, "specs": [*(working.get("specs") or []), spec]}
    return [error for error in history_errors(base, {ticker: candidate}) if error not in before]


def _git(root: Path, *args: str) -> str:
    # Git object payloads are UTF-8. Pin the decoder so immutable hashes are
    # identical on Windows hosts whose process locale is otherwise cp1252.
    result = subprocess.run(["git", "-C", str(root), *args], text=True, encoding="utf-8",
                            capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def _current_docs(root: Path) -> dict[str, dict]:
    docs = {}
    for path in root.glob("*/research/falsifier_specs.json"):
        docs[path.parents[1].name] = json.loads(path.read_text(encoding="utf-8"))
    return docs


def _base_docs(root: Path, base_ref: str) -> dict[str, dict]:
    paths = [line.strip() for line in _git(root, "ls-tree", "-r", "--name-only", base_ref).splitlines()
             if line.strip().endswith("/research/falsifier_specs.json")]
    docs = {}
    for relative in paths:
        raw = _git(root, "show", f"{base_ref}:{relative}")
        docs[Path(relative).parts[0]] = json.loads(raw)
    return docs


def _parse_draft(text: str) -> tuple[dict | None, str]:
    # The promoter's own tolerance for the secret-scanner pragma, imported
    # here rather than at module top because the promoter imports this module.
    from promote_falsifier_drafts import _strip_secret_pragma
    try:
        draft = json.loads(_strip_secret_pragma(text))
    except json.JSONDecodeError as exc:
        return None, str(exc)
    return (draft, "") if isinstance(draft, dict) else (None, "not a JSON object")


def _base_text(root: Path, base_ref: str, relative: str) -> str | None:
    try:
        return _git(root, "show", f"{base_ref}:{relative}")
    except RuntimeError:
        return None  # not on the base: a new draft


def simulated_promotion_errors(root: Path, base_ref: str,
                               current_docs: dict[str, dict]) -> list[str]:
    """Promote, in memory, every approved draft this tree newly approves.

    The promoter only runs in the falsifier lane, on main, after merge, and
    this check used to read sidecars alone -- so a PR could approve a draft
    that the promoter would append and this very check would then reject.
    CEG did exactly that on 2026-09-07: a draft stamped revision 1 while
    superseding a revision 1 passed its PR, then failed every lane run for
    more than two weeks.

    A draft counts as newly approved when it was not approved, or carried a
    different spec, at ``base_ref``. A draft already approved on the base is
    the lane's to hold back and report; turning every unrelated PR red over it
    would repeat the trap this check exists to close. The same goes for a draft
    that does not parse: the promoter holds it back, so it is an error only in
    the tree that introduces or changes it.
    """
    errors: list[str] = []
    working = {ticker: {**doc, "specs": list(doc.get("specs") or [])}
               for ticker, doc in current_docs.items()}
    for path in sorted(root.glob("*/research/falsifier_drafts/*.json")):
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        draft, unparseable = _parse_draft(text)
        if draft is None:
            if _base_text(root, base_ref, relative) != text:
                errors.append(f"draft {relative} is not valid JSON: {unparseable}")
            continue
        if draft.get("status") != "approved":
            continue
        spec = draft.get("spec") or {}
        base_text = _base_text(root, base_ref, relative)
        prior = _parse_draft(base_text)[0] if base_text is not None else None
        if prior and prior.get("status") == "approved" and prior.get("spec") == spec:
            continue
        # The promoter's first gate. It also keeps a malformed spec_revision
        # ("v2") away from _identity's int(), which would otherwise crash here.
        invalid = spec_errors(spec)
        if invalid:
            errors.append(f"approved draft {relative} would not promote: {invalid[0]}")
            continue
        ticker = path.parents[2].name
        sidecar = working.setdefault(ticker, {"specs": []})
        identity = _identity(ticker, spec)
        if identity and identity in {_identity(ticker, row) for row in sidecar["specs"]}:
            continue
        problems = promotion_errors(ticker, current_docs.get(ticker) or {"specs": []},
                                    sidecar, spec)
        if problems:
            errors.extend(f"approved draft {relative} would not promote: {problem}"
                          for problem in problems)
        else:
            sidecar["specs"].append(spec)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--base-ref", default="origin/main")
    args = parser.parse_args()
    current = _current_docs(args.root)
    errors = history_errors(_base_docs(args.root, args.base_ref), current)
    errors += simulated_promotion_errors(args.root, args.base_ref, current)
    for error in errors:
        print(f"ERROR: {error}")
    print(f"falsifier history: {len(errors)} violation(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
