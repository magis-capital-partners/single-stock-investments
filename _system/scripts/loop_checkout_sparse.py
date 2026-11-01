#!/usr/bin/env python3
"""Sparse checkout for the epistemic loops (memory triage, falsifier, committee).

The loop scripts read the control plane under _system/ and every ticker's
research/ tree. They do not read filings, the activist-report and wisdom
document corpora, or dashboard payloads, with three exceptions:

  * graph_invariants.py P6 reads each data feed registered in
    _system/graph/graph_sources.json.
  * graph_invariants.py E5 (and every Source node) stats each path a belief
    cites as support.
  * refresh_falsifier_evidence.py reads the latest 20-F or 40-F cover under
    {TICKER}/investor-documents/sec-edgar/ when companyfacts has no share
    count. Promotion runs first and can make a drafted ticker due, so every
    ticker with falsifier specs or drafts is covered.

CHECKOUT_PATTERNS is the static set each workflow passes to actions/checkout.
extra_patterns() adds the paths above that are tracked at HEAD, so the loops
see on disk what a full checkout would show them.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CHECKOUT_PATTERNS = (
    "/*",
    "!/*/",
    "/.github/",
    "/_eval/",
    "/_system/",
    "!/_system/reference/activist-reports/",
    "!/_system/reference/investment-wisdom/",
    "/*/research/",
    "/dashboard/private-assets.json",
)

_SPECIAL = set("\\*?[")


def escape(path: str) -> str:
    """One literal path as a non-cone sparse-checkout pattern."""
    text = "".join("\\" + ch if ch in _SPECIAL else ch for ch in path)
    if text.endswith(" "):
        text = text[:-1] + "\\ "
    return "/" + text


def feed_paths(config: dict) -> list[str]:
    """Repo-relative files P6 and P7 judge from disk."""
    paths = []
    for section, field in (("data_feeds", "path"), ("live_feeds", "evidence_path")):
        feeds = config.get(section) if isinstance(config, dict) else None
        for name, feed in sorted((feeds or {}).items()):
            if name.startswith("_") or not isinstance(feed, dict):
                continue
            raw = str(feed.get(field) or "").strip()
            if raw and not raw.startswith(("/", "~")):
                paths.append(raw)
    return paths


def source_refs(root: Path) -> list[str]:
    sys.path.insert(0, str(root / "_system" / "scripts"))
    import graph_build

    builder = graph_build.GraphBuilder(root)
    builder.build()
    return [node["path"] for node in builder.nodes.values() if node["type"] == "Source" and node["path"]]


def cover_filing_patterns(root: Path) -> list[str]:
    tickers = {path.parents[1].name.upper() for path in root.glob("*/research/falsifier_specs.json")}
    tickers |= {path.parents[1].name.upper() for path in root.glob("*/research/falsifier_drafts")}
    return [f"{escape(ticker)}/investor-documents/sec-edgar/{form}_*.htm*"
            for ticker in sorted(tickers) for form in ("20-F", "40-F")]


def head_types(root: Path, paths: list[str]) -> dict[str, str]:
    """blob or tree for each path tracked at HEAD; untracked paths are left out."""
    safe = [p for p in paths if p and "\n" not in p and not p.startswith("/") and ".." not in Path(p).parts]
    if not safe:
        return {}
    out = subprocess.run(
        ["git", "-C", str(root), "cat-file", "--batch-check=%(objecttype)"],
        input="".join(f"HEAD:{p}\n" for p in safe),
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if len(out) != len(safe):
        raise RuntimeError("git cat-file returned an unexpected number of rows")
    return {path: kind for path, kind in zip(safe, out) if kind in ("blob", "tree")}


def extra_patterns(root: Path = ROOT) -> list[str]:
    sys.path.insert(0, str(root / "_system" / "scripts"))
    import graph_build

    config = graph_build.load_json(root / "_system" / "graph" / "graph_sources.json") or {}
    wanted = sorted(set(feed_paths(config)) | set(source_refs(root)))
    kinds = head_types(root, wanted)
    named = [escape(path) + ("/" if kinds[path] == "tree" else "") for path in wanted if path in kinds]
    return named + cover_filing_patterns(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--static", action="store_true", help="print CHECKOUT_PATTERNS instead")
    args = parser.parse_args(argv)
    for line in CHECKOUT_PATTERNS if args.static else extra_patterns(args.root.resolve()):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
