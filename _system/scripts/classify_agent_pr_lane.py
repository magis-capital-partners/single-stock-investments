#!/usr/bin/env python3
"""Choose the automerge lane for an agent pull request.

A cursor branch that touches a ticker research tree stays on the research
lane. The provenance gate then requires a research manifest or committee
packet, so a research diff that forgot those artifacts still fails closed.
A cursor branch that does not touch ticker research is a code change and
must pass every CI check. ``_system/research`` is the control plane, not a
ticker packet. codex and claude branches are always code.
"""
from __future__ import annotations

import argparse
from pathlib import Path


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
