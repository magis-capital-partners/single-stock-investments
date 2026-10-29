#!/usr/bin/env python3
"""Run the YouTube research lane end to end, on this host rather than in CI.

The lane was written for `youtube-refresh.yml`, which pins itself to a
`self-hosted, linux, youtube-egress` runner so caption traffic leaves from a
stable residential IP instead of a hosted datacenter one. That runner was never
registered: `GET /actions/runners` returns zero, so every scheduled run has sat
`queued` until the next night's run displaced it. The lane has therefore never
executed in CI at all, while reading as "not failed" the whole time -- a queued
job shows no red X anywhere.

Registering that runner was considered and rejected on 2026-09-06. This
repository is **public**, and a self-hosted runner on a public repository lets
any fork pull request execute code on the host. The host in question is the
operator's workstation: it holds `_secrets/`, a research-vault push token, and
sits on the same network as the trading systems. The egress IP the label exists
to provide is this machine's already, so running the lane directly gives up
nothing and removes the exposure entirely.

**Runs from its own worktree, not the primary checkout.** Concurrent agents
share the main working tree here, and a lane that stages files into a shared
index eventually has them swept into somebody else's commit. `git worktree`
gives a separate index and HEAD while sharing the 21 GB object store, so
isolation costs ~1 GB of sparse checkout rather than a 14 GB second clone.
The worktree pulls `main` at the start of every run: the NY4 hub is a file copy
with no `.git`, and the silent drift that produced is not worth repeating.

**Whisper is opt-in and off by default.** The CI job routes caption-less videos
through local Whisper at `--batch 4`. On this box that would be a third
competitor for memory alongside the podcast Whisper backfill and the analysis
batch, which already leave under 1 GB free; the analyser's own logs show it
waiting on a 600 MB floor. Videos without captions are queued and left queued
until someone asks for them.

    python _system/scripts/youtube_lane.py            # discover -> captions -> publish
    python _system/scripts/youtube_lane.py --hours 2  # longer caption window
    python _system/scripts/youtube_lane.py --whisper 4 --no-push
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

# A video title carries whatever the uploader typed, and cp1252 is what Python
# picks for a redirected stdout on Windows. A U+2060 in a podcast title killed
# an analysis run on 2026-08-29 -- the line reporting success was the crash.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from vault_git import clear_stale_git_state, run_git, vault_lock  # noqa: E402
from vault_paths import videos_root  # noqa: E402

# Written by publish_video_dashboard.py and read by the dashboard. Listed
# explicitly rather than added with `git add -A`: this worktree tracks main, and
# a broad add here would commit whatever else a pull happened to leave behind.
MAIN_PATHS = (
    "dashboard/data/insights/manifest.json",
    "dashboard/data/insights/videos.json",
    "_system/reference/video/insights_index_mirror.json",
)

# Per-video detail shards, one file per admitted video, created and deleted as
# the corpus moves. A fixed file list cannot express that, and listing only the
# index files meant videos.json advertised 95 videos while 63 stale shards were
# committed and 32 had never been added at all -- every one of those a 404 on
# click. Scoped to this one directory so the `git add -A` discipline above still
# holds: nothing outside it is ever staged by this lane.
MAIN_DIRS = ("dashboard/data/insights/video_details",)

# The podcast batch publishes the same way. The manifest is shared with the
# video shard, so a podcast push rewrites it and must start from the copy
# already on main rather than an empty file.
PODCAST_PATHS = (
    "dashboard/data/insights/manifest.json",
    "dashboard/data/insights/podcasts.json",
    "_system/reference/podcasts/insights_index_mirror.json",
)
PODCAST_DIRS = ("dashboard/data/insights/podcast_episodes",)

# The branch this lane publishes to. It commits to HEAD and then pushes, so
# `git push origin main` -- which resolves the *local* ref of that name --
# published whatever main happened to point at rather than the commit just
# made. Pushed as HEAD:main instead, which is correct detached as well as on a
# branch. lane_worktree.ps1 keeps lane worktrees on a detached FETCH_HEAD
# precisely so nobody's branch switch can move them, so detached is the
# expected state here and must not be refused.
MAIN_BRANCH = "main"

# Lines of git's own output kept per stream when a command fails. A failed
# `pull --rebase` opens with a fetch preamble ("From <remote>", a ref update)
# and ends with the reason, so it is the tail that explains, never the head.
GIT_TAIL_LINES = 12


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(message: str) -> None:
    print(f"[{stamp()}] {message}", flush=True)


def describe_failure(exc: BaseException) -> str:
    """The command that failed and, in git's own words, why.

    `str()` of a CalledProcessError is the command alone. From 2026-09-21 to
    09-23 that was all the log kept of "untracked working tree files would be
    overwritten by checkout", the one line that said what to fix. stderr
    carries git's verdict; stdout is where a rebase names the file it
    conflicted on, so both tails are kept.
    """
    if not isinstance(exc, (subprocess.CalledProcessError, subprocess.TimeoutExpired)):
        return f"{type(exc).__name__}: {exc}"
    command = shlex.join(str(part) for part in exc.cmd)
    if isinstance(exc, subprocess.TimeoutExpired):
        detail = [f"`{command}` timed out after {exc.timeout}s"]
    else:
        detail = [f"`{command}` exited {exc.returncode}"]
    for stream in (exc.stderr, exc.output):
        if isinstance(stream, bytes):
            stream = stream.decode("utf-8", "replace")
        lines = [line.rstrip() for line in (stream or "").splitlines() if line.strip()]
        detail += [f"    {line}" for line in lines[-GIT_TAIL_LINES:]]
    return "\n".join(detail)


def load_env_file(path: Path) -> int:
    """Read `export KEY='value'` lines into os.environ. Returns keys set.

    The secrets files use shell syntax because they are also `source`d by hand;
    quoting is single because Google key material is base64-ish and contains
    characters bash would otherwise expand.
    """
    if not path.is_file():
        return 0
    pattern = re.compile(r"^\s*(?:export\s+)?([A-Z0-9_]+)\s*=\s*(.*?)\s*$")
    count = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = pattern.match(line)
        if not match:
            continue
        key, raw = match.group(1), match.group(2)
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
            raw = raw[1:-1]
        os.environ[key] = raw
        count += 1
    return count


def step(name: str, args: list[str], *, required: bool, timeout: float | None = None) -> bool:
    """Run one stage. A non-required stage that fails does not end the run.

    `timeout` exists for the caption stage and is not a safety net there, it is
    the actual bound. `fetch_video_transcript --daemon --hours N` checks its
    deadline *between* passes, and a single pass walks the whole pending
    backlog waiting for a pacing slot -- 153 items at 20/hour is about seven
    and a half hours. Left to run, it would be killed by the task's execution
    limit and score/build/publish/commit would never happen, stranding fetched
    captions uncommitted in the vault until the next day's run.
    """
    log(f"-> {name}")
    try:
        proc = subprocess.run([sys.executable, "-u", *args], cwd=ROOT, timeout=timeout)
    except subprocess.TimeoutExpired:
        # Nothing is lost: the backlog is persisted per item, and a fetch cut
        # short counts as transient, which this lane deliberately never charges
        # against an item's retry budget.
        log(f"{name} hit its {timeout:.0f}s budget; moving on")
        return True
    if proc.returncode == 0:
        return True
    level = "FAILED" if required else "failed (continuing)"
    log(f"{name} {level}: exit {proc.returncode}")
    return False


def self_update() -> bool:
    """Pull main into this worktree so the lane runs current code.

    Returns True when HEAD moved. The caller re-executes in that case: the
    modules already imported are the code from before the pull, and that is
    how a lane that had just updated itself still published with the old
    in-place manifest write.

    autoStash because the worktree carries `_secrets/` and whatever a previous
    run left behind; a plain rebase refuses outright when anything is unstaged,
    which is how the podcast analysis batch once analysed two episodes and
    pushed neither.

    The three published paths are reset first, and that is not tidiness. They
    are derived output -- `publish_video_dashboard.py` rebuilds them from the
    vault every run -- and the daily data pipeline rewrites the same
    `videos.json` on main (HEAD's copy was regenerated at 08:36Z on
    2026-09-06). Carrying a local edit to a file the upstream also edits is how
    an autostash pop turns into a conflict, and a conflict here would strand
    the worktree rather than merely skip an update. Discarding costs nothing:
    the corpus they are derived from is committed in the vault.

    The detail-shard directory is reset the same way and for the same reason,
    with a `clean` as well as a `checkout`: most of its drift is *untracked*
    files, which a checkout leaves in place and an autostash then carries into
    the rebase.
    """
    for rel in MAIN_PATHS:
        if (ROOT / rel).is_file():
            run_git(ROOT, "checkout", "--", rel, check=False, timeout=120)
    for rel in MAIN_DIRS:
        if (ROOT / rel).is_dir():
            run_git(ROOT, "checkout", "--", rel, check=False, timeout=120)
            run_git(ROOT, "clean", "-fdq", "--", rel, check=False, timeout=120)
    before = run_git(ROOT, "rev-parse", "HEAD", check=False, timeout=60)
    before_sha = before.stdout.strip() if before.returncode == 0 else ""
    try:
        # This Mac runs the lane from the media-lane commit, which is not on
        # main. Rebasing that checkout replays the commit onto main inside the
        # worktree the LaunchAgent is executing. Leave it. The shard is
        # published from a separate main worktree instead.
        contained = run_git(ROOT, "merge-base", "--is-ancestor", "HEAD",
                            f"origin/{MAIN_BRANCH}", check=False, timeout=60)
        if contained.returncode != 0:
            log("self-update skipped: checkout is not on origin/main, "
                "so rebasing it would replay local commits")
            return False
        run_git(ROOT, "-c", "rebase.autoStash=true", "pull", "--rebase",
                "origin", "main", timeout=900)
        log("worktree updated from origin/main")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        # Running slightly stale beats not running. Say so rather than dying.
        log(f"self-update skipped: {describe_failure(exc)}")
        run_git(ROOT, "rebase", "--abort", check=False, timeout=120)
        return False
    after = run_git(ROOT, "rev-parse", "HEAD", check=False, timeout=60)
    after_sha = after.stdout.strip() if after.returncode == 0 else ""
    return bool(before_sha and after_sha and before_sha != after_sha)


def push_vault(message: str) -> bool | None:
    """Commit the videos/ subtree of the shared vault.

    The Whisper backfill and the analysis batch commit to this same clone every
    few minutes. Two git processes in one repository collide on .git/index.lock,
    and that collision wedged the vault for fourteen hours on 2026-08-31, so the
    same advisory lock those two take is taken here.

    Returns what push_main returns: True on a completed push, None when there
    was nothing to commit, False when a push was needed and did not happen.
    Waiting out the lock is the last kind. The corpus this run wrote is still
    uncommitted, which is a failed push rather than a skipped one.
    """
    repo = videos_root().parent
    try:
        with vault_lock(repo, owner="youtube_lane", log=lambda m: log(m.strip())):
            return _push_vault_locked(repo, message)
    except OSError as exc:  # TimeoutError, in practice: the lock was never ours
        log(f"vault push failed: {describe_failure(exc)}")
        return False


def _push_vault_locked(repo: Path, message: str) -> bool | None:
    try:
        clear_stale_git_state(repo, log=lambda m: log(m.strip()))
        run_git(repo, "add", "-A", "videos", timeout=300)
        staged = run_git(repo, "diff", "--cached", "--quiet", check=False, timeout=120)
        if staged.returncode == 0:
            log("vault: nothing to commit")
            return None
        run_git(repo, "commit", "-m", message, timeout=300)
        run_git(repo, "-c", "rebase.autoStash=true", "pull", "--rebase",
                "origin", "main", timeout=900)
        run_git(repo, "push", "origin", "main", timeout=600)
        log("vault: pushed")
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        log(f"vault push failed: {describe_failure(exc)}")
        # Unwound while the lock is still held, so no other writer can be
        # mid-rebase when this aborts one. Guarded because the dashboard publish
        # has not run yet: on 2026-09-17 a plain `git commit` in this vault
        # outlived its 300-second timeout, and an abort that did the same must
        # not take the publish down with it.
        try:
            run_git(repo, "rebase", "--abort", check=False, timeout=120)
            clear_stale_git_state(repo, log=lambda m: log(m.strip()))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as undo:
            log(f"vault unwind failed: {describe_failure(undo)}")
        return False


def _publish_worktree() -> Path:
    override = os.environ.get("YOUTUBE_PUBLISH_WORKTREE", "").strip()
    if override:
        return Path(override)
    return Path.home() / "Projects" / "ssi-dashboard-publish"


def _head_is_origin_main() -> bool:
    """True when this checkout has nothing origin/main does not already have."""
    run_git(ROOT, "fetch", "origin", MAIN_BRANCH, timeout=300)
    contained = run_git(ROOT, "merge-base", "--is-ancestor", "HEAD",
                        f"origin/{MAIN_BRANCH}", check=False, timeout=60)
    return contained.returncode == 0


def _ensure_publish_worktree() -> Path:
    """A detached sparse checkout of origin/main, used only to publish shards.

    The lane worktree on this Mac is the media-lane commit. Committing the
    shard there and pushing HEAD:main would publish that commit to the public
    repository. The shard is copied onto a checkout that starts at origin/main,
    and only the published paths are committed.
    """
    path = _publish_worktree()
    if not (path / ".git").exists():
        if path.exists():
            raise OSError(f"publish worktree path exists and is not a worktree: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        # --no-checkout first. `worktree add --sparse` is not in this git, and a
        # normal add would materialize the whole repository (~15 GB) just to
        # publish a handful of dashboard files.
        run_git(ROOT, "worktree", "add", "--detach", "--no-checkout", str(path),
                f"origin/{MAIN_BRANCH}", timeout=300)
        run_git(path, "sparse-checkout", "init", "--cone", timeout=120)
        run_git(path, "sparse-checkout", "set",
                "dashboard/data/insights", "_system/reference/video", timeout=120)
        run_git(path, "checkout", "--detach", f"origin/{MAIN_BRANCH}", timeout=300)
    # Expand before reset so a cone created for videos also materializes the
    # podcast mirror. set is idempotent.
    run_git(path, "sparse-checkout", "set",
            "dashboard/data/insights",
            "_system/reference/video",
            "_system/reference/podcasts",
            timeout=120)
    run_git(path, "fetch", "origin", MAIN_BRANCH, timeout=300)
    run_git(path, "reset", "--hard", f"origin/{MAIN_BRANCH}", timeout=180)
    return path


INSIGHT_MANIFEST = "dashboard/data/insights/manifest.json"


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _manifest_repo_root(path: Path) -> Path | None:
    parts = path.parts
    if "dashboard" not in parts:
        return None
    return Path(*parts[: parts.index("dashboard")])


def _managed_manifest(path: Path) -> tuple[Path, str, dict] | None:
    """Return repo root, dashboard-relative path, and receipt when this file is managed."""
    root = _manifest_repo_root(path)
    if root is None:
        return None
    relative = path.relative_to(root / "dashboard").as_posix()
    receipt = root / "dashboard" / "private-assets.json"
    if not receipt.is_file() and (root / ".git").exists():
        # git show, not sparse-checkout add. add turns a full checkout into a
        # sparse one. The publish worktree is already sparse; the blob is still
        # in HEAD, and writing it here is enough to read the receipt.
        shown = run_git(root, "show", "HEAD:dashboard/private-assets.json",
                        check=False, timeout=120)
        if shown.returncode == 0 and shown.stdout.strip():
            receipt.parent.mkdir(parents=True, exist_ok=True)
            text = shown.stdout if shown.stdout.endswith("\n") else shown.stdout + "\n"
            receipt.write_text(text, encoding="utf-8")
    if not receipt.is_file():
        return None
    try:
        manifest = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entry = (manifest.get("assets") or {}).get(relative)
    if not isinstance(entry, dict) or "public_sha256" not in entry or "private_sha256" not in entry:
        return None
    return root, relative, entry


def _resolved_manifest(path: Path) -> dict:
    """The full manifest to patch. A public placeholder is read from the vault."""
    from private_dashboard_assets import digest, read_resolved_json
    from reconcile_insights_event_summary import is_publishable_manifest

    managed = _managed_manifest(path)
    doc = _read_json(path)
    if managed is None:
        if not is_publishable_manifest(doc):
            raise RuntimeError(f"refusing to publish onto a stub insight manifest at {path}")
        return doc
    root, relative, entry = managed
    current = digest(path) if path.is_file() else None
    if current not in (entry["public_sha256"], entry["private_sha256"]):
        raise RuntimeError(
            "Managed dashboard asset changed; export its private snapshot before deployment: "
            + relative
        )
    if doc.get("private_snapshot") is True:
        resolved, _restored = read_resolved_json(root / "dashboard", relative)
    else:
        resolved = doc
    if not is_publishable_manifest(resolved):
        raise RuntimeError(f"refusing to publish onto a stub insight manifest at {path}")
    return resolved


def _canonical_json(document: dict) -> str:
    return json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n"


def _events_beside(manifest_path: Path) -> list | None:
    """The events list for this manifest, read from the vault when the public file is a placeholder."""
    document = _read_json(manifest_path.parent / "events.json")
    if document.get("private_snapshot") is True:
        root = _manifest_repo_root(manifest_path)
        if root is None:
            return None
        from private_dashboard_assets import read_resolved_json
        try:
            document, _restored = read_resolved_json(root / "dashboard", "data/insights/events.json")
        except (OSError, RuntimeError, ValueError):
            return None
    events = document.get("events")
    if isinstance(events, list) and all(isinstance(event, dict) for event in events):
        return events
    return None


def _write_receipt_entry(path: Path, relative: str, entry: dict) -> None:
    document = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"assets": {}}
    if not isinstance(document, dict):
        raise RuntimeError(f"private receipt is not an object: {path}")
    assets = document.setdefault("assets", {})
    if not isinstance(assets, dict):
        raise RuntimeError(f"private receipt has no asset map: {path}")
    assets[relative] = {"private_sha256": entry["private_sha256"], "public_sha256": entry["public_sha256"]}
    text = json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _export_managed_document(repo: Path, relative: str, document: dict) -> None:
    """Store one dashboard document privately and leave its public path a placeholder.

    This does not walk the rest of the receipt. migrate() re-exports every
    hydrated file it can see, which would redact the lane's other working copies.
    """
    import hashlib

    from migrate_dashboard_sources import public_snapshot
    from private_dashboard_assets import private_object
    from vault_paths import research_vault_root

    vault = research_vault_root()
    if vault is None or not (vault / ".git").exists():
        raise RuntimeError(
            "A configured private research-vault checkout is required; public files were not changed."
        )
    payload = _canonical_json(document).encode("utf-8")
    private_hash = hashlib.sha256(payload).hexdigest()
    destination = private_object(vault, private_hash)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        temporary = destination.with_name(destination.name + ".tmp")
        temporary.write_bytes(payload)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != private_hash:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"Private copy failed verification: {relative}")
        temporary.replace(destination)
    public_text = _canonical_json(public_snapshot(document))
    entry = {
        "private_sha256": private_hash,
        "public_sha256": hashlib.sha256(public_text.encode("utf-8")).hexdigest(),
    }
    journal = vault / "dashboard-private" / "migration-journal.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"path": relative, "scope": "dashboard", "entry": entry}) + "\n")
    receipt = repo / "dashboard" / "private-assets.json"
    _write_receipt_entry(receipt, relative, entry)
    vault_receipt = vault / "dashboard-private" / "manifest.json"
    if vault_receipt.is_file():
        _write_receipt_entry(vault_receipt, relative, entry)
    else:
        vault_receipt.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(receipt, vault_receipt)
    public_path = repo / "dashboard" / relative
    temporary = public_path.with_suffix(public_path.suffix + ".tmp")
    temporary.write_text(public_text, encoding="utf-8")
    temporary.replace(public_path)
    if _read_json(public_path).get("private_snapshot") is not True:
        raise RuntimeError(f"Managed dashboard asset was published in full: {relative}")


def _merged_published_manifest(repo: Path, relative: str, entry: dict, document: dict,
                               *, videos: bool, podcasts: bool) -> dict:
    """Patch this publish onto the vault copy so a lane manifest cannot replace the corpus."""
    from private_dashboard_assets import private_object
    from reconcile_insights_event_summary import (
        apply_media_fields, is_publishable_manifest, reconciled_manifest,
    )
    from vault_paths import research_vault_root

    base = None
    vault = research_vault_root()
    if vault is not None:
        private = private_object(vault, entry["private_sha256"])
        if private.is_file():
            loaded = _read_json(private)
            if is_publishable_manifest(loaded):
                base = loaded
    merged = document if base is None else apply_media_fields(
        base, document, videos=videos, podcasts=podcasts)
    events = _events_beside(repo / "dashboard" / relative)
    if events is not None:
        merged = reconciled_manifest(merged, events)
    if not is_publishable_manifest(merged):
        raise RuntimeError(f"refusing to publish onto a stub insight manifest at {relative}")
    return merged


def _restore_recorded_placeholder(path: Path, document: dict, entry: dict) -> None:
    """Put back the receipt's public bytes when the working file is the private object."""
    import hashlib

    from migrate_dashboard_sources import public_snapshot

    public_text = _canonical_json(public_snapshot(document))
    if hashlib.sha256(public_text.encode("utf-8")).hexdigest() != entry["public_sha256"]:
        raise RuntimeError(
            "Managed dashboard asset changed; export its private snapshot before deployment: "
            + path.as_posix()
        )
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(public_text, encoding="utf-8")
    temporary.replace(path)


