"""Rebuild derived manifest counts from the canonical committed event shard.

Media-only publishers can carry an older manifest while preserving the current
event shard. Reconcile metadata before strict validation; never alter events,
raw intake counts, classifications or evidence.

The count is always taken from the events list that ships with the manifest.
A publisher may patch its own source-health fields onto that manifest. It may
not replace the manifest with a stub, and it may not keep a retained-event
count from a different events list.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
INSIGHTS_REL = "dashboard/data/insights"


def reconciled_manifest(manifest: dict, events: list[dict]) -> dict:
    if not isinstance(manifest, dict) or not isinstance(events, list):
        raise ValueError("Manifest must be an object and events must be a list")
    if any(not isinstance(event, dict) for event in events):
        raise ValueError("Each retained event must be an object")
    result = copy.deepcopy(manifest)
    summary = result.setdefault("provenance", {}).setdefault("event_triage_summary", {})
    dates = sorted(e["observed_at"] for e in events if e.get("observed_at"))
    # Keep the same retained-feed definitions as build_insights.finalize_events.
    summary.update({
        "signal": sum(e.get("tier") == "signal" and bool(e.get("feed_eligible")) for e in events),
        "context": sum(e.get("tier") == "context" and bool(e.get("feed_eligible")) for e in events),
        "noise": sum(e.get("tier") == "noise" or not e.get("feed_eligible") for e in events),
        "human_review": sum(e.get("triage_verdict") == "human_review" for e in events),
        "scheduled": sum(e.get("event_kind") == "scheduled" for e in events),
        "missing_evidence": sum(e.get("evidence_status") == "missing" for e in events),
        "retained_event_count": len(events),
        "history_start": dates[0] if dates else None,
        "history_end": dates[-1] if dates else None,
    })
    result["event_count"] = len(events)
    return result


def is_publishable_manifest(doc: object) -> bool:
    """A manifest the dashboard can load: source health plus an event summary.

    The 2026-10-19 download sync committed a 368-byte file with only
    ``generated_at`` and ``shards``. That file is not a manifest.
    """
    if not isinstance(doc, dict):
        return False
    health = doc.get("source_health")
    provenance = doc.get("provenance")
    if not isinstance(health, dict) or not health:
        return False
    if not isinstance(provenance, dict):
        return False
    return isinstance(provenance.get("event_triage_summary"), dict)


def _manifest_score(doc: object) -> tuple[int, int, int, int]:
    if not isinstance(doc, dict):
        return (-1, -1, -1, -1)
    health = doc.get("source_health")
    health_n = len(health) if isinstance(health, dict) else 0
    try:
        letters = int(doc.get("letter_count") or 0)
    except (TypeError, ValueError):
        letters = 0
    return (1 if is_publishable_manifest(doc) else 0, letters, health_n, len(doc))


def richer_manifest(left: dict | None, right: dict | None) -> dict | None:
    """Prefer the copy that still has source health and the letter corpus."""
    if _manifest_score(left) >= _manifest_score(right):
        return copy.deepcopy(left) if isinstance(left, dict) else None
    return copy.deepcopy(right) if isinstance(right, dict) else None


def _content_score(doc: object, keys: tuple[str, ...]) -> int:
    if not isinstance(doc, dict):
        return -1
    total = 0
    for key in keys:
        value = doc.get(key)
        if isinstance(value, (list, dict)):
            total += len(value)
        elif value not in (None, "", [], {}):
            total += 1
    return total


def richer_content_shard(upstream: dict | None, replayed: dict | None, keys: tuple[str, ...]) -> dict | None:
    """Keep the shard that still holds rows. Ties stay with the upstream copy."""
    if _content_score(upstream, keys) >= _content_score(replayed, keys) and isinstance(upstream, dict):
        return copy.deepcopy(upstream)
    if isinstance(replayed, dict):
        return copy.deepcopy(replayed)
    return None


def apply_media_fields(destination: dict, source: dict | None, *, videos: bool, podcasts: bool) -> dict:
    """Copy only the fields a media publisher owns onto the manifest that ships.

    Event counts, the letter corpus and every other source's health stay on
    ``destination``. Those belong to the events shard and the intake rebuild,
    not to a video or podcast worktree that may be hours behind.
    """
    if not isinstance(destination, dict):
        raise ValueError("destination manifest must be an object")
    result = copy.deepcopy(destination)
    if not isinstance(source, dict):
        return result
    health = source.get("source_health") if isinstance(source.get("source_health"), dict) else {}
    shards = source.get("shards") if isinstance(source.get("shards"), dict) else {}
    if videos:
        if "videos" in health:
            result.setdefault("source_health", {})["videos"] = copy.deepcopy(health["videos"])
        for key in ("video_count", "video_status_counts", "video_newest_published"):
            if key in source:
                result[key] = copy.deepcopy(source[key])
        for key in ("videos", "video_details"):
            if key in shards:
                result.setdefault("shards", {})[key] = shards[key]
    if podcasts:
        if "podcasts" in health:
            result.setdefault("source_health", {})["podcasts"] = copy.deepcopy(health["podcasts"])
        for key in ("podcasts", "podcast_episodes"):
            if key in shards:
                result.setdefault("shards", {})[key] = shards[key]
    return result


def prepare_published_manifest(base: dict, events: list, mutate) -> dict:
    """Patch one publisher's fields, then derive counts from ``events``.

    ``mutate`` receives a copy of ``base`` and may edit only that copy.
    """
    if not is_publishable_manifest(base):
        raise ValueError("refusing to publish from a stub insight manifest")
    if not isinstance(events, list) or any(not isinstance(event, dict) for event in events):
        raise ValueError("events shard must be a list of objects")
    updated = copy.deepcopy(base)
    mutate(updated)
    updated = reconciled_manifest(updated, events)
    if not is_publishable_manifest(updated):
        raise ValueError("refusing to write a stub insight manifest")
    return updated


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    return value if isinstance(value, dict) else None


def _git_show_json(root: Path, spec: str) -> dict | None:
    result = subprocess.run(
        ["git", "show", spec],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _dump(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"


def resolve_rebase_conflicts(root: Path | None = None) -> int:
    """Resolve conflicted insight shards without rebuilding them from nothing.

    ``build_dashboard_data`` re-shards whatever is on disk. Deleting a
    conflicted manifest and calling it a regeneration is how the daily
    download sync replaced the manifest with a 368-byte stub and nulled the
    podcast shard. Keep the side that still has rows, then set the retained
    event count from the events list that remains.
    """
    root = root or ROOT
    listed = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if listed.returncode != 0:
        raise RuntimeError(listed.stderr.strip() or "git diff failed")
    conflicted = [
        line.strip()
        for line in listed.stdout.splitlines()
        if line.strip().startswith(f"{INSIGHTS_REL}/")
    ]
    if not conflicted:
        return 0

    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from build_dashboard_shards import INSIGHTS_SHARDS

    def stages(rel: str) -> tuple[dict | None, dict | None]:
        return _git_show_json(root, f":2:{rel}"), _git_show_json(root, f":3:{rel}")

    resolved: list[str] = []
    for rel in conflicted:
        if rel.endswith("/manifest.json"):
            continue
        name = Path(rel).name
        stem = name[:-5] if name.endswith(".json") else name
        keys = tuple(INSIGHTS_SHARDS.get(stem, ()))
        upstream, replayed = stages(rel)
        chosen = richer_content_shard(upstream, replayed, keys or ("generated_at",))
        if chosen is None:
            raise ValueError(f"no usable side for conflicted {rel}")
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_dump(chosen), encoding="utf-8")
        resolved.append(rel)

    manifest_rel = f"{INSIGHTS_REL}/manifest.json"
    if manifest_rel in conflicted:
        upstream, replayed = stages(manifest_rel)
        chosen = richer_manifest(upstream, replayed)
        if not is_publishable_manifest(chosen):
            raise ValueError("conflicted insight manifest has no publishable side")
        events_doc = _read_json(root / INSIGHTS_REL / "events.json")
        events = events_doc.get("events") if isinstance(events_doc, dict) else None
        if not isinstance(events, list):
            raise ValueError("cannot derive retained_event_count without an events list")
        chosen = reconciled_manifest(chosen, events)
        path = root / manifest_rel
        path.write_text(_dump(chosen), encoding="utf-8")
        resolved.append(manifest_rel)

    if resolved:
        subprocess.run(["git", "add", "--", *resolved], cwd=root, check=True)
    return len(resolved)


def reconcile(data_dir: Path) -> bool:
    path = data_dir / "insights/manifest.json"
    original = json.loads(path.read_text(encoding="utf-8"))
    shard = json.loads((data_dir / "insights/events.json").read_text(encoding="utf-8"))
    updated = reconciled_manifest(original, shard.get("events"))
    if updated == original:
        return False
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as out:
        json.dump(updated, out, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        out.write("\n")
        temporary = Path(out.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "dashboard/data")
    parser.add_argument(
        "--resolve-rebase-conflicts",
        action="store_true",
        help="Resolve conflicted dashboard/data/insights shards during a rebase.",
    )
    args = parser.parse_args()
    if args.resolve_rebase_conflicts:
        count = resolve_rebase_conflicts(ROOT)
        print(f"Resolved {count} insight shard conflict(s)" if count else "No insight shard conflicts")
        return
    changed = reconcile(args.data_dir)
    print("Reconciled event summary from retained events" if changed else "Event summary already consistent")


if __name__ == "__main__":
    main()
