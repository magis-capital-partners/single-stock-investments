#!/usr/bin/env python3
"""Canonical document identity and duplicate suppression for investor letters.

Duplicate source files remain in the research vault.  This module chooses one
deterministic canonical copy for extraction and records every alternate source
for auditability.  Exact normalized-text duplicates are removed before the
expensive matcher runs; conservative near-duplicates are reconciled after fund
and reporting-period identity are known.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from vault_paths import path_to_letters_ref, resolve_ref_to_path


DUPLICATE_NAME_RE = re.compile(
    r"(?i)(?:\(\d+\)|\bcopy\b|\bduplicate\b|[-_ ](?:final|vfinal)[-_ ]?\d+)$"
)


def normalize_document_text(text: str) -> str:
    """Normalize layout noise without erasing semantic content."""
    value = (text or "").replace("\ufeff", " ").replace("\u00ad", "")
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value


def normalized_content_hash(text: str) -> str:
    return hashlib.sha256(normalize_document_text(text).encode("utf-8")).hexdigest()


def canonical_document_id(content_hash: str) -> str:
    return f"letter-{content_hash[:20]}"


def _stable_ref(path: Path) -> str:
    return path_to_letters_ref(path) or str(path).replace("\\", "/")


def _canonical_score(path: Path, content_length: int) -> tuple:
    stem = path.stem.strip()
    matching_pdf = path.with_suffix(".pdf").exists()
    in_incoming = any(part.upper() == "INCOMING" for part in path.parts)
    duplicateish = bool(DUPLICATE_NAME_RE.search(stem))
    # max() chooses the best source; the final lexical component makes ties
    # deterministic across filesystems and repeated pipeline runs.
    return (
        int(matching_pdf),
        int(not in_incoming),
        int(not duplicateish),
        content_length,
        -len(stem),
        _stable_ref(path).lower(),
    )


def deduplicate_letter_files(files: list[Path]) -> tuple[list[Path], dict[str, dict], dict]:
    """Collapse exact normalized-text duplicates before letter extraction."""
    groups: dict[str, list[tuple[Path, int]]] = defaultdict(list)
    empty: list[Path] = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        normalized = normalize_document_text(text)
        if not normalized:
            # Empty extracts are not treated as duplicates: they require repair,
            # and collapsing them would hide distinct failed source documents.
            empty.append(path)
            continue
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        groups[digest].append((path, len(normalized)))

    selected: list[Path] = list(empty)
    metadata: dict[str, dict] = {}
    duplicate_groups: list[dict] = []
    for digest, members in groups.items():
        canonical_path, content_length = max(
            members, key=lambda item: _canonical_score(item[0], item[1])
        )
        selected.append(canonical_path)
        alternates = sorted(
            (_stable_ref(path) for path, _length in members if path != canonical_path),
            key=str.lower,
        )
        ref = _stable_ref(canonical_path)
        metadata[str(canonical_path.resolve()).lower()] = {
            "canonical_document_id": canonical_document_id(digest),
            "content_hash": digest,
            "content_length": content_length,
            "duplicate_sources": alternates,
            "duplicate_count": len(alternates),
        }
        if alternates:
            duplicate_groups.append(
                {
                    "canonical_document_id": canonical_document_id(digest),
                    "canonical_source": ref,
                    "duplicate_sources": alternates,
                    "duplicate_count": len(alternates),
                    "method": "normalized_text_sha256",
                }
            )

    selected.sort(key=lambda p: str(p).lower())
    duplicate_groups.sort(key=lambda row: row["canonical_source"].lower())
    audit = {
        "schema_version": 1,
        "input_files": len(files),
        "canonical_files": len(selected),
        "exact_duplicate_groups": len(duplicate_groups),
        "exact_duplicates_suppressed": sum(row["duplicate_count"] for row in duplicate_groups),
        "empty_extracts_retained": len(empty),
        "exact_groups": duplicate_groups,
    }
    return selected, metadata, audit


def _record_text(record: dict) -> str:
    path = resolve_ref_to_path(record.get("source_file"))
    if path is None or not path.exists():
        return ""
    return normalize_document_text(path.read_text(encoding="utf-8", errors="ignore"))


def _near_duplicate(left: str, right: str) -> bool:
    if min(len(left), len(right)) < 500:
        return False
    length_ratio = min(len(left), len(right)) / max(len(left), len(right))
    if length_ratio < 0.97:
        return False
    matcher = SequenceMatcher(None, left, right, autojunk=False)
    if matcher.real_quick_ratio() < 0.985 or matcher.quick_ratio() < 0.985:
        return False
    return matcher.ratio() >= 0.985


def _record_score(record: dict, text_length: int) -> tuple:
    path = resolve_ref_to_path(record.get("source_file"))
    if path is None:
        return (0, 0, 0, text_length, 0, str(record.get("source_file") or "").lower())
    return _canonical_score(path, text_length)


def _duplicate_name_key(record: dict) -> str:
    """Filename family used to bound the expensive OCR similarity check."""
    source = str(record.get("source_file") or "")
    stem = Path(source).stem
    stem = DUPLICATE_NAME_RE.sub("", stem).lower()
    return re.sub(r"[^a-z0-9]+", "", stem)


def deduplicate_letter_records(letters: list[dict], exact_audit: dict) -> tuple[list[dict], dict]:
    """Collapse conservative OCR/format variants within one fund-period bucket."""
    buckets: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    texts: dict[int, str] = {}
    for idx, letter in enumerate(letters):
        key = (
            str(letter.get("fund_id") or ""),
            str(letter.get("quarter") or ""),
            str(letter.get("letter_date") or ""),
        )
        # An unresolved fund or period is not sufficient evidence that two
        # documents describe the same letter.  Grouping all such records in
        # one empty bucket would also turn this conservative audit into an
        # accidental O(n²) scan of the archive.
        if not all(key):
            continue
        buckets[key].append(idx)

    parent = list(range(len(letters)))

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[b] = a

    for indices in buckets.values():
        if len(indices) < 2:
            continue
        # OCR variants must have a duplicate-like filename family as well as
        # the same resolved fund and reporting period.  Exact content copies
        # were already collapsed above; this bound prevents a prolific fund
        # from causing an all-pairs text comparison across an entire period.
        name_groups: dict[str, list[int]] = defaultdict(list)
        for idx in indices:
            name_key = _duplicate_name_key(letters[idx])
            if name_key:
                name_groups[name_key].append(idx)
        for candidate_indices in name_groups.values():
            if len(candidate_indices) < 2:
                continue
            for offset, left_idx in enumerate(candidate_indices):
                left = texts.setdefault(left_idx, _record_text(letters[left_idx]))
                for right_idx in candidate_indices[offset + 1 :]:
                    right = texts.setdefault(right_idx, _record_text(letters[right_idx]))
                    if left and right and _near_duplicate(left, right):
                        union(left_idx, right_idx)

    components: dict[int, list[int]] = defaultdict(list)
    for idx in range(len(letters)):
        components[find(idx)].append(idx)

    output: list[dict] = []
    near_groups: list[dict] = []
    for members in components.values():
        if len(members) == 1:
            output.append(letters[members[0]])
            continue
        canonical_idx = max(
            members,
            key=lambda idx: _record_score(
                letters[idx], len(texts.setdefault(idx, _record_text(letters[idx])))
            ),
        )
        canonical = dict(letters[canonical_idx])
        duplicate_sources = set(canonical.get("duplicate_sources") or [])
        for idx in members:
            if idx == canonical_idx:
                continue
            duplicate_sources.add(str(letters[idx].get("source_file") or ""))
            duplicate_sources.update(letters[idx].get("duplicate_sources") or [])
        duplicate_sources.discard("")
        canonical["duplicate_sources"] = sorted(duplicate_sources, key=str.lower)
        canonical["duplicate_count"] = len(canonical["duplicate_sources"])
        output.append(canonical)
        near_groups.append(
            {
                "canonical_document_id": canonical.get("canonical_document_id"),
                "canonical_source": canonical.get("source_file"),
                "duplicate_sources": canonical["duplicate_sources"],
                "duplicate_count": len(members) - 1,
                "method": "same_fund_period_text_similarity_0.985",
            }
        )

    output.sort(key=lambda row: str(row.get("source_file") or "").lower())
    near_groups.sort(key=lambda row: str(row.get("canonical_source") or "").lower())
    audit = {
        **exact_audit,
        "canonical_letters": len(output),
        "near_duplicate_groups": len(near_groups),
        "near_duplicates_suppressed": sum(row["duplicate_count"] for row in near_groups),
        "total_duplicates_suppressed": (
            int(exact_audit.get("exact_duplicates_suppressed") or 0)
            + sum(row["duplicate_count"] for row in near_groups)
        ),
        "near_groups": near_groups,
    }
    return output, audit
