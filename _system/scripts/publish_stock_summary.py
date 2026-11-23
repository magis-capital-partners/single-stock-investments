"""Publish a complete stock Summary release to the existing private R2 bucket."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from private_storage import PrivateStorage, store_bytes
from stock_summary import SCHEMA, audit, read

POINTER = "stock-summary/v1/current.json"
POINTER_LIMIT = 1024 * 1024
READER_LIMIT = 20 * 1024 * 1024
BUNDLE_COUNT = 32


def encoded(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()


def publish(document, store):
    coverage = audit(document)
    objects = store.objects
    pointer_key = objects.base + POINTER
    before = objects.http.request("GET", pointer_key, limit=POINTER_LIMIT)
    previous = json.loads(before) if before else {}
    if previous.get("as_of", "") > document["as_of"]:
        raise ValueError("A newer Summary release is already published")

    groups = {}
    locations = {}
    for ticker, row in sorted(document["listings"].items()):
        bucket = int(hashlib.sha256(ticker.encode()).hexdigest()[:4], 16) % BUNDLE_COUNT
        locations[ticker] = bucket
        groups.setdefault(bucket, {})[ticker] = row

    def verified(key, payload, current):
        raw = encoded(payload)
        if len(raw) > READER_LIMIT:
            raise ValueError(f"Stock Summary bundle exceeds its reader budget: {key}")
        receipt = (
            current
            if current and current.get("sha256") == hashlib.sha256(raw).hexdigest()
            else store_bytes(objects, raw)
        )
        if store.restore(key, records={key: receipt}) != raw:
            raise ValueError(f"Stock Summary bundle failed read-back: {key}")
        return receipt

    bundles = {}
    for i, group in groups.items():
        key = str(i)
        bundles[key] = verified(
            key,
            {"schema": SCHEMA, "as_of": document["as_of"], "listings": group},
            previous.get("bundles", {}).get(key),
        )
        print(f"Verified {len(bundles)} of {len(groups)} stock Summary bundles", flush=True)
    coverage_record = verified("coverage", coverage, previous.get("coverage"))
    pointer = encoded(
        {
            "schema": SCHEMA,
            "as_of": document["as_of"],
            "locations": locations,
            "aliases": document["aliases"],
            "bundles": bundles,
            "coverage": coverage_record,
        }
    )
    if len(pointer) > POINTER_LIMIT:
        raise ValueError("Stock Summary pointer exceeds its reader budget")
    if objects.http.request("GET", pointer_key, limit=POINTER_LIMIT) != before:
        raise ValueError("Stock Summary changed during publication. Retry from the new pointer.")
    objects.put(pointer)
    objects.http.request("PUT", pointer_key, pointer, limit=POINTER_LIMIT)
    if objects.http.request("GET", pointer_key, limit=POINTER_LIMIT) != pointer:
        raise ValueError("Stock Summary pointer failed read-back")
    return coverage["counts"]


def published_release(store, *, listings=False):
    objects = store.objects
    raw = objects.http.request("GET", objects.base + POINTER, limit=POINTER_LIMIT)
    if not raw:
        raise ValueError("Stock Summary release is awaiting publication")
    pointer = json.loads(raw)
    if pointer.get("schema") != SCHEMA:
        raise ValueError("Unknown stock Summary pointer")
    coverage = json.loads(store.restore("coverage", records={"coverage": pointer["coverage"]}))
    if coverage["as_of"] != pointer["as_of"] or set(coverage["listings"]) != set(pointer["locations"]):
        raise ValueError("Summary release coverage differs from its published identity")
    if listings:
        coverage["listings"] = {}
        for key, receipt in pointer["bundles"].items():
            group = json.loads(store.restore(key, records={key: receipt}))
            if group["as_of"] != pointer["as_of"]:
                raise ValueError("Stock Summary bundle release date differs from its pointer")
            coverage["listings"].update(group["listings"])
        audit(coverage)
    return coverage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    if bool(args.input) == bool(args.verify):
        parser.error("Supply --input or --verify")
    store = PrivateStorage(root=args.root)
    if args.verify:
        report = published_release(store)
        registry = read(args.root / "_system/portfolio/registry.json")["holdings"]
        queued = sorted(set(registry) - set(report["registered"]))
        print(
            json.dumps(
                {
                    "as_of": report["as_of"],
                    "symbols": len(report["registered"]),
                    "listings": len(report["listings"]),
                    "counts": report["counts"],
                    "new_symbols_awaiting_refresh": queued,
                }
            )
        )
    else:
        print(json.dumps(publish(read(args.input), store)), flush=True)


if __name__ == "__main__":
    main()
