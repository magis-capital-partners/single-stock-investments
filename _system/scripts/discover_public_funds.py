#!/usr/bin/env python3
"""Discover registered fund vehicles from as-filed SEC N-CEN adviser records.

Only principal advisers are linked. Sub-adviser appointments do not establish
ownership of a whole fund portfolio. Explicit appointment dates are retained.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import zipfile
from collections import defaultdict
from urllib.parse import urljoin

from investor_history import ARCHIVE, connect, download, iso, now, table, write_json
from sec_client import get_bytes

CATALOGUE = "https://www.sec.gov/data-research/sec-markets-data/form-n-cen-data-sets"


def legal_name(value):
    value = re.sub(r"\s*/\s*[A-Za-z]{2,3}\s*$", "", value)
    value = re.sub(r"\bL[.\s]*L[.\s]*P\.?$", "LLP", value, flags=re.IGNORECASE)
    value = re.sub(r"\bL[.\s]*P\.?$", "LP", value, flags=re.IGNORECASE)
    words = re.findall(r"[a-z0-9]+", value.lower())
    legal = {
        "llc",
        "llp",
        "lp",
        "inc",
        "ltd",
        "limited",
        "plc",
        "corp",
        "corporation",
        "ag",
        "gmbh",
        "and",
    }
    return "".join(word for word in words if word not in legal)


def discover_from_zip(path, managers):
    names = defaultdict(set)
    for manager in managers:
        if manager.get("book") == "overlap_only":
            continue
        if manager.get("identity_status") == "unverified_document_identity":
            continue
        for name in [manager.get("sec_name"), manager.get("display_name")]:
            if name and len(legal_name(name)) >= 5:
                names[legal_name(name)].add(manager["manager_id"])
    output = []
    with zipfile.ZipFile(path) as zipped:
        submissions = {
            r["ACCESSION_NUMBER"]: r for r in table(zipped, "SUBMISSION.tsv")
        }
        funds = {r["FUND_ID"]: r for r in table(zipped, "FUND_REPORTED_INFO.tsv")}
        for row in table(zipped, "ADVISER.tsv"):
            if row.get("ADVISER_TYPE", "").strip().lower() != "advisor":
                continue
            matched = names.get(legal_name(row.get("ADVISER_NAME", "")), set())
            if len(matched) != 1:
                continue
            fund = funds.get(row["FUND_ID"])
            if not fund or not fund.get("SERIES_ID") or fund["SERIES_ID"] == "N/A":
                continue
            submission = submissions[fund["ACCESSION_NUMBER"]]
            accession = fund["ACCESSION_NUMBER"]
            output.append(
                {
                    "manager_id": next(iter(matched)),
                    "cik": submission["CIK"],
                    "series_id": fund["SERIES_ID"],
                    "fund_name": fund["FUND_NAME"],
                    "adviser_name": row["ADVISER_NAME"],
                    "crd": row.get("CRD_NUM"),
                    "observed_at": iso(submission["REPORT_ENDING_PERIOD"]),
                    "appointment_start": iso(row.get("ADVISOR_START_DATE")),
                    "appointment_end": iso(row.get("ADVISOR_TERMINATED_DATE")),
                    "source_url": f"https://www.sec.gov/Archives/edgar/data/{int(submission['CIK'])}/{accession.replace('-', '')}/{accession}-index.html",
                }
            )
    return output


def discover(managers, *, deadline=None):
    html = get_bytes(CATALOGUE).decode("utf-8")
    urls = list(
        dict.fromkeys(
            urljoin(CATALOGUE, url)
            for url in re.findall(r'href=["\']([^"\']+\.zip)', html)
        )
    )
    if not urls:
        raise ValueError("SEC N-CEN archive catalogue is empty")
    db = connect()
    records = []
    review = []
    for url in urls:
        if deadline and time.monotonic() >= deadline:
            review.append(
                {
                    "reason": "N-CEN fund discovery awaits checkpoint continuation",
                    "url": url,
                }
            )
            continue
        try:
            print(f"Discovering funds in {url.rsplit('/', 1)[-1]}", flush=True)
            path = download(db, url, ARCHIVE / "ncen")
            records.extend(discover_from_zip(path, managers))
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
            review.append({"url": url, "reason": str(exc)})
    db.close()
    groups = {}
    for record in records:
        key = (record["manager_id"], record["cik"])
        source = groups.setdefault(
            key,
            {
                "kind": "nport",
                "manager_id": key[0],
                "cik": key[1],
                "series_ids": set(),
                "queries": set(),
                "series_links": defaultdict(list),
            },
        )
        source["series_ids"].add(record["series_id"])
        source["queries"].add(record["fund_name"])
        source["series_links"][record["series_id"]].append(record)
    sources = []
    for source in groups.values():
        source["series_ids"] = sorted(source["series_ids"])
        source["queries"] = sorted(source["queries"])
        source["series_links"] = {
            key: sorted(values, key=lambda r: r["observed_at"])
            for key, values in source["series_links"].items()
        }
        sources.append(source)
    result = {
        "generated_at": now(),
        "sources": sources,
        "review": review,
        "catalogue_note": "SEC N-CEN bulk datasets currently omit schema 3.1 submissions. Explicit source mappings and unlinked-identity coverage are retained alongside discovery.",
    }
    write_json(ARCHIVE / "discovered_funds.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=14400)
    args = parser.parse_args()
    universe = json.loads((ARCHIVE / "universe.json").read_text(encoding="utf-8"))
    result = discover(universe["managers"], deadline=time.monotonic() + args.seconds)
    print(
        json.dumps(
            {
                "registered_adviser_sources": len(result["sources"]),
                "fund_series": sum(len(s["series_ids"]) for s in result["sources"]),
                "review": len(result["review"]),
            }
        )
    )


if __name__ == "__main__":
    main()
