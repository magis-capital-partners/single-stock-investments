"""Versioned collection ledger. Public SEC and file imports only; no broker API.

The mutable working database is isolated from every frozen experiment. Raw
sources, processing failures, candidate gaps and external dependencies survive
resumes. Downloads have one shared four-request-per-second limiter and stop on
denial rather than trying another identity or host to bypass it.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import random
import re
import sqlite3
import time
import threading
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse, urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from .enrich_edgar import _iter_submission_rows
from .event_audit import audit_clause, ratio, WORDS
from .filings import parse_announcement
from .ingest_splits import _hits_from_rows, store_edgar_hits
from .ledger import write_json, load_jsonl

VERSION = "expansion_v2"
CLASSIFIER_VERSION = "bounded_clause_v5"
SPLIT_MARKER = r"\breverse[\s-]+(?:stock[\s-]+|share[\s-]+)?split|\bshare[\s-]+consolidation|\bconsolidation\s+of\s+shares|\bADS\b.{0,30}?ratio|\bdepositary\s+share.{0,30}?ratio"
FORMS = (
    "8-K",
    "8-K/A",
    "6-K",
    "6-K/A",
    "DEF 14A",
    "PRE 14A",
    "DEFA14A",
    "DEF 14C",
    "PRE 14C",
)


def visible_text(body):
    """Native parsing avoids Python objects for every filing tag."""
    from lxml import html, etree

    try:
        if isinstance(body, bytes) and body.lstrip().startswith(b"<?xml"):
            tree = etree.fromstring(
                body,
                etree.XMLParser(recover=True, resolve_entities=False, no_network=True),
            )
        else:
            tree = html.fromstring(body, parser=html.HTMLParser(no_network=True))
        for node in tree.xpath("//script|//style"):
            node.getparent().remove(node)
        return " ".join(t.strip() for t in tree.itertext() if t.strip())
    except (etree.ParserError, etree.XMLSyntaxError, ValueError, AttributeError):
        return (
            body.decode("utf-8", errors="replace")
            if isinstance(body, bytes)
            else str(body)
        )


SCHEMA = """
CREATE TABLE IF NOT EXISTS collection_sources (
 url TEXT PRIMARY KEY, sha256 TEXT, file TEXT, bytes INTEGER,
 fetched_at TEXT, status TEXT, error TEXT, attempts INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS collection_jobs (
 kind TEXT, key TEXT, status TEXT, updated_at TEXT, detail TEXT,
 PRIMARY KEY(kind,key));
CREATE TABLE IF NOT EXISTS disclosures (
 accession TEXT PRIMARY KEY, cik TEXT, ticker TEXT, form TEXT, filed_at TEXT,
 available_at TEXT, clock_basis TEXT, stage TEXT, ratio REAL, scheduled TEXT,
 eligible INTEGER, review_status TEXT, text_file TEXT, source_json TEXT, audit_json TEXT);
CREATE TABLE IF NOT EXISTS security_history (
 security_id TEXT, cik TEXT, ticker TEXT, valid_from TEXT, valid_to TEXT,
 exchange TEXT, currency TEXT, kind TEXT, verified INTEGER, source_url TEXT,
 PRIMARY KEY(security_id,ticker,valid_from));
CREATE TABLE IF NOT EXISTS evidence_imports (
 kind TEXT, key TEXT, available_at TEXT, data_json TEXT, source_sha256 TEXT,
 PRIMARY KEY(kind,key,available_at));
CREATE TABLE IF NOT EXISTS review_revisions (
 id INTEGER PRIMARY KEY, accession TEXT, recorded_at TEXT, data_json TEXT);
CREATE TABLE IF NOT EXISTS independent_actions (
 security_id TEXT, ticker TEXT, ex_date TEXT, ratio REAL, announced_at TEXT,
 verified INTEGER, source_url TEXT, source_sha256 TEXT,
 PRIMARY KEY(security_id,ex_date));
"""


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def stored_path(cfg, path):
    path = Path(path).resolve()
    try:
        return path.relative_to(cfg.repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def location(cfg):
    return cfg.local_dir / "expansion" / VERSION


def connect(cfg):
    root = location(cfg)
    root.mkdir(parents=True, exist_ok=True)
    db = root / "working.sqlite"
    created = not db.exists()
    if created:
        source = cfg.local_dir / "reruns/fundamentals_v1/input.sqlite"
        if not source.exists():
            source = cfg.db_path
        if not source.exists():
            from .import_ledger import import_ledger

            import_ledger(cfg.ledger_dir, cfg.db_path, cfg.decisions_db_path)
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as old:
            with sqlite3.connect(db) as new:
                old.backup(new)
        preserved = [
            cfg.ledger_dir / "book_runs.jsonl",
            cfg.ledger_dir / "decisions.jsonl",
            cfg.ledger_dir / "book_source_manifests.jsonl",
        ]
        write_json(
            root / "baseline_manifest.json",
            {
                "created_at": utcnow(),
                "source": str(source),
                "sha256": digest(source),
                "preserved": [
                    {"file": stored_path(cfg, p), "sha256": digest(p)}
                    for p in preserved
                    if p.exists()
                ],
                "version": VERSION,
            },
        )
    conn = sqlite3.connect(db, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA journal_mode=WAL")
    if created:
        # Rehydrate the published metadata on a clean checkout. Source text
        # and licensed prices still require their documented local caches.
        columns = [r[1] for r in conn.execute("PRAGMA table_info(edgar_hits)")]
        for row in load_jsonl(cfg.ledger_dir / "expansion_discovery.jsonl"):
            conn.execute(
                "INSERT OR IGNORE INTO edgar_hits ("
                + ",".join(columns)
                + ") VALUES ("
                + ",".join("?" for _ in columns)
                + ")",
                tuple(row.get(k) for k in columns),
            )
        for row in load_jsonl(cfg.ledger_dir / "expansion_disclosures.jsonl"):
            conn.execute(
                "INSERT OR IGNORE INTO disclosures VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                tuple(
                    row.get(k)
                    for k in (
                        "accession",
                        "cik",
                        "ticker",
                        "form",
                        "filed_at",
                        "available_at",
                        "clock_basis",
                        "stage",
                        "ratio",
                        "scheduled",
                        "eligible",
                        "review_status",
                    )
                )
                + (None, "[]", "{}"),
            )
        conn.commit()
    return conn


def bootstrap(cfg, legacy_root):
    """Take a consistent read-only legacy snapshot and retain immutable caches.

    Hard links on the same volume avoid duplicating tens of GB. Subsequent
    downloads replace files atomically, so the archived repository is unchanged.
    """
    legacy_root = Path(legacy_root).resolve()
    old = legacy_root / "data/expansion" / VERSION
    root = location(cfg).resolve()
    if not old.joinpath("working.sqlite").exists():
        raise ValueError("Legacy expansion working.sqlite is missing")
    root.mkdir(parents=True, exist_ok=True)
    destination = root / "working.sqlite"
    if destination.exists():
        raise ValueError(
            "Working snapshot already exists; resume it instead of replacing it"
        )
    with sqlite3.connect(
        old.joinpath("working.sqlite").as_uri() + "?mode=ro", uri=True
    ) as source:
        with sqlite3.connect(destination) as target:
            source.backup(target)
    count = 0
    for src, dst in [
        (old / "sources", root / "sources"),
        (old / "text", root / "text"),
        (legacy_root / "data/raw/companyfacts", cfg.raw_dir / "companyfacts"),
        (legacy_root / "data/raw/edgar", cfg.edgar_cache),
    ]:
        for path in src.rglob("*"):
            if not path.is_file():
                continue
            target = (dst / path.relative_to(src)).resolve()
            if not target.is_relative_to(cfg.local_dir.resolve()):
                raise ValueError("Cache destination escaped the local workbench")
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(path, target)
            except OSError:
                shutil.copy2(path, target)
            count += 1
    with sqlite3.connect(destination) as conn:
        migrate_legacy_paths(cfg, conn)
    preserved = [
        cfg.ledger_dir / name
        for name in (
            "book_runs.jsonl",
            "decisions.jsonl",
            "book_source_manifests.jsonl",
        )
    ]
    write_json(
        root / "baseline_manifest.json",
        {
            "created_at": utcnow(),
            "version": VERSION,
            "source": str(old / "working.sqlite"),
            "snapshot_sha256": digest(destination),
            "preserved": [
                {"file": stored_path(cfg, p), "sha256": digest(p)}
                for p in preserved
                if p.exists()
            ],
            "migration": "consistent SQLite backup; immutable caches retained; source workbench unchanged",
        },
    )
    conn = connect(cfg)
    job(conn, "migration", "legacy_workbench", "completed", {"cache_files": count})
    conn.close()
    return {"cache_files": count, "working_snapshot": str(destination)}


def migrate_legacy_paths(cfg, conn):
    """Normalize both Windows and POSIX paths from the preserved workbench."""
    mappings = {
        "data/expansion/" + VERSION + "/": stored_path(cfg, location(cfg)) + "/",
        "data/raw/companyfacts/": stored_path(cfg, cfg.raw_dir / "companyfacts") + "/",
        "data/raw/edgar/": stored_path(cfg, cfg.edgar_cache) + "/",
    }

    def mapped(value):
        if not isinstance(value, str):
            return value
        path = value.replace("\\", "/")
        for old, new in mappings.items():
            if path.startswith(old):
                return new + path[len(old) :]
        return value

    for table, key, field in [
        ("disclosures", "accession", "text_file"),
        ("collection_sources", "url", "file"),
    ]:
        for identity, value in conn.execute(
            f"SELECT {key},{field} FROM {table}"
        ).fetchall():
            replacement = mapped(value)
            if replacement != value:
                conn.execute(
                    f"UPDATE {table} SET {field}=? WHERE {key}=?",
                    (replacement, identity),
                )
    for accession, body in conn.execute(
        "SELECT accession,source_json FROM disclosures"
    ).fetchall():
        sources = json.loads(body or "[]")
        changed = False
        for source in sources:
            if source.get("file") and mapped(source["file"]) != source["file"]:
                source["file"] = mapped(source["file"])
                changed = True
        if changed:
            conn.execute(
                "UPDATE disclosures SET source_json=? WHERE accession=?",
                (json.dumps(sources), accession),
            )
    conn.commit()


def job(conn, kind, key, status, detail=None):
    conn.execute(
        "INSERT OR REPLACE INTO collection_jobs VALUES (?,?,?,?,?)",
        (kind, key, status, utcnow(), json.dumps(detail or {}, allow_nan=False)),
    )
    conn.commit()


class SourceUnavailable(RuntimeError):
    pass


class SecArchive:
    def __init__(self, cfg, conn, offline=False):
        self.cfg, self.offline = cfg, offline
        db_path = conn.execute("PRAGMA database_list").fetchone()[2]
        self.conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.root = location(cfg) / "sources"
        self.root.mkdir(exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": cfg.section("edgar")["user_agent"],
                "Accept-Encoding": "gzip, deflate",
            }
        )
        self.last = 0.0
        self.denied = None
        self.failed = {}
        self.submission_indexes = {}
        self.db_lock = threading.RLock()
        self.rate_lock = threading.Lock()
        self.url_guard = threading.Lock()
        self.url_locks = {}
        self.issuer_locks = {}
        self.rate_db = location(cfg) / "sec_rate.sqlite"
        with sqlite3.connect(self.rate_db, timeout=30) as gate:
            gate.execute(
                "CREATE TABLE IF NOT EXISTS request_clock (id INTEGER PRIMARY KEY,next_at REAL)"
            )

    def rate_slot(self):
        """One four-request/second budget across all collection processes."""
        with sqlite3.connect(self.rate_db, timeout=30) as gate:
            gate.execute("BEGIN IMMEDIATE")
            old = gate.execute(
                "SELECT next_at FROM request_clock WHERE id=1"
            ).fetchone()
            at = max(time.time(), old[0] if old else 0)
            gate.execute(
                "INSERT OR REPLACE INTO request_clock VALUES (1,?)", (at + 0.25,)
            )
            gate.commit()
        time.sleep(max(0, at - time.time()))

    def get(self, url):
        with self.url_guard:
            lock = self.url_locks.setdefault(url, threading.Lock())
        with lock:
            return self._get(url)

    def _get(self, url):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {
            "www.sec.gov",
            "data.sec.gov",
            "efts.sec.gov",
        }:
            raise ValueError("Only public SEC sources are allowed")
        path = self.root / (hashlib.sha256(url.encode()).hexdigest() + ".gz")
        with self.db_lock:
            old = self.conn.execute(
                "SELECT * FROM collection_sources WHERE url=?", (url,)
            ).fetchone()
        if old and old["status"] == "archived" and path.exists():
            raw = gzip.decompress(path.read_bytes())
            if hashlib.sha256(raw).hexdigest() != old["sha256"]:
                raise SourceUnavailable("Archived source hash mismatch")
            return raw
        if url in self.failed:
            raise SourceUnavailable(self.failed[url])
        if (
            old
            and old["status"] == "unavailable"
            and any(
                s in (old["error"] or "") for s in ("exceeds 60MB", "404 Client Error")
            )
        ):
            raise SourceUnavailable(old["error"])
        if self.offline or self.denied:
            raise SourceUnavailable(self.denied or "not_cached")
        attempts = (old["attempts"] if old else 0) + 1
        try:
            self.rate_slot()
            if self.denied:
                raise SourceUnavailable(self.denied)
            response = self.session.get(url, timeout=(15, 45), stream=True)
            if response.status_code in {403, 429}:
                self.denied = f"SEC denied access with HTTP {response.status_code}; resume after access recovers"
                raise SourceUnavailable(self.denied)
            response.raise_for_status()
            chunks, size = [], 0
            with response:
                for chunk in response.iter_content(1024 * 1024):
                    size += len(chunk)
                    if size > 60 * 1024 * 1024:
                        raise SourceUnavailable(
                            "Source exceeds 60MB per-document limit; requires primary-document fallback"
                        )
                    chunks.append(chunk)
            raw = b"".join(chunks)
            if (
                not raw
                or b"<!doctype html" in raw[:100].lower()
                and b"access denied" in raw[:10000].lower()
            ):
                raise SourceUnavailable("Empty or denied content")
            temp = path.with_suffix(".tmp")
            temp.write_bytes(gzip.compress(raw, compresslevel=3, mtime=0))
            temp.replace(path)
            with self.db_lock:
                self.conn.execute(
                    "INSERT OR REPLACE INTO collection_sources VALUES (?,?,?,?,?,?,?,?)",
                    (
                        url,
                        hashlib.sha256(raw).hexdigest(),
                        stored_path(self.cfg, path),
                        len(raw),
                        utcnow(),
                        "archived",
                        None,
                        attempts,
                    ),
                )
                self.conn.commit()
            return raw
        except (requests.RequestException, SourceUnavailable) as exc:
            self.failed[url] = str(exc)
            with self.db_lock:
                self.conn.execute(
                    "INSERT OR REPLACE INTO collection_sources VALUES (?,?,?,?,?,?,?,?)",
                    (
                        url,
                        None,
                        None,
                        None,
                        utcnow(),
                        "unavailable",
                        str(exc)[:250],
                        attempts,
                    ),
                )
                self.conn.commit()
            raise SourceUnavailable(str(exc)) from exc

    def json(self, url):
        return json.loads(self.get(url))

    def primary_parts(self, hit):
        with self.url_guard:
            lock = self.issuer_locks.setdefault(str(hit["cik"]), threading.Lock())
        with lock:
            return self._primary_parts(hit)

    def _primary_parts(self, hit):
        """Use the official submissions index for oversized complete filings."""
        cik = str(int(hit["cik"]))
        acc = str(hit["accession"]).replace("-", "")
        if cik not in self.submission_indexes:
            doc = self.json(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
            rows = _iter_submission_rows(doc)
            self.submission_indexes[cik] = {
                "rows": {r["accession_nodash"]: r for r in rows},
                "parts": (doc.get("filings") or {}).get("files", []),
                "loaded": set(),
            }
        index = self.submission_indexes[cik]
        if acc not in index["rows"]:
            for part in index["parts"]:
                if part["name"] in index["loaded"] or not part.get(
                    "filingFrom", "0000"
                ) <= hit["filed_at"][:10] <= part.get("filingTo", "9999"):
                    continue
                rows = _iter_submission_rows(
                    self.json("https://data.sec.gov/submissions/" + part["name"])
                )
                index["rows"].update({r["accession_nodash"]: r for r in rows})
                index["loaded"].add(part["name"])
                if acc in index["rows"]:
                    break
        filing = index["rows"].get(acc)
        if not filing or not filing.get("primary"):
            raise SourceUnavailable(
                "No official primary-document mapping for this issuer/accession"
            )
        base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/"
        primary = base + filing["primary"]
        raw = self.get(primary)
        soup = BeautifulSoup(
            raw, "xml" if raw.lstrip().startswith(b"<?xml") else "lxml"
        )
        parts = [
            {
                "kind": hit["form"],
                "filename": filing["primary"],
                "text": visible_text(raw),
            }
        ]
        urls = [primary]
        for link in soup.find_all("a", href=True):
            href = link["href"].split("#", 1)[0]
            url = urljoin(primary, href)
            if (
                not href
                or not url.startswith(base)
                or not url.lower().endswith((".htm", ".html", ".txt"))
            ):
                continue
            if not re.search(r"ex.?99|ex.?3|press|release", href, re.I):
                continue
            if url in urls:
                continue
            body = self.get(url)
            parts.append(
                {
                    "kind": "EX-99",
                    "filename": href,
                    "text": visible_text(body),
                }
            )
            urls.append(url)
        return parts, [
            {
                "url": u,
                "sha256": hashlib.sha256(self.get(u)).hexdigest(),
                "raw_complete": False,
            }
            for u in urls
        ]


def public_clock(accept, filed):
    """Unknown dissemination waits until midnight following the filing day.

    This deliberately gives up same-day/pre-open entries unless a separately
    archived public-release timestamp is supplied. Acceptance is retained for
    audit but never promoted to verified public availability.
    """
    return (
        datetime.combine(
            date.fromisoformat(filed) + timedelta(days=1),
            datetime.min.time(),
            ZoneInfo("America/New_York"),
        ).isoformat(),
        "next_day_conservative_dissemination",
    )


def filing_parts(raw):
    text = raw.decode("utf-8", errors="replace")
    result = []
    for block in re.findall(r"<DOCUMENT>(.*?)</DOCUMENT>", text, re.S | re.I):
        kind = re.search(r"<TYPE>([^\r\n<]+)", block, re.I)
        name = re.search(r"<FILENAME>([^\r\n<]+)", block, re.I)
        kind = kind.group(1).strip() if kind else ""
        # Primary, releases, charter/financing and financial exhibits. Do not
        # parse binary graphic payloads as prose.
        if not (
            kind.upper().startswith(("EX-99", "EX-3", "EX-10", "EX-101"))
            or kind.upper() in FORMS
            or kind.upper().startswith(("10-", "20-F", "40-F"))
        ):
            continue
        payload = re.search(r"<TEXT>(.*?)(?:</TEXT>|$)", block, re.S | re.I)
        body = payload.group(1) if payload else block
        # HTML tags may separate the words in the phrase. The visible-text
        # classifier proves the relation; this prefilter only skips binaries.
        if not re.search(
            r"\breverse\b|\bconsolidation\b|\bADS\b|\bdepositary\b", body, re.I
        ):
            continue
        extracted = visible_text(body)
        result.append(
            {
                "kind": kind,
                "filename": name.group(1).strip() if name else None,
                "text": extracted,
            }
        )
    if not result:
        result = [
            {
                "kind": "unknown_primary",
                "filename": None,
                "text": visible_text(text),
            }
        ]
    return result


def classify_documents(parts, filed):
    """Per-document clauses avoid mixing a past split with a new release."""
    found = []
    for p in parts:
        if not re.search(SPLIT_MARKER, p["text"], re.I):
            continue
        body = re.sub(r"\s+", " ", p["text"])
        spans = []
        for match in re.finditer(SPLIT_MARKER, body, re.I):
            lo, hi = max(0, match.start() - 300), min(len(body), match.end() + 1000)
            if spans and lo <= spans[-1][1] and hi - spans[-1][0] <= 2600:
                spans[-1] = (spans[-1][0], hi)
            else:
                spans.append((lo, hi))
        for lo, hi in spans:
            clause = re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", body[lo:hi])
            audit = audit_clause(clause, filed, marker="(?:" + SPLIT_MARKER + ")")
            if audit["category"] == "unresolved_clause" and re.search(
                r"proposal|subject to (?:shareholder |stockholder )?approval",
                clause,
                re.I,
            ):
                audit.update(
                    category="authorization_or_proposal", eligible=True, reason=None
                )
            cancelled = parse_announcement(clause)["cancelled"]
            audit["document"] = p["filename"]
            audit["document_type"] = p["kind"]
            audit["source_offset"] = lo
            audit["ratio"] = audit.get("exact_ratio") or ratio(clause)
            if re.search(r"ADS|depositary", clause, re.I):
                number = r"(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|twenty|thirty|forty|fifty|hundred)"
                change = re.search(
                    r"from\s+(?:one|1)\s+ADS.{0,45}?(?:representing|for)\s+"
                    + number
                    + r"\s+ordinary\s+shares?.{0,100}?to\s+(?:one|1)\s+ADS.{0,45}?(?:representing|for)\s+"
                    + number
                    + r"\s+ordinary\s+shares?",
                    clause,
                    re.I,
                )
                if change:

                    def numeric(token):
                        return WORDS.get(
                            token.lower(),
                            100
                            if token.lower() == "hundred"
                            else float(token)
                            if token.replace(".", "", 1).isdigit()
                            else None,
                        )

                    old, new = map(numeric, change.groups())
                    if old and new:
                        audit["ratio"] = old / new
                        if old >= new:
                            audit.update(
                                category="unrelated_mention",
                                eligible=False,
                                reason="ADS_change_is_not_a_reverse_consolidation",
                            )
            if cancelled:
                audit.update(
                    category="cancelled_at_publication",
                    eligible=False,
                    reason="cancelled_at_publication",
                )
            found.append(audit)
    if not found:
        return {
            "category": "unrelated_mention",
            "eligible": False,
            "reason": "no_reverse_split_clause",
            "documents": [],
        }
    eligible = [a for a in found if a["eligible"]]
    # Conflicting schedules are not resolved by choosing a profitable date.
    schedules = {
        a.get("announced_ex_date") for a in eligible if a.get("announced_ex_date")
    }
    if len(schedules) > 1:
        return {
            "category": "unresolved_clause",
            "eligible": False,
            "reason": "conflicting_schedules",
            "documents": found,
        }
    selected = next(
        (a for a in eligible if a["category"] == "scheduled_action"),
        (eligible or found)[0],
    )
    return {**selected, "documents": found}


def process_hit(cfg, conn, archive, hit, *, persist=True):
    acc = str(hit["accession"]).replace("-", "")
    cik = str(int(hit["cik"]))
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{acc[:10]}-{acc[10:12]}-{acc[12:]}.txt"
    legacy = cfg.edgar_cache / cik.zfill(10) / (acc + ".txt")
    evidence = []
    try:
        raw = archive.get(url)
        parts = filing_parts(raw)
        evidence = [
            {
                "url": url,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "raw_complete": True,
            }
        ]
        review = "automated_requires_adjudication"
    except SourceUnavailable:
        if legacy.exists():
            text = legacy.read_text(encoding="utf-8", errors="replace")
            parts = [
                {
                    "kind": hit["form"],
                    "filename": "legacy_extracted_primary",
                    "text": text,
                }
            ]
            evidence = [
                {
                    "file": stored_path(cfg, legacy),
                    "sha256": digest(legacy),
                    "raw_complete": False,
                }
            ]
            review = "legacy_primary_only_exhibits_unavailable"
        else:
            parts, evidence = archive.primary_parts(hit)
            review = "primary_and_linked_exhibits_requires_adjudication"
    audit = classify_documents(parts, hit["filed_at"][:10])
    audit["classifier_version"] = CLASSIFIER_VERSION
    combined = "\n\n".join(p["text"] for p in parts)
    out = location(cfg) / "text" / cik.zfill(10)
    out.mkdir(parents=True, exist_ok=True)
    path = out / (acc + ".txt")
    temp = path.with_suffix(".part")
    temp.write_text(combined, encoding="utf-8")
    temp.replace(path)
    available, basis = public_clock(hit.get("accept_time"), hit["filed_at"][:10])
    record = (
        acc,
        cik,
        hit.get("ticker"),
        hit["form"],
        hit["filed_at"][:10],
        available,
        basis,
        audit["category"],
        audit.get("ratio"),
        audit.get("announced_ex_date"),
        int(audit["eligible"]),
        review,
        stored_path(cfg, path),
        json.dumps(evidence),
        json.dumps(audit),
    )
    prepared = {"record": record, "hit": hit, "audit": audit, "review": review}
    if persist:
        save_disclosure(conn, prepared)
        return audit
    return prepared


def save_disclosure(conn, prepared):
    record, hit, audit, review = (
        prepared[k] for k in ("record", "hit", "audit", "review")
    )
    conn.execute(
        "INSERT OR REPLACE INTO disclosures VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        record,
    )
    conn.execute(
        "UPDATE edgar_hits SET text_parsed=1,substantive=?,cancelled=?,parsed_ratio=?,parsed_ex_date=? WHERE accession=? AND form=?",
        (
            int(audit["eligible"]),
            int(audit["category"] == "cancelled_at_publication"),
            audit.get("ratio"),
            audit.get("announced_ex_date"),
            hit["accession"],
            hit["form"],
        ),
    )
    job(
        conn,
        "filing",
        record[0],
        "processed",
        {
            "stage": audit["category"],
            "raw_complete": review == "automated_requires_adjudication",
        },
    )


def pilot_sample(hits, count=50, seed=20261012):
    groups = defaultdict(list)
    for hit in hits:
        groups[(hit["filed_at"][:4], hit["form"], bool(hit.get("ticker")))].append(hit)
    rng = random.Random(seed)
    groups = {
        k: sorted(v, key=lambda h: h["accession"]) for k, v in sorted(groups.items())
    }
    for group in groups.values():
        rng.shuffle(group)
    selected = []
    while groups and len(selected) < count:
        for key in list(groups):
            selected.append(groups[key].pop())
            if not groups[key]:
                del groups[key]
            if len(selected) == count:
                break
    return selected


def collect_filings(
    cfg, *, offline=False, pilot=False, limit=None, start=None, end=None
):
    conn = connect(cfg)
    archive = SecArchive(cfg, conn, offline)
    hits = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM edgar_hits WHERE accession NOT IN (SELECT accession FROM disclosures) AND filed_at BETWEEN ? AND ? ORDER BY text_parsed DESC, CASE WHEN form LIKE '8-K%' THEN 0 WHEN form LIKE '6-K%' THEN 1 ELSE 2 END,filed_at,accession",
            (start or "0000", end or "9999"),
        )
    ]
    if pilot:
        hits = pilot_sample(hits)
        write_json(
            location(cfg) / "pilot_selection.json",
            {
                "seed": 20261012,
                "selection_basis": "year/form/ticker availability; no returns",
                "accessions": [h["accession"] for h in hits],
            },
        )
    if limit is not None:
        hits = hits[:limit]
    done = 0
    last_export = 0

    # A bounded prefetch keeps slow complete filings from holding up unrelated
    # cache hits. All workers share the same four-request/second budget.
    def prefetched():
        if offline:
            for h in hits:
                try:
                    yield h, process_hit(cfg, None, archive, h, persist=False), None
                except (SourceUnavailable, ValueError, TypeError) as exc:
                    yield h, None, exc
            return
        with ThreadPoolExecutor(max_workers=8) as pool:
            pending = {}
            queue = iter(hits)

            def submit_one():
                h = next(queue, None)
                if h is not None:
                    pending[
                        pool.submit(process_hit, cfg, None, archive, h, persist=False)
                    ] = h

            for _ in range(12):
                submit_one()
            while pending:
                completed, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in completed:
                    h = pending.pop(future)
                    try:
                        prepared = future.result()
                        error = None
                    except (SourceUnavailable, ValueError, TypeError) as exc:
                        prepared = None
                        error = exc
                    yield h, prepared, error
                    if archive.denied:
                        for p in pending:
                            p.cancel()
                        return
                    submit_one()

    for hit, prepared, error in prefetched():
        try:
            if error:
                raise error
            save_disclosure(conn, prepared)
            done += 1
        except (SourceUnavailable, ValueError, TypeError) as exc:
            job(
                conn,
                "filing",
                hit["accession"],
                "unavailable",
                {"error": str(exc)[:250]},
            )
            if archive.denied:
                break
        if done - last_export >= 100:
            print(
                f"Filings processed this batch: {done}; remaining queued: {len(hits) - done}",
                flush=True,
            )
            export_coverage(cfg, conn)
            last_export = done
    job(
        conn,
        "batch",
        "filings",
        "access_unavailable" if archive.denied else "completed_batch",
        {
            "processed": done,
            "selected": len(hits),
            "offline": offline,
            "error": archive.denied,
            "start": start,
            "end": end,
        },
    )
    export_coverage(cfg, conn)
    archive.conn.close()
    conn.close()
    return {"processed": done, "selected": len(hits), "access_error": archive.denied}


def reclassify_cached(cfg):
    """Reapply the bounded clause parser to preserved text, without downloads."""
    conn = connect(cfg)
    migrate_legacy_paths(cfg, conn)
    rows = [
        dict(r)
        for r in conn.execute("SELECT * FROM disclosures ORDER BY filed_at,accession")
    ]
    counts = Counter()
    for row in rows:
        if (
            json.loads(row["audit_json"] or "{}").get("classifier_version")
            == CLASSIFIER_VERSION
        ):
            counts["current"] += 1
            continue
        if not row.get("text_file"):
            counts["text_unavailable"] += 1
            continue
        path = cfg.repo_root / row["text_file"]
        if not path.exists():
            counts["text_unavailable"] += 1
            continue
        parsed = classify_documents(
            [
                {
                    "text": path.read_text(encoding="utf-8", errors="replace"),
                    "kind": "archived_combined_text",
                    "filename": row["accession"],
                }
            ],
            row["filed_at"],
        )
        parsed["classifier_version"] = CLASSIFIER_VERSION
        parsed["input_text_sha256"] = digest(path)
        conn.execute(
            "UPDATE disclosures SET stage=?,ratio=?,scheduled=?,eligible=?,audit_json=? WHERE accession=?",
            (
                parsed["category"],
                parsed.get("ratio"),
                parsed.get("announced_ex_date"),
                int(parsed["eligible"]),
                json.dumps(parsed),
                row["accession"],
            ),
        )
        conn.commit()
        counts["reclassified"] += 1
        if counts["reclassified"] % 1000 == 0:
            print(
                f"Cached disclosures reclassified: {counts['reclassified']:,}",
                flush=True,
            )
    job(conn, "reclassification", CLASSIFIER_VERSION, "completed", dict(counts))
    export_coverage(cfg, conn)
    conn.close()
    return dict(counts)


def submissions(cfg, conn, archive, cik, start="2015-01-01", end="2026-10-08"):
    cik = str(int(cik))
    url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    doc = archive.json(url)
    rows = _iter_submission_rows(doc)
    for part in (doc.get("filings") or {}).get("files") or []:
        if part.get("filingTo", "9999") < start or part.get("filingFrom", "0000") > end:
            continue
        rows.extend(
            _iter_submission_rows(
                archive.json(f"https://data.sec.gov/submissions/{part['name']}")
            )
        )
    seen = set()
    selected = []
    for row in rows:
        acc = row["accession_nodash"]
        if (
            not acc
            or acc in seen
            or not start <= str(row["filed_at"] or "") <= end
            or row["form"] not in FORMS
        ):
            continue
        seen.add(acc)
        selected.append(
            {
                **row,
                "cik": cik,
                "accession": acc,
                "name": doc.get("name"),
                "ticker": None,
            }
        )
    # Submission headers are discovery only. Text must prove an announcement.
    store_edgar_hits(conn, selected)
    job(
        conn,
        "submissions",
        cik,
        "completed",
        {"start": start, "end": end, "filings": len(selected)},
    )
    return len(selected)


def discover_history(
    cfg,
    start="2005-01-01",
    end=None,
    *,
    offline=False,
    query=None,
    forms=FORMS,
    job_kind="search",
):
    """Monthly, per-form search windows and quarterly independent indexes.

    The index is a coverage inventory; it does not turn every filing into a
    split. Searches must exhaust reported hits or retain an incomplete flag.
    """
    end = end or date.today().isoformat()
    conn = connect(cfg)
    archive = SecArchive(cfg, conn, offline)
    from .ingest_splits import EDGAR_REVERSE_SPLIT_QUERY

    query = query or EDGAR_REVERSE_SPLIT_QUERY
    cursor = date.fromisoformat(start)
    finish = date.fromisoformat(end)
    windows = []
    while cursor <= finish:
        following = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        last = min(finish, following - timedelta(days=1))
        for form in forms:
            windows.append((cursor.isoformat(), last.isoformat(), form))
        cursor = following
    queue = list(windows)
    total_added = 0
    visited = 0
    while queue:
        lo, hi, form = queue.pop(0)
        key = f"{lo}/{hi}/{form}"
        old = conn.execute(
            "SELECT status FROM collection_jobs WHERE kind=? AND key=?", (job_kind, key)
        ).fetchone()
        if old and old["status"] == "completed":
            continue
        try:
            offset = 0
            collected = []
            while True:
                params = {
                    "q": query,
                    "dateRange": "custom",
                    "startdt": lo,
                    "enddt": hi,
                    "forms": form,
                    "from": offset,
                    "size": 100,
                }
                data = archive.json(
                    "https://efts.sec.gov/LATEST/search-index?" + urlencode(params)
                )
                total = data.get("hits", {}).get("total", {})
                n = (
                    total.get("value", 0)
                    if isinstance(total, dict)
                    else int(total or 0)
                )
                relation = (
                    total.get("relation", "eq") if isinstance(total, dict) else "eq"
                )
                if n >= 10000 or relation != "eq":
                    if lo == hi:
                        job(
                            conn,
                            job_kind,
                            key,
                            "incomplete_result_window",
                            {"reported": n},
                        )
                    else:
                        middle = (
                            date.fromisoformat(lo)
                            + (date.fromisoformat(hi) - date.fromisoformat(lo)) // 2
                        )
                        queue[:0] = [
                            (lo, middle.isoformat(), form),
                            ((middle + timedelta(days=1)).isoformat(), hi, form),
                        ]
                        job(conn, job_kind, key, "subdivided", {"reported": n})
                    break
                raw_hits = data.get("hits", {}).get("hits", [])
                collected.extend(_hits_from_rows(raw_hits, form))
                offset += len(raw_hits)
                if offset >= n or not raw_hits:
                    if offset < n:
                        job(
                            conn,
                            job_kind,
                            key,
                            "incomplete_page",
                            {"received": offset, "reported": n},
                        )
                    else:
                        store_edgar_hits(conn, collected)
                        job(
                            conn,
                            job_kind,
                            key,
                            "completed",
                            {"received": offset, "reported": n, "query": query},
                        )
                        total_added += len(collected)
                    break
        except (SourceUnavailable, ValueError) as exc:
            job(conn, job_kind, key, "unavailable", {"error": str(exc)[:250]})
            if archive.denied:
                break
        visited += 1
        if visited % 50 == 0:
            print(
                f"Discovery windows processed: {visited}; queued: {len(queue)}; hit rows: {total_added:,}",
                flush=True,
            )
            export_coverage(cfg, conn)
    # A coverage source independent of current ticker membership.
    for year in range(int(start[:4]), int(end[:4]) + 1):
        for quarter in range(1, 5):
            q_start = date(year, 3 * quarter - 2, 1)
            if q_start > finish or date(year, 3 * quarter, 1) + timedelta(
                days=31
            ) < date.fromisoformat(start):
                continue
            url = f"https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/master.idx"
            key = f"{year}/QTR{quarter}"
            if archive.denied:
                job(
                    conn, "quarter_index", key, "unavailable", {"error": archive.denied}
                )
                continue
            try:
                raw = archive.get(url).decode("utf-8", errors="replace")
                counts = Counter()
                for line in raw.splitlines():
                    cols = line.split("|")
                    if len(cols) == 5 and cols[0].isdigit() and start <= cols[3] <= end:
                        counts[cols[2]] += 1
                job(
                    conn,
                    "quarter_index",
                    key,
                    "completed",
                    {
                        "forms": dict(counts),
                        "all_filings": sum(counts.values()),
                        "url": url,
                    },
                )
            except SourceUnavailable as exc:
                job(
                    conn, "quarter_index", key, "unavailable", {"error": str(exc)[:250]}
                )
    export_coverage(cfg, conn)
    archive.conn.close()
    conn.close()
    return {"discovered_hit_rows": total_added, "access_error": archive.denied}


def episodes(disclosures):
    groups = defaultdict(list)
    output = []
    for d in sorted(disclosures, key=lambda x: (x["filed_at"], x["accession"])):
        if not d["eligible"]:
            continue
        key = (d["cik"], d.get("ticker") or "unmapped")
        group = groups[key]
        previous = group[-1] if group else None
        days = (
            (
                date.fromisoformat(d["filed_at"])
                - date.fromisoformat(previous["last_filed"])
            ).days
            if previous
            else 9999
        )
        # Same schedule is strong evidence. Unscheduled merging is explicitly
        # provisional and never treats repetitions as independent companies.
        ratio_ok = previous and (
            not d.get("ratio")
            or not previous.get("ratio")
            or abs(float(d["ratio"]) / float(previous["ratio"]) - 1) < 0.001
        )
        same = ratio_ok and (
            d.get("scheduled")
            and previous.get("scheduled") == d["scheduled"]
            or not d.get("scheduled")
            and not previous.get("scheduled")
            and days <= 90
            or d.get("scheduled")
            and not previous.get("scheduled")
            and days <= 90
        )
        if same:
            ep = previous
            ep["linkage_review"] = "provisional_chronological_linkage"
        else:
            ep = {
                "id": f"{d['cik']}/{d['accession']}",
                "cik": d["cik"],
                "ticker": d.get("ticker"),
                "first_filed": d["filed_at"],
                "scheduled": d.get("scheduled"),
                "ratio": d.get("ratio"),
                "disclosures": [],
                "linkage_review": "automated_requires_adjudication",
            }
            group.append(ep)
            output.append(ep)
        ep["disclosures"].append(d["accession"])
        ep["last_filed"] = d["filed_at"]
        ep["scheduled"] = d.get("scheduled") or ep.get("scheduled")
        ep["ratio"] = d.get("ratio") or ep.get("ratio")
    return output


def export_coverage(cfg, conn=None):
    own = conn is None
    conn = conn or connect(cfg)
    hits = conn.execute("SELECT count(*),sum(text_parsed=1) FROM edgar_hits").fetchone()
    ds = [
        dict(r)
        for r in conn.execute(
            "SELECT accession,cik,ticker,filed_at,scheduled,ratio,eligible,stage FROM disclosures ORDER BY filed_at,accession"
        )
    ]
    eps = episodes(ds)
    stages = Counter(d["stage"] for d in ds)
    jobs = Counter(
        (r["kind"], r["status"])
        for r in conn.execute("SELECT kind,status FROM collection_jobs")
    )
    forms = [
        dict(r)
        for r in conn.execute(
            "SELECT form,count(*) AS discovered,sum(accession IN (SELECT accession FROM disclosures)) AS processed FROM edgar_hits GROUP BY form ORDER BY count(*) DESC"
        )
    ]
    years = [
        dict(r)
        for r in conn.execute(
            "SELECT substr(filed_at,1,4) AS year,count(*) AS discovered,sum(accession IN (SELECT accession FROM disclosures)) AS processed FROM edgar_hits GROUP BY year ORDER BY year"
        )
    ]
    current = location(cfg) / "replay_summary.json"
    replay_info = (
        json.loads(current.read_text(encoding="utf-8")) if current.exists() else None
    )
    errors = [
        dict(r)
        for r in conn.execute(
            "SELECT kind,key,status,detail,updated_at FROM collection_jobs WHERE status IN ('unavailable','access_unavailable','incomplete_page','incomplete_result_window') ORDER BY updated_at DESC LIMIT 100"
        )
    ]
    baseline = json.loads(
        (location(cfg) / "baseline_manifest.json").read_text(encoding="utf-8")
    )
    preserved = [
        {
            **p,
            "unchanged": (cfg.repo_root / p["file"]).exists()
            and digest(cfg.repo_root / p["file"]) == p["sha256"],
        }
        for p in baseline["preserved"]
        if p["file"] != "data/strategy_decisions.sqlite"
    ]
    data = {
        "schema_version": "expansion_coverage.v2",
        "built_at": utcnow(),
        "version": VERSION,
        "inventory": {
            "filing_hits": hits[0],
            "legacy_or_new_text_parsed": hits[1] or 0,
            "processed_disclosures": len(ds),
            "pending_hits": hits[0] - len(ds),
            "provisional_episodes": len(eps),
            "episode_issuers": len({e["cik"] for e in eps}),
            "eligible_disclosures": sum(d["eligible"] for d in ds),
            "raw_archived_sources": conn.execute(
                "SELECT count(*) FROM collection_sources WHERE status='archived'"
            ).fetchone()[0],
            "imported_evidence": conn.execute(
                "SELECT count(*) FROM evidence_imports"
            ).fetchone()[0],
        },
        "by_form": forms,
        "by_year": years,
        "stages": dict(stages),
        "jobs": [
            {"kind": k, "status": s, "count": n} for (k, s), n in sorted(jobs.items())
        ],
        "errors": errors,
        "replay": replay_info,
        "preserved": preserved,
        "dependencies": [
            {
                "item": "Historical quotes and retired-security mappings",
                "status": "needs_source_or_import",
                "action": "Import a documented 20-event supplier pilot",
            },
            {
                "item": "Historical account borrow permission",
                "status": "unavailable_until_imported",
                "action": "Import dated approval, reference, quantity and fee records",
            },
            {
                "item": "Analyst event adjudication and custom financial facts",
                "status": "requires_source_review",
                "action": "Record sourced revisions; automated episodes remain provisional",
            },
            {
                "item": "Whole SSI portfolio",
                "status": "needs_dated_holdings_and_NAV",
                "action": "Import reconciled holdings, owner flows and NAV",
            },
        ],
        "limits": [
            "Search hits are not independent events",
            "SEC acceptance is not verified public release time",
            "Corporate-action reconstruction and episode links require adjudication",
            "No $1 price exclusion in the new experiment",
            "No protected broker or Theta resources used",
        ],
        "links": {
            "ssi": "https://single-stock-investments-2wt.pages.dev/",
            "short_alpha": "https://single-stock-investments-2wt.pages.dev/#/ideas/short-alpha",
            "furnace": "https://github.com/magis-capital-partners/single-stock-investments/blob/main/_system/frameworks/short_alpha_filing_furnace.md",
        },
    }
    public = cfg.public_dir
    public.mkdir(parents=True, exist_ok=True)
    write_json(public / "expansion.json", data)
    write_json(location(cfg) / "coverage.json", data)
    # Full records stay in SQLite; publish derived, sharded metadata once per
    # completed study rather than rewriting large files at every checkpoint.
    if own:
        conn.close()
    return data
