#!/usr/bin/env python3
"""Fully automated Fund Letters lane: summarize, verify, publish, persist.

One cycle is: repair saved drafts, summarize the next batch with the local
model, import every verified draft into the private archive, publish it on
machine-verified checks (no human attestation), export a release, sync it
to D1/private R2 when credentials are present, and commit the private
summaries to the research vault. Progress is durable at every step: each
letter is a file, each publication is recorded in publish_state.json, and
the vault commit is the checkpoint. Nothing here touches the public repo
with letter content, ThetaData, or the IB Gateway.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import fund_letters as fl  # noqa: E402
import summarize_fund_letter_reader as summarizer  # noqa: E402
from letter_dedup import normalized_content_hash  # noqa: E402
from vault_paths import letters_root, resolve_ref_to_path  # noqa: E402

SUMMARIZER = ROOT / "_system/scripts/summarize_fund_letter_reader.py"
SYNC = ROOT / "_system/scripts/sync_fund_letters_release.py"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_step(label: str, argv: list[str], env: dict) -> int:
    print(json.dumps({"step": label, "at": now()}), flush=True)
    proc = subprocess.run(argv, env=env, text=True, capture_output=True)
    for line in (proc.stdout or "").splitlines()[-6:]:
        print(line, flush=True)
    if proc.returncode:
        print(json.dumps({"step_failed": label, "code": proc.returncode,
                          "tail": (proc.stderr or proc.stdout or "")[-400:]}), flush=True)
    return proc.returncode


def output_dir() -> Path:
    path = letters_root() / "_reader_summaries"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_state() -> dict:
    path = output_dir() / "publish_state.json"
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state: dict) -> None:
    path = output_dir() / "publish_state.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(path)


def ensure_inventory(db) -> None:
    count = db.execute("SELECT COUNT(*) FROM fl_letters").fetchone()[0]
    if count:
        return
    records = json.loads((letters_root() / "insights.json").read_text(encoding="utf-8")).get("letters") or []
    result = fl.inventory(db, records, None)
    result.pop("identity_audit", None)
    print(json.dumps({"inventory": result}), flush=True)


def publish_verified(db, state: dict) -> dict:
    counts = {"published": 0, "quarantined": 0, "already": 0}
    records_by_ref = {}
    for record in json.loads((letters_root() / "insights.json").read_text(encoding="utf-8")).get("letters") or []:
        records_by_ref[record.get("source_file")] = record
    for path in sorted(output_dir().glob("*.json")):
        if path.name in {"progress.json", "publish_state.json"} or path.name.endswith(".draft.json"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("status") != "draft":
            continue
        if payload.get("prompt_version") != summarizer.PROMPT_VERSION:
            continue
        content_hash = path.stem
        draft_file = output_dir() / f"{content_hash}.draft.json"
        if not draft_file.is_file():
            continue
        draft_raw = draft_file.read_bytes()
        draft_digest = hashlib.sha256(draft_raw).hexdigest()
        prior = state.get(content_hash) or {}
        if prior.get("draft_digest") == draft_digest and prior.get("result") in {"published", "quarantined"}:
            counts["already"] += 1
            continue
        record = records_by_ref.get(payload.get("source_ref")) or {}
        source_path = resolve_ref_to_path(record.get("source_file"))
        if source_path is None or not source_path.is_file():
            state[content_hash] = {"result": "quarantined", "reason": "source extract missing", "draft_digest": draft_digest, "at": now()}
            counts["quarantined"] += 1
            continue
        digest = normalized_content_hash(source_path.read_text(encoding="utf-8", errors="replace"))
        row = db.execute("SELECT id FROM fl_letters WHERE content_hash=?", (digest,)).fetchone()
        if not row:
            state[content_hash] = {"result": "quarantined", "reason": "letter not in archive inventory", "draft_digest": draft_digest, "at": now()}
            counts["quarantined"] += 1
            continue
        draft = json.loads(draft_raw.decode("utf-8"))
        try:
            revision_id, errors = fl.save_draft(db, row[0], draft, fl.AUTO_AUTHOR)
            if errors:
                raise ValueError("; ".join(errors))
            result = fl.publish_automated(db, revision_id)
            state[content_hash] = {"result": "published", "letter_id": row[0], "revision_id": revision_id,
                                   "draft_digest": draft_digest, "at": now(), "auto_resolved": result["auto_resolved"]}
            counts["published"] += 1
            print(json.dumps({"published": payload.get("fund_id"), "period": payload.get("reporting_period"),
                              "letter_id": row[0]}), flush=True)
        except Exception as exc:  # a failed letter never blocks the batch
            db.rollback()
            state[content_hash] = {"result": "quarantined", "reason": str(exc)[:300], "draft_digest": draft_digest, "at": now()}
            counts["quarantined"] += 1
            print(json.dumps({"quarantined": payload.get("fund_id"), "reason": str(exc)[:200]}), flush=True)
        save_state(state)
    return counts


def export_and_sync(db, env: dict, sync_remote: bool) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    release = ROOT / "_private/fund_letters/releases" / f"auto-{stamp}"
    manifest = fl.export_release(db, release)
    out = {"release": manifest["id"], "published_letters": len(manifest.get("published") or {}), "synced": False}
    if not sync_remote:
        out["sync"] = "not requested"
        return out
    config = Path(os.environ.get("FUND_LETTERS_WRANGLER_CONFIG", ROOT / "_cf_project/wrangler.jsonc"))
    wrangler = ROOT / "dashboard/cloudflare/node_modules/wrangler/bin/wrangler.js"
    if not config.is_file() or not wrangler.is_file():
        out["sync"] = "pending: wrangler config or local wrangler install missing"
        return out
    if not (os.environ.get("CLOUDFLARE_API_TOKEN") and os.environ.get("CLOUDFLARE_ACCOUNT_ID")):
        out["sync"] = "pending: CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID must be in the environment for the D1 budget check"
        return out
    settings = json.loads(config.read_text(encoding="utf-8"))
    database = next((d for d in settings.get("d1_databases", []) if d.get("binding") == "DB"), None)
    if not database:
        out["sync"] = "pending: config has no DB binding"
        return out
    code = run_step("sync-release", [sys.executable, str(SYNC), str(release), "--config", str(config),
                                     "--remote", "--target-database-id", database["database_id"],
                                     "--activate", "--max-batches", "100"], env)
    out["synced"] = code == 0
    if code:
        out["sync"] = "sync step failed; rerun resumes from the release progress file"
    return out


def commit_vault(env: dict, note: str) -> dict:
    vault = Path(env["RESEARCH_VAULT_ROOT"]) if env.get("RESEARCH_VAULT_ROOT") else letters_root().parents[1]
    target = "superinvestor-letters/_reader_summaries"

    def git(*argv: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(vault), *argv], text=True, capture_output=True)

    git("add", "--", target)
    status = git("status", "--porcelain", "--", target)
    if not status.stdout.strip():
        return {"committed": False}
    message = f"Fund letter summaries: {note} ({now()})"
    done = git("commit", "-m", message, "--", target)
    if done.returncode:
        return {"committed": False, "reason": (done.stderr or done.stdout)[-300:]}
    pushed = git("push")
    return {"committed": True, "pushed": pushed.returncode == 0,
            "reason": "" if pushed.returncode == 0 else (pushed.stderr or "")[-300:]}


def cycle(args, db, state: dict, env: dict) -> dict:
    if not args.no_repair:
        run_step("repair", [sys.executable, str(SUMMARIZER), "--repair-existing"], env)
    if not args.no_summarize:
        code = run_step("summarize", [sys.executable, str(SUMMARIZER), "--limit", str(args.batch), "--retry-failed"], env)
        if code:
            print(json.dumps({"note": "summarize step did not complete (a manual run may hold the lock); publishing continues"}), flush=True)
    published = {"published": 0, "quarantined": 0, "already": 0}
    if not args.no_publish:
        published = publish_verified(db, state)
    release = {}
    if published["published"] and not args.no_publish:
        release = export_and_sync(db, env, args.sync_remote)
    vault = commit_vault(env, f"{published['published']} newly published") if args.commit_vault else {"committed": False}
    return {"at": now(), **published, "release": release, "vault": vault}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, default=5, help="Letters summarized per cycle")
    parser.add_argument("--cycles", type=int, default=1, help="0 runs forever")
    parser.add_argument("--sleep", type=int, default=120, help="Seconds between cycles when running forever")
    parser.add_argument("--no-summarize", action="store_true")
    parser.add_argument("--no-repair", action="store_true")
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--sync-remote", action="store_true", help="Push each release to D1/private R2 and activate it")
    parser.add_argument("--no-commit-vault", dest="commit_vault", action="store_false")
    args = parser.parse_args()
    env = dict(os.environ)
    db = fl.connect()
    ensure_inventory(db)
    state = load_state()
    done = 0
    while True:
        done += 1
        print(json.dumps(cycle(args, db, state, env)), flush=True)
        if args.cycles and done >= args.cycles:
            return 0
        time.sleep(max(10, args.sleep))


if __name__ == "__main__":
    raise SystemExit(main())
