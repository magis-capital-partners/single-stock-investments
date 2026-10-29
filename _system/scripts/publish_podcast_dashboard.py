#!/usr/bin/env python3
"""Publish the podcast catalog shard without rebuilding unrelated feeds.

The analysis and reader-summary batches commit the vault.  This is the step
that turns those metas into the files the dashboard actually loads, and pushes
only those files from a checkout of origin/main.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import build_podcast_insights as bpi
import youtube_lane
from build_insights import podcast_by_show
from reconcile_insights_event_summary import prepare_published_manifest

ROOT = Path(__file__).resolve().parents[2]
INSIGHTS_DIR = ROOT / "dashboard" / "data" / "insights"
MANIFEST_PATH = INSIGHTS_DIR / "manifest.json"
SHARD_PATH = INSIGHTS_DIR / "podcasts.json"


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_json(path: Path, value: dict, *, compact: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        if compact
        else json.dumps(value, indent=2, ensure_ascii=False)
    ) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _manifest() -> dict:
    """The manifest on this checkout, or the one already on the publish worktree.

    A podcast publish rewrites manifest.json. Starting from an empty file would
    drop every other shard the site loads. A public placeholder is read from
    the vault so the rewrite is not applied to the metadata stub.
    """
    if MANIFEST_PATH.is_file():
        try:
            manifest = youtube_lane._resolved_manifest(MANIFEST_PATH)
        except RuntimeError:
            manifest = load_json(MANIFEST_PATH)
        if len((manifest.get("shards") or {})) >= 3:
            return manifest
    manifest = load_json(MANIFEST_PATH)
    if len((manifest.get("shards") or {})) >= 3:
        return manifest
    publish_worktree = getattr(youtube_lane, "_publish_worktree", None)
    if publish_worktree is not None:
        alt = publish_worktree() / "dashboard" / "data" / "insights" / "manifest.json"
        other = load_json(alt)
        if len((other.get("shards") or {})) >= 3:
            return other
    return manifest


def publish() -> dict:
    payload = bpi.build()
    rows = [bpi.index_row_from_episode(ep) for ep in (payload.get("episodes") or [])]
    shard = {
        "generated_at": payload.get("generated_at"),
        "episode_count": payload.get("episode_count", 0),
        "podcast_index": rows,
        "podcast_by_show": podcast_by_show(payload),
    }
    write_json(SHARD_PATH, shard)

    analysed = sum(1 for row in rows if row.get("has_analysis"))
    claims = sum(int(row.get("claim_count") or 0) for row in rows)
    with_summary = sum(1 for row in rows if (row.get("summary_preview") or "").strip())
    transcript_ready = sum(
        1
        for ep in payload.get("episodes") or []
        if isinstance(ep.get("reader_summary"), dict)
        and ep["reader_summary"].get("status") == "ready"
        and ep["reader_summary"].get("source_basis") == "transcript"
    )
    with_reader_summary = sum(
        1
        for ep in payload.get("episodes") or []
        if isinstance(ep.get("reader_summary"), dict)
        and (ep["reader_summary"].get("overview") or "").strip()
        )

    def mutate(manifest: dict) -> None:
        manifest.setdefault("shards", {})["podcasts"] = "data/insights/podcasts.json"
        manifest["shards"]["podcast_episodes"] = "data/insights/podcast_episodes/"
        health = manifest.setdefault("source_health", {})
        health["podcasts"] = {
            "status": "ok" if rows else "empty",
            "items": len(rows),
            "episode_count": len(rows),
            "transcript_count": payload.get("transcript_count"),
            "whisper_pending": payload.get("whisper_pending"),
            "generated_at": payload.get("generated_at"),
            "with_analysis": analysed,
            "with_reader_summary": with_reader_summary,
            "transcript_ready": transcript_ready,
            "claims": claims,
            "detail_shards": payload.get("episode_detail_shards", 0),
            "path": "_system/reference/podcasts/insights_index_mirror.json",
        }

    events = youtube_lane._events_beside(MANIFEST_PATH)
    try:
        manifest = prepare_published_manifest(_manifest(), events, mutate)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    write_json(MANIFEST_PATH, manifest)
    try:
        youtube_lane.seal_insights_manifest(MANIFEST_PATH, videos=False, podcasts=True)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    return {
        "episode_count": len(rows),
        "with_analysis": analysed,
        "with_reader_summary": with_reader_summary,
        "transcript_ready": transcript_ready,
        "with_summary_preview": with_summary,
        "claims": claims,
        "detail_shards": payload.get("episode_detail_shards", 0),
        "generated_at": payload.get("generated_at"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--push", action="store_true",
                        help="Commit the shard on origin/main and push it.")
    args = parser.parse_args()
    if args.push and youtube_lane.self_update() is True:
        print("re-executing so this publish uses the publisher it just pulled")
        os.execv(sys.executable, [sys.executable, *sys.argv])
    result = publish()
    print(
        f"podcast dashboard: {result['episode_count']} episodes, "
        f"{result['detail_shards']} detail shards, "
        f"{result['with_reader_summary']} reader summaries "
        f"({result['transcript_ready']} transcript-ready), "
        f"{result['with_analysis']} analysed, {result['claims']} claims"
    )
    if args.push and not result["episode_count"]:
        print("refusing to push an empty podcast catalog")
        return 1
    if args.push:
        push_main = youtube_lane.push_main
        try:
            pushed = push_main(
                f"chore(podcasts): publish analysed episodes {youtube_lane.stamp()}",
                paths=youtube_lane.PODCAST_PATHS,
                dirs=youtube_lane.PODCAST_DIRS,
            )
        except (AttributeError, TypeError) as exc:
            print(f"podcast publish requires the generalised youtube_lane.push_main: {exc}")
            return 1
        if pushed is False:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
