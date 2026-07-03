#!/usr/bin/env python3
"""Re-download and push onboard investor PDFs in small commits."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "_system" / "scripts" / "us_ticker_config.json"
DOWNLOAD = ROOT / "_system" / "scripts" / "download_us_investor_docs.py"
MAX_BYTES = 3 * 1024 * 1024
RETRIES = 5

TICKERS = [
    "ASPN", "AXON", "B", "BRBR", "COLD", "ECHO", "EFOR", "ENPH", "EQPT", "ETOR",
    "FLUX", "FTRE", "GPGI", "GS", "GTX", "HEI.A", "HL", "INV", "JPM", "LBRDK",
    "MCHB", "MDB", "POST", "SHC", "SRPT", "TBBK", "TOI", "WEST", "XTIA",
]


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, check=check)


def ensure_main() -> None:
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    if branch != "main":
        raise SystemExit(f"Expected branch main, on {branch!r}")


def tracked_pdfs() -> set[str]:
    out = subprocess.check_output(["git", "ls-files", "*.pdf"], cwd=ROOT, text=True)
    return {line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()}


def ensure_sparse(ticker: str) -> None:
    run(["git", "sparse-checkout", "add", f"{ticker}/investor-documents"], check=False)


def sync_remote() -> None:
    for attempt in range(1, 4):
        r = run(["git", "fetch", "origin"], check=False)
        if r.returncode == 0:
            break
        time.sleep(attempt * 5)
    else:
        print("WARN: git fetch failed; continuing", file=sys.stderr)
        return
    status = subprocess.check_output(["git", "status", "-sb"], cwd=ROOT, text=True)
    if "behind" in status:
        r = run(["git", "pull", "--rebase", "--autostash", "origin", "main"], check=False)
        if r.returncode != 0:
            run(["git", "rebase", "--abort"], check=False)
            raise SystemExit("git pull --rebase failed; resolve manually")


def download_ticker(ticker: str) -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    if ticker not in cfg or not cfg[ticker].get("ir_roots"):
        print(f"SKIP download {ticker}: no ir_roots")
        return
    ensure_sparse(ticker)
    print(f"\n=== DOWNLOAD {ticker} ===")
    r = run([sys.executable, str(DOWNLOAD), "--ticker", ticker], check=False)
    if r.returncode != 0:
        print(f"WARN: download {ticker} exited {r.returncode}; pushing partial set", file=sys.stderr)


def batches_for(paths: list[Path]) -> list[list[Path]]:
    batches: list[list[Path]] = []
    cur: list[Path] = []
    cur_sz = 0
    for pdf in paths:
        sz = pdf.stat().st_size
        if sz > MAX_BYTES:
            if cur:
                batches.append(cur)
                cur, cur_sz = [], 0
            batches.append([pdf])
            continue
        if cur and cur_sz + sz > MAX_BYTES:
            batches.append(cur)
            cur, cur_sz = [], 0
        cur.append(pdf)
        cur_sz += sz
    if cur:
        batches.append(cur)
    return batches


def push_batch(rels: list[str], label: str) -> None:
    sync_remote()
    run(["git", "add", "--sparse", *rels])
    if run(["git", "diff", "--cached", "--quiet"], check=False).returncode == 0:
        return
    run(["git", "commit", "-m", label])
    for attempt in range(1, RETRIES + 1):
        r = run(["git", "push", "origin", "main"], check=False)
        if r.returncode == 0:
            print(f"  pushed {len(rels)} file(s): {label}")
            return
        wait = min(attempt * 8, 40)
        print(f"  push retry {attempt}/{RETRIES} in {wait}s …", file=sys.stderr)
        time.sleep(wait)
        sync_remote()
    raise SystemExit(f"Push failed: {label}")


def push_ticker_pdfs(ticker: str) -> int:
    ensure_sparse(ticker)
    tracked = tracked_pdfs()
    base = ROOT / ticker / "investor-documents"
    if not base.exists():
        return 0
    pending = [
        p for p in sorted(base.rglob("*.pdf"))
        if p.relative_to(ROOT).as_posix() not in tracked
    ]
    if not pending:
        print(f"  {ticker}: no new PDFs")
        return 0
    print(f"  {ticker}: pushing {len(pending)} PDFs …")
    pushed = 0
    for i, batch in enumerate(batches_for(pending), 1):
        rels = [p.relative_to(ROOT).as_posix() for p in batch]
        sz = sum(p.stat().st_size for p in batch)
        label = f"Onboard PDFs: {ticker} ({i}, {len(rels)} files, {sz // 1024}KB)"
        push_batch(rels, label)
        pushed += len(batch)
    return pushed


def main() -> None:
    ensure_main()
    for ticker in TICKERS:
        ensure_sparse(ticker)
    total = 0
    for ticker in TICKERS:
        download_ticker(ticker)
        total += push_ticker_pdfs(ticker)
    print(f"\nDone — pushed {total} PDFs total")


if __name__ == "__main__":
    main()