def seal_insights_manifest(path: Path, *, videos: bool, podcasts: bool) -> bool:
    """Export a managed insights manifest and leave the public file as its placeholder.

    Returns True when a new private object has to be pushed before the public commit.
    An unmanaged manifest is left as written. The Mac Mini media lane commits this
    file in place on main; the off-main worktree path already sealed it.
    """
    managed = _managed_manifest(path)
    if managed is None or not path.is_file():
        return False
    repo, relative, entry = managed
    from private_dashboard_assets import digest

    current = digest(path)
    if current == entry["public_sha256"]:
        return False
    document = _read_json(path)
    if document.get("private_snapshot") is True or current == entry["private_sha256"]:
        if current == entry["private_sha256"] and document.get("private_snapshot") is not True:
            _restore_recorded_placeholder(path, document, entry)
            return False
        raise RuntimeError(
            "Managed dashboard asset changed; export its private snapshot before deployment: "
            + relative
        )
    merged = _merged_published_manifest(
        repo, relative, entry, document, videos=videos, podcasts=podcasts)
    _export_managed_document(repo, relative, merged)
    return True


def _seal_managed_payload(path: Path) -> bool:
    """Keep a managed episode or shard file out of the public commit.

    A working copy that still is the recorded private object is put back to its
    placeholder. A new payload is exported. Returns True when the vault must be pushed.
    """
    managed = _managed_manifest(path)
    if managed is None or not path.is_file():
        return False
    repo, relative, entry = managed
    from private_dashboard_assets import digest

    current = digest(path)
    if current == entry["public_sha256"]:
        return False
    document = _read_json(path)
    if not document:
        raise RuntimeError(
            "Managed dashboard asset changed; export its private snapshot before deployment: "
            + relative
        )
    if current == entry["private_sha256"] and document.get("private_snapshot") is not True:
        _restore_recorded_placeholder(path, document, entry)
        return False
    if document.get("private_snapshot") is True:
        raise RuntimeError(
            "Managed dashboard asset changed; export its private snapshot before deployment: "
            + relative
        )
    _export_managed_document(repo, relative, document)
    return True


