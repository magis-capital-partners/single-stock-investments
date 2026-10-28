#!/usr/bin/env python3
"""Resume a private Fund Letters release into D1/R2; local simulation is the default.

Remote mode requires an explicit database UUID, matching config, a working daily
budget check, and a private R2 binding. It never deploys code or changes Access.
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
    def execute(path: Path):
        call(["d1", "execute", "DB", "--remote" if args.remote else "--local", "--yes", "--file", str(path)], retries=R2_RETRY_LIMIT)
    if args.rollback:
        execute(release / "rollback.sql")
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
    batches = [lines[i:i+250] for i in range(0, len(lines), 250)]
    for index in range(state["batch"], min(len(batches), state["batch"] + args.max_batches)):
        file = release / "current-batch.sql"
        file.write_text("".join(batches[index]), encoding="utf-8")
        execute(file)
        state["batch"] = index + 1
        state_path.write_text(json.dumps(state), encoding="utf-8")
    complete = state["batch"] == len(batches)
    if args.activate and complete:
        execute(release / "activate.sql")
    print(json.dumps({"release_id": manifest["id"], "remote": args.remote, "imported_batches": state["batch"], "total_batches": len(batches), "complete": complete, "activation_requested": args.activate, "activation_attempted": bool(args.activate and complete)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
