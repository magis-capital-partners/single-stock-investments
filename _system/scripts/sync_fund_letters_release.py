#!/usr/bin/env python3
"""Resume a private Fund Letters release into D1/R2; local simulation is the default.

Remote mode requires an explicit database UUID, matching config, a working daily
budget check, and a private R2 binding. It never deploys code or changes Access.

Every release is a full snapshot, so most of its statements were already sent
with an earlier one. Remote mode keeps a ledger of the inserts the database has
accepted and sends only the rest; --full ignores the ledger and replays
everything (use it after the remote database has been restored or rebuilt).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
R2_PUT_GAP_SECONDS = 0.75
R2_RETRY_LIMIT = 8
# One wrangler --command. The whole command is a single process argument, and
# macOS allows about 1 MB for all arguments together; D1 itself was measured
# accepting 480 KB in one call.
COMMAND_BYTES = 400_000
BATCH_STATEMENTS = 250
# D1 refuses a single statement longer than this (SQLITE_TOOBIG).
STATEMENT_BYTES = 100_000
INSERT_PREFIX = "INSERT OR IGNORE INTO "


def statements(text: str) -> list[str]:
    output = []
    current = ""
    for line in text.splitlines(keepends=True):
        current += line
        if sqlite3.complete_statement(current):
            output.append(current)
            current = ""
    if current.strip():
        raise ValueError("Incomplete release SQL")
    return output


def byte_batches(lines: list[str], limit: int = COMMAND_BYTES, count: int = BATCH_STATEMENTS) -> list[list[str]]:
    """Group statements into commands bounded by bytes as well as by count."""
    batches, current, size = [], [], 0
    for line in lines:
        length = len(line.encode("utf-8"))
        if length > STATEMENT_BYTES:
            raise ValueError(f"A release statement is {length} bytes; D1 accepts at most {STATEMENT_BYTES}: {line[:90]!r}")
        if current and (size + length > limit or len(current) >= count):
            batches.append(current)
            current, size = [], 0
        current.append(line)
        size += length
    if current:
        batches.append(current)
    return batches


def fingerprint(statement: str) -> str:
    return hashlib.sha256(statement.encode("utf-8")).hexdigest()[:24]


def pending(lines: list[str], applied: set[str]) -> list[str]:
    """Statements still to send. An accepted INSERT OR IGNORE can never do
    anything a second time, so it is skipped. Updates are conditional on the
    current remote row and are always sent again."""
    return [line for line in lines if not (line.startswith(INSERT_PREFIX) and fingerprint(line) in applied)]


def ledger_path(database_id: str) -> Path:
    # Outside releases/, which is pruned down to the newest snapshot.
    return ROOT / "_private/fund_letters/applied" / f"{database_id}.txt"


def read_ledger(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def record_applied(path: Path, batch: list[str]) -> None:
    marks = [fingerprint(line) for line in batch if line.startswith(INSERT_PREFIX)]
    if not marks:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(marks) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def budget_check() -> None:
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    # Wrangler OAuth access tokens are not Account Analytics API tokens.
    if token.startswith("cfoat_"):
        print(json.dumps({"budget": "unavailable", "reason": "wrangler OAuth token cannot read Account Analytics; continuing without the soft budget probe"}), flush=True)
        return
    path = ROOT / ".github/actions/deploy-cloudflare-dashboard/d1_budget.py"
    spec = importlib.util.spec_from_file_location("fund_letter_d1_budget", path)
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    result = module.check(os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""), token, datetime.now(timezone.utc).date().isoformat())
    if result.over:
        raise RuntimeError("Remote import deferred: " + result.describe())
    if not result.available:
        # Analytics can be rate-limited or unreadable. The D1 quota error remains the backstop.
        print(json.dumps({"budget": "unavailable", "reason": result.reason[:180]}), flush=True)


def rate_limited(text: str) -> bool:
    lowered = text.lower()
    return "429" in text or "too many requests" in lowered or "rate limited" in lowered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", type=Path)
    parser.add_argument("--config", type=Path, required=True, help="JSON Wrangler config for the existing application")
    parser.add_argument("--remote", action="store_true")
    parser.add_argument("--target-database-id", help="Must exactly match the DB binding in config")
    parser.add_argument("--max-batches", type=int, default=5)
    parser.add_argument("--full", action="store_true", help="Replay every statement, ignoring the ledger of accepted inserts")
    parser.add_argument("--activate", action="store_true", help="Activate reviewed pointers after data/source import")
    parser.add_argument("--rollback", action="store_true", help="Restore the prior pointers recorded by this release")
    args = parser.parse_args()
    release = args.release.resolve()
    if ROOT / "_private" not in release.parents:
        raise ValueError("Release must be inside _private")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    db = next((d for d in config.get("d1_databases", []) if d["binding"] == "DB"), None)
    bucket = next((b for b in config.get("r2_buckets", []) if b["binding"] == "PRIVATE_ARTIFACTS"), None)
    if not db:
        raise ValueError("Missing DB binding")
    if args.remote and (not args.target_database_id or db["database_id"] != args.target_database_id or not bucket):
        raise ValueError("Remote mode needs a matching explicit database UUID and PRIVATE_ARTIFACTS R2 binding")
    if args.max_batches < 1:
        raise ValueError("max-batches must be positive")
    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    if hashlib.sha256((release / "archive.sql").read_bytes()).hexdigest()[:24] != manifest["id"]:
        raise ValueError("Release SQL does not match its immutable manifest")
    state_path = release / ("remote-progress.json" if args.remote else "local-progress.json")
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"release_id": manifest["id"], "database_id": db["database_id"], "uploaded": [], "batch": 0}
    if state["release_id"] != manifest["id"] or state["database_id"] != db["database_id"]:
        raise ValueError("Progress marker does not match this release/database")
    wrangler = ROOT / "dashboard/cloudflare/node_modules/wrangler/bin/wrangler.js"
    # OAuth access tokens (cfoat_*) are not API tokens. If the parent lane exported
    # one as CLOUDFLARE_API_TOKEN for the soft budget probe, strip it so Wrangler
    # uses its logged-in OAuth session for D1/R2 instead of a 401/429 death spiral.
    wrangler_env = dict(os.environ)
    if wrangler_env.get("CLOUDFLARE_API_TOKEN", "").startswith("cfoat_"):
        wrangler_env.pop("CLOUDFLARE_API_TOKEN", None)
    def call(arguments: list[str], *, retries: int = 1):
        last = ""
        for attempt in range(1, retries + 1):
            proc = subprocess.run(
                ["node", str(wrangler), *arguments, "--config", str(args.config.resolve())],
                capture_output=True, text=True, encoding="utf-8", env=wrangler_env,
            )
            if proc.returncode == 0:
                return
            last = (proc.stdout or "") + (proc.stderr or "")
            if attempt < retries and rate_limited(last):
                wait = min(60.0, 2.0 ** attempt)
                print(json.dumps({"retry": attempt, "wait_seconds": wait, "reason": "rate_limited"}), flush=True)
                time.sleep(wait)
                continue
            (release / "last-error.log").write_text(last, encoding="utf-8")
            raise RuntimeError("Release step failed. Details saved to private last-error.log; rerun resumes safely.")
    def execute(sql: str):
        # --file posts to the D1 import API, which rejects this account's OAuth
        # session (401, error 10000). The same session can run the SQL through
        # the query API, so each command travels as one argument and has to
        # stay inside the limits byte_batches enforces.
        call(["d1", "execute", "DB", "--remote" if args.remote else "--local", "--yes", "--command", sql], retries=R2_RETRY_LIMIT)
    def execute_file(path: Path):
        for batch in byte_batches(statements(path.read_text(encoding="utf-8"))):
            execute("".join(batch))
    if args.rollback:
        execute_file(release / "rollback.sql")
        print(json.dumps({"rolled_back": manifest["id"], "remote": args.remote}))
        return 0
    if args.remote:
        budget_check()
        sources = list(manifest.get("source_objects") or [])
        for index, digest in enumerate(sources):
            if digest in state["uploaded"]:
                continue
            call(
                ["r2", "object", "put", f"{bucket['bucket_name']}/fund-letters/source/{digest}.txt", "--remote", "--file", str(release / "sources" / f"{digest}.txt")],
                retries=R2_RETRY_LIMIT,
            )
            state["uploaded"].append(digest)
            state_path.write_text(json.dumps(state), encoding="utf-8")
            if index + 1 < len(sources):
                time.sleep(R2_PUT_GAP_SECONDS)
            if len(state["uploaded"]) % 10 == 0:
                print(json.dumps({"uploaded": len(state["uploaded"]), "total": len(sources)}), flush=True)
    lines = statements((release / "archive.sql").read_text(encoding="utf-8"))
    # The ledger describes the remote database only. A local simulation is
    # disposable, so it always replays the whole release.
    ledger = ledger_path(db["database_id"]) if args.remote else None
    applied = read_ledger(ledger) if ledger and not args.full else set()
    todo = pending(lines, applied)
    # Inserts first, so a run cut short by --max-batches always shortens the
    # next one. Every update refers to a row inserted by this release or an
    # earlier one, so it loses nothing by running last.
    todo = [line for line in todo if line.startswith(INSERT_PREFIX)] + [line for line in todo if not line.startswith(INSERT_PREFIX)]
    batches = byte_batches(todo)
    # The batch marker belongs to one plan. Once the ledger has grown the plan
    # is a different, shorter one and starts from its own beginning.
    plan = hashlib.sha256("".join(todo).encode("utf-8")).hexdigest()[:24]
    if state.get("plan") != plan:
        state.update({"plan": plan, "batch": 0})
    sent = 0
    for index in range(state["batch"], min(len(batches), state["batch"] + args.max_batches)):
        execute("".join(batches[index]))
        if ledger:
            record_applied(ledger, batches[index])
        sent += 1
        state["batch"] = index + 1
        state_path.write_text(json.dumps(state), encoding="utf-8")
    complete = state["batch"] == len(batches)
    if args.activate and complete:
        execute_file(release / "activate.sql")
    print(json.dumps({"release_id": manifest["id"], "remote": args.remote, "statements": len(lines), "already_applied": len(lines) - len(todo), "sent_batches": sent, "imported_batches": state["batch"], "total_batches": len(batches), "complete": complete, "activation_requested": args.activate, "activation_attempted": bool(args.activate and complete)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