def _managed_relative_paths(repo: Path) -> set[str]:
    receipt = repo / "dashboard" / "private-assets.json"
    if not receipt.is_file():
        return set()
    try:
        document = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    assets = document.get("assets") if isinstance(document, dict) else None
    return set(assets) if isinstance(assets, dict) else set()


def _vault_dashboard_private_dirty() -> bool:
    from vault_paths import research_vault_root

    vault = research_vault_root()
    if vault is None or not (vault / ".git").exists():
        return False
    status = run_git(vault, "status", "--porcelain", "--", "dashboard-private",
                     check=False, timeout=120)
    return bool(status.stdout.strip())


def _receipt_dirty(repo: Path) -> bool:
    rel = "dashboard/private-assets.json"
    if not (repo / rel).is_file():
        return False
    diff = run_git(repo, "diff", "--quiet", "HEAD", "--", rel, check=False, timeout=60)
    return diff.returncode != 0


def _seal_in_place_publish(repo: Path, paths: tuple[str, ...], dirs: tuple[str, ...],
                           *, videos: bool, podcasts: bool) -> None:
    """Seal managed files on a main checkout before they are staged.

    The Mac Mini lane (metis@Drews-Mac-mini.local) is a checkout of main, so
    push_main commits this worktree directly. The private-snapshot export added
    for the off-main worktree never ran, and the full insights manifest was
    pushed over its placeholder (ed7a50a16bb and the publishes after it).
    """
    receipt = repo / "dashboard" / "private-assets.json"
    if not receipt.is_file():
        # Materialize from HEAD when this checkout is sparse. A repository
        # that has never managed dashboard files must not touch a vault.
        _managed_manifest(repo / INSIGHT_MANIFEST)
    if not receipt.is_file():
        return
    exported = False
    manifest = repo / INSIGHT_MANIFEST
    if INSIGHT_MANIFEST in paths and manifest.is_file():
        exported = seal_insights_manifest(manifest, videos=videos, podcasts=podcasts) or exported
    for rel in paths:
        if rel == INSIGHT_MANIFEST:
            continue
        path = repo / rel
        if path.is_file():
            exported = _seal_managed_payload(path) or exported
    managed_keys = _managed_relative_paths(repo)
    for rel in dirs:
        root = repo / rel
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                relative = path.relative_to(repo / "dashboard").as_posix()
            except ValueError:
                continue
            if relative not in managed_keys:
                continue
            exported = _seal_managed_payload(path) or exported
    if exported or _vault_dashboard_private_dirty():
        preserved = _push_private_dashboard_objects(
            "Preserve restricted insights manifest snapshot")
        if preserved is False:
            raise RuntimeError(
                "Private snapshot was not pushed; refusing to publish the public insights manifest"
            )


