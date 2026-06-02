"""Shared helpers for Marvin mechanical pipelines."""
from __future__ import annotations

import re
from pathlib import Path


def latest_deep_dive_date(research_dir: Path) -> str | None:
    """Return YYYY-MM-DD from newest deep_dive_*.md, or None."""
    dives = sorted(research_dir.glob("deep_dive_*.md"), reverse=True)
    for p in dives:
        m = re.match(r"deep_dive_(\d{4}-\d{2}-\d{2})\.md$", p.name)
        if m:
            return m.group(1)
    return None


def has_evidence_refresh_config(val: dict) -> bool:
    er = val.get("evidence_refresh") or {}
    return bool(er.get("type"))
