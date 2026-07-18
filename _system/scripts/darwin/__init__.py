"""Darwin adaptive portfolio layer (Marvin research → allocation)."""

from __future__ import annotations

from typing import Any

__all__ = ["run_pipeline"]


def __getattr__(name: str) -> Any:
    # Lazy: importing darwin.external_sources (used by intake-full) must not
    # pull pipeline → numpy when Darwin deps are not installed.
    if name == "run_pipeline":
        from .pipeline import run_pipeline

        return run_pipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