def _republish_managed_manifest(path: Path, document: dict) -> None:
    """Write a manifest. A managed asset is exported privately and the public file stays a placeholder."""
    managed = _managed_manifest(path)
    text = json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if managed is None:
        path.write_text(text, encoding="utf-8")
        return
    root, relative, entry = managed
    from migrate_dashboard_sources import migrate
    from private_dashboard_assets import hydration_state, write_hydration

    state = hydration_state(root)
    state["dashboard/" + relative] = entry["private_sha256"]
    write_hydration(root, state)
    path.write_text(text, encoding="utf-8")
    migrate(root, paths=["dashboard/" + relative])
    published = _read_json(path)
    if published.get("private_snapshot") is not True:
        raise RuntimeError(f"Managed dashboard asset was published in full: {relative}")


def _sync_insight_manifest(src: Path, dst: Path, *, videos: bool, podcasts: bool) -> None:
    """Patch this lane's media fields onto the manifest that already matches events.

    The lane worktree keeps its own manifest for hours. Copying that file
    onto origin/main put a retained_event_count of 1539 next to an events
    shard of 1530. The destination events list is the one this commit leaves
    in place, so the count is derived from it.

    The public file is a managed private snapshot. Patching it in place and
    committing the result published the full feed (08cf14351, de15a0e1d,
    de5b8ff43). The updated document is stored as the vault object and the
    public path is left as the metadata placeholder.
    """
    from reconcile_insights_event_summary import apply_media_fields, reconciled_manifest

    destination = _resolved_manifest(dst)
    merged = apply_media_fields(destination, _read_json(src), videos=videos, podcasts=podcasts)
    events = _events_beside(dst)
    if not isinstance(events, list):
        raise RuntimeError(f"insight events shard missing beside {dst}")
    _republish_managed_manifest(dst, reconciled_manifest(merged, events))


