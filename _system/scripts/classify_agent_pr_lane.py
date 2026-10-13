#!/usr/bin/env python3
"""Choose the automerge lane for an agent pull request.

A cursor branch that touches a ticker research tree stays on the research
lane. The provenance gate then requires a research manifest or committee
packet, so a research diff that forgot those artifacts still fails closed.
A cursor branch that does not touch ticker research is a code change and
must pass every CI check. ``_system/research`` is the control plane, not a
ticker packet. codex and claude branches are always code.

A grok branch (``grok/<desk>/<yyyy-mm-dd>-<slug>``) is a desk bot. When every
changed path is on the bot data allowlist it is a ``data`` PR: the data guard
and every CI check must pass. Any other path makes it a ``code`` PR, which a
human reviews. ``check_contributor_paths.py`` owns the allowlist.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from check_contributor_paths import classify_branch, is_allowlisted
except ImportError:  # an old branch head without the guard: grok PRs are code
    classify_branch = None  # type: ignore[assignment]
    is_allowlisted = None  # type: ignore[assignment]


def is_ticker_research(path: str) -> bool:
    """True for ``{TICKER}/research/...``, not ``_system/research/...``."""
    if path.startswith("_system/") or path.startswith("."):
        return False
    parts = path.split("/")
    return len(parts) >= 3 and parts[1] == "research"


def classify(head_ref: str, files: list[str]) -> str:
    if head_ref.startswith("cursor/"):
        if any(is_ticker_research(path) for path in files):
            return "research"
        return "code"
    if head_ref.startswith(("codex/", "claude/")):
        return "code"
    if head_ref.startswith("grok/"):
        if (
            classify_branch is not None
            and is_allowlisted is not None
            and classify_branch(head_ref) == "grok"
            and files
            and all(is_allowlisted(f) for f in files)
        ):
            return "data"
        return "code"
    return "none"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--head-ref", required=True)
    parser.add_argument("--files", type=Path, required=True,
                        help="newline-separated paths changed by the pull request")
    args = parser.parse_args(argv)
    text = args.files.read_text(encoding="utf-8")
    files = [line.strip() for line in text.splitlines() if line.strip()]
    print(classify(args.head_ref, files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
