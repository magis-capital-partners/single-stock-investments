#!/usr/bin/env python3
"""Resumable public holdings archive. SEC HTTPS only; no broker/market-data APIs.

Raw bulk downloads and as-filed rows live outside Git. Published books retain
security classes, options, principal amounts, reporting dates and amendments.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import sqlite3
import sys
import time
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system/scripts"))
from sec_client import get_bytes
from thirteenf_core import (
    annotate_weights,
    merge_filings,
    quarter_from_period,
    reconcile,
    value_to_usd,
)

ARCHIVE = ROOT / "_private/investor-history"
OWNERSHIP = ROOT / "_system/reference/market-data/ownership"
DATA = ROOT / "dashboard/data/holdings"
PAGES = {
    "13f": "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets",
    "nport": "https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets",
}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso(value):
    if not value or str(value).strip().upper() in {"N/A", "NA", "NONE", "NULL", "NIL"}:
        return ""
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%Y%m%d", "%m/%d/%Y"):
        try:
            return (
                datetime.strptime(str(value), fmt)
                .replace(tzinfo=timezone.utc)
                .strftime("%Y-%m-%d")
            )
        except ValueError:
            pass
    raise ValueError(f"Unknown reporting date: {value}")


def write_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def connect(path=ARCHIVE / "archive.sqlite"):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=60)
    db.row_factory = sqlite3.Row
    db.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        CREATE TABLE IF NOT EXISTS filings (
          accession TEXT PRIMARY KEY, manager_id TEXT NOT NULL, cik TEXT,
          period_end TEXT, filed_at TEXT, form TEXT, amendment_type TEXT,
          status TEXT NOT NULL, source_url TEXT, metadata TEXT NOT NULL,
          error TEXT, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS positions (
          accession TEXT NOT NULL, ordinal INTEGER NOT NULL, payload TEXT NOT NULL,
          PRIMARY KEY(accession, ordinal));
        CREATE TABLE IF NOT EXISTS position_books (
          accession TEXT PRIMARY KEY, payload_gzip BLOB NOT NULL);
        CREATE INDEX IF NOT EXISTS filings_manager_period ON filings(manager_id,period_end);
        CREATE INDEX IF NOT EXISTS filings_cik ON filings(CAST(cik AS INTEGER));
        CREATE TABLE IF NOT EXISTS downloads (
          url TEXT PRIMARY KEY, sha256 TEXT, bytes INTEGER, status TEXT,
          error TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS discovery (
          cik TEXT PRIMARY KEY, manager_id TEXT, status TEXT, filing_count INTEGER,
          error TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS checkpoints (key TEXT PRIMARY KEY, payload TEXT);
        CREATE TABLE IF NOT EXISTS raw_documents (
          accession TEXT, role TEXT, sha256 TEXT NOT NULL, content_gzip BLOB NOT NULL,
          PRIMARY KEY(accession,role));
    """)
    db.execute(
        "UPDATE filings SET status='seed' WHERE status!='seed' AND json_extract(metadata,'$.saved_merged_book')=1"
    )
    db.execute("DELETE FROM filings WHERE accession LIKE 'discovery:%'")
    db.execute("DELETE FROM position_books WHERE accession LIKE 'discovery:%'")
    db.commit()
    return db


def bulk_urls(kind="13f"):
    page = get_bytes(PAGES[kind]).decode("utf-8")
    urls = [
        urljoin(PAGES[kind], value)
        for value in re.findall(r'href=["\']([^"\']+\.zip)["\']', page, re.IGNORECASE)
    ]
    if not urls:
        raise RuntimeError(f"SEC {kind} catalogue returned no archives")
    return list(dict.fromkeys(urls))