def _sync_published(src: Path, dst: Path, paths: tuple[str, ...] = MAIN_PATHS,
                    dirs: tuple[str, ...] = MAIN_DIRS) -> None:
    videos = "dashboard/data/insights/videos.json" in paths
    podcasts = "dashboard/data/insights/podcasts.json" in paths
    for rel in (*paths, *dirs):
        source = src / rel
        target = dst / rel
        if rel == INSIGHT_MANIFEST:
            _sync_insight_manifest(source, target, videos=videos, podcasts=podcasts)
            continue
        if source.is_dir():
            _sync_directory(source, target, dst)
            continue
        if source.is_file() and _managed_manifest(target) is not None:
            # A managed public file stays the placeholder. Copying the lane's
            # full document is how podcast episode shards landed in the public repo.
            continue
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def _sync_directory(source: Path, target: Path, repo: Path) -> None:
    """Copy a shard directory without replacing managed public placeholders."""
    target.mkdir(parents=True, exist_ok=True)
    incoming = {path.relative_to(source).as_posix() for path in source.rglob("*") if path.is_file()}
    for existing in list(target.rglob("*")):
        if not existing.is_file():
            continue
        child = existing.relative_to(target).as_posix()
        if child in incoming:
            continue
        if _managed_manifest(existing) is not None:
            continue
        existing.unlink()
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        dest = target / path.relative_to(source)
        if _managed_manifest(dest) is not None:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)


