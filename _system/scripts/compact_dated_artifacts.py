#!/usr/bin/env python3
"""Materialize canonical undated evidence files, compact redundant dated copies, and guard staged commits.

For each target ticker folder:
  1. Ensures canonical undated artifacts exist:
     - ``{TICKER}/research/evidence/thematic_context.md``
     - ``{TICKER}/research/evidence/insider_signal.md``
     - ``{TICKER}/research/evidence/filing_digest.md``
     - ``{TICKER}/research/evidence/filing_facts.json``
     - ``{TICKER}/research/evidence/management_digest.md``
     - ``{TICKER}/research/evidence/management_facts.json``
     - ``{TICKER}/research/evidence/world_model_context.md``
     - ``{TICKER}/research/evidence/ssi_evidence_pack.json``
     - ``{TICKER}/research/evidence/ssi_claims.json``
     - ``{TICKER}/research/evidence/ssi_verified_claims.json``
     - ``{TICKER}/research/evidence/ssi_time_zero.json``
     - ``{TICKER}/research/evidence/ssi_report_gate.json``
     - ``{TICKER}/research/ssi_report.md``
     - ``{TICKER}/research/activist_reconcile.md``
     - ``{TICKER}/research/charts/total_return.svg``
     - ``{TICKER}/third-party-analyses/source_inventory.json``
     - ``{TICKER}/third-party-analyses/source_inventory.md``
  2. With ``--prune-redundant``, deletes superseded older dated ``*_YYYY-MM-DD.*``
     files while keeping the canonical undated file and the newest dated file
     (and never touching paths referenced by MEMORY.md, valuation_fact_ledger.json,
     thesis_card.json, or short-alpha candidates.json), plus compacts superseded
     system-level run receipts and pending review digests. Never touches raw PDFs.
  3. With ``--guard-staged``, inspects staged git changes before commit in CI,
     mirrors any staged dated artifact to its canonical undated path, and
     unstages/deletes redundant dated files whose semantic content matches the
     prior dated copy.

Usage:
  python _system/scripts/compact_dated_artifacts.py --holdings-only
  python _system/scripts/compact_dated_artifacts.py --all --prune-redundant
  python _system/scripts/compact_dated_artifacts.py --guard-staged
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from atomic_io import (  # noqa: E402
    semantic_json_sha256,
    semantic_text_sha256,
    write_text_if_changed,
)

DATED_FAMILIES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "research/evidence",
        "thematic_context.md",
        re.compile(r"^thematic_context_(\d{4}-\d{2}-\d{2})\.md$"),
    ),
    (
        "research/evidence",
        "insider_signal.md",
        re.compile(r"^insider_signal_(\d{4}-\d{2}-\d{2})\.md$"),
    ),
    (
        "research/evidence",
        "filing_digest.md",
        re.compile(r"^filing_digest_(\d{4}-\d{2}-\d{2})\.md$"),
    ),
    (
        "research/evidence",
        "filing_facts.json",
        re.compile(r"^filing_facts_(\d{4}-\d{2}-\d{2})\.json$"),
    ),
    (
        "research/evidence",
        "management_digest.md",
        re.compile(r"^management_digest_(\d{4}-\d{2}-\d{2})\.md$"),
    ),
    (
        "research/evidence",
        "management_facts.json",
        re.compile(r"^management_facts_(\d{4}-\d{2}-\d{2})\.json$"),
    ),
    (
        "research/evidence",
        "world_model_context.md",
        re.compile(r"^world_model_context_(\d{4}-\d{2}-\d{2})\.md$"),
    ),
    (
        "research/evidence",
        "ssi_evidence_pack.json",
        re.compile(r"^ssi_evidence_pack_(\d{4}-\d{2}-\d{2})\.json$"),
    ),
    (
        "research/evidence",
        "ssi_claims.json",
        re.compile(r"^ssi_claims_(\d{4}-\d{2}-\d{2})\.json$"),
    ),
    (
        "research/evidence",
        "ssi_verified_claims.json",
        re.compile(r"^ssi_verified_claims_(\d{4}-\d{2}-\d{2})\.json$"),
    ),
    (
        "research/evidence",
        "ssi_time_zero.json",
        re.compile(r"^ssi_time_zero_(\d{4}-\d{2}-\d{2})\.json$"),
    ),
    (
        "research/evidence",
        "ssi_report_gate.json",
        re.compile(r"^ssi_report_gate_(\d{4}-\d{2}-\d{2})\.json$"),
    ),
    (
        "research",
        "ssi_report.md",
        re.compile(r"^ssi_report_(\d{4}-\d{2}-\d{2})\.md$"),
    ),
    (
        "research",
        "activist_reconcile.md",
        re.compile(r"^activist_reconcile_(\d{4}-\d{2}-\d{2})\.md$"),
    ),
    (
        "research/charts",
        "total_return.svg",
        re.compile(r"^total_return_(\d{4}-\d{2}-\d{2})\.svg$"),
    ),
    (
        "third-party-analyses",
        "source_inventory.json",
        re.compile(r"^source_inventory_(\d{4}-\d{2}-\d{2})\.json$"),
    ),
    (
        "third-party-analyses",
        "source_inventory.md",
        re.compile(r"^source_inventory_(\d{4}-\d{2}-\d{2})\.md$"),
    ),
)

REVIEW_SUPERSEDED_FAMILIES: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"^(news)_(\d{4}-\d{2}-\d{2})\.md$"), 3),
    (re.compile(r"^(event_triage)_(\d{4}-\d{2}-\d{2})\.md$"), 2),
    (re.compile(r"^(fund_family_proposals)_(\d{4}-\d{2}-\d{2})\.md$"), 2),
    (re.compile(r"^(ls_algo_ic_queue)_(\d{4}-\d{2}-\d{2})\.md$"), 2),
    (re.compile(r"^(activist_triage)_(\d{4}-\d{2}-\d{2})\.md$"), 2),
    (re.compile(r"^(filing_insights)_(\d{4}-\d{2}-\d{2})\.md$"), 2),
    (re.compile(r"^(activist_press_digest)_(\d{4}-\d{2}-\d{2})\.md$"), 2),
    (re.compile(r"^(darwin_regime_brief)_(\d{4}-\d{2}-\d{2})\.md$"), 2),
    (re.compile(r"^(transcript_coverage)_(\d{4}-\d{2}-\d{2})\.md$"), 2),
    (re.compile(r"^(world_model_review_[A-Za-z0-9.\-]+)_(\d{4}-\d{2}-\d{2})\.md$"), 1),
)


def protected_paths(root: Path = ROOT) -> set[Path]:
    """Return resolved paths referenced by MEMORY.md, fact ledgers, thesis cards, or short-alpha."""
    protected: set[Path] = set()
    mem = root / "_system" / "memory" / "MEMORY.md"
    if mem.is_file():
        try:
            for span in re.findall(r"`([^`\n]+)`", mem.read_text(encoding="utf-8", errors="ignore")):
                if "/" in span and " " not in span and "*" not in span and "{" not in span:
                    protected.add((root / span.rstrip("/")).resolve())
        except OSError:
            pass

    for ledger_path in root.glob("*/research/valuation_fact_ledger.json"):
        try:
            doc = json.loads(ledger_path.read_text(encoding="utf-8"))
            for fact in doc.get("facts") or []:
                ref = (fact.get("source") or {}).get("ref")
                if isinstance(ref, str) and ref:
                    protected.add((root / ref).resolve())
        except (OSError, json.JSONDecodeError):
            pass

    for card_path in root.glob("*/research/thesis_card.json"):
        try:
            doc = json.loads(card_path.read_text(encoding="utf-8"))
            ref = doc.get("filing_digest")
            if isinstance(ref, str) and ref:
                protected.add((root / ref).resolve())
        except (OSError, json.JSONDecodeError):
            pass

    sa = root / "_system" / "research" / "short-alpha" / "candidates.json"
    if sa.is_file():
        try:
            for ref in re.findall(r'"([A-Za-z0-9._-]+/research/[^"]+)"', sa.read_text(encoding="utf-8", errors="ignore")):
                protected.add((root / ref).resolve())
        except OSError:
            pass

    return protected


def holdings_tickers(root: Path = ROOT) -> list[str]:
    reg_path = root / "_system" / "portfolio" / "registry.json"
    if not reg_path.is_file():
        return []
    try:
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    holdings = reg.get("holdings") or {}
    return sorted(str(k).upper() for k in holdings.keys() if (root / str(k).upper()).is_dir())


def all_ticker_dirs(root: Path = ROOT) -> list[str]:
    return sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir()
        and not p.name.startswith((".", "_"))
        and p.name not in ("dashboard", "docs", "tmp", "terminals")
        and ((p / "research").is_dir() or (p / "third-party-analyses").is_dir())
    )


def compact_ticker(
    ticker: str,
    *,
    root: Path = ROOT,
    prune_redundant: bool = False,
    dry_run: bool = False,
    protected: set[Path] | None = None,
) -> dict[str, int]:
    tdir = root / ticker
    canonical_written = 0
    pruned_count = 0
    bytes_reclaimed = 0
    prot = protected if protected is not None else set()

    for subdir_rel, canonical_name, dated_re in DATED_FAMILIES:
        subdir = tdir / subdir_rel
        if not subdir.is_dir():
            continue
        dated_matches: list[tuple[str, Path]] = []
        for entry in subdir.iterdir():
            if not entry.is_file():
                continue
            m = dated_re.match(entry.name)
            if m:
                dated_matches.append((m.group(1), entry))
        if not dated_matches:
            continue
        dated_matches.sort(key=lambda item: item[0])
        _newest_date, newest_path = dated_matches[-1]
        canonical_path = subdir / canonical_name

        if not dry_run:
            content = newest_path.read_text(encoding="utf-8", errors="ignore")
            if write_text_if_changed(canonical_path, content):
                canonical_written += 1
        elif not canonical_path.is_file():
            canonical_written += 1

        if prune_redundant and len(dated_matches) > 1:
            for _old_date, old_path in dated_matches[:-1]:
                if old_path.resolve() in prot:
                    continue
                try:
                    sz = old_path.stat().st_size
                except OSError:
                    sz = 0
                if not dry_run:
                    try:
                        old_path.unlink()
                        pruned_count += 1
                        bytes_reclaimed += sz
                    except OSError:
                        pass
                else:
                    pruned_count += 1
                    bytes_reclaimed += sz

    return {
        "canonical_written": canonical_written,
        "pruned_count": pruned_count,
        "bytes_reclaimed": bytes_reclaimed,
    }


def compact_system_artifacts(
    *,
    root: Path = ROOT,
    prune_redundant: bool = False,
    dry_run: bool = False,
) -> dict[str, int]:
    """Prune superseded run receipts in _system/data/runs and superseded review queues."""
    pruned_count = 0
    bytes_reclaimed = 0
    if not prune_redundant:
        return {"pruned_count": 0, "bytes_reclaimed": 0}

    def _unlink(path: Path) -> None:
        nonlocal pruned_count, bytes_reclaimed
        try:
            sz = path.stat().st_size
        except OSError:
            sz = 0
        if not dry_run:
            try:
                path.unlink()
                pruned_count += 1
                bytes_reclaimed += sz
            except OSError:
                pass
        else:
            pruned_count += 1
            bytes_reclaimed += sz

    runs_dir = root / "_system" / "data" / "runs"
    if runs_dir.is_dir():
        uni_runs = sorted(runs_dir.glob("power_zone_universe_run_*.json"))
        if len(uni_runs) > 1:
            for old_p in uni_runs[:-1]:
                _unlink(old_p)

        sec_re = re.compile(r"^power_zone_security_run_(\d{4}-\d{2}-\d{2})_(.+)\.json$")
        by_slug: dict[str, list[tuple[str, Path]]] = {}
        for entry in runs_dir.iterdir():
            if not entry.is_file():
                continue
            m = sec_re.match(entry.name)
            if m:
                by_slug.setdefault(m.group(2), []).append((m.group(1), entry))
        for _slug, items in by_slug.items():
            if len(items) > 1:
                items.sort(key=lambda x: x[0])
                for _dt, old_p in items[:-1]:
                    _unlink(old_p)

        ep_dir = runs_dir / "epistemic_loop"
        if ep_dir.is_dir() and (ep_dir / "run_latest.json").is_file():
            for entry in sorted(ep_dir.glob("run_*.json")):
                if entry.name != "run_latest.json":
                    _unlink(entry)

    res_dir = root / "_system" / "research"
    if res_dir.is_dir():
        fi_summaries = sorted(res_dir.glob("filing_insights_summary_*.json"))
        if fi_summaries:
            newest_fi = fi_summaries[-1]
            canon_fi = res_dir / "filing_insights_summary.json"
            if not dry_run:
                write_text_if_changed(canon_fi, newest_fi.read_text(encoding="utf-8", errors="ignore"))
            for old_fi in fi_summaries:
                _unlink(old_fi)

    pending_dir = root / "_system" / "reviews" / "pending"
    if pending_dir.is_dir():
        grouped: dict[str, tuple[int, list[tuple[str, Path]]]] = {}
        for entry in pending_dir.iterdir():
            if not entry.is_file():
                continue
            for rx, keep_latest in REVIEW_SUPERSEDED_FAMILIES:
                m = rx.match(entry.name)
                if m:
                    prefix, dt = m.group(1), m.group(2)
                    _, lst = grouped.setdefault(prefix, (keep_latest, []))
                    lst.append((dt, entry))
                    break
        for _prefix, (keep_latest, items) in grouped.items():
            if len(items) <= 1:
                continue
            items.sort(key=lambda x: x[0])
            # Deduplicate consecutive semantically identical files, keeping the newest of each run
            unique_items: list[tuple[str, Path]] = []
            for dt, p in items:
                try:
                    h = semantic_text_sha256(p.read_text(encoding="utf-8", errors="ignore"))
                except OSError:
                    h = ""
                if unique_items:
                    prev_dt, prev_p = unique_items[-1]
                    try:
                        prev_h = semantic_text_sha256(prev_p.read_text(encoding="utf-8", errors="ignore"))
                    except OSError:
                        prev_h = None
                    if h and h == prev_h:
                        _unlink(prev_p)
                        unique_items[-1] = (dt, p)
                        continue
                unique_items.append((dt, p))
            if len(unique_items) > keep_latest:
                for _dt, old_p in unique_items[:-keep_latest]:
                    _unlink(old_p)

    return {"pruned_count": pruned_count, "bytes_reclaimed": bytes_reclaimed}


def _file_semantic_hash(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() == ".json":
        try:
            return semantic_json_sha256(json.loads(text))
        except json.JSONDecodeError:
            pass
    return semantic_text_sha256(text)


def guard_staged_changes(root: Path = ROOT) -> dict[str, int]:
    """Inspect git staged changes and strip redundant dated artifacts before commit."""
    res = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=AM"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        return {"inspected": 0, "canonicalized": 0, "dropped_redundant": 0}

    staged = [line.strip() for line in res.stdout.splitlines() if line.strip()]
    prot = protected_paths(root)
    canonicalized = 0
    dropped = 0

    for rel in staged:
        full_path = root / rel
        if not full_path.is_file():
            continue
        parts = Path(rel).parts
        # Check ticker dated families
        if len(parts) >= 3 and not parts[0].startswith((".", "_")) and parts[0] not in ("dashboard", "docs"):
            ticker = parts[0]
            subdir_rel = "/".join(parts[1:-1])
            fname = parts[-1]
            for fam_subdir, canonical_name, dated_re in DATED_FAMILIES:
                if subdir_rel != fam_subdir:
                    continue
                m = dated_re.match(fname)
                if not m:
                    continue
                subdir = root / ticker / fam_subdir
                canonical_path = subdir / canonical_name
                content = full_path.read_text(encoding="utf-8", errors="ignore")
                if write_text_if_changed(canonical_path, content):
                    canonicalized += 1
                subprocess.run(
                    ["git", "add", "--sparse", "--", str(canonical_path.relative_to(root))],
                    cwd=str(root),
                    check=False,
                )
                # Find other dated files in the same family
                siblings = sorted(
                    e for e in subdir.iterdir() if e.is_file() and dated_re.match(e.name) and e != full_path
                )
                if siblings:
                    newest_sib = siblings[-1]
                    if _file_semantic_hash(newest_sib) == _file_semantic_hash(full_path):
                        # Staged dated file is semantically identical to existing dated file -> drop new duplicate
                        subprocess.run(
                            ["git", "rm", "-f", "--quiet", "--", rel],
                            cwd=str(root),
                            check=False,
                        )
                        dropped += 1
                    else:
                        # Legitimate update -> remove older superseded siblings
                        for old_sib in siblings:
                            if old_sib.resolve() in prot:
                                continue
                            old_rel = str(old_sib.relative_to(root))
                            subprocess.run(
                                ["git", "rm", "-f", "--quiet", "--", old_rel],
                                cwd=str(root),
                                check=False,
                            )
                            old_sib.unlink(missing_ok=True)
                            dropped += 1
                break

        # Check _system/reviews/pending superseded families
        if len(parts) == 4 and parts[:3] == ("_system", "reviews", "pending"):
            fname = parts[3]
            pending_dir = root / "_system" / "reviews" / "pending"
            for rx, keep_latest in REVIEW_SUPERSEDED_FAMILIES:
                m = rx.match(fname)
                if not m:
                    continue
                prefix = m.group(1)
                siblings = sorted(
                    e
                    for e in pending_dir.iterdir()
                    if e.is_file() and rx.match(e.name) and rx.match(e.name).group(1) == prefix and e != full_path
                )
                if siblings:
                    newest_sib = siblings[-1]
                    if _file_semantic_hash(newest_sib) == _file_semantic_hash(full_path):
                        subprocess.run(
                            ["git", "rm", "-f", "--quiet", "--", rel],
                            cwd=str(root),
                            check=False,
                        )
                        dropped += 1
                        break
                    all_files = sorted(siblings + [full_path], key=lambda p: p.name)
                    if len(all_files) > keep_latest:
                        for old_p in all_files[:-keep_latest]:
                            if old_p == full_path:
                                continue
                            old_rel = str(old_p.relative_to(root))
                            subprocess.run(
                                ["git", "rm", "-f", "--quiet", "--", old_rel],
                                cwd=str(root),
                                check=False,
                            )
                            old_p.unlink(missing_ok=True)
                            dropped += 1
                break

    return {
        "inspected": len(staged),
        "canonicalized": canonicalized,
        "dropped_redundant": dropped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tickers", nargs="*", help="Explicit tickers to compact")
    parser.add_argument("--holdings-only", action="store_true", help="Compact registry holdings")
    parser.add_argument("--all", action="store_true", help="Compact all ticker directories and system runs/reviews")
    parser.add_argument(
        "--prune-redundant",
        action="store_true",
        help="Delete older superseded dated copies (keeps canonical + newest dated file)",
    )
    parser.add_argument(
        "--guard-staged",
        action="store_true",
        help="Inspect git staged changes and remove redundant dated files before commit",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    if args.guard_staged:
        res = guard_staged_changes(args.root)
        if res["canonicalized"] or res["dropped_redundant"]:
            print(
                f"compact_dated_artifacts --guard-staged: inspected={res['inspected']} "
                f"canonicalized={res['canonicalized']} dropped_redundant={res['dropped_redundant']}"
            )
        return 0

    if args.tickers:
        targets = [t.upper() for t in args.tickers]
    elif args.all:
        targets = all_ticker_dirs(args.root)
    else:
        targets = holdings_tickers(args.root)

    prot = protected_paths(args.root) if args.prune_redundant else set()
    totals: dict[str, Any] = {
        "tickers": len(targets),
        "canonical_written": 0,
        "pruned_count": 0,
        "bytes_reclaimed": 0,
    }
    for tk in targets:
        res = compact_ticker(
            tk,
            root=args.root,
            prune_redundant=args.prune_redundant,
            dry_run=args.dry_run,
            protected=prot,
        )
        totals["canonical_written"] += res["canonical_written"]
        totals["pruned_count"] += res["pruned_count"]
        totals["bytes_reclaimed"] += res["bytes_reclaimed"]

    if args.all and args.prune_redundant:
        sys_res = compact_system_artifacts(
            root=args.root,
            prune_redundant=args.prune_redundant,
            dry_run=args.dry_run,
        )
        totals["system_pruned_count"] = sys_res["pruned_count"]
        totals["pruned_count"] += sys_res["pruned_count"]
        totals["bytes_reclaimed"] += sys_res["bytes_reclaimed"]

    print(json.dumps({"dry_run": args.dry_run, **totals}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
