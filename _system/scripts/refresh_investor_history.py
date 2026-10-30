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


def refresh(*, seconds=14400, corpus=None, public=True):
    deadline = time.monotonic() + seconds
    corpus = corpus or letters_root() / "insights.json"
    try:
        history.write_json(investor_universe.ROSTER, investor_universe.fetch_roster())
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print(
            f"Public roster refresh pending; dated snapshot retained: {exc}", flush=True
        )
    universe = investor_universe.compile_universe(
        corpus_path=corpus, resolve_public=True
    )
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
    history.backfill_filings(db, managers, deadline=deadline)
    history.reparse_cached(db)
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
            d["id"]: d
            for d in json.loads(previous.read_text(encoding="utf-8")).get(
                "disclosures", []
            )
        }
    retained.update({d["id"]: d for d in documents})
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
