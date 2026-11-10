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
import re
import shutil
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
LMS_MODEL = os.environ.get("FUND_LETTERS_LMS_MODEL", "qwen/qwen3.5-9b")
LMS_IDENTIFIER = os.environ.get("FUND_LETTERS_LMS_IDENTIFIER", "qwen-gpu")
# Limits past which the lane waits instead of summarizing. See memory_shortage().
# With the model and both lanes working, this 16 GB Mac sits at a few gigabytes of swap.
MAX_SWAP_GB = float(os.environ.get("FUND_LETTERS_MAX_SWAP_GB", "12"))
MIN_FREE_DISK_GB = float(os.environ.get("FUND_LETTERS_MIN_FREE_DISK_GB", "8"))
# A letter already being read is put down when swap climbs this far while it is in progress.
ABORT_SWAP_GB = float(os.environ.get("FUND_LETTERS_ABORT_SWAP_GB", str(MAX_SWAP_GB + 6)))
ACCOUNT_ID_RE = re.compile(r"\b([0-9a-f]{32})\b")
OAUTH_TOKEN_RE = re.compile(r'(?m)^oauth_token\s*=\s*"([^"]+)"\s*$')


def wrangler_js() -> Path:
    return ROOT / "dashboard/cloudflare/node_modules/wrangler/bin/wrangler.js"


def apply_wrangler_login(env: dict) -> str | None:
    """Use `wrangler login` for the D1 budget check when no API token is configured.

    A token already exported in the process environment is kept. The OAuth
    token is refreshed by `wrangler whoami` and is never written to the log.
    """
    if os.environ.get("CLOUDFLARE_API_TOKEN") and os.environ.get("CLOUDFLARE_ACCOUNT_ID"):
        env["CLOUDFLARE_API_TOKEN"] = os.environ["CLOUDFLARE_API_TOKEN"]
        env["CLOUDFLARE_ACCOUNT_ID"] = os.environ["CLOUDFLARE_ACCOUNT_ID"]
        return None
    wrangler = wrangler_js()
    if not wrangler.is_file():
        return "local wrangler install missing"
    proc = subprocess.run(
        ["node", str(wrangler), "whoami"],
        env=env, text=True, capture_output=True, encoding="utf-8",
    )
    config = Path(env.get("WRANGLER_OAUTH_CONFIG") or (Path.home() / "Library/Preferences/.wrangler/config/default.toml"))
    token = OAUTH_TOKEN_RE.search(config.read_text(encoding="utf-8")) if config.is_file() else None
    account = ACCOUNT_ID_RE.search(proc.stdout or "")
    if proc.returncode or not account or not token:
        return "wrangler login is missing or expired"
    env["CLOUDFLARE_ACCOUNT_ID"] = account.group(1)
    env["CLOUDFLARE_API_TOKEN"] = token.group(1)
    return None


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


def find_lms() -> Path | None:
    for candidate in (shutil.which("lms"), Path.home() / ".lmstudio/bin/lms"):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def model_answering() -> bool:
    import llm_local

    # LM Studio gives its internal server a new port on every load, so an
    # address remembered from an earlier cycle proves nothing.
    llm_local._RESOLVED.clear()
    try:
        return bool(llm_local.models())
    except llm_local.LocalLLMUnavailable:
        return False


def ensure_model() -> bool:
    """Load the local model when nothing is answering.

    The lane used to rely on the podcast lane having loaded it. After a restart,
    or once the model had been unloaded to free memory, every cycle failed with
    "no local LLM server" until someone noticed. The load command is the media
    lane's, so the two lanes share one copy of the model. LM Studio's own server
    on port 1234 is never started here: older callers prefer it when it answers
    and then fail on its JSON mode.
    """
    if model_answering():
        return True
    lms = find_lms()
    if lms is None:
        print(json.dumps({"model": "unavailable", "reason": "lms CLI not found; open LM Studio and load the model"}), flush=True)
        return False
    try:
        listed = subprocess.run([str(lms), "ps"], text=True, capture_output=True, timeout=60).stdout or ""
        if LMS_IDENTIFIER in listed:
            # Another lane is part-way through loading it. A second load would
            # put a second copy of the model in memory.
            time.sleep(45)
            return model_answering()
        print(json.dumps({"step": "load-model", "model": LMS_MODEL, "at": now()}), flush=True)
        subprocess.run([str(lms), "load", LMS_MODEL, "--identifier", LMS_IDENTIFIER,
                        "-c", str(summarizer.CONTEXT_TOKENS), "--parallel", "1", "-y", "--gpu", "max"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"model": "unavailable", "reason": f"lms failed: {exc}"[:200]}), flush=True)
        return False
    ready = model_answering()
    if not ready:
        print(json.dumps({"model": "unavailable", "reason": "the model was loaded but its server is not answering"}), flush=True)
    return ready


