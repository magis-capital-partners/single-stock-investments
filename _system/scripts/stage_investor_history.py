#!/usr/bin/env python3
"""Restore and stage the pinned complete archive behind existing site auth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import global_disclosures
import investor_history as history
from investor_history_checkpoint import restore
from vault_paths import research_vault_root


def compact_history(data, *, max_bytes=4 * 1024 * 1024):
    """Bounded books per manager keep all years within the static asset budget."""
    path = data / "directory_index.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    for manager in index["managers"]:
        records = manager.get("history") or []
        paths = list(dict.fromkeys(record["book_path"] for record in records))
        if len(paths) < 2:
            continue
        bundle = {}
        used = 0
        part = 0
        locations = {}

        def flush(bundle, part, manager=manager, locations=locations):
            relative = f"history/{manager['manager_id']}/books-{part}.json"
            history.write_json(
                data / relative, {"schema_version": 2, "quarters": bundle}
            )
            locations.update({quarter: relative for quarter in bundle})

        for relative in paths:
            books = json.loads((data / relative).read_text(encoding="utf-8"))[
                "quarters"
            ]
            for quarter, book in sorted(books.items()):
                size = len(json.dumps(book, ensure_ascii=False).encode("utf-8"))
                if bundle and used + size > max_bytes:
                    flush(bundle, part)
                    part += 1
                    bundle = {}
                    used = 0
                bundle[quarter] = book
                used += size
        if bundle:
            flush(bundle, part)
        for record in records:
            record["book_path"] = locations[record["quarter"]]
        manager["book_path"] = records[-1]["book_path"]
        for relative in paths:
            stale = (data / relative).resolve()
            if (
                stale.is_relative_to(data.resolve())
                and relative not in locations.values()
            ):
                stale.unlink()
    history.write_json(path, index)


def stage(site, *, vault=None, receipt=None, cache=None):
    receipt = receipt or history.DATA / "archive_receipt.json"
    if not receipt.exists():
        return {"configured": False}
    identity = json.loads(receipt.read_text())["identity"]
    vault = vault or research_vault_root()
    if vault is None:
        raise RuntimeError("Research vault required for the pinned holdings archive")
    cache = cache or history.ARCHIVE / "deploy"
    if not restore(
        vault / "dashboard-private/investor-history", cache, identity=identity
    ):
        raise RuntimeError(
            "Pinned investor archive is missing; refusing an incomplete deployment"
        )
    universe = json.loads((cache / "universe.json").read_text(encoding="utf-8"))
    # The private universe retains non-filers and unresolved document identities.
    # Only the known SEC owners have public filings; identity labels never join books.
    db = history.connect(cache / "archive.sqlite")
    try:
        history.sync_managers(db, universe["managers"])
        coverage = history.export(db, universe["managers"], site / "data/holdings")
    finally:
        db.close()
    disclosures = json.loads((cache / "disclosures.json").read_text(encoding="utf-8"))
    global_disclosures.upgrade_nport_snapshots(
        disclosures["disclosures"], cache / "public-cache.sqlite"
    )
    result = global_disclosures.publish(
        disclosures["disclosures"],
        universe,
        data=site / "data/holdings",
        review=disclosures.get("review", []),
        preserve=False,
        save_archive=False,
    )
    compact_history(site / "data/holdings")
    compact_disclosures(site / "data/holdings")
    oversized = [
        p
        for p in (site / "data/holdings").rglob("*.json")
        if p.stat().st_size >= 20 * 1024 * 1024
    ]
    if oversized:
        raise RuntimeError(
            f"{len(oversized)} holdings assets exceed the deployment size bound"
        )
    return {
        "configured": True,
        "identity": identity,
        "filings": coverage["filings"],
        **result,
    }


def compact_disclosures(data, *, max_bytes=4 * 1024 * 1024):
    for manifest_path in (data / "disclosures").glob("*.json"):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        paths = list(
            dict.fromkeys(
                path
                for paths in manifest.get("quarters", {}).values()
                for path in paths
            )
        )
        if len(paths) < 2:
            continue
        groups = {}
        bundle = []
        used = 0
        part = 0

        def flush(bundle, part, manifest=manifest, groups=groups):
            relative = f"disclosures/{manifest['manager_id']}/books-{part}.json"
            history.write_json(data / relative, {"snapshots": bundle})
            for snapshot in bundle:
                quarter = (
                    snapshot.get("quarter")
                    or history.quarter_from_period(snapshot.get("period_end"))
                    or history.quarter_from_period(snapshot.get("disclosed_at"))
                    or "undated"
                )
                if relative not in groups.setdefault(quarter, []):
                    groups[quarter].append(relative)

        for relative in paths:
            for snapshot in json.loads((data / relative).read_text(encoding="utf-8"))[
                "snapshots"
            ]:
                size = len(json.dumps(snapshot, ensure_ascii=False).encode("utf-8"))
                if bundle and used + size > max_bytes:
                    flush(bundle, part)
                    part += 1
                    bundle = []
                    used = 0
                bundle.append(snapshot)
                used += size
        if bundle:
            flush(bundle, part)
        manifest["quarters"] = groups
        history.write_json(manifest_path, manifest)
        retained = {path for paths in groups.values() for path in paths}
        for relative in paths:
            stale = (data / relative).resolve()
            if stale.is_relative_to(data.resolve()) and relative not in retained:
                stale.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=history.ROOT / "_cf_project/site")
    parser.add_argument("--vault", type=Path)
    args = parser.parse_args()
    print(json.dumps(stage(args.site, vault=args.vault)))


if __name__ == "__main__":
    main()
