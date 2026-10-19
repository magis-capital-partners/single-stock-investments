#!/usr/bin/env python3
"""Audit reader-summary coverage from vault meta to the published dashboard.

A summary in ``*.meta.json`` is not a published summary.  This checker walks
meta -> vault catalog -> dashboard podcast index -> per-episode shards and
reports where coverage stops.  It is intentionally structural: it does not
re-read every transcript, so it can run in a refresh without becoming another
analysis pass.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from summarize_podcast_episode import reader_summary_errors  # noqa: E402
from vault_paths import podcasts_root  # noqa: E402


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _count(counter: dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1


def audit() -> dict:
    vault = podcasts_root(create=False)
    meta_by_id: dict[str, dict] = {}
    meta_status: dict[str, int] = {}
    meta_basis: dict[str, int] = {}
    meta_errors: dict[str, list[str]] = {}
    if vault:
        for path in (vault / "episodes").rglob("*.meta.json"):
            doc = load_json(path)
            eid = str(doc.get("episode_id") or path.name.replace(".meta.json", ""))
            if not eid:
                continue
            summary = doc.get("reader_summary") if isinstance(doc.get("reader_summary"), dict) else {}
            meta_by_id[eid] = summary
            _count(meta_status, str(summary.get("status") or "missing"))
            _count(meta_basis, str(summary.get("source_basis") or "missing"))
            errors = reader_summary_errors(summary) if summary else ["missing reader_summary"]
            if errors:
                meta_errors[eid] = errors[:6]

    catalog = load_json(vault / "insights.json") if vault else {}
    catalog_by_id: dict[str, dict] = {}
    for ep in catalog.get("episodes") or []:
        if isinstance(ep, dict) and ep.get("episode_id"):
            catalog_by_id[str(ep["episode_id"])] = (
                ep.get("reader_summary") if isinstance(ep.get("reader_summary"), dict) else {}
            )

    dashboard_path = ROOT / "dashboard" / "data" / "insights" / "podcasts.json"
    dashboard = load_json(dashboard_path)
    index_by_id: dict[str, dict] = {}
    for row in dashboard.get("podcast_index") or []:
        if isinstance(row, dict) and row.get("episode_id"):
            index_by_id[str(row["episode_id"])] = row

    shard_dir = ROOT / "dashboard" / "data" / "insights" / "podcast_episodes"
    shard_by_id: dict[str, dict] = {}
    if shard_dir.is_dir():
        for path in shard_dir.glob("*.json"):
            doc = load_json(path)
            eid = str(doc.get("episode_id") or path.stem)
            if eid:
                shard_by_id[eid] = (
                    doc.get("reader_summary") if isinstance(doc.get("reader_summary"), dict) else {}
                )

    all_ids = set(meta_by_id) | set(catalog_by_id) | set(index_by_id) | set(shard_by_id)

    def missing_from(source: dict[str, dict]) -> list[str]:
        return sorted(eid for eid in all_ids if not source.get(eid))

    published_missing = sorted(
        eid
        for eid in all_ids
        if not (index_by_id.get(eid) or {}).get("summary_preview")
        or not (index_by_id.get(eid) or {}).get("summary_source_label")
        or not shard_by_id.get(eid)
    )
    transcript_ready = sum(
        1
        for summary in meta_by_id.values()
        if summary.get("status") == "ready" and summary.get("source_basis") == "transcript"
    )
    transcript_total = sum(
        1
        for eid, summary in meta_by_id.items()
        if summary.get("source_basis") == "transcript" or (index_by_id.get(eid) or {}).get("transcript_source")
    )

    return {
        "episodes": len(all_ids),
        "meta": {
            "with_reader_summary": sum(1 for s in meta_by_id.values() if s),
            "missing": missing_from(meta_by_id)[:20],
            "missing_count": len(missing_from(meta_by_id)),
            "by_status": meta_status,
            "by_basis": meta_basis,
            "invalid_count": len(meta_errors),
            "invalid_samples": {k: meta_errors[k] for k in list(meta_errors)[:10]},
            "transcript_ready": transcript_ready,
        },
        "catalog": {
            "with_reader_summary": sum(1 for s in catalog_by_id.values() if s),
            "missing_count": len(missing_from(catalog_by_id)),
            "missing": missing_from(catalog_by_id)[:20],
        },
        "dashboard_index": {
            "rows": len(index_by_id),
            "with_summary_preview": sum(
                1 for row in index_by_id.values() if (row.get("summary_preview") or "").strip()
            ),
            "with_source_label": sum(
                1 for row in index_by_id.values() if (row.get("summary_source_label") or "").strip()
            ),
            "missing_count": sum(
                1
                for row in index_by_id.values()
                if not (row.get("summary_preview") or "").strip()
                or not (row.get("summary_source_label") or "").strip()
            ),
        },
        "episode_shards": {
            "files": len(shard_by_id),
            "with_reader_summary": sum(1 for s in shard_by_id.values() if s),
            "missing_count": len(missing_from(shard_by_id)),
            "missing": missing_from(shard_by_id)[:20],
        },
        "published_missing_count": len(published_missing),
        "published_missing": published_missing[:20],
        "transcript_catalogued": transcript_total,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--require-published",
        action="store_true",
        help="Fail when any published index row or episode shard lacks a reader summary",
    )
    parser.add_argument(
        "--require-meta",
        action="store_true",
        help="Fail when any vault episode lacks a structurally valid reader summary",
    )
    args = parser.parse_args()

    report = audit()
    problems: list[str] = []
    if args.require_meta:
        if report["meta"]["missing_count"]:
            problems.append(f"{report['meta']['missing_count']} vault episodes lack reader_summary")
        if report["meta"]["invalid_count"]:
            problems.append(f"{report['meta']['invalid_count']} reader summaries are structurally invalid")
    if args.require_published:
        if report["published_missing_count"]:
            problems.append(
                f"{report['published_missing_count']} published episodes lack a summary preview or shard"
            )

    if args.json:
        print(json.dumps({"report": report, "problems": problems}, indent=2))
    else:
        print(
            "podcast reader summaries: "
            f"meta {report['meta']['with_reader_summary']}/{report['episodes']} "
            f"catalog {report['catalog']['with_reader_summary']}/{report['episodes']} "
            f"index previews {report['dashboard_index']['with_summary_preview']}/{report['dashboard_index']['rows']} "
            f"shards {report['episode_shards']['with_reader_summary']}/{report['episode_shards']['files']}"
        )
        print(
            "status "
            + ", ".join(f"{k}={v}" for k, v in sorted(report["meta"]["by_status"].items()))
        )
        print(
            "basis "
            + ", ".join(f"{k}={v}" for k, v in sorted(report["meta"]["by_basis"].items()))
        )
        for problem in problems:
            print(f"ERROR: {problem}")
        if not problems:
            print("OK: podcast reader-summary coverage checks passed")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