def release_model() -> bool:
    """Unload the model while the machine is short of memory. True when it was unloaded.

    A loaded model holds about ten gigabytes whether or not anyone is asking
    it anything. It is left alone when another lane is in the middle of a
    reply; `ensure_model` in either lane loads it again when it is next wanted.
    """
    lms = find_lms()
    if lms is None:
        return False
    try:
        listed = subprocess.run([str(lms), "ps"], text=True, capture_output=True, timeout=60).stdout or ""
        row = next((line.split() for line in listed.splitlines() if line.split()[:1] == [LMS_IDENTIFIER]), [])
        if "IDLE" not in row:
            return False
        done = subprocess.run([str(lms), "unload", LMS_IDENTIFIER], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return False
    if done.returncode:
        return False
    print(json.dumps({"step": "unload-model", "model": LMS_MODEL, "at": now()}), flush=True)
    return True


def _sysctl(name: str) -> str:
    try:
        return subprocess.run(["sysctl", "-n", name], text=True, capture_output=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def memory_shortage(pressure: str | None = None, swap: str | None = None, free_disk_gb: float | None = None) -> str | None:
    """Why the lane should wait this cycle, or None when there is room.

    On 2026-11-10 this Mac ran out of swap space and the kernel panicked:
    other jobs held tens of gigabytes while the model was answering. macOS
    grows swap onto the startup disk, so a nearly full disk and a large swap
    are the same emergency. Summarizing through it only adds page traffic and
    GPU load to a machine that is already failing, so the lane sits the
    cycle out, unloads the model, and tries again on the next one. Publishing
    still runs.
    """
    pressure = _sysctl("kern.memorystatus_vm_pressure_level") if pressure is None else pressure
    if pressure.strip() == "4":
        return "the system reports critical memory pressure"
    swap = _sysctl("vm.swapusage") if swap is None else swap
    used = re.search(r"used = ([\d.]+)([MG])", swap)
    if used:
        gigabytes = float(used.group(1)) / (1024 if used.group(2) == "M" else 1)
        if gigabytes > MAX_SWAP_GB:
            return f"{gigabytes:.0f} GB of swap is in use (limit {MAX_SWAP_GB:.0f} GB)"
    if free_disk_gb is None:
        try:
            free_disk_gb = shutil.disk_usage(Path.home()).free / 1e9
        except OSError:
            free_disk_gb = None
    if free_disk_gb is not None and free_disk_gb < MIN_FREE_DISK_GB:
        return f"only {free_disk_gb:.0f} GB of disk is free for swap (minimum {MIN_FREE_DISK_GB:.0f} GB)"
    return None


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
    records = json.loads((letters_root() / "insights.json").read_text(encoding="utf-8")).get("letters") or []
    links = fl.drive_source_links(records)
    if not db.execute("SELECT COUNT(*) FROM fl_letters").fetchone()[0]:
        result = fl.inventory(db, records, links)
        result.pop("identity_audit", None)
        print(json.dumps({"inventory": result}), flush=True)
    linked = fl.attach_source_links(db, links)
    if linked:
        print(json.dumps({"original_links_added": linked}), flush=True)


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
        if payload.get("prompt_version") not in summarizer.PUBLISHABLE_VERSIONS:
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


def prune_old_releases(keep: Path) -> int:
    """Drop superseded release snapshots.

    Each publish copies every letter extract into a new directory. The live
    archive is archive.sqlite, and sync resumes from the release it was given,
    so older directories are only spare copies. One of them is about 580 MB;
    leaving them all on disk is what filled the machine.
    """
    root = keep.parent
    removed = 0
    if not root.is_dir():
        return 0
    for path in root.iterdir():
        if not path.is_dir() or path.resolve() == keep.resolve():
            continue
        shutil.rmtree(path)
        removed += 1
    if removed:
        print(json.dumps({"pruned_releases": removed, "kept": keep.name}), flush=True)
    return removed


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
    login_problem = apply_wrangler_login(env)
    if not (env.get("CLOUDFLARE_API_TOKEN") and env.get("CLOUDFLARE_ACCOUNT_ID")):
        out["sync"] = "pending: " + (login_problem or "CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID must be in the environment for the D1 budget check")
        return out
    settings = json.loads(config.read_text(encoding="utf-8"))
    database = next((d for d in settings.get("d1_databases", []) if d.get("binding") == "DB"), None)
    if not database:
        out["sync"] = "pending: config has no DB binding"
        return out
    code = run_step("sync-release", [sys.executable, str(SYNC), str(release), "--config", str(config),
                                     "--remote", "--target-database-id", database["database_id"],
                                     "--activate", "--max-batches", "2000"], env)
    out["synced"] = code == 0
    if code:
        out["sync"] = "sync step failed; rerun resumes from the release progress file"
    out["pruned_releases"] = prune_old_releases(release)
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


def summarize_batch(args, env: dict) -> int:
    """Summarize up to one batch, a letter at a time. Returns how many runs started.

    A letter takes several minutes of model time, so memory is looked at
    before every letter and not once per batch: a batch that began with room
    to spare must not keep the model busy for most of an hour after the
    machine has run short.
    """
    started = 0
    for index in range(max(1, args.batch)):
        shortage = memory_shortage()
        if shortage:
            released = release_model()
            print(json.dumps({"note": f"summarize step skipped: {shortage}; "
                                      + ("the model was unloaded to give its memory back; " if released else "")
                                      + "publishing continues"}), flush=True)
            break
        if not ensure_model():
            print(json.dumps({"note": "summarize step skipped: the local model is not available; publishing continues"}), flush=True)
            break
        command = [sys.executable, str(SUMMARIZER), "--limit", "1", "--retry-failed"]
        if args.refresh_older and index < args.refresh_older:
            command += ["--refresh-older", "1"]
        started += 1
        if run_step("summarize", command, {**env, "FUND_LETTERS_ABORT_SWAP_GB": str(ABORT_SWAP_GB)}):
            print(json.dumps({"note": "summarize step did not complete (a manual run may hold the lock); publishing continues"}), flush=True)
            break
    return started


def cycle(args, db, state: dict, env: dict) -> dict:
    if not args.no_repair:
        run_step("repair", [sys.executable, str(SUMMARIZER), "--repair-existing"], env)
    if not args.no_summarize:
        summarize_batch(args, env)
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
    parser.add_argument("--refresh-older", type=int, default=0,
                        help="Each cycle, also redo this many summaries written by an earlier method")
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
