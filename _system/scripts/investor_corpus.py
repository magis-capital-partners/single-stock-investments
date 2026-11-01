"""Read classified or legacy raw letter indexes without changing source files."""

from __future__ import annotations

import json
import hashlib
from collections import defaultdict
from pathlib import Path

PREFIX = "_system/reference/superinvestor-letters/"


def source_path(corpus: Path, reference: str) -> Path | None:
    """A catalog reference may read only within its own corpus directory."""
    try:
        relative = Path(str(reference or "").removeprefix(PREFIX))
        if relative.is_absolute() or ".." in relative.parts:
            return None
        candidate = (corpus.parent / relative).resolve()
        return (
            candidate
            if candidate.is_relative_to(corpus.parent.resolve()) and candidate.is_file()
            else None
        )
    except (OSError, ValueError):
        return None


def load_records(corpus: Path) -> list[dict]:
    document = json.loads(corpus.read_text(encoding="utf-8-sig"))
    rows = document.get("letters", []) if isinstance(document, dict) else document

    def classified(row):
        return isinstance(row.get("letter_eligible"), bool) and bool(
            row.get("document_type")
        )

    if all(classified(row) for row in rows):
        return rows

    # Reuse the reader's classification, dates and fund identity policy. A raw
    # index is not evidence that every stored research document is a letter.
    from build_superinvestor_insights import classify_document
    from fund_identity import consolidate_letter_funds_stable
    from fund_registry import FALLBACK_OVERRIDES_PATH, FundResolver
    from letter_dedup import deduplicate_letter_files

    overrides = corpus.parent / "letters_date_overrides.json"
    resolver = FundResolver(
        funds_path=corpus.parent / "funds.json",
        overrides_path=overrides if overrides.is_file() else FALLBACK_OVERRIDES_PATH,
    )
    output = [
        dict(row)
        for row in rows
        if classified(row) and not row.get("_source_unavailable")
    ]
    unavailable = [dict(row) for row in rows if row.get("_source_unavailable")]
    referenced = {
        str(path)
        for row in rows
        if classified(row)
        for path in [source_path(corpus, row.get("source_file"))]
        if path is not None
    }
    available = {}
    for row in rows:
        if classified(row):
            continue
        path = source_path(corpus, row.get("source_file"))
        if path is None:
            unavailable.append(
                {
                    **row,
                    "document_type": "unclassified",
                    "letter_eligible": False,
                    "_source_unavailable": True,
                }
            )
            continue
        available[str(path)] = row

    # Legacy indexes can retain removed paths and omit newly imported files.
    # Inventory the same text formats as the reader before preparing records.
    for pattern in ("*.txt", "*.md"):
        for path in corpus.parent.rglob(pattern):
            reference = PREFIX + path.relative_to(corpus.parent).as_posix()
            safe = source_path(corpus, reference)
            if safe is not None and str(safe) not in referenced:
                available.setdefault(
                    str(safe), {"source_file": reference, "positions": []}
                )

    selected, metadata, _audit = deduplicate_letter_files([Path(p) for p in available])
    for path in selected:
        row = available[str(path)]
        text = path.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            unavailable.append(
                {
                    **row,
                    "document_type": "unclassified",
                    "letter_eligible": False,
                    "_source_unavailable": True,
                }
            )
            continue
        kind, eligible, reason = classify_document(path, text)
        identity = resolver.resolve(path, text)
        output.append(
            {
                **row,
                **identity,
                **metadata.get(str(path.resolve()).lower(), {}),
                "fund_resolution": identity["resolution"],
                "document_type": kind,
                "letter_eligible": eligible and row.get("letter_eligible") is not False,
                "classification_reason": reason,
                "positions": row.get("positions")
                if isinstance(row.get("positions"), list)
                else [],
            }
        )
    return [*consolidate_letter_funds_stable(output)[0], *unavailable]


def reconcile_sources(records, universe, archived):
    """Retain known publishers by exact document identity; quarantine uncertainty."""
    source_ids = dict(universe.get("source_ids", {}))
    managers = {m["manager_id"]: m for m in universe["managers"]}
    by_document = defaultdict(set)
    names = {}
    for document in archived:
        owner, fund = document["manager_id"], document.get("vehicle_id")
        if (
            document.get("source_kind") == "fund_disclosure"
            and owner in managers
            and fund
            and source_ids.get(fund) == owner
        ):
            by_document[document["id"]].add((owner, fund))
            names[fund] = document.get("vehicle_name")
    unknown = defaultdict(list)
    for record in records:
        fund = record.get("fund_id")
        if (
            fund
            and fund not in source_ids
            and record.get("letter_eligible") is True
            and record.get("document_type") in {"investor_letter", "fund_report"}
        ):
            unknown[fund].append(record)
    aliases = {}
    added = []
    membership = {
        key: list(value) for key, value in universe.get("membership", {}).items()
    }
    for fund, documents in unknown.items():
        candidates = set().union(
            *(by_document.get(d.get("canonical_document_id"), set()) for d in documents)
        )
        if len(candidates) == 1:
            _owner, canonical = next(iter(candidates))
            aliases[fund] = canonical
            continue
        # No name-based join can combine two known SEC owners. The source is
        # still accessible through Fund names to review rather than discarded.
        manager_id = "source-" + hashlib.sha256(fund.encode()).hexdigest()[:16]
        while manager_id in managers:
            manager_id += "-document"
        managers[manager_id] = {
            "manager_id": manager_id,
            "display_name": documents[0].get("fund") or fund,
            "cik": None,
            "files_13f": False,
            "identity_status": "unverified_document_identity",
        }
        source_ids[fund] = manager_id
        membership[manager_id] = ["document_corpus"]
        added.append(
            {
                "manager_id": manager_id,
                "reason": "Current document publisher requires identity review",
            }
        )
    if added:
        universe = {
            **universe,
            "managers": sorted(managers.values(), key=lambda m: m["manager_id"]),
            "source_ids": source_ids,
            "membership": membership,
            "identity_review": [*universe.get("identity_review", []), *added],
        }
    current = [
        {
            **record,
            "fund_id": aliases[record["fund_id"]],
            "fund": names.get(aliases[record["fund_id"]]) or record.get("fund"),
        }
        if record.get("fund_id") in aliases
        else record
        for record in records
    ]
    return universe, current
