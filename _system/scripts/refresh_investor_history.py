#!/usr/bin/env python3
"""One resumable end-to-end public holdings and private disclosure refresh."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import zipfile
from pathlib import Path

import global_disclosures
import investor_history as history
import investor_universe
from vault_paths import letters_root


def retain_archived_identities(current, previous):
    """Keep historical letter publishers when a source corpus rotates."""
    managers = {m["manager_id"]: m for m in current["managers"]}
    historical = {m["manager_id"]: m for m in previous.get("managers", [])}
    identities = current.setdefault("source_ids", {})
    for fund_id, manager_id in previous.get("source_ids", {}).items():
        if fund_id in identities:
            continue
        old = historical.get(manager_id)
        if manager_id not in managers and old and not old.get("cik"):
            managers[manager_id] = old
        if manager_id in managers:
            identities[fund_id] = manager_id
    current["managers"] = list(managers.values())
    return current


def current_disclosure_identity(document, universe):
    if document.get("source_kind") == "fund_disclosure":
        owner = universe.get("source_ids", {}).get(document.get("vehicle_id"))
        if owner:
            return {**document, "manager_id": owner}
    return document


def refresh(*, seconds=14400, corpus=None, public=True):
    deadline = time.monotonic() + seconds
    corpus = corpus or letters_root() / "insights.json"
    if not corpus.is_file():
        raise FileNotFoundError(
            "The private letter corpus is required; retain the previous complete snapshot."
        )
    try:
        history.write_json(investor_universe.ROSTER, investor_universe.fetch_roster())
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print(
            f"Public roster refresh pending; dated snapshot retained: {exc}", flush=True
        )
    saved_universe = history.ARCHIVE / "universe.json"
    previous_universe = (
        json.loads(saved_universe.read_text(encoding="utf-8"))
        if saved_universe.exists()
        else {}
    )
    universe = investor_universe.compile_universe(
        corpus_path=corpus, resolve_public=True
    )
    universe = retain_archived_identities(universe, previous_universe)
    history.write_json(saved_universe, universe)
    managers = json.loads(
        (history.OWNERSHIP / "managers.json").read_text(encoding="utf-8")
    )["managers"]
    db = history.connect()
    history.sync_managers(db, managers)
    urls = history.bulk_urls()
    with db:
        db.execute(
            "INSERT OR REPLACE INTO checkpoints VALUES('bulk_catalogue',?)",
            (json.dumps(urls),),
        )
    fingerprint = hashlib.sha256(
        json.dumps(sorted(history.cik_map(managers).items())).encode()
    ).hexdigest()
    for url in urls:
        if time.monotonic() >= deadline:
            break
        key = f"bulk_import:{url.rsplit('/', 1)[-1]}:{fingerprint}"
        if db.execute("SELECT 1 FROM checkpoints WHERE key=?", (key,)).fetchone():
            continue
        print(f"Backfilling {url.rsplit('/', 1)[-1]}", flush=True)
        try:
            path = history.download(db, url)
            count = history.ingest_bulk(db, path, managers)
            with db:
                db.execute(
                    "INSERT OR REPLACE INTO checkpoints VALUES(?,?)",
                    (key, json.dumps({"filings": count, "at": history.now()})),
                )
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
            print(f"Bulk archive awaits retry: {exc}", flush=True)
    # Discover every older submissions page and every accession, not just a
    # fixed number of periods. Unknown layouts and missing pages stay visible.
    history.import_saved_books(db, managers)
    history.reparse_cached(db)
    history.backfill_parallel(
        history.ARCHIVE / "archive.sqlite", managers, deadline=deadline
    )
    coverage = history.export(db, managers)
    db.close()
    documents, review = (
        global_disclosures.corpus_disclosures(corpus, universe)
        if corpus.exists()
        else ([], [{"reason": "Eligible source corpus unavailable"}])
    )
    if public:
        from discover_public_funds import discover

        discovered = discover(universe["managers"], deadline=deadline)
        review.extend(discovered["review"])
        sources = json.loads(global_disclosures.SOURCES.read_text())["sources"]
        sources.extend(discovered["sources"])
        fetched, errors = global_disclosures.public_disclosures(
            sources, deadline=deadline
        )
        documents.extend(fetched)
        review.extend(errors)
    previous = history.ARCHIVE / "disclosures.json"
    retained = {}
    if previous.exists():
        retained = {
            (d["manager_id"], d["id"]): d
            for raw in json.loads(previous.read_text(encoding="utf-8")).get(
                "disclosures", []
            )
            for d in [current_disclosure_identity(raw, universe)]
        }
    retained.update({(d["manager_id"], d["id"]): d for d in documents})
    global_disclosures.upgrade_nport_snapshots(
        list(retained.values()), history.ARCHIVE / "public-cache.sqlite"
    )
    disclosure_coverage = global_disclosures.publish(
        list(retained.values()), universe, review=review
    )
    result = {
        "filings": coverage["filings"],
        "filing_history_complete": coverage["complete"],
        **disclosure_coverage,
    }
    print(json.dumps(result), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=14400)
    parser.add_argument("--corpus", type=Path)
    args = parser.parse_args()
    refresh(seconds=args.seconds, corpus=args.corpus)


if __name__ == "__main__":
    main()