def _push_private_dashboard_objects(message: str) -> bool | None:
    """Commit dashboard-private objects before the public receipt that names them."""
    from vault_paths import research_vault_root

    repo = research_vault_root()
    if repo is None or not (repo / ".git").exists():
        log("vault: no checkout; cannot preserve the insight manifest")
        return False
    try:
        with vault_lock(repo, owner="youtube_lane", log=lambda m: log(m.strip())):
            clear_stale_git_state(repo, log=lambda m: log(m.strip()))
            run_git(repo, "add", "-A", "--", "dashboard-private", timeout=300)
            staged = run_git(repo, "diff", "--cached", "--quiet", "--", "dashboard-private",
                             check=False, timeout=120)
            if staged.returncode == 0:
                return None
            run_git(repo, "commit", "-m", message, timeout=300)
            run_git(repo, "-c", "rebase.autoStash=true", "pull", "--rebase",
                    "origin", "main", timeout=900)
            run_git(repo, "push", "origin", "HEAD:main", timeout=600)
            log("vault: preserved dashboard snapshot")
            return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        log(f"vault snapshot push failed: {describe_failure(exc)}")
        try:
            run_git(repo, "rebase", "--abort", check=False, timeout=120)
            clear_stale_git_state(repo, log=lambda m: log(m.strip()))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as undo:
            log(f"vault unwind failed: {describe_failure(undo)}")
        return False


