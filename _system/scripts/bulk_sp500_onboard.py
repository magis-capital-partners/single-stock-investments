#!/usr/bin/env python3
"""Batch-onboard S&P 500 names missing from registry (scaffold + SEC + returns).

Deep dives are queued for CI batch dispatch (not run inline).

Usage:
  python _system/scripts/bulk_sp500_onboard.py --batch-size 8 --offset 0
  python _system/scripts/bulk_sp500_onboard.py --batch-size 8 --offset 8 --trigger-deep-dive
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
SP500_PATH = ROOT / "_system" / "reference" / "market-data" / "index" / "sp500_constituents.json"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
QUEUE_PATH = ROOT / "_system" / "data" / "deep_dive_dispatch_queue.json"
STATUS_PATH = ROOT / "_system" / "portfolio" / "sp500_onboard_status.jsonl"
MANIFEST_DIR = ROOT / "_system" / "portfolio" / "sp500_onboard_batches"
PY = sys.executable


def load_sp500_rows() -> list[dict]:
    if not SP500_PATH.exists():
        subprocess.run([PY, str(SCRIPTS / "darwin" / "refresh_sp500_constituents.py")], cwd=ROOT, check=True)
    data = json.loads(SP500_PATH.read_text(encoding="utf-8"))
    if data.get("rows"):
        return data["rows"]
    companies = data.get("companies") or {}
    return [{"ticker": t, "company": companies.get(t, t)} for t in data.get("tickers") or []]


def holdings_set() -> set[str]:
    reg = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return set((reg.get("holdings") or {}).keys())


def missing_rows() -> list[dict]:
    have = holdings_set()
    return [r for r in load_sp500_rows() if r["ticker"] not in have]


def append_status(row: dict) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATUS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def update_deep_dive_queue(batch_tickers: list[str], max_parallel: int = 3) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "sp500_bulk_onboard",
        "max_parallel": max_parallel,
        "tickers": batch_tickers,
    }
    QUEUE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def trigger_batch_deep_dive(tickers: list[str], max_parallel: int) -> int:
    if not tickers:
        return 0
    csv = ",".join(tickers)
    proc = subprocess.run(
        [
            "gh",
            "workflow",
            "run",
            "marvin-deep-dive.yml",
            "--ref",
            "main",
            "-f",
            "mode=batch",
            "-f",
            f"tickers={csv}",
            "-f",
            f"max_parallel={max_parallel}",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
    return proc.returncode


def onboard_one(ticker: str, company: str, *, skip_download: bool) -> int:
    cmd = [
        PY,
        str(SCRIPTS / "onboard_ticker.py"),
        "--ticker",
        ticker,
        "--company",
        company,
        "--market",
        "US",
        "--no-deep-dive",
    ]
    if skip_download:
        cmd.append("--skip-download")
    return subprocess.run(cmd, cwd=ROOT).returncode


def fetch_returns(ticker: str) -> tuple[bool, str]:
    sys.path.insert(0, str(SCRIPTS))
    from download_ira_research import download_ticker_returns  # noqa: E402

    return download_ticker_returns(ticker, "US")


def write_manifest(batch_id: str, rows: list[dict]) -> Path:
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = MANIFEST_DIR / f"batch_{batch_id}_{today}.json"
    if path.exists():
        path = MANIFEST_DIR / f"batch_{batch_id}_{today}_{datetime.now(timezone.utc).strftime('%H%M%S')}.json"
    path.write_text(
        json.dumps({"date": today, "batch_id": batch_id, "tickers": rows}, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def git_push_batch() -> int:
    stash = subprocess.run(["git", "stash", "push", "-u", "-m", "sp500-onboard-wip"], cwd=ROOT)
    pull = subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=ROOT)
    if pull.returncode != 0:
        if stash.returncode == 0:
            subprocess.run(["git", "stash", "pop"], cwd=ROOT)
        return pull.returncode
    push = subprocess.run(["git", "push", "origin", "main"], cwd=ROOT)
    if stash.returncode == 0:
        subprocess.run(["git", "stash", "pop"], cwd=ROOT)
    return push.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.5, help="Pause between tickers")
    ap.add_argument("--trigger-deep-dive", action="store_true", help="gh workflow run batch after onboard")
    ap.add_argument("--max-parallel", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--git-commit",
        action="store_true",
        help="Stage onboarded tickers + returns and commit (does not push)",
    )
    ap.add_argument(
        "--git-push",
        action="store_true",
        help="After --git-commit, pull --rebase and push to origin main",
    )
    ap.add_argument(
        "--loop-until-done",
        action="store_true",
        help="Repeat batches at offset 0 until no missing tickers (uses --git-commit if set)",
    )
    args = ap.parse_args()

    if args.loop_until_done:
        batch_num = len(list(MANIFEST_DIR.glob("batch_*_*.json")))
        while True:
            pending = missing_rows()
            if not pending:
                print("All S&P 500 names onboarded.")
                return 0
            print(f"\n=== Loop batch {batch_num} · {len(pending)} still missing ===")
            loop_args = argparse.Namespace(**{**vars(args), "offset": 0, "loop_until_done": False})
            rc = main_inner(loop_args, batch_num)
            if rc != 0:
                return rc
            batch_num += 1
        return 0

    return main_inner(args, args.offset // max(args.batch_size, 1))


def main_inner(args: argparse.Namespace, batch_num: int) -> int:

    pending = missing_rows()
    total_missing = len(pending)
    batch = pending[args.offset : args.offset + args.batch_size]
    batch_id = str(batch_num)

    print(f"SP500 missing: {total_missing} · batch {batch_id} offset {args.offset} size {len(batch)}")
    if not batch:
        print("Nothing to onboard in this batch.")
        return 0

    if args.dry_run:
        for r in batch:
            print(f"  {r['ticker']}: {r['company']}")
        return 0

    manifest_path = write_manifest(batch_id, batch)
    print(f"Manifest: {manifest_path.relative_to(ROOT)}")

    ok_tickers: list[str] = []
    for i, row in enumerate(batch):
        t = row["ticker"]
        company = row.get("company") or t
        print(f"\n[{i + 1}/{len(batch)}] Onboard {t} — {company}")
        code = onboard_one(t, company, skip_download=args.skip_download)
        ret_ok, ret_msg = False, "skipped"
        if code == 0 and not args.skip_download:
            ret_ok, ret_msg = fetch_returns(t)
        status = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ticker": t,
            "onboard_exit": code,
            "returns_ok": ret_ok,
            "returns_detail": ret_msg,
            "offset": args.offset,
        }
        append_status(status)
        if code == 0:
            ok_tickers.append(t)
        if args.sleep > 0 and i < len(batch) - 1:
            time.sleep(args.sleep)

    if ok_tickers:
        update_deep_dive_queue(ok_tickers, max_parallel=args.max_parallel)
        print(f"Queued {len(ok_tickers)} tickers for deep dive: {QUEUE_PATH.relative_to(ROOT)}")

    if args.trigger_deep_dive and ok_tickers:
        rc = trigger_batch_deep_dive(ok_tickers, args.max_parallel)
        if rc == 0:
            print("Triggered marvin-deep-dive.yml batch workflow")
        else:
            print("Deep dive workflow trigger failed (queue file still updated)", file=sys.stderr)

    failed = len(batch) - len(ok_tickers)
    print(f"\nBatch done: ok={len(ok_tickers)} failed={failed}")

    if args.git_commit and ok_tickers:
        paths = [
            "_system/portfolio/registry.json",
            "_system/portfolio/holdings.md",
            "_system/portfolio/sp500_onboard_status.jsonl",
            str(manifest_path.relative_to(ROOT)),
            "_system/data/deep_dive_dispatch_queue.json",
        ]
        for t in ok_tickers:
            paths.append(t)
            key = t.replace(".", "_")
            paths.append(f"_system/reference/market-data/returns/{key}.csv")
            paths.append(f"_system/reviews/pending/{t}_onboard_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md")
        stage = [PY, "-c", "import subprocess,sys; [subprocess.run(['git','add',p]) for p in sys.argv[1:]]", *paths]
        subprocess.run(stage, cwd=ROOT)
        msg = f"onboard(sp500): batch {batch_id} — {', '.join(ok_tickers)}"
        commit = subprocess.run(["git", "commit", "-m", msg], cwd=ROOT)
        if commit.returncode != 0:
            print("git commit failed", file=sys.stderr)
            return commit.returncode
        if args.git_push:
            rc = git_push_batch()
            if rc != 0:
                print("git push failed", file=sys.stderr)
                return rc

    return 1 if failed and not ok_tickers else 0


if __name__ == "__main__":
    raise SystemExit(main())
