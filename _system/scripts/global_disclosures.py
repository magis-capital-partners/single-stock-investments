#!/usr/bin/env python3
"""Dated international disclosures from public funds and the private corpus.

Disclosures never supplement a 13F denominator or imply an exit by omission.
Original text, source membership and evidence stay in the private archive.
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
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from pathlib import Path
from urllib.parse import urlencode, urlparse
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system/scripts"))
from investor_history import ARCHIVE, iso, now, write_json
from sec_client import get_bytes, get_json
from vault_paths import letters_root, resolve_ref_to_path

SOURCES = ROOT / "_system/reference/investors/disclosure_sources.json"
EXCHANGES = {
    "HK": ".HK",
    "LN": ".L",
    "JP": ".T",
    "JT": ".T",
    "FP": ".PA",
    "GY": ".DE",
    "NA": ".AS",
    "SS": ".ST",
    "AU": ".AX",
    "SM": ".MC",
    "SW": ".SW",
    "KS": ".KS",
    "US": "",
}


def local(node):
    return node.tag.rsplit("}", 1)[-1]


def child_text(node, name, default=""):
    return next(
        ((x.text or "").strip() for x in node.iter() if local(x) == name), default
    )


def number(value):
    if value in (None, "", "N/A", "—", "-"):
        return None
    return float(str(value).replace(",", "").replace("%", "").strip())


def normalize_symbol(symbol, exchange=""):
    symbol = symbol.strip().upper()
    if exchange == "HK" and symbol.isdigit():
        symbol = symbol.zfill(4)
    suffix = EXCHANGES.get(exchange, "")
    return symbol if not suffix or symbol.endswith(suffix) else symbol + suffix


@contextmanager
def public_cache():
    archive = ARCHIVE / "public-cache.sqlite"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(archive, timeout=60)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.execute(
            "CREATE TABLE IF NOT EXISTS documents (url TEXT PRIMARY KEY,sha256 TEXT NOT NULL,content_gzip BLOB NOT NULL)"
        )
        yield db


def public_document(url, path):
    """Preserve original public XML across checkpoint/CI continuations."""
    with public_cache() as db:
        found = db.execute(
            "SELECT sha256,content_gzip FROM documents WHERE url=?", (url,)
        ).fetchone()
        if found:
            raw = gzip.decompress(found[1])
            if hashlib.sha256(raw).hexdigest() != found[0]:
                raise ValueError("Preserved public document checksum mismatch")
            return raw
        raw = path.read_bytes() if path.exists() else get_bytes(url)
        ET.fromstring(raw)
        with db:
            db.execute(
                "INSERT INTO documents VALUES(?,?,?)",
                (url, hashlib.sha256(raw).hexdigest(), gzip.compress(raw, mtime=0)),
            )
        return raw


def parse_nport(raw, manager_id, *, source_url):
    root = ET.fromstring(raw)
    period = iso(child_text(root, "repPdDate"))
    if not period:
        raise ValueError("N-PORT has no reporting date")
    series_id = child_text(root, "seriesId")
    series_name = child_text(root, "seriesName")
    if not series_id or not series_name:
        raise ValueError("N-PORT fund vehicle is unidentified")
    positions = []
    for node in root.iter():
        if local(node) != "invstOrSec":
            continue
        identifiers = {}
        for item in node.iter():
            if local(item) in {"isin", "ticker", "other"}:
                value = item.attrib.get("value") or (item.text or "").strip()
                if value:
                    identifiers[local(item)] = value
        positions.append(
            {
                "issuer": child_text(node, "name"),
                "title_of_class": child_text(node, "title"),
                "cusip": child_text(node, "cusip"),
                "isin": identifiers.get("isin"),
                "ticker": identifiers.get("ticker", ""),
                "shares": number(child_text(node, "balance")),
                "unit": child_text(node, "units"),
                "currency": child_text(node, "curCd"),
                "value_usd": number(child_text(node, "valUSD")),
                "weight_pct": number(child_text(node, "pctVal")),
                "weight_basis": "fund_net_assets",
                "country": child_text(node, "invCountry"),
                "asset_category": child_text(node, "assetCat"),
                "position_side": child_text(node, "payOffProf") or None,
                "source_kind": "nport",
            }
        )
    if not positions and not any(local(node) == "invstOrSecs" for node in root.iter()):
        raise ValueError("N-PORT has no investment rows; retained for review")
    return {
        "manager_id": manager_id,
        "vehicle_id": series_id,
        "vehicle_name": series_name,
        "period_end": period,
        "filed_at": None,
        "source_kind": "nport",
        "source_url": source_url,
        "partial": False,
        "scope": "single_registered_fund",
        "positions": positions,
    }


def parse_holdings_csv(raw, source):
    columns = source["columns"]
    rows = []
    periods = set()
    for item in csv.DictReader(
        io.StringIO(raw.decode(source.get("encoding", "utf-8-sig")))
    ):
        row = {key: item.get(column, "").strip() for key, column in columns.items()}
        period = iso(row.pop("period_end", None) or source.get("period_end"))
        if not period:
            raise ValueError("Published holdings CSV requires an explicit as-of date")
        periods.add(period)
        if not row.get("issuer") and not row.get("ticker") and not row.get("isin"):
            continue
        for key in ("shares", "value_usd", "weight_pct"):
            row[key] = number(row.get(key))
        row["weight_basis"] = source.get("weight_basis", "unspecified_disclosed_weight")
        row["source_kind"] = "published_holdings"
        rows.append(row)
    if len(periods) != 1 or not rows:
        raise ValueError("CSV must contain a non-empty, single-date fund snapshot")
    return {
        "manager_id": source["manager_id"],
        "vehicle_id": source["vehicle_id"],
        "vehicle_name": source["vehicle_name"],
        "period_end": next(iter(periods)),
        "source_kind": "published_holdings",
        "source_url": source["url"],
        "partial": source.get("partial", True),
        "scope": "single_fund_disclosure",
        "positions": rows,
    }


HELD = re.compile(
    r"\b(?:we (?:own|hold|bought|purchased|initiated|added)|our (?:position|holding|investment)|largest holding|long position|new position)\b",
    re.IGNORECASE,
)
EXCLUDED = re.compile(
    r"\b(?:exited|sold (?:all|out|the (?:entire|remaining))|no longer|used to|previously (?:held|owned)|short(?:ed|ing)?|benchmark|competitor)\b",
    re.IGNORECASE,
)
TABLE_HEADING = re.compile(
    r"(?:top\s+(?:\d+|ten|five)\s+(?:holdings|positions)|(?:holdings|positions)\s+as\s+(?:of|at)|portfolio\s+(?:holdings|composition)|schedule of investments)",
    re.IGNORECASE,
)


def extract_document_positions(text, mentions=()):
    """Only explicit held claims and holdings-table rows; unknown weights stay null."""
    positions = {}
    for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
        if not HELD.search(sentence) or EXCLUDED.search(sentence):
            continue
        for match in re.finditer(
            r"\(([A-Z0-9][A-Z0-9.-]{0,14})(?:\s+(HK|LN|JP|JT|FP|GY|NA|SS|CN|AU|SM|SW|KS|US))?\)",
            sentence,
        ):
            ticker = normalize_symbol(match[1], match[2] or "")
            positions[ticker] = {
                "ticker": ticker,
                "issuer": ticker,
                "weight_pct": None,
                "weight_basis": None,
                "source_kind": "fund_disclosure",
                "evidence_quote": sentence.strip(),
            }
    for mention in mentions:
        ticker = (mention.get("ticker") or "").strip()
        commentary = mention.get("commentary") or mention.get("thesis") or ""
        action = (mention.get("action") or "").lower()
        if not ticker or action in {"exit", "sell", "short", "watchlist"}:
            continue
        if not HELD.search(commentary) or EXCLUDED.search(commentary):
            continue
        positions[ticker] = {
            "ticker": ticker,
            "issuer": mention.get("company") or ticker,
            "weight_pct": None,
            "weight_basis": None,
            "source_kind": "fund_disclosure",
            "evidence_quote": commentary,
        }
    remaining = 0
    for line in text.splitlines():
        if TABLE_HEADING.search(line):
            remaining = 45
            continue
        if not remaining:
            continue
        remaining -= 1
        if len(line) > 220 or EXCLUDED.search(line):
            continue
        match = re.match(
            r"^\s*(?:\d+[.)]\s+)?(?P<name>[A-Za-z][^%]{2,130}?)\s+(?P<weight>\d{1,2}(?:\.\d+)?)\s*%\s*$",
            line,
        )
        if not match:
            match = re.match(
                r"^\s*(?P<weight>\d{1,2}(?:\.\d+)?)\s*%\s+(?P<name>[A-Za-z][^%]{2,130})\s*$",
                line,
            )
        if not match:
            continue
        name = match["name"].strip()
        if re.search(
            r"\b(return|performance|index|net exposure|gross exposure|total|NAV)\b",
            name,
            re.IGNORECASE,
        ):
            continue
        symbol = re.search(
            r"\(([A-Z0-9][A-Z0-9.-]{0,14})(?:\s+(HK|LN|JP|JT|FP|GY|NA|SS|CN|AU|SM|SW|US))?\)",
            name,
        )
        ticker = normalize_symbol(symbol[1], symbol[2] or "") if symbol else ""
        key = ticker or "issuer:" + name.lower()
        positions[key] = {
            "issuer": name,
            "ticker": ticker,
            "weight_pct": float(match["weight"]),
            "weight_basis": "unspecified_disclosed_weight",
            "source_kind": "fund_disclosure",
            "evidence_quote": line.strip(),
        }
    return list(positions.values())


def corpus_disclosures(corpus, universe):
    document = json.loads(corpus.read_text(encoding="utf-8-sig"))
    from fund_letters import verified_date

    output = []
    review = []
    for entry in document.get("letters", []):
        if not entry.get("letter_eligible") or entry.get("document_type") not in {
            "investor_letter",
            "fund_report",
        }:
            continue
        manager_id = universe["source_ids"].get(entry.get("fund_id"))
        if not manager_id:
            review.append(
                {
                    "fund_id": entry.get("fund_id"),
                    "reason": "Manager identity not linked",
                }
            )
            continue
        ref = entry.get("source_file") or ""
        path = resolve_ref_to_path(ref)
        if not path or not path.is_file():
            suffix = ref.removeprefix("_system/reference/superinvestor-letters/")
            candidate = (corpus.parent / suffix).resolve()
            if candidate.is_relative_to(corpus.parent.resolve()):
                path = candidate
        if not path or not path.is_file():
            review.append(
                {
                    "manager_id": manager_id,
                    "reason": "Source text unavailable",
                    "source_ref": ref,
                }
            )
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        positions = extract_document_positions(text, entry.get("positions", []))
        if not positions:
            continue
        quarter = entry.get("quarter")
        date_source = entry.get("date_source") or ""
        dated = verified_date(entry)
        doc_id = (
            entry.get("canonical_document_id")
            or hashlib.sha256(ref.encode()).hexdigest()[:24]
        )
        output.append(
            {
                "id": doc_id,
                "manager_id": manager_id,
                "vehicle_id": entry["fund_id"],
                "vehicle_name": entry["fund"],
                "quarter": quarter,
                "period_end": None,
                "disclosed_at": dated,
                "date_basis": date_source,
                "source_kind": "fund_disclosure",
                "source_ref": ref,
                "source_url": "/fund-letters/?" + urlencode({"fund": entry["fund_id"]}),
                "partial": True,
                "scope": "explicitly_disclosed_positions",
                "positions": positions,
            }
        )
    return output, review


def nport_filings(cik, query=None, *, form="NPORT-P"):
    if query:
        found = {}
        offset = 0
        while True:
            params = {
                "q": f'"{query}"',
                "forms": form,
                "ciks": f"{int(cik):010d}",
                "dateRange": "custom",
                "startdt": "2019-01-01",
                "enddt": now()[:10],
                "from": offset,
                "size": 100,
            }
            result = get_json(
                "https://efts.sec.gov/LATEST/search-index?" + urlencode(params)
            )
            hits = result.get("hits", {}).get("hits", [])
            if not hits:
                break
            for hit in hits:
                source = hit.get("_source", {})
                if source.get("file_type") not in {"NPORT-P", "NPORT-P/A"}:
                    continue
                if str(int(cik)) not in {str(int(x)) for x in source.get("ciks", [])}:
                    continue
                accession = source["adsh"]
                found[accession] = {
                    "accession": accession,
                    "filed_at": source["file_date"],
                    "form": source["file_type"],
                    "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/primary_doc.xml",
                }
            offset += len(hits)
            total = result.get("hits", {}).get("total", {})
            total = total.get("value", offset) if isinstance(total, dict) else total
            if offset >= total:
                break
        if form == "NPORT-P":
            found.update(
                {
                    filing["accession"]: filing
                    for filing in nport_filings(cik, query, form="NPORT-P/A")
                }
            )
        return sorted(found.values(), key=lambda r: (r["filed_at"], r["accession"]))
    main = get_json(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
    block = main.get("filings", {})
    blocks = [block.get("recent", {})]
    for page in block.get("files", []):
        blocks.append(get_json("https://data.sec.gov/submissions/" + page["name"]))
    filings = {}
    for part in blocks:
        for i, filing_form in enumerate(part.get("form", [])):
            if filing_form not in {"NPORT-P", "NPORT-P/A"}:
                continue
            accession = part["accessionNumber"][i]
            primary = part["primaryDocument"][i]
            if "/" in primary:
                primary = primary.rsplit("/", 1)[-1]
            filings[accession] = {
                "accession": accession,
                "filed_at": part["filingDate"][i],
                "form": filing_form,
                "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{primary}",
            }
    return sorted(filings.values(), key=lambda r: (r["filed_at"], r["accession"]))


def load_nport(source, filing):
    cache = ARCHIVE / "nport" / (filing["accession"] + ".xml")
    parsed = parse_nport(
        public_document(filing["url"], cache),
        source["manager_id"],
        source_url=filing["url"],
    )
    if source.get("series_ids") and parsed["vehicle_id"] not in source["series_ids"]:
        return None
    if (
        source.get("series_name_contains")
        and source["series_name_contains"].lower() not in parsed["vehicle_name"].lower()
    ):
        return None
    links = source.get("series_links", {}).get(parsed["vehicle_id"], [])
    eligible = [
        link
        for link in links
        if (
            not link["appointment_start"]
            or link["appointment_start"] <= parsed["period_end"]
        )
        and (
            not link["appointment_end"]
            or parsed["period_end"] <= link["appointment_end"]
        )
    ]
    if links and (not eligible):
        return None
    if eligible:
        before = [
            link for link in eligible if link["observed_at"] <= parsed["period_end"]
        ]
        relationship = (
            max(before, key=lambda row: row["observed_at"])
            if before
            else min(eligible, key=lambda row: row["observed_at"])
        )
        parsed["adviser_relationship_observed_at"] = relationship["observed_at"]
        parsed["adviser_relationship_source"] = relationship["source_url"]
    parsed.update(
        {
            "id": filing["accession"],
            "filed_at": filing["filed_at"],
            "form": filing["form"],
        }
    )
    return parsed


def public_disclosures(sources, *, deadline=None, workers=4):
    output, review = [], []
    with public_cache():
        pass  # Initialize WAL before parallel downloads open their connections.
    for source in sources:
        print(
            f"Reading public funds: {source['manager_id']} ({source.get('cik', source['kind'])})",
            flush=True,
        )
        if deadline and time.monotonic() >= deadline:
            review.append(
                {
                    "manager_id": source["manager_id"],
                    "reason": "Public source awaits next checkpoint continuation",
                }
            )
            continue
        try:
            if source["kind"] == "nport":
                if source.get("queries"):
                    discovered = {}
                    for query in source["queries"]:
                        if deadline and time.monotonic() >= deadline:
                            break
                        for filing in nport_filings(source["cik"], query):
                            discovered[filing["accession"]] = filing
                    filings = sorted(
                        discovered.values(),
                        key=lambda row: (row["filed_at"], row["accession"]),
                    )
                else:
                    filings = nport_filings(source["cik"], source.get("query"))
                if not filings:
                    raise ValueError(
                        "No registered-fund filings discovered for configured source"
                    )

                def read_one(filing, source=source):
                    if deadline and time.monotonic() >= deadline:
                        return None, None
                    try:
                        return load_nport(source, filing), None
                    except (OSError, ValueError, KeyError, ET.ParseError) as exc:
                        return None, {
                            "manager_id": source["manager_id"],
                            "accession": filing["accession"],
                            "reason": str(exc),
                        }

                with ThreadPoolExecutor(max_workers=workers) as pool:
                    for parsed, error in pool.map(read_one, filings):
                        if error:
                            review.append(error)
                        elif parsed:
                            output.append(parsed)
                if deadline and time.monotonic() >= deadline:
                    review.append(
                        {
                            "manager_id": source["manager_id"],
                            "reason": "Public source awaits next checkpoint continuation",
                        }
                    )
            elif source["kind"] == "csv":
                url = source["url"]
                if urlparse(url).scheme != "https":
                    raise ValueError("Published fund source must use HTTPS")
                parsed = parse_holdings_csv(get_bytes(url), source)
                parsed["id"] = hashlib.sha256(
                    (url + parsed["period_end"]).encode()
                ).hexdigest()[:24]
                output.append(parsed)
            else:
                raise ValueError(
                    f"Unsupported public disclosure source: {source['kind']}"
                )
        except (OSError, ValueError, KeyError, ET.ParseError) as exc:
            review.append({"manager_id": source["manager_id"], "reason": str(exc)})
    return output, review


def publish(
    disclosures,
    universe,
    *,
    data=ROOT / "dashboard/data/holdings",
    review=(),
    preserve=True,
    save_archive=True,
):
    disclosures = list(
        {
            (document["manager_id"], document["id"]): document
            for document in disclosures
        }.values()
    )
    private = ARCHIVE / "disclosures.json"
    if save_archive:
        write_json(
            private,
            {"generated_at": now(), "disclosures": disclosures, "review": list(review)},
        )
    by_manager = defaultdict(list)
    for document in disclosures:
        public = {
            key: value for key, value in document.items() if key not in {"source_ref"}
        }
        public["positions"] = [
            {key: value for key, value in row.items() if key != "evidence_quote"}
            for row in document["positions"]
        ]
        by_manager[document["manager_id"]].append(public)
    from thirteenf_core import quarter_from_period

    def document_quarter(document):
        value = (
            document.get("quarter")
            or quarter_from_period(document.get("period_end"))
            or quarter_from_period(document.get("disclosed_at"))
        )
        return value if re.fullmatch(r"\d{4}Q[1-4]", value or "") else "undated"

    for manager_id, documents in by_manager.items():
        groups = defaultdict(list)
        latest = {}
        for document in documents:
            quarter = document_quarter(document)
            groups[quarter].append(document)
            vehicle = document.get("vehicle_id") or document["id"]
            latest[vehicle] = max(
                latest.get(vehicle, ""), quarter if quarter != "undated" else ""
            )
        manifest = {
            "schema_version": 2,
            "manager_id": manager_id,
            "quarters": {},
            "latest_quarters": sorted(set(latest.values()) - {""}),
        }
        for quarter, snapshots in groups.items():
            chunks = [[]]
            used = 0
            for snapshot in sorted(
                snapshots,
                key=lambda d: (
                    d.get("period_end") or d.get("disclosed_at") or d.get("id", "")
                ),
            ):
                length = len(json.dumps(snapshot).encode())
                if length > 1500000:
                    positions = snapshot["positions"]
                    snapshot = {**snapshot, "positions": [], "positions_parts": []}
                    for part, start in enumerate(range(0, len(positions), 10000)):
                        relative = f"disclosures/{manager_id}/{snapshot['id']}-positions-{part}.json"
                        write_json(
                            data / relative,
                            {"positions": positions[start : start + 10000]},
                        )
                        snapshot["positions_parts"].append(relative)
                    length = len(json.dumps(snapshot).encode())
                if used + length > 4000000 and chunks[-1]:
                    chunks.append([])
                    used = 0
                chunks[-1].append(snapshot)
                used += length
            paths = []
            for part, chunk in enumerate(chunks):
                relative = f"disclosures/{manager_id}/{quarter}-{part}.json"
                write_json(data / relative, {"snapshots": chunk})
                paths.append(relative)
            manifest["quarters"][quarter] = paths
        write_json(data / "disclosures" / f"{manager_id}.json", manifest)
    index_path = data / "directory_index.json"
    index = (
        json.loads(index_path.read_text(encoding="utf-8"))
        if index_path.exists()
        else {"schema_version": 2, "managers": [], "quarters": {}}
    )
    existing = {m["manager_id"]: m for m in index["managers"]}
    source_ids = defaultdict(list)
    for fund_id, manager_id in universe.get("source_ids", {}).items():
        source_ids[manager_id].append(fund_id)
    for manager in universe["managers"]:
        row = existing.setdefault(
            manager["manager_id"],
            {
                "manager_id": manager["manager_id"],
                "name": manager["display_name"],
                "history": [],
                "coverage_status": "no_public_13f_loaded",
            },
        )
        row["identity_status"] = manager.get("identity_status", "public_identity")
        row["fund_ids"] = sorted(source_ids.get(manager["manager_id"], []))
        documents = by_manager.get(manager["manager_id"], [])
        row["disclosure_count"] = len(documents)
        row["disclosure_quarters"] = sorted(
            {document_quarter(d) for d in documents} - {"undated"}
        )
    index["managers"] = sorted(existing.values(), key=lambda r: r["manager_id"])
    index["disclosure_coverage"] = {
        "snapshots": len(disclosures),
        "managers": len(by_manager),
        "unresolved_sources": len(review),
        "identity_review": len(universe.get("identity_review", [])),
    }
    write_json(index_path, index)
    # Any directory association with a private document must remain in the vault.
    # The deployment already restores checksum-addressed private assets behind auth.
    if preserve:
        from migrate_dashboard_sources import migrate

        restricted = [
            "dashboard/"
            + str(index_path.relative_to(ROOT / "dashboard")).replace("\\", "/")
        ]
        migrate(ROOT, paths=restricted)
    return index["disclosure_coverage"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=letters_root() / "insights.json")
    parser.add_argument("--public", action="store_true")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    universe = json.loads((ARCHIVE / "universe.json").read_text(encoding="utf-8"))
    documents, review = (
        corpus_disclosures(args.corpus, universe)
        if args.corpus.exists()
        else ([], [{"reason": "Eligible document corpus unavailable"}])
    )
    if args.public:
        from discover_public_funds import discover

        discovered = discover(universe["managers"])
        review.extend(discovered["review"])
        sources = (
            json.loads(SOURCES.read_text(encoding="utf-8"))["sources"]
            + discovered["sources"]
        )
        public, errors = public_disclosures(sources)
        documents.extend(public)
        review.extend(errors)
    write_json(
        ARCHIVE / "disclosures.json",
        {"generated_at": now(), "disclosures": documents, "review": review},
    )
    if args.publish:
        print(json.dumps(publish(documents, universe, review=review)))
    else:
        print(json.dumps({"snapshots": len(documents), "review": len(review)}))


if __name__ == "__main__":
    main()
