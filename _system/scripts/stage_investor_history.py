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
    result = global_disclosures.publish(
        disclosures["disclosures"],
        universe,
        data=site / "data/holdings",
        review=disclosures.get("review", []),
        preserve=False,
        save_archive=False,
    )
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=history.ROOT / "_cf_project/site")
    parser.add_argument("--vault", type=Path)
    args = parser.parse_args()
    print(json.dumps(stage(args.site, vault=args.vault)))


if __name__ == "__main__":
    main()
