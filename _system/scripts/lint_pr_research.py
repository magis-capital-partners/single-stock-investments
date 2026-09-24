#!/usr/bin/env python3
"""Lint deep dives for tickers touched in a PR diff.

Two rules keep a PR from being blocked by what it did not change:

* The deep-dive and adversarial consistency lints run only when the PR touches
  one of the surfaces they compare: a deep dive, an adversarial review, or
  valuation.json. A PR that only adds a falsifier draft or a review receipt no
  longer inherits a deep dive whose stated return drifted from a valuation the
  daily sync rewrote (PR #1019: "Returns statement (synthesis) 3.11% vs
  valuation.json base 2.64%" on a deep dive it never opened).
* A lint that fails is re-run on the base branch's copy of the ticker. If every
  failure line is already there, the failure is labelled INHERITED and does not
  block; any new line blocks. When the base copy cannot be built, the failure
  blocks (fail closed).

Usage:
  python _system/scripts/lint_pr_research.py
  python _system/scripts/lint_pr_research.py --base origin/main
  python _system/scripts/lint_pr_research.py --base origin/main --name-only-file /tmp/pr-files.txt
"""
from __future__ import annotations

import argparse
import io
import json
from collections import Counter
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
PY = sys.executable
TICKER_RE = re.compile(r"^([^/]+)/research/")

MECHANICAL_EVIDENCE = re.compile(r"^[^/]+/research/evidence/thematic_context_\d{4}-\d{2}-\d{2}\.md$")
MECHANICAL_INSIDER = re.compile(r"^[^/]+/research/evidence/insider_signal_\d{4}-\d{2}-\d{2}\.md$")
MECHANICAL_MI = re.compile(r"^[^/]+/research/market_inputs\.json$")
# What lint_deep_dive.py and lint_adversarial.py --consistency-only compare.
CONSISTENCY_SURFACE = re.compile(
    r"^(?P<ticker>[^/]+)/research/(?:deep_dive_[^/]*\.md|adversarial_[^/]*\.md|valuation\.json)$"
)
# Output lines that describe a run rather than a finding.
INFORMATIONAL = ("WARN", "OK:", "OK ", "SKIP", "INFO", "---", "No deep dives found")
# What the lint scripts read, for building the base branch's copy of a ticker.
BASE_SHARED_PATHS = (
    "_system/scripts",
    "_system/portfolio",
    "_system/reference/market-data/themes/manifest.json",
    "_system/reference/market-data/insider/manifest.json",
)

sys.path.insert(0, str(SCRIPTS))
from marvin_pipeline_common import has_evidence_refresh_config  # noqa: E402


def _normalize_paths(lines: list[str]) -> list[str]:
    return [line.strip().replace("\\", "/") for line in lines if line.strip()]


def read_name_only_file(path: Path) -> list[str]:
    return _normalize_paths(path.read_text(encoding="utf-8").splitlines())