def _push_published_apart(message: str, paths: tuple[str, ...] = MAIN_PATHS,
                          dirs: tuple[str, ...] = MAIN_DIRS) -> bool | None:
    """Commit the shard on a main checkout and push that, not the lane HEAD."""
    repo = _ensure_publish_worktree()
    _sync_published(ROOT, repo, paths, dirs)
    if INSIGHT_MANIFEST in paths:
        preserved = _push_private_dashboard_objects(
            "Preserve restricted insights manifest snapshot")
        if preserved is False:
            return False
    present = [p for p in paths if (repo / p).is_file()]
    receipt = "dashboard/private-assets.json"
    if INSIGHT_MANIFEST in paths and (repo / receipt).is_file():
        present.append(receipt)
    if present:
        run_git(repo, "add", "--sparse", "--", *present, timeout=300)
    # Always stage the shard directory, including when the sync removed it.
    # Gating on the directory still existing left a deleted corpus in the index.
    for rel in dirs:
        run_git(repo, "add", "--sparse", "-A", rel, timeout=300)
    staged = run_git(repo, "diff", "--cached", "--quiet", check=False, timeout=120)
    if staged.returncode == 0:
        log("main: nothing to commit")
        return None
    run_git(repo, "commit", "-m", message, timeout=300)
    run_git(repo, "-c", "rebase.autoStash=true", "pull", "--rebase",
            "origin", MAIN_BRANCH, timeout=900)
    run_git(repo, "push", "origin", f"HEAD:{MAIN_BRANCH}", timeout=600)
    log("main: pushed")
    return True


