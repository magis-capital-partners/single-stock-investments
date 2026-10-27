#!/usr/bin/env python3
"""Content-hash gated atomic file I/O and standardized feed envelope helpers.

Prevents no-op git churn when daily scheduled pipelines regenerate JSON or
Markdown artifacts whose semantic content has not changed since the previous
build, and attaches the standardized ``_envelope`` metadata block to dashboard
and system feeds.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_VOLATILE_JSON_KEYS: frozenset[str] = frozenset(
    {
        "generated_at",
        "build_time",
        "generated",
        "built_at",
        "scan_date",
        "checked_at",
        "imported_at",
        "_envelope",
    }
)

_VOLATILE_MD_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(\*\*(?:Generated|Date|Scan date|Updated):\*\*)\s*\S+.*$", re.MULTILINE), r"\1 <DATE>"),
    (re.compile(r"^(Build:\s*)\S+(\s*·.*)$", re.MULTILINE), r"\1<DATE>\2"),
    (re.compile(r"^(#\s+[^\n]+?\()\d{4}-\d{2}-\d{2}(\)\s*)$", re.MULTILINE), r"\1<DATE>\2"),
    (re.compile(r"^(#\s+[^\n]+?(?:—|--|-)\s*)\d{4}-\d{2}-\d{2}(\s*)$", re.MULTILINE), r"\1<DATE>\2"),
    (
        re.compile(
            r"(cross_check_third_party_|filing_digest_|insider_signal_|thematic_context_|source_inventory_|world_model_review_[A-Za-z0-9.\-]+_|world_model_promote_[A-Za-z0-9.\-]+_|activist_reconcile_|management_digest_|ssi_report_)\d{4}-\d{2}-\d{2}"
        ),
        r"\1<DATE>",
    ),
)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_semantic_text(text: str) -> str:
    norm = text.replace("\r\n", "\n").strip()
    for pattern, repl in _VOLATILE_MD_PATTERNS:
        norm = pattern.sub(repl, norm)
    return norm


def semantic_text_sha256(text: str) -> str:
    normalized = normalize_semantic_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _strip_volatile_json(value: Any, ignore_keys: frozenset[str]) -> Any:
    if isinstance(value, dict):
        return {
            str(k): _strip_volatile_json(v, ignore_keys)
            for k, v in sorted(value.items(), key=lambda item: str(item[0]))
            if str(k) not in ignore_keys
        }
    if isinstance(value, list):
        return [_strip_volatile_json(item, ignore_keys) for item in value]
    return value


def semantic_json_sha256(
    payload: Any,
    ignore_keys: set[str] | frozenset[str] | tuple[str, ...] | None = None,
    volatile_keys: set[str] | frozenset[str] | tuple[str, ...] | None = None,
) -> str:
    keys = set(DEFAULT_VOLATILE_JSON_KEYS)
    if ignore_keys is not None:
        keys.update(ignore_keys)
    if volatile_keys is not None:
        keys.update(volatile_keys)
    cleaned = _strip_volatile_json(payload, frozenset(keys))
    canonical = json.dumps(cleaned, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        delete=False,
        newline="\n",
    ) as handle:
        handle.write(text)
        tmp = Path(handle.name)
    try:
        for attempt in range(7):
            try:
                tmp.replace(path)
                break
            except OSError as exc:
                transient=exc.errno in {13,22} or getattr(exc,'winerror',None) in {5,32,33}
                if not transient or attempt==6:raise
                time.sleep(.1*2**attempt)
    finally:
        tmp.unlink(missing_ok=True)


def write_text_if_changed(path: Path, content: str) -> bool:
    """Write ``content`` to ``path`` only if its semantic hash changed."""
    final_text = content if content.endswith("\n") else content + "\n"
    if path.exists():
        try:
            existing = path.read_text(encoding="utf-8", errors="ignore")
            if semantic_text_sha256(existing) == semantic_text_sha256(final_text):
                return False
        except OSError:
            pass
    _atomic_write_text(path, final_text)
    return True


def write_json_if_changed(
    path: Path,
    payload: Any,
    *,
    indent: int | None = 2,
    sort_keys: bool = False,
    ignore_keys: set[str] | frozenset[str] | tuple[str, ...] | None = None,
    volatile_keys: set[str] | frozenset[str] | tuple[str, ...] | None = None,
) -> bool:
    """Write JSON ``payload`` to ``path`` only if its semantic hash changed."""
    new_hash = semantic_json_sha256(payload, ignore_keys=ignore_keys, volatile_keys=volatile_keys)
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if semantic_json_sha256(existing, ignore_keys=ignore_keys, volatile_keys=volatile_keys) == new_hash:
                return False
        except (OSError, json.JSONDecodeError):
            pass
    text = json.dumps(payload, indent=indent, sort_keys=sort_keys, ensure_ascii=False) + "\n"
    _atomic_write_text(path, text)
    return True


def write_superseded_review_md(
    pending_dir: Path,
    prefix: str,
    date_str: str,
    content: str,
    *,
    keep_latest: int = 2,
) -> Path:
    """Write a dated review markdown file only when semantically changed, and cap older copies."""
    pending_dir.mkdir(parents=True, exist_ok=True)
    out = pending_dir / f"{prefix}_{date_str}.md"
    final_text = content if content.endswith("\n") else content + "\n"
    new_hash = semantic_text_sha256(final_text)
    existing = sorted(pending_dir.glob(f"{prefix}_*.md"))
    if existing and not out.exists():
        prev = existing[-1]
        try:
            if semantic_text_sha256(prev.read_text(encoding="utf-8", errors="ignore")) == new_hash:
                if keep_latest > 0 and len(existing) > keep_latest:
                    for old_p in existing[:-keep_latest]:
                        old_p.unlink(missing_ok=True)
                return prev
        except OSError:
            pass
    write_text_if_changed(out, final_text)
    all_files = sorted(pending_dir.glob(f"{prefix}_*.md"))
    if keep_latest > 0 and len(all_files) > keep_latest:
        for old_p in all_files[:-keep_latest]:
            if old_p != out:
                old_p.unlink(missing_ok=True)
    return out


def attach_envelope(
    payload: dict[str, Any],
    *,
    feed_id: str,
    as_of: str | None = None,
    row_count: int | None = None,
    upstream_inputs: list[dict[str, Any]] | None = None,
    health_status: str = "healthy",
    structural_errors: int = 0,
) -> dict[str, Any]:
    """Attach a standardized ``_envelope`` block while keeping legacy stamps."""
    gen = (
        payload.get("generated_at")
        or payload.get("build_time")
        or payload.get("generated")
        or payload.get("built_at")
        or now_iso()
    )
    if "generated_at" not in payload:
        payload["generated_at"] = gen
    resolved_as_of = as_of or payload.get("as_of") or str(gen)[:10]
    digest = semantic_json_sha256(payload)
    payload["_envelope"] = {
        "schema_version": "magis.feed.v2",
        "feed_id": feed_id,
        "generated_at": gen,
        "as_of": resolved_as_of,
        "content_sha256": f"sha256:{digest}",
        "row_count": row_count if row_count is not None else 0,
        "upstream_inputs": list(upstream_inputs or []),
        "health": {
            "status": health_status,
            "structural_errors": int(structural_errors),
        },
    }
    return payload
