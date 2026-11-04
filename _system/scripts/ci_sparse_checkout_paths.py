#!/usr/bin/env python3
"""Emit git sparse-checkout paths for CI profiles (one path per line).

Profiles:
  news         — portfolio news ingest (holdings news JSON only)
  marvin-pick  — marvin_pick_ticker metadata (holdings research md/json)
  downloads    — same research trees as marvin-pick; document batches are added later
  drive        — ticker research, third-party analyses, Drive intake folders, desk-brief inputs
  two-phase-watch — INV Accelsius cooling watch (eight ticker trees + INV shard)
  dashboard    — deploy rebuild checkout (base paths only)
  thirteen-f   — Data Pipeline 13F job (the dashboard files that job reads)
  buyback-radar — buyback snapshots, consumer shards, and the two books it patches
  activist     — Data Pipeline activist job (downloads trees, third-party analyses, desk-brief inputs)
  fact_currency — Research quality currency scan (valuation models, fact ledgers, companyfacts)
  graph_invariants — Research quality graph job (every tree it reads; no filing archives)
  graph_invariants_sources — cited sources graph_build would find missing (second pass)

Base paths (_system, .github, and for most profiles the whole dashboard
tree) are set by ci_checkout_workspace.sh. This script emits the extra
paths. thirteen-f emits dashboard files instead of ticker trees; the shell
passes files-only so the whole dashboard tree stays out of the checkout.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
DESK_BRIEFS_DIR = ROOT / "_system" / "data" / "desk_briefs"

# Soft cap for the dashboard profile (must stay tiny — SPX-scale explosion caused 5h checkouts).
BASE_PROFILE_PATH_CAP = 200


def load_holdings() -> list[str]:
    if not REGISTRY_PATH.exists():
        return []
    reg = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return sorted((reg.get("holdings") or {}).keys())


def tracked_company_dirs() -> list[str]:
    """Top-level company trees in git, not holdings only.

    Drive intake accepts a PDF for any ticker folder in the repo. Listing
    those trees from git avoids checking out the filing PDFs under them.
    """
    import subprocess

    result = subprocess.run(
        ["git", "ls-tree", "--name-only", "-d", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "git ls-tree failed")
    skip = {
        ".claude",
        ".cursor",
        ".github",
        ".vscode",
        "_eval",
        "_external",
        "_system",
        "contracts",
        "dashboard",
        "docs",
        "ops-watchdog",
        "outputs",
        "tests",
    }
    return sorted(
        name
        for name in result.stdout.splitlines()
        if name and name not in skip and not name.startswith(".")
    )


def anchored(rel: str) -> str:
    """A tracked path as a literal, root-anchored sparse pattern."""
    return "/" + re.sub(r"([*?\[\\])", r"\\\1", rel.rstrip("/"))


def tracked_files() -> list[str]:
    """Every file at HEAD. Trees are fetched even under --filter=blob:none."""
    import subprocess

    result = subprocess.run(
        ["git", "ls-tree", "-r", "-z", "--name-only", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.decode("utf-8", "replace").strip() or "git ls-tree failed")
    return [name for name in result.stdout.decode("utf-8").split("\0") if name]


def _json_strings(node) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for value in node.values() for s in _json_strings(value)]
    if isinstance(node, list):
        return [s for value in node for s in _json_strings(value)]
    return []


def graph_invariants_paths() -> list[str]:
    """Everything the graph-invariants job reads, without the filing archives.

    The job lists every top-level folder, reads every ticker's research tree,
    all of _system, the root docs, and the P6 feeds graph_sources.json names.
    The filing trees (investor-documents and the like, ~44 GiB) are read only
    where a fact or belief cites one file, and graph_invariants_sources adds
    those after this pass. Top-level files of every folder stay, so the set
    of folders the checks iterate is the same as on a full checkout.
    """
    files = tracked_files()
    patterns = [
        "/*",
        "!/*/",
        "/*/*",
        "!/*/*/",
        "/*/research/",
        "/_system/",
        # Activist PDFs (~2 GiB). Nothing in the job opens them.
        "!/_system/reference/activist-reports/",
        "/.github/",
        "/docs/",
    ]
    has_top_file: set[str] = set()
    for name in files:
        parts = name.split("/")
        if len(parts) == 2 or (len(parts) > 2 and parts[1] == "research"):
            has_top_file.add(parts[0])
    # A folder holding only subfolders would vanish from the listing; one of
    # its files keeps it there.
    keep_folder: dict[str, str] = {}
    for name in files:
        top = name.split("/", 1)[0]
        if "/" in name and top not in has_top_file:
            keep_folder.setdefault(top, name)
    patterns.extend(anchored(name) for _, name in sorted(keep_folder.items()))
    # P6 feed paths and any other repo path the graph config names.
    tracked = set(files)
    prefixes = {name.rsplit("/", 1)[0] for name in files if "/" in name}
    config_path = ROOT / "_system" / "graph" / "graph_sources.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read {config_path}: {exc}")
    named = set()
    for value in _json_strings(config):
        rel = value.strip().rstrip("/")
        if rel in tracked or rel in prefixes:
            named.add(rel)
    patterns.extend(anchored(rel) for rel in sorted(named))
    return patterns


def graph_invariants_sources() -> list[str]:
    """Cited source paths that are tracked but not in the worktree.

    E5 checks that each source a fact or belief cites exists on disk, and
    graph_build is what decides which paths those are. Asking it, rather than
    keeping a second parser here, means the checkout and the check cannot
    disagree about what is cited.
    """
    sys.path.insert(0, str(ROOT / "_system" / "scripts"))
    import graph_build

    builder = graph_build.GraphBuilder(ROOT)
    builder.build()
    files = tracked_files()
    tracked = set(files)
    dirs = {name.rsplit("/", 1)[0] for name in files if "/" in name}
    missing: set[str] = set()
    for node in builder.nodes.values():
        if node.get("type") != "Source" or node.get("status") != "missing":
            continue
        rel = os.path.normpath(str(node.get("path") or "")).replace("\\", "/")
        if rel in tracked or rel in dirs:
            missing.add(rel)
    return [anchored(rel) for rel in sorted(missing)]


def desk_brief_inputs() -> list[str]:
    """Every inputs_read path a committed desk brief cites, as an anchored pattern.

    Any rebuild that runs build_dashboard_data also runs check_desk_briefs,
    which rejects a brief whose cited path is missing from the worktree.
    Briefs cite root files (AGENT_INDEX.md) and ticker files outside the
    profile's own trees. Patterns are anchored with a leading "/" so a root
    file name does not match the same name in every directory.
    """
    paths: set[str] = set()
    for brief in sorted(DESK_BRIEFS_DIR.glob("*/*.json")):
        try:
            payload = json.loads(brief.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        for entry in payload.get("inputs_read") or []:
            rel = entry.get("path") if isinstance(entry, dict) else None
            if not isinstance(rel, str) or not rel or rel.startswith(("/", "\\")):
                continue
            if "\\" in rel or ":" in rel or ".." in Path(rel).parts:
                continue
            paths.add("/" + re.sub(r"([*?\[])", r"\\\1", rel.rstrip("/")))
    return sorted(paths)


def paths_for_profile(profile: str) -> list[str]:
    holdings = load_holdings()
    paths: list[str] = []

    if profile == "news":
        for ticker in holdings:
            paths.append(f"{ticker}/research/news")
        return paths

    if profile in {"marvin-pick", "downloads"}:
        for ticker in holdings:
            paths.extend(
                [
                    f"{ticker}/research/news",
                    f"{ticker}/research",
                    f"{ticker}/.onboard_status.json",
                    f"{ticker}/INDEX.csv",
                    f"{ticker}/_download_log.txt",
                    f"{ticker}/investor-documents/DOWNLOAD_MANIFEST.json",
                    f"{ticker}/investor-documents/TRANSCRIPT_MANIFEST.json",
                ]
            )
        return paths

    if profile == "two-phase-watch":
        tickers = ["NVDA", "AMD", "VRT", "JCI", "SMCI", "DELL", "HPE", "INV"]
        extra: list[str] = []
        for ticker in tickers:
            extra.extend(
                [
                    f"{ticker}/research",
                    f"{ticker}/investor-documents",
                ]
            )
        extra.append("dashboard/data/tickers/INV.json")
        return extra

    if profile == "marvin-forecast":
        ticker = os.environ.get("CI_FORECAST_TICKER", "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9.^_-]+", ticker):
            raise SystemExit("CI_FORECAST_TICKER is required and must be a safe ticker")
        if ticker not in holdings:
            raise SystemExit(f"CI_FORECAST_TICKER is not in the portfolio registry: {ticker}")
        return [
            f"{ticker}/research",
            f"{ticker}/.onboard_status.json",
            f"{ticker}/investor-documents/DOWNLOAD_MANIFEST.json",
            f"{ticker}/investor-documents/TRANSCRIPT_MANIFEST.json",
        ]

    if profile == "dashboard":
        # The pages rebuild reads market-data / portfolio / dashboard under
        # _system and dashboard/ (already in base sparse set). No ticker trees.
        return []

    if profile == "thirteen-f":
        # Read by build_overlap_holdings.py / ingest_13f.py, and rewritten by
        # the thirteen-f job. holdings/ covers by_ticker, by_manager, the
        # managers index, and the feed. Not the rest of dashboard/data.
        return [
            "dashboard/data/overlap_holders.json",
            "dashboard/data/overlap_holdings.json",
            "dashboard/data/fund_holdings_summary.json",
            "dashboard/data/index_membership.json",
            "dashboard/data/holdings",
        ]

    if profile == "buyback-radar":
        # ci_checkout_workspace.sh passes "listed", so this is the whole
        # checkout plus .github. No ticker filings and no activist-report tree.
        return [
            "_system/scripts",
            "_system/portfolio",
            "_system/data/buyback_radar",
            "_system/reference/market-data/fundamentals",
            ".gitattributes",
            "dashboard/private-assets.json",
            "dashboard/data/buyback_radar.json",
            "dashboard/data/buyback_companies.json",
            "dashboard/data/buyback_manifest.json",
            "dashboard/data/buyback_snapshots",
            "dashboard/data/tickers",
            "dashboard/data/agent_shards",
            "dashboard/data/special_situations.json",
            "dashboard/data/short_alpha.json",
        ]

    if profile == "activist":
        # The scan reads and writes third-party-analyses/ (reports, indexes,
        # short_reports, inventory) and research/activist_reconcile.md. The
        # rebuild step runs build_dashboard_data on the same trees the
        # downloads job keeps. Report refs point here or into _system, never
        # into the filing PDFs, which stay out.
        paths.append(".gitattributes")
        for ticker in holdings:
            paths.extend(
                [
                    f"{ticker}/README.md",
                    f"{ticker}/research",
                    f"{ticker}/third-party-analyses",
                    f"{ticker}/.onboard_status.json",
                    f"{ticker}/INDEX.csv",
                    f"{ticker}/_download_log.txt",
                    f"{ticker}/investor-documents/DOWNLOAD_MANIFEST.json",
                    f"{ticker}/investor-documents/TRANSCRIPT_MANIFEST.json",
                    f"{ticker}/investor-documents/research-notes",
                ]
            )
        paths.extend(desk_brief_inputs())
        return paths

    if profile == "drive":
        # README makes the ticker directory exist for normalize_ticker.
        # research/ and third-party-analyses/ are what import and the insights
        # rebuild read. drive-intake/ is the company-PDF destination.
        # investor-documents/*.pdf and *.htm stay out: that tree is 41 GiB.
        paths = []
        for ticker in tracked_company_dirs():
            paths.extend(
                [
                    f"{ticker}/README.md",
                    f"{ticker}/research",
                    f"{ticker}/third-party-analyses",
                    f"{ticker}/investor-documents/drive-intake",
                ]
            )
        paths.extend(desk_brief_inputs())
        return paths

    if profile == "fact_currency":
        # ci_checkout_workspace.sh passes "listed". The scanner globs these two
        # files per ticker and opens every source ref ending in
        # sec_companyfacts.json; the unanchored last pattern takes every
        # tracked file a ref like that can name.
        return [
            "/_system/scripts/",
            "/*/research/valuation.json",
            "/*/research/valuation_fact_ledger.json",
            "*sec_companyfacts.json",
        ]

    if profile == "graph_invariants":
        return graph_invariants_paths()

    if profile == "graph_invariants_sources":
        return graph_invariants_sources()

    raise SystemExit(f"Unknown sparse profile: {profile}")


def main() -> None:
    args = [a for a in sys.argv[1:] if a]
    count_only = False
    if args and args[0] == "--count":
        count_only = True
        args = args[1:]
    if len(args) != 1:
        raise SystemExit(f"Usage: {sys.argv[0]} [--count] <profile>")
    profile = args[0].strip()
    seen: set[str] = set()
    out: list[str] = []
    for path in paths_for_profile(profile):
        if path not in seen:
            seen.add(path)
            out.append(path)

    if profile == "dashboard" and len(out) > BASE_PROFILE_PATH_CAP:
        raise SystemExit(
            f"ERROR: sparse profile {profile!r} has {len(out)} paths "
            f"(cap {BASE_PROFILE_PATH_CAP}). Refusing SPX-scale checkout explosion."
        )

    if count_only:
        print(len(out))
        return

    for path in out:
        print(path)


if __name__ == "__main__":
    main()
