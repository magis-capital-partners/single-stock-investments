"""Open questions registry per ticker (Phase D)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT

TEMPLATE = """# Open questions — {ticker}

**As of:** {date}

## What changed in the market narrative?

- [ ] (LLM / macro / sector regime shift)

## What would falsify our base case?

- [ ] 

## What is the market implied story we disagree with?

- [ ] 

## Next research action

- [ ] 
"""


def ensure_open_questions(ticker: str) -> Path | None:
    research = ROOT / ticker / "research"
    if not research.is_dir():
        return None
    path = research / "open_questions.md"
    if path.exists():
        return path
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path.write_text(TEMPLATE.format(ticker=ticker, date=day), encoding="utf-8")
    return path


def scaffold_all_questions(tickers: list[str]) -> dict:
    created = []
    existing = []
    for t in tickers:
        p = ROOT / t / "research" / "open_questions.md"
        if p.exists():
            existing.append(t)
        else:
            if ensure_open_questions(t):
                created.append(t)
    return {"created": created, "existing": existing, "total": len(created) + len(existing)}
