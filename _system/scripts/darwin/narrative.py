"""Lightweight narrative covariates from deep dives (Workstream C)."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .config import ROOT


def _hash_embed(text: str, dim: int = 8) -> list[float]:
    """Deterministic pseudo-embedding (no ML deps)."""
    if not text:
        return [0.0] * dim
    tokens = re.findall(r"[a-z]{4,}", text.lower())
    vec = [0.0] * dim
    for tok in tokens[:200]:
        h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
        for i in range(dim):
            vec[i] += ((h >> (i * 4)) & 15) / 15.0 - 0.5
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [round(x / norm, 4) for x in vec]


def executive_summary_snippet(ticker_dir: Path, as_of: str | None = None) -> str:
    research = ticker_dir / "research"
    if not research.exists():
        return ""
    if as_of:
        from .pit import latest_dated_md_as_of

        dive_path = latest_dated_md_as_of(research, "deep_dive", as_of)
        if not dive_path:
            return ""
        text = dive_path.read_text(encoding="utf-8", errors="ignore")
    else:
        dives = sorted(research.glob("deep_dive_*.md"), reverse=True)
        if not dives:
            return ""
        text = dives[0].read_text(encoding="utf-8", errors="ignore")
    for heading in ("Executive summary", "## Executive summary", "### Executive summary"):
        idx = text.find(heading)
        if idx >= 0:
            chunk = text[idx : idx + 1200]
            chunk = re.sub(r"#+ ", "", chunk)
            return chunk[:800]
    return text[:600]


def narrative_features_for_row(ticker: str, one_line: str | None, as_of: str | None = None) -> dict:
    ticker_dir = ROOT / ticker
    snippet = executive_summary_snippet(ticker_dir, as_of=as_of)
    combined = " ".join(filter(None, [one_line or "", snippet]))
    emb = _hash_embed(combined, dim=8)
    return {
        "narrative_snippet_len": len(combined),
        "narrative_embedding": emb,
    }