def download(db, url, raw_dir=ARCHIVE / "raw"):
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / url.rsplit("/", 1)[-1]
    receipt = db.execute("SELECT * FROM downloads WHERE url=?", (url,)).fetchone()
    if (
        path.exists()
        and receipt
        and receipt["status"] == "loaded"
        and hashlib.sha256(path.read_bytes()).hexdigest() == receipt["sha256"]
    ):
        return path
    try:
        raw = get_bytes(url)
        with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
            if zipped.testzip():
                raise ValueError("Archive CRC validation failed")
        tmp = path.with_suffix(".zip.tmp")
        tmp.write_bytes(raw)
        tmp.replace(path)
        db.execute(
            "INSERT OR REPLACE INTO downloads VALUES(?,?,?,?,?,?)",
            (url, hashlib.sha256(raw).hexdigest(), len(raw), "loaded", None, now()),
        )
        db.commit()
        return path
    except (OSError, ValueError, KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
        db.execute(
            "INSERT OR REPLACE INTO downloads VALUES(?,?,?,?,?,?)",
            (url, None, None, "error", str(exc), now()),
        )
        db.commit()
        raise


def table(zipped, name):
    matched = next(
        (
            item
            for item in zipped.namelist()
            if item.rsplit("/", 1)[-1].lower() == name.lower()
        ),
        None,
    )
    if matched is None:
        raise ValueError(f"Missing SEC bulk table {name}")
    with zipped.open(matched) as raw:
        yield from csv.DictReader(
            io.TextIOWrapper(raw, encoding="utf-8-sig"), delimiter="\t"
        )


def store_filing(db, filing, rows=(), *, status="loaded", error=None):
    accession = filing["accession"]
    payload = gzip.compress(
        json.dumps(list(rows), ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        ),
        compresslevel=3,
        mtime=0,
    )
    previous = db.execute(
        "SELECT f.metadata,f.status,f.error,b.payload_gzip FROM filings f LEFT JOIN position_books b USING(accession) WHERE f.accession=?",
        (accession,),
    ).fetchone()
    if previous and (
        json.loads(previous["metadata"]) == filing
        and previous["status"] == status
        and previous["error"] == error
        and previous["payload_gzip"] == payload
    ):
        return  # Re-reading an immutable source must not rewrite the large archive.
    with db:
        db.execute(
            """INSERT OR REPLACE INTO filings VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                accession,
                filing["manager_id"],
                filing.get("cik"),
                filing.get("period_end"),
                filing.get("filed_at"),
                filing.get("form", "13F-HR"),
                filing.get("amendment_type"),
                status,
                filing.get("source_url"),
                json.dumps(filing),
                error,
                now(),
            ),
        )
        db.execute("DELETE FROM positions WHERE accession=?", (accession,))
        db.execute(
            "INSERT OR REPLACE INTO position_books VALUES(?,?)", (accession, payload)
        )


def filing_rows(db, accession):
    compressed = db.execute(
        "SELECT payload_gzip FROM position_books WHERE accession=?", (accession,)
    ).fetchone()
    if compressed:
        return json.loads(gzip.decompress(compressed[0]))
    return [
        json.loads(row[0])
        for row in db.execute(
            "SELECT payload FROM positions WHERE accession=? ORDER BY ordinal",
            (accession,),
        )
    ]


def store_raw_documents(db, accession, parsed):
    import gzip

    with db:
        for role, key in [
            ("information_table", "raw_info_bytes"),
            ("cover_page", "raw_primary_bytes"),
        ]:
            value = parsed.get(key)
            if value:
                digest = hashlib.sha256(value).hexdigest()
                previous = db.execute(
                    "SELECT sha256 FROM raw_documents WHERE accession=? AND role=?",
                    (accession, role),
                ).fetchone()
                if previous and previous[0] == digest:
                    continue
                db.execute(
                    "INSERT OR REPLACE INTO raw_documents VALUES(?,?,?,?)",
                    (
                        accession,
                        role,
                        digest,
                        gzip.compress(value, mtime=0),
                    ),
                )


def store_parse_failure(db, meta, exc):
    meta.pop("normalized_rows_sha256", None)
    from thirteenf_legacy import PARSER_VERSION, LegacyParseError

    if isinstance(exc, LegacyParseError):
        meta.update(parser="legacy-text", parser_version=PARSER_VERSION)
    if getattr(exc, "raw_documents", None):
        store_raw_documents(db, meta["accession"], exc.raw_documents)
    if getattr(exc, "raw_document", None):
        store_raw_documents(db, meta["accession"], {"raw_info_bytes": exc.raw_document})
    rows = getattr(exc, "partial_rows", None) or []
    if rows:
        meta.update(exc.primary or {})
        meta["partial_rows"] = True
        meta["reconciliation"] = reconcile(len(rows), rows, exc.primary)
    store_filing(db, meta, rows, status="review" if rows else "error", error=str(exc))


def restore_filing_cache(db, meta, cache):
    """Recover original documents from a durable checkpoint without HTTP."""
    from thirteenf_period import _cache_paths

    info, primary, receipt = _cache_paths(cache, meta["manager_id"], meta["accession"])
    if info.exists() and receipt.exists():
        return
    documents = db.execute(
        "SELECT role,sha256,content_gzip FROM raw_documents WHERE accession=?",
        (meta["accession"],),
    ).fetchall()
    for document in documents:
        path = info if document["role"] == "information_table" else primary
        raw = gzip.decompress(document["content_gzip"])
        if hashlib.sha256(raw).hexdigest() != document["sha256"]:
            raise ValueError("Preserved filing checksum mismatch")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(raw)
        temporary.replace(path)
    if documents:
        write_json(
            receipt,
            {
                "info_url": meta.get("source_url") or meta.get("index_url"),
                "primary_url": None,
                "form": meta.get("form"),
                "report_date": meta.get("period_end") or meta.get("report_date"),
                "filing_date": meta.get("filed_at") or meta.get("filing_date"),
            },
        )


def cik_map(managers):
    mapping = {}
    for manager in managers:
        for value in [
            manager.get("cik"),
            *(
                x.get("cik") if isinstance(x, dict) else x
                for x in manager.get("cik_history", [])
            ),
        ]:
            if value:
                key = str(int(value))
                if key in mapping and mapping[key] != manager["manager_id"]:
                    raise ValueError(f"CIK {key} assigned to multiple managers")
                mapping[key] = manager["manager_id"]
    return mapping


def sync_managers(db, managers):
    with db:
        for cik, manager_id in cik_map(managers).items():
            db.execute(
                "UPDATE filings SET manager_id=?,metadata=json_set(metadata,'$.manager_id',?) WHERE CAST(cik AS INTEGER)=? AND manager_id!=?",
                (manager_id, manager_id, int(cik), manager_id),
            )
            db.execute(
                "UPDATE discovery SET manager_id=? WHERE CAST(cik AS INTEGER)=? AND manager_id!=?",
                (manager_id, int(cik), manager_id),
            )


def ingest_bulk(db, path, managers, *, skip_preserved=True):
    mapping = cik_map(managers)
    filings = {}
    with zipfile.ZipFile(path) as zipped:
        for row in table(zipped, "SUBMISSION.tsv"):
            manager = mapping.get(str(int(row["CIK"])))
            if not manager:
                continue
            accession = row["ACCESSION_NUMBER"]
            filings[accession] = {
                "accession": accession,
                "manager_id": manager,
                "cik": row["CIK"],
                "period_end": iso(row.get("PERIODOFREPORT")),
                "filed_at": iso(row["FILING_DATE"]),
                "form": row["SUBMISSIONTYPE"],
                "as_filed_submission": row,
                "source_url": f"https://www.sec.gov/Archives/edgar/data/{int(row['CIK'])}/{accession.replace('-', '')}/{accession}-index.html",
            }
        # Identity corrections should not force another scan of every security
        # in an unchanged SEC archive. All selected accessions must already have
        # their complete original bulk rows (or an authoritative document).
        if skip_preserved and filings:
            complete = True
            for accession in filings:
                record = db.execute(
                    "SELECT status,metadata FROM filings WHERE accession=?",
                    (accession,),
                ).fetchone()
                if record is None or record["status"] in {
                    "seed",
                    "discovered",
                    "error",
                }:
                    complete = False
                    break
                metadata = json.loads(record["metadata"])
                if (
                    not metadata.get("as_filed_submission")
                    and not metadata.get("authoritative_filing_parsed")
                    and record["status"] != "notice"
                ):
                    complete = False
                    break
            if complete:
                return len(filings)
        for row in table(zipped, "COVERPAGE.tsv"):
            filing = filings.get(row["ACCESSION_NUMBER"])
            if filing:
                filing["as_filed_cover"] = row
                filing["amendment_type"] = row.get("AMENDMENTTYPE") or None
                filing["period_end"] = (
                    iso(row.get("REPORTCALENDARORQUARTER")) or filing["period_end"]
                )
                filing["sec_name"] = row.get("FILINGMANAGER_NAME")
        for row in table(zipped, "SUMMARYPAGE.tsv"):
            filing = filings.get(row["ACCESSION_NUMBER"])
            if filing:
                filing["as_filed_summary"] = row
                filing["table_entry_total"] = (
                    int(row["TABLEENTRYTOTAL"]) if row.get("TABLEENTRYTOTAL") else None
                )
                filing["table_value_total_usd"] = value_to_usd(
                    row.get("TABLEVALUETOTAL"), filing["filed_at"]
                )
                filing["confidential_omitted"] = row.get("ISCONFIDENTIALOMITTED") in {
                    "Y",
                    "true",
                    "1",
                }
        rows = defaultdict(list)
        for row in table(zipped, "INFOTABLE.tsv"):
            filing = filings.get(row["ACCESSION_NUMBER"])
            if filing is None:
                continue
            rows[filing["accession"]].append(
                {
                    "issuer": row["NAMEOFISSUER"],
                    "title_of_class": row.get("TITLEOFCLASS", ""),
                    "cusip": row["CUSIP"],
                    "figi": row.get("FIGI"),
                    "shares": int(float(row["SSHPRNAMT"]))
                    if row.get("SSHPRNAMT")
                    else None,
                    "sh_prn": row.get("SSHPRNAMTTYPE") or "SH",
                    "put_call": row.get("PUTCALL") or None,
                    "value_usd": value_to_usd(row.get("VALUE"), filing["filed_at"]),
                    "discretion": row.get("INVESTMENTDISCRETION"),
                    "other_manager": row.get("OTHERMANAGER"),
                    "voting_sole": row.get("VOTING_AUTH_SOLE"),
                    "voting_shared": row.get("VOTING_AUTH_SHARED"),
                    "voting_none": row.get("VOTING_AUTH_NONE"),
                    "as_filed": row,
                }
            )
    for accession, filing in filings.items():
        positions = rows.get(accession, [])
        if filing["form"] in {"13F-NT", "13F-NT/A"}:
            store_filing(db, filing, status="notice")
            continue
        report = reconcile(len(positions), positions, filing)
        filing["reconciliation"] = report
        store_filing(
            db,
            filing,
            positions,
            status="loaded" if report["ok"] else "review",
            error=None if report["ok"] else "Cover-page reconciliation failed",
        )
    return len(filings)


def import_saved_books(db, managers, positions=OWNERSHIP / "13f/positions"):
    by_id = {row["manager_id"]: row for row in managers}
    count = 0
    for path in sorted(positions.glob("*/*.csv")):
        manager = by_id.get(path.stem)
        if not manager:
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            continue
        for row in rows:
            for key in ("shares", "value_usd", "rank"):
                row[key] = int(float(row[key])) if row.get(key) else None
            row["weight_pct"] = (
                float(row["weight_pct"]) if row.get("weight_pct") else None
            )
        first = rows[0]
        accession = first.get("accession") or f"saved:{path.parent.name}:{path.stem}"
        if db.execute(
            "SELECT 1 FROM filings WHERE accession=? AND status!='seed'", (accession,)
        ).fetchone():
            continue
        store_filing(
            db,
            {
                "manager_id": path.stem,
                "cik": manager.get("cik"),
                "accession": accession,
                "period_end": first["period_end"],
                "filed_at": first.get("filed_at"),
                "form": "13F-HR",
                "source_url": first.get("source_url"),
                "saved_merged_book": True,
            },
            rows,
            status="seed",
        )
        count += 1
    return count


def backfill_filings(
    db, managers, cache=ARCHIVE / "filings", *, before=None, deadline=None
):
    from ownership_common import list_13f_filings
    from thirteenf_period import fetch_filing_tables

    errors = 0
    for manager in managers:
        if deadline and time.monotonic() >= deadline:
            break
        if not manager.get("cik"):
            continue
        for cik in [
            manager["cik"],
            *(
                x.get("cik") if isinstance(x, dict) else x
                for x in manager.get("cik_history", [])
            ),
        ]:
            if not cik:
                continue
            try:
                filings = list_13f_filings(str(cik), limit=None, strict=True)
            except (
                OSError,
                ValueError,
                KeyError,
                ET.ParseError,
                zipfile.BadZipFile,
            ) as exc:
                with db:
                    db.execute(
                        "INSERT OR REPLACE INTO discovery VALUES(?,?,?,?,?,?)",
                        (
                            str(int(cik)),
                            manager["manager_id"],
                            "error",
                            None,
                            str(exc),
                            now(),
                        ),
                    )
                errors += 1
                continue
            with db:
                db.execute(
                    "INSERT OR REPLACE INTO discovery VALUES(?,?,?,?,?,?)",
                    (
                        str(int(cik)),
                        manager["manager_id"],
                        "loaded",
                        len(filings),
                        None,
                        now(),
                    ),
                )
                # Persist the entire accession manifest before the work budget
                # can interrupt downloads. An unvisited filing must remain a
                # visible queued record, even for the last manager in a run.
                db.executemany(
                    "INSERT OR IGNORE INTO filings VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        (
                            filing["accession"],
                            manager["manager_id"],
                            str(cik),
                            filing.get("report_date"),
                            filing.get("filing_date"),
                            filing["form"],
                            None,
                            "discovered",
                            filing.get("index_url"),
                            json.dumps(
                                {
                                    **filing,
                                    "manager_id": manager["manager_id"],
                                    "cik": cik,
                                    "period_end": filing.get("report_date"),
                                    "filed_at": filing.get("filing_date"),
                                    "source_url": filing.get("index_url"),
                                }
                            ),
                            None,
                            now(),
                        )
                        for filing in filings
                    ],
                )
            # Even a no-op DELETE starts a write transaction. Release it
            # before the next HTTPS request or an already-loaded book can
            # hold the SQLite writer while every other worker waits.
            with db:
                db.execute(
                    "DELETE FROM filings WHERE accession=?",
                    (f"discovery:{manager['manager_id']}:{cik}",),
                )
            for filing in reversed(filings):
                if deadline and time.monotonic() >= deadline:
                    break
                existing = db.execute(
                    "SELECT status,metadata FROM filings WHERE accession=?",
                    (filing["accession"],),
                ).fetchone()
                if existing and existing["status"] in {
                    "loaded",
                    "notice",
                    "as_filed_warning",
                    "confidential",
                }:
                    continue
                if existing and existing["status"] in {"review", "error"}:
                    from thirteenf_legacy import PARSER_VERSION

                    previous = json.loads(existing["metadata"])
                    if (
                        previous.get("parser") == "legacy-text"
                        and previous.get("parser_version") == PARSER_VERSION
                    ):
                        continue  # The original remains reviewable until a parser upgrade.
                meta = {
                    **filing,
                    "manager_id": manager["manager_id"],
                    "cik": cik,
                    "period_end": filing.get("report_date"),
                    "filed_at": filing.get("filing_date"),
                    "source_url": filing.get("index_url"),
                }
                if filing["form"] in {"13F-NT", "13F-NT/A"}:
                    store_filing(db, meta, status="notice")
                    continue
                if before and (filing.get("filing_date") or "9999") >= before:
                    if not existing:
                        store_filing(db, meta, status="discovered")
                    continue
                store_filing(db, meta, status="discovered")
                try:
                    restore_filing_cache(db, meta, cache)
                    parsed = fetch_filing_tables(
                        filing,
                        fund_id=manager["manager_id"],
                        cache_dir=cache,
                        offline=False,
                    )
                    if parsed is None:
                        raise ValueError("No parsable information table")
                    primary = parsed.get("primary") or {}
                    meta.update(primary)
                    meta.update(
                        {
                            "period_end": parsed.get("report_date"),
                            "amendment_type": parsed.get("amendment_type"),
                            "source_url": parsed.get("info_url"),
                        }
                    )
                    report = reconcile(parsed["raw_count"], parsed["rows"], primary)
                    meta["reconciliation"] = report
                    meta["authoritative_filing_parsed"] = True
                    status = (
                        "confidential"
                        if primary.get("confidential_omitted") and not parsed["rows"]
                        else "loaded"
                        if report["ok"]
                        else "review"
                        if primary.get("parser") == "legacy-text"
                        and not report["rows_match"]
                        else "as_filed_warning"
                    )
                    store_filing(
                        db,
                        meta,
                        parsed["rows"],
                        status=status,
                        error=None
                        if report["ok"]
                        else "As-filed cover-page totals do not reconcile with all reported rows",
                    )
                    store_raw_documents(db, filing["accession"], parsed)
                except (
                    OSError,
                    ValueError,
                    KeyError,
                    ET.ParseError,
                    zipfile.BadZipFile,
                ) as exc:
                    store_parse_failure(db, meta, exc)
                    errors += 1
                    print(
                        f"{manager['manager_id']} {filing['accession']}: {exc}",
                        flush=True,
                    )
            print(
                f"{manager['manager_id']}: accounted for {len(filings)} filings",
                flush=True,
            )
    return errors


def reparse_cached(db, cache=ARCHIVE / "filings"):
    from thirteenf_period import fetch_filing_tables

    count = 0
    pending = 0
    from thirteenf_legacy import PARSER_VERSION

    records = db.execute(
        "SELECT * FROM filings WHERE accession NOT LIKE 'discovery:%' AND ((status IN ('error','review') AND (coalesce(json_extract(metadata,'$.parser'),'')!='legacy-text' OR coalesce(json_extract(metadata,'$.parser_version'),'')!=?)) OR (json_extract(metadata,'$.parser')='legacy-text' AND coalesce(json_extract(metadata,'$.parser_version'),'')!=?))",
        (PARSER_VERSION, PARSER_VERSION),
    ).fetchall()
    for record in records:
        meta = json.loads(record["metadata"])
        try:
            restore_filing_cache(db, meta, cache)
            parsed = fetch_filing_tables(
                meta, fund_id=record["manager_id"], cache_dir=cache, offline=True
            )
            if parsed is None:
                continue
            # A previous parser's derived-row checksum and partial flag do
            # not describe this new parse. Original-document SHA checksums
            # remain immutable in raw_documents.
            meta.pop("normalized_rows_sha256", None)
            meta.pop("partial_rows", None)
            primary = parsed.get("primary") or {}
            meta.update(primary)
            meta.update(
                {
                    "period_end": parsed.get("report_date"),
                    "amendment_type": parsed.get("amendment_type"),
                    "source_url": parsed.get("info_url"),
                }
            )
            report = reconcile(parsed["raw_count"], parsed["rows"], primary)
            meta["reconciliation"] = report
            meta["authoritative_filing_parsed"] = True
            status = (
                "confidential"
                if primary.get("confidential_omitted") and not parsed["rows"]
                else "loaded"
                if report["ok"]
                else "review"
                if primary.get("parser") == "legacy-text" and not report["rows_match"]
                else "as_filed_warning"
            )
            store_filing(
                db,
                meta,
                parsed["rows"],
                status=status,
                error=None
                if report["ok"]
                else "As-filed cover-page totals do not reconcile with all reported rows",
            )
            store_raw_documents(db, record["accession"], parsed)
            count += int(report["ok"])
        except (OSError, ValueError, KeyError, ET.ParseError) as exc:
            if getattr(exc, "raw_documents", None) or getattr(
                exc, "raw_document", None
            ):
                meta["parser_version"] = PARSER_VERSION
                store_parse_failure(db, meta, exc)
            pending += 1  # Original source error remains visible.
    if pending:
        print(f"Cached filings still awaiting parser review: {pending}", flush=True)
    return count


def backfill_parallel(database, managers, *, workers=2, before=None, deadline=None):
    """Bounded HTTPS concurrency, with one SQLite owner per worker."""
    with closing(connect(database)):
        pass  # Establish WAL and the schema before worker connections race.
    batches = [managers[offset::workers] for offset in range(workers)]

    def run(batch):
        with closing(connect(database)) as connection:
            return backfill_filings(connection, batch, before=before, deadline=deadline)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return sum(pool.map(run, [batch for batch in batches if batch]))


def export(db, managers, data=DATA):
    from ownership_common import load_cusip_map, portfolio_universe

    symbols = load_cusip_map()
    _universe, names = portfolio_universe()
    index = []
    quarters = defaultdict(int)
    failures = []
    published = set()
    owners = defaultdict(set)
    for cik, manager_id in cik_map(managers).items():
        owners[manager_id].add(cik)

    def belongs(record):
        # A corrected or unlinked identity may leave older cache rows behind.
        # A matching display ID alone must never attach another filer's book.
        return (
            not record["cik"] or str(int(record["cik"])) in owners[record["manager_id"]]
        )

    for manager in managers:
        records = [
            record
            for record in db.execute(
                "SELECT * FROM filings WHERE manager_id=? ORDER BY period_end,filed_at,accession",
                (manager["manager_id"],),
            )
            if belongs(record)
        ]
        periods = defaultdict(list)
        for record in records:
            unknown_amendment = (
                record["form"].endswith("/A")
                and record["form"] not in {"13F-NT/A"}
                and record["amendment_type"] not in {"NEW HOLDINGS", "RESTATEMENT"}
            )
            if (
                record["status"] in {"error", "review", "discovered", "seed"}
                or unknown_amendment
            ):
                failures.append(
                    {
                        "manager_id": manager["manager_id"],
                        "accession": record["accession"],
                        "status": record["status"],
                        "reason": record["error"]
                        or (
                            "Amendment type requires review"
                            if unknown_amendment
                            else "Awaiting original filing"
                        ),
                        "period_end": record["period_end"],
                        "source_url": record["source_url"],
                    }
                )
            if record["period_end"] and not record["form"] in {"13F-NT", "13F-NT/A"}:
                periods[record["period_end"]].append(record)
        history = []
        bundle_year = None
        bundle = {}
        for period, filings in sorted(periods.items()):
            if not any(
                f["status"]
                in {"loaded", "seed", "review", "as_filed_warning", "confidential"}
                for f in filings
            ):
                continue
            if any(f["status"] == "loaded" for f in filings):
                filings = [f for f in filings if f["status"] != "seed"]
            parts = []
            for f in filings:
                if f["status"] not in {
                    "loaded",
                    "seed",
                    "review",
                    "as_filed_warning",
                    "confidential",
                }:
                    continue
                if f["form"].endswith("/A") and f["amendment_type"] not in {
                    "NEW HOLDINGS",
                    "RESTATEMENT",
                }:
                    continue
                positions = filing_rows(db, f["accession"])
                parts.append(
                    {
                        "form": {"13F-E": "13F-HR", "13F-E/A": "13F-HR/A"}.get(
                            f["form"], f["form"]
                        ),
                        "amendment_type": f["amendment_type"],
                        "rows": positions,
                    }
                )
            anchors = [
                i
                for i, f in enumerate(filings)
                if f["status"]
                in {"loaded", "review", "seed", "as_filed_warning", "confidential"}
                and (
                    not f["form"].endswith("/A") or f["amendment_type"] == "RESTATEMENT"
                )
            ]
            effective = filings[anchors[-1] :] if anchors else filings
            positions = annotate_weights(merge_filings(parts))
            parser_gap = any(
                f["status"] in {"error", "review", "seed", "discovered"}
                or (
                    f["form"].endswith("/A")
                    and f["amendment_type"] not in {"NEW HOLDINGS", "RESTATEMENT"}
                )
                for f in effective
            )
            for row in positions:
                if parser_gap or row.get("value_usd") is None:
                    row["weight_pct"] = None
                row.pop("as_filed", None)
                row["ticker"] = symbols.get(row.get("cusip")) or row.get("ticker") or ""
                row["weight_basis"] = (
                    "reported_13f_non_option_book"
                    if row.get("weight_pct") is not None
                    else None
                )
                row["source_kind"] = "13f"
            quarter = quarter_from_period(period)
            if not quarter:
                continue
            last = filings[-1]
            incomplete = any(
                f["status"] != "loaded"
                or (
                    f["form"].endswith("/A")
                    and f["amendment_type"] not in {"NEW HOLDINGS", "RESTATEMENT"}
                )
                for f in effective
            )
            confidential = any(
                json.loads(f["metadata"]).get("confidential_omitted") for f in effective
            )
            metadata = {
                "quarter": quarter,
                "period_end": period,
                "filed_at": last["filed_at"],
                "positions": len(positions),
                "ssi_overlap": sum(
                    (r.get("ssi_ticker") or r.get("ticker")) in names for r in positions
                ),
                "partial": incomplete or confidential,
                "source_kind": "13f",
            }
            payload = {
                **metadata,
                "schema_version": 2,
                "manager_id": manager["manager_id"],
                "name": manager["display_name"],
                "cik": manager.get("cik"),
                "positions": positions,
                "filings": [
                    {
                        "accession": f["accession"],
                        "form": f["form"],
                        "filed_at": f["filed_at"],
                        "source_url": f["source_url"],
                        "status": f["status"],
                    }
                    for f in filings
                ],
                "confidential_omitted": confidential,
                "in_base_irr": False,
            }
            year = quarter[:4]
            if bundle_year is not None and year != bundle_year:
                path = data / "history" / manager["manager_id"] / f"{bundle_year}.json"
                write_json(path, {"schema_version": 2, "quarters": bundle})
                published.add(path)
                bundle = {}
            bundle_year = year
            metadata["book_path"] = f"history/{manager['manager_id']}/{year}.json"
            # Bound both asset size and browser response size for large advisers.
            if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > 1500000:
                payload["positions_parts"] = []
                for part, start in enumerate(range(0, len(positions), 10000)):
                    relative = f"history/{manager['manager_id']}/{quarter}-positions-{part}.json"
                    path = data / relative
                    write_json(path, {"positions": positions[start : start + 10000]})
                    published.add(path)
                    payload["positions_parts"].append(relative)
                payload["positions"] = []
            bundle[quarter] = payload
            history.append(metadata)
            quarters[quarter] += 1
        if bundle_year is not None:
            path = data / "history" / manager["manager_id"] / f"{bundle_year}.json"
            write_json(path, {"schema_version": 2, "quarters": bundle})
            published.add(path)
        latest = history[-1] if history else {}
        index.append(
            {
                "manager_id": manager["manager_id"],
                "name": manager["display_name"],
                "cik": manager.get("cik"),
                **latest,
                "history": history,
                "filing_gaps": [
                    failure
                    for failure in failures
                    if failure["manager_id"] == manager["manager_id"]
                ],
                "first_quarter": history[0]["quarter"] if history else None,
                "coverage_status": "partial"
                if any(f["manager_id"] == manager["manager_id"] for f in failures)
                else "available"
                if history
                else "no_public_13f_loaded",
            }
        )
    counts = defaultdict(int)
    manager_ids = {manager["manager_id"] for manager in managers}
    for row in db.execute(
        "SELECT manager_id,cik,status,count(*) AS count FROM filings GROUP BY manager_id,cik,status"
    ):
        if row["manager_id"] in manager_ids and belongs(row):
            counts[row["status"]] += row["count"]
    discovered = {
        r["cik"] for r in db.execute("SELECT cik FROM discovery WHERE status='loaded'")
    }
    undiscovered = sorted(set(cik_map(managers)) - discovered)
    catalogue = db.execute(
        "SELECT payload FROM checkpoints WHERE key='bulk_catalogue'"
    ).fetchone()
    expected_downloads = json.loads(catalogue[0]) if catalogue else []
    loaded_downloads = {
        r[0] for r in db.execute("SELECT url FROM downloads WHERE status='loaded'")
    }
    missing_downloads = sorted(set(expected_downloads) - loaded_downloads)
    fingerprint = hashlib.sha256(
        json.dumps(sorted(cik_map(managers).items())).encode()
    ).hexdigest()
    missing_imports = [
        url
        for url in expected_downloads
        if not db.execute(
            "SELECT 1 FROM checkpoints WHERE key=?",
            (f"bulk_import:{url.rsplit('/', 1)[-1]}:{fingerprint}",),
        ).fetchone()
    ]
    coverage = {
        "generated_at": now(),
        "filings": counts,
        "manager_count": len(index),
        "unresolved": failures,
        "unresolved_count": len(failures),
        "undiscovered_ciks": undiscovered,
        "missing_bulk_archives": missing_downloads,
        "unimported_bulk_archives": missing_imports,
        "backfill_processed": not undiscovered
        and bool(expected_downloads)
        and not missing_imports
        and not missing_downloads
        and not counts.get("discovered")
        and not counts.get("seed"),
        "discovery_errors": [
            dict(row)
            for row in db.execute(
                "SELECT manager_id,cik,error FROM discovery WHERE status='error'"
            )
            if row["manager_id"] in manager_ids and belongs(row)
        ],
        "downloads": [
            dict(r)
            for r in db.execute(
                "SELECT url,status,error,bytes FROM downloads ORDER BY url"
            )
        ],
        "complete": not failures
        and not undiscovered
        and bool(expected_downloads)
        and not missing_downloads
        and not missing_imports,
        "scope": "Public filings discovered for the registered manager universe; undisclosed positions are unavailable.",
    }
    write_json(
        data / "directory_index.json",
        {
            "schema_version": 2,
            "generated_at": now(),
            "managers": index,
            "quarters": dict(sorted(quarters.items())),
            "coverage": {
                k: v
                for k, v in coverage.items()
                if k not in {"unresolved", "downloads"}
            },
        },
    )
    write_json(data / "coverage.json", coverage)
    history_root = (data / "history").resolve()
    for stale in (data / "history").rglob("*.json"):
        if stale not in published and stale.resolve().is_relative_to(history_root):
            stale.unlink()
    return coverage


def main():
    from sec_client import _DEFAULT

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument(
        "--workers",
        type=int,
        choices=[1, 2, 3, 4, 6],
        default=2,
        help="Bounded parallel archive downloads or filing-history workers",
    )
    parser.add_argument(
        "--request-interval",
        type=float,
        default=0.4,
        help="Minimum SEC request interval across all workers; at least 0.2 seconds",
    )
    parser.add_argument("--bulk", action="store_true")
    parser.add_argument("--all-filings", action="store_true")
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Exhaust filing discovery; parse filings before the XML bulk archive",
    )
    parser.add_argument(
        "--cached-bulk",
        action="store_true",
        help="Ingest downloaded archives without network access",
    )
    parser.add_argument(
        "--reparse",
        action="store_true",
        help="Retry quarantined records using already cached original filings",
    )
    parser.add_argument(
        "--seconds",
        type=int,
        default=14400,
        help="Work budget; filing checkpoints survive the next run",
    )
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--manager")
    parser.add_argument("--database", type=Path, default=ARCHIVE / "archive.sqlite")
    parser.add_argument("--registry", type=Path, default=OWNERSHIP / "managers.json")
    args = parser.parse_args()
    _DEFAULT.min_interval = max(0.2, args.request_interval)
    db = connect(args.database)
    deadline = time.monotonic() + args.seconds
    managers = json.loads(args.registry.read_text(encoding="utf-8"))["managers"]
    sync_managers(db, managers)
    selected = (
        [m for m in managers if m["manager_id"] in args.manager.split(",")]
        if args.manager
        else managers
    )
    fingerprint = hashlib.sha256(
        json.dumps(sorted(cik_map(selected).items())).encode()
    ).hexdigest()
    if args.cached_bulk:
        for path in sorted((ARCHIVE / "raw").glob("*.zip")):
            if time.monotonic() >= deadline:
                break
            key = f"bulk_import:{path.name}:{fingerprint}"
            if db.execute("SELECT 1 FROM checkpoints WHERE key=?", (key,)).fetchone():
                continue
            print(f"Ingesting {path.name}", flush=True)
            count = ingest_bulk(db, path, selected)
            with db:
                db.execute(
                    "INSERT OR REPLACE INTO checkpoints VALUES(?,?)",
                    (key, json.dumps({"filings": count, "at": now()})),
                )
    if args.bulk or args.download_only:
        urls = bulk_urls()
        with db:
            db.execute(
                "INSERT OR REPLACE INTO checkpoints VALUES('bulk_catalogue',?)",
                (json.dumps(urls),),
            )
        if args.download_only:

            def fetch_one(url):
                if time.monotonic() >= deadline:
                    return
                with closing(connect(args.database)) as worker_db:
                    try:
                        print(f"Downloading {url.rsplit('/', 1)[-1]}", flush=True)
                        download(worker_db, url)
                    except (
                        OSError,
                        ValueError,
                        KeyError,
                        ET.ParseError,
                        zipfile.BadZipFile,
                    ) as exc:
                        print(f"Archive failed: {exc}", flush=True)

            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                list(pool.map(fetch_one, urls))
            db.close()
            return 0
        for url in urls:
            if time.monotonic() >= deadline:
                break
            key = f"bulk_import:{url.rsplit('/', 1)[-1]}:{fingerprint}"
            if (
                args.bulk
                and db.execute(
                    "SELECT 1 FROM checkpoints WHERE key=?", (key,)
                ).fetchone()
            ):
                continue
            print(f"Downloading {url.rsplit('/', 1)[-1]}", flush=True)
            try:
                path = download(db, url)
                if args.bulk:
                    key = f"bulk_import:{path.name}:{fingerprint}"
                    if not db.execute(
                        "SELECT 1 FROM checkpoints WHERE key=?", (key,)
                    ).fetchone():
                        count = ingest_bulk(db, path, selected)
                        with db:
                            db.execute(
                                "INSERT OR REPLACE INTO checkpoints VALUES(?,?)",
                                (key, json.dumps({"filings": count, "at": now()})),
                            )
                        print(f"Loaded {count} manager filings", flush=True)
            except (
                OSError,
                ValueError,
                KeyError,
                ET.ParseError,
                zipfile.BadZipFile,
            ) as exc:
                print(f"Archive failed: {exc}", flush=True)
    if not args.download_only:
        import_saved_books(db, selected)
    if args.reparse:
        print(f"Reparsed {reparse_cached(db)} cached filings", flush=True)
    if args.all_filings or args.legacy:
        backfill_parallel(
            args.database,
            selected,
            workers=args.workers,
            before="2013-05-01" if args.legacy else None,
            deadline=deadline,
        )
    if args.export:
        result = export(db, managers)
        print(
            json.dumps(
                {
                    k: v
                    for k, v in result.items()
                    if k
                    not in {
                        "downloads",
                        "unresolved",
                        "undiscovered_ciks",
                        "missing_bulk_archives",
                    }
                }
            )
        )
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