def push_main(message: str, paths: tuple[str, ...] = MAIN_PATHS,
              dirs: tuple[str, ...] = MAIN_DIRS) -> bool | None:
    """Commit the published video shard to this repository's main.

    True on a completed push, None when there was nothing to push, False when
    the push was attempted and failed. The caller needs all three: returning a
    bare False for both "nothing to commit" and "the rebase blew up" is what let
    a failed push exit 0.
    """
    try:
        # Detached at origin/main (the lane worktree's normal state) reports no
        # branch and publishes in place. A *named* branch that is not main is
        # not: on 2026-09-24 and -25 this worktree sat on
        # wip/youtube-video-details, where a commit to HEAD and a push of `main`
        # were two unrelated things, and two days of work went nowhere while
        # the vault push succeeded and the lane logged green.
        head = run_git(ROOT, "symbolic-ref", "-q", "--short", "HEAD",
                       check=False, timeout=120)
        branch = head.stdout.strip() if head.returncode == 0 else ""
        if branch and branch != MAIN_BRANCH:
            log(f"main: worktree is on '{branch}', not '{MAIN_BRANCH}' or detached; "
                "refusing to publish from a branch this lane does not track")
            return False
        present = [p for p in paths if (ROOT / p).is_file()]
        present_dirs = [d for d in dirs if (ROOT / d).is_dir()]
        if not present and not present_dirs:
            log("main: no published shard to commit")
            return None
        # Detached is fine only when it is origin/main. A detached media-lane
        # commit is not: pull --rebase would replay it and HEAD:main would
        # publish it. The shard still has to reach main, so it is committed on
        # a checkout that starts there.
        if not _head_is_origin_main():
            log("main: checkout is not origin/main; publishing the shard from "
                "a main worktree so local commits stay local")
            return _push_published_apart(message, paths, dirs)
        videos = "dashboard/data/insights/videos.json" in paths
        podcasts = "dashboard/data/insights/podcasts.json" in paths
        try:
            _seal_in_place_publish(ROOT, paths, dirs, videos=videos, podcasts=podcasts)
        except RuntimeError as exc:
            log(f"main: {exc}")
            return False
        present = [p for p in paths if (ROOT / p).is_file()]
        if _receipt_dirty(ROOT):
            present.append("dashboard/private-assets.json")
        if present:
            run_git(ROOT, "add", "--sparse", *present, timeout=300)
        for rel in present_dirs:
            # -A so a shard that disappeared from the corpus is staged as a
            # deletion; without it the index keeps advertising a dead video.
            run_git(ROOT, "add", "--sparse", "-A", rel, timeout=300)
        staged = run_git(ROOT, "diff", "--cached", "--quiet", check=False, timeout=120)
        if staged.returncode == 0:
            log("main: nothing to commit")
            return None
        run_git(ROOT, "commit", "-m", message, timeout=300)
        run_git(ROOT, "-c", "rebase.autoStash=true", "pull", "--rebase",
                "origin", MAIN_BRANCH, timeout=900)
        # HEAD:main, not main. The bare refspec pushes the local branch of that
        # name, which on a detached or renamed checkout is not the commit this
        # run just made.
        run_git(ROOT, "push", "origin", f"HEAD:{MAIN_BRANCH}", timeout=600)
        log("main: pushed")
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        log(f"main push failed: {describe_failure(exc)}")
        run_git(ROOT, "rebase", "--abort", check=False, timeout=120)
        apart = _publish_worktree()
        if (apart / ".git").exists():
            run_git(apart, "rebase", "--abort", check=False, timeout=120)
        return False


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--hours", type=float, default=1.0,
                   help="Caption daemon window. Pacing is 150s between fetches "
                        "and 20/hour, so this is mostly a wait (default %(default)s).")
    p.add_argument("--whisper", type=int, default=0,
                   help="Videos to route through local Whisper. 0 queues them "
                        "and transcribes none, which is the default because "
                        "this host is already memory-bound.")
    p.add_argument("--no-push", action="store_true", help="Run, commit nothing.")
    p.add_argument("--no-update", action="store_true", help="Skip the worktree pull.")
    args = p.parse_args()

    scripts = ROOT / "_system" / "scripts"
    keys = load_env_file(ROOT / "_secrets" / "youtube.env")
    if not os.environ.get("YOUTUBE_API_KEY"):
        log("YOUTUBE_API_KEY is not set; discovery cannot run")
        return 2
    log(f"loaded {keys} key(s) from _secrets/youtube.env")
    log(f"vault -> {videos_root()}")

    if not args.no_update and self_update() is True:
        log("re-executing so this run uses the publisher it just pulled")
        os.execv(sys.executable, [sys.executable, *sys.argv])

    # Discovery is cheap (playlistItems at 1 unit per 50 videos against a
    # 10,000/day free tier) but it is also the only stage that can add work.
    # If it fails there is nothing new to fetch, so the rest still runs against
    # whatever the backlog already holds.
    step("discover", [str(scripts / "discover_videos.py")], required=False)
    # --hours is passed as well as enforced: the daemon uses it to stop cleanly
    # at a pass boundary when it can, and the wall-clock budget catches the case
    # where a single pass outlives the window. A small margin so the clean exit
    # wins whenever it is available.
    step("captions", [str(scripts / "fetch_video_transcript.py"),
                      "--daemon", "--hours", str(args.hours)],
         required=False, timeout=args.hours * 3600 + 300)

    whisper_args = [str(scripts / "video_whisper_backfill.py")]
    whisper_args += ["--queue-only"] if args.whisper <= 0 else ["--batch", str(args.whisper)]
    step("whisper", whisper_args, required=False)

    # Relevance is decided on the transcript, never on metadata, so scoring has
    # to follow the fetch rather than gate it.
    step("score", [str(scripts / "score_video_relevance.py")], required=False)
    if not step("build", [str(scripts / "build_video_insights.py")], required=True):
        return 1

    vault_pushed = None
    if not args.no_push:
        vault_pushed = push_vault(f"chore(videos): transcript refresh {stamp()}")

    # The shard is what the dashboard actually reads. A stage that writes must
    # name its reader, so publishing runs even under --no-push: skipping it
    # there would make a dry run silently stop one stage short of the thing
    # most likely to break, which is the whole reason to have a dry run.
    # Ordered after the vault commit so a failed publish cannot leave the
    # corpus uncommitted.
    published = step("publish", [str(scripts / "publish_video_dashboard.py")], required=True)
    if args.no_push:
        log("--no-push: ran the chain, committed nothing")
        return 0 if published else 1
    code = 0 if published else 1
    if published:
        # A failed push must reach the exit code. On 2026-09-08 the vault push
        # succeeded, `git pull --rebase origin main` exited 1, and the lane still
        # returned 0 -- so the scheduled task recorded LastResult=0 and the only
        # trace was a line in the log nobody reads. The content survived because
        # the vault is the source CI reads, but the run reported success while
        # half of its publish path had failed.
        if push_main(f"chore(videos): publish admitted research {stamp()}") is False:
            log("main push failed; exiting non-zero so the scheduler sees it")
            code = 1
    # The vault push is judged here rather than where it failed, so a vault
    # failure never costs the dashboard its publish. From 2026-09-21 to 09-23
    # four untracked letters in the vault blocked every `pull --rebase`, each
    # run logged "vault push failed" and exited 0, and the task read green
    # while three days of corpus commits sat unpushed on this disk.
    if vault_pushed is False:
        log("vault push failed earlier in this run; exiting non-zero so the scheduler sees it")
        code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