def git_diff_names(base: str) -> list[str]:
    """Return paths changed on this branch vs merge-base with ``base``.

    Never fall back to a two-dot compare against the tip of ``base``: on shallow
    CI clones that incorrectly includes main-only commits (e.g. authorize waves)
    and poisons unrelated PRs with foreign tickers.
    """
    r = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode == 0:
        return _normalize_paths((r.stdout or "").splitlines())

    mb = subprocess.run(
        ["git", "merge-base", base, "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if mb.returncode != 0 or not (mb.stdout or "").strip():
        print(
            "ERROR: cannot compute merge-base for PR lint; "
            "deepen git history or pass --name-only-file from the GitHub PR file list.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    merge_base = mb.stdout.strip()
    r2 = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{merge_base}...HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if r2.returncode != 0:
        print(
            f"ERROR: git diff failed for {merge_base}...HEAD: {(r2.stderr or r2.stdout or '').strip()}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return _normalize_paths((r2.stdout or "").splitlines())


def tickers_from_paths(paths: list[str]) -> list[str]:
    tickers: set[str] = set()
    for line in paths:
        if "/research/" not in line:
            continue
        m = TICKER_RE.match(line)
        if m and not m.group(1).startswith(("_", ".")):
            tickers.add(m.group(1))
    return sorted(tickers)


def tickers_from_diff(base: str) -> list[str]:
    return tickers_from_paths(git_diff_names(base))


def valuation_overlay_only_diff(ticker: str, base: str) -> bool:
    vp = f"{ticker}/research/valuation.json"
    r = subprocess.run(
        ["git", "show", f"{base}:{vp}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return False
    try:
        old = json.loads(r.stdout)
    except json.JSONDecodeError:
        return False
    new_path = ROOT / ticker / "research" / "valuation.json"
    if not new_path.exists():
        return False
    try:
        new = json.loads(new_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    forbidden = ("inputs", "scenarios", "implied_return", "results", "segment_build", "nav_overlay")
    for key in forbidden:
        if old.get(key) != new.get(key):
            return False
    return old.get("context_overlay") != new.get("context_overlay")


def valuation_insider_only_diff(ticker: str, base: str) -> bool:
    vp = f"{ticker}/research/valuation.json"
    r2 = subprocess.run(
        ["git", "show", f"{base}:{vp}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if r2.returncode != 0:
        return False
    try:
        old = json.loads(r2.stdout)
        new = json.loads((ROOT / ticker / "research" / "valuation.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    forbidden = ("inputs", "scenarios", "implied_return", "results", "segment_build", "nav_overlay")
    for key in forbidden:
        if old.get(key) != new.get(key):
            return False
    return old.get("insider_signal") != new.get("insider_signal")


def _is_committee_side_path(path: str) -> bool:
    return "/research/committee_work/" in path or path.endswith("/research/valuation_workbench.json")


def _is_derived_path(path: str) -> bool:
    return path.endswith("/research/lenses.json")


def _is_mechanical_path(path: str, ticker: str, base: str) -> bool:
    if path.endswith("/research/valuation.json"):
        return valuation_overlay_only_diff(ticker, base) or valuation_insider_only_diff(ticker, base)
    if path.endswith("/research/authorized_evidence.json"):
        # Queue authorize packets / contract_backfill stubs — not narrative research.
        return True
    if MECHANICAL_EVIDENCE.match(path) or MECHANICAL_INSIDER.match(path) or MECHANICAL_MI.match(path):
        return True
    if "/research/evidence/filing_facts_" in path and path.endswith(".json"):
        return True
    return False


def research_diff_kind(ticker: str, paths: list[str], base: str) -> str:
    """Per ticker: derived_only | mechanical_only | committee_only | narrative | mixed."""
    tk_paths = [p for p in paths if p.startswith(f"{ticker}/research/")]
    if not tk_paths:
        return "narrative"
    if all(_is_derived_path(p) for p in tk_paths):
        return "derived_only"
    if all(_is_committee_side_path(p) for p in tk_paths):
        return "committee_only"
    non_mechanical = [p for p in tk_paths if not _is_mechanical_path(p, ticker, base)]
    if not non_mechanical:
        return "mechanical_only"
    val_only = all(p.endswith("/research/valuation.json") for p in non_mechanical)
    if val_only and (valuation_overlay_only_diff(ticker, base) or valuation_insider_only_diff(ticker, base)):
        return "mechanical_only"
    if any(p.endswith(".md") for p in non_mechanical):
        return "mixed" if any(not p.endswith(".md") for p in non_mechanical) else "narrative"
    return "mixed"


def touched_consistency_surfaces(ticker: str, paths: list[str]) -> list[str]:
    """The deep dives, adversarial reviews and valuation.json this PR changed for ``ticker``."""
    return sorted(
        path for path in paths
        if (match := CONSISTENCY_SURFACE.match(path)) and match.group("ticker") == ticker
    )


def failure_lines(output: str) -> Counter[str]:
    """The finding lines of a lint run, normalised and counted.

    Counted, not a set: a lint prints one line per finding, and identical
    findings print identical lines. A PR that adds three more id-less
    qualitative_adjustments rows to a valuation that already had one prints
    the same line four times; as a set that was "one line, already on main",
    i.e. INHERITED, and the PR's three new findings went through.
    """
    lines: Counter[str] = Counter()
    for raw in output.splitlines():
        line = raw.strip().replace("\\", "/")
        if line and not line.startswith(INFORMATIONAL):
            lines[line] += 1
    return lines


class BaseTrees:
    """The base branch's copy of what the lint scripts read, one tree per ticker.

    Built with ``git archive``, so it needs no worktree and leaves the checkout
    alone. Paths absent on the base (a ticker new in this PR) are skipped.
    """

    def __init__(self, base: str) -> None:
        self.base = base
        self._trees: dict[str, Path | None] = {}

    def _exists(self, path: str) -> bool:
        proc = subprocess.run(
            ["git", "cat-file", "-e", f"{self.base}:{path}"], cwd=ROOT, capture_output=True
        )
        return proc.returncode == 0

    def tree(self, ticker: str) -> Path | None:
        if ticker not in self._trees:
            self._trees[ticker] = self._build(ticker)
        return self._trees[ticker]

    def _build(self, ticker: str) -> Path | None:
        wanted = [*BASE_SHARED_PATHS, f"{ticker}/research", f"{ticker}/third-party-analyses"]
        present = [path for path in wanted if self._exists(path)]
        if f"{ticker}/research" not in present or "_system/scripts" not in present:
            return None
        proc = subprocess.run(
            ["git", "archive", "--format=tar", self.base, "--", *present],
            cwd=ROOT, capture_output=True,
        )
        if proc.returncode != 0:
            return None
        dest = Path(tempfile.mkdtemp(prefix="lint-base-"))
        with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as archive:
            archive.extractall(dest, filter="data")
        return dest

    def cleanup(self) -> None:
        for tree in self._trees.values():
            if tree is not None:
                shutil.rmtree(tree, ignore_errors=True)


def _run_script(root: Path, script: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PY, str(root / "_system" / "scripts" / script), *args],
        cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def run_lint(ticker: str, script: str, args: list[str], base_trees: BaseTrees) -> str:
    """Run one lint; return "ok", "inherited" or "failed"."""
    head = _run_script(ROOT, script, args)
    output = (head.stdout or "") + (head.stderr or "")
    if output:
        print(output, end="" if output.endswith("\n") else "\n")
    if head.returncode == 0:
        return "ok"
    found = failure_lines(output)
    tree = base_trees.tree(ticker)
    if tree is None or not found:
        return "failed"
    base = _run_script(tree, script, args)
    already = failure_lines((base.stdout or "") + (base.stderr or ""))
    # A line is inherited only as many times as main prints it.
    new = found - already
    if base.returncode != 0 and not new:
        print(
            f"INHERITED {ticker} {script}: all {sum(found.values())} failure line(s) are already on "
            f"{base_trees.base}; this PR did not introduce them."
        )
        print(
            f"::warning title=Inherited research lint ({ticker})::{script} fails identically on "
            f"{base_trees.base}; not blocking this PR."
        )
        return "inherited"
    for line, count in sorted(new.items()):
        times = f" (x{count} more than on {base_trees.base})" if line in already else ""
        print(f"NEW {ticker} {script}: {line}{times}")
    return "failed"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main", help="Git base ref for diff")
    parser.add_argument(
        "--name-only-file",
        default="",
        help="Optional file of changed paths (one per line). Prefer the GitHub PR file list in CI.",
    )
    args = parser.parse_args()

    if args.name_only_file:
        paths = read_name_only_file(Path(args.name_only_file))
        print(f"Using --name-only-file ({len(paths)} path(s))")
    else:
        paths = git_diff_names(args.base)
    tickers = tickers_from_paths(paths)
    if not tickers:
        print("SKIP: no ticker research paths in diff")
        return 0

    base_trees = BaseTrees(args.base)
    try:
        return _lint_tickers(tickers, paths, args.base, base_trees)
    finally:
        base_trees.cleanup()


def _lint_tickers(tickers: list[str], paths: list[str], base: str, base_trees: BaseTrees) -> int:
    failed = 0
    inherited = 0

    def lint(ticker: str, script: str, args: list[str]) -> None:
        nonlocal failed, inherited
        outcome = run_lint(ticker, script, args, base_trees)
        if outcome == "failed":
            failed += 1
        elif outcome == "inherited":
            inherited += 1

    for ticker in tickers:
        dive = ROOT / ticker / "research"
        if not dive.is_dir():
            continue
        kind = research_diff_kind(ticker, paths, base)
        print(f"\n=== lint {ticker} ({kind}) ===")
        if kind == "derived_only":
            lenses_path = dive / "lenses.json"
            try:
                lenses = json.loads(lenses_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                print(f"FAIL {ticker}: invalid lenses.json: {exc}")
                failed += 1
                continue
            required = {
                "ticker": str,
                "lenses": list,
                "valuation_blend": dict,
                "consensus": dict,
            }
            errors = [
                key
                for key, expected in required.items()
                if not isinstance(lenses.get(key), expected)
            ]
            if errors:
                print(f"FAIL {ticker}: lenses.json missing/invalid: {', '.join(errors)}")
                failed += 1
            continue
        if not list(dive.glob("deep_dive_*.md")):
            print(f"SKIP {ticker}: no deep dive")
            continue
        if kind == "committee_only":
            print(f"SKIP {ticker}: committee_work-only diff")
            continue
        if kind == "mechanical_only":
            val_path = ROOT / ticker / "research" / "valuation.json"
            val: dict = {}
            if val_path.exists():
                try:
                    val = json.loads(val_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    val = {}
            if val.get("context_overlay"):
                lint(ticker, "lint_context_overlay.py", [ticker])
            if val.get("insider_signal"):
                lint(ticker, "lint_insider_signal.py", [ticker])
            continue
        surfaces = touched_consistency_surfaces(ticker, paths)
        if surfaces:
            print(f"{ticker}: consistency lint for {', '.join(surfaces)}")
            lint(ticker, "lint_deep_dive.py", [ticker, "--milly"])
            lint(ticker, "lint_adversarial.py", [ticker, "--consistency-only"])
        else:
            print(
                f"SKIP {ticker}: deep-dive consistency lint; this PR touches no deep dive, "
                "adversarial review or valuation.json"
            )
        val_path = ROOT / ticker / "research" / "valuation.json"
        if val_path.exists():
            try:
                val = json.loads(val_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                val = {}
            if has_evidence_refresh_config(val) or val.get("valuation_mode") == "optionality":
                lint(ticker, "check_evidence_completeness.py", [ticker])

    if failed:
        print(f"\nFAIL: {failed} lint invocation(s)" + (f"; {inherited} inherited" if inherited else ""))
        return 1
    suffix = f"; {inherited} inherited failure(s) not blocking (see INHERITED)" if inherited else ""
    print(f"\nOK: {len(tickers)} ticker(s){suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
