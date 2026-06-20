#!/usr/bin/env python3
"""Ingest Dropbox investment research folders into the local research library.

The pipeline is intentionally source-preserving:

* downloaded archives and extracted originals live under ``00_sources``;
* parsed text, tables, metadata, indexes, and summaries live under derived
  folders that can be regenerated;
* every derived artifact keeps a pointer back to the raw Dropbox path.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import sys
import textwrap
import time
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIBRARY_ROOT = ROOT / "_system" / "dropbox_ingestion"
TODAY = datetime.now(timezone.utc).date().isoformat()

SOURCE_CONFIGS = {
    "stahl_private": {
        "label": "Stahl Dropbox private folder",
        "url": "https://www.dropbox.com/scl/fo/b1h09s3qn0s7g75tkrm7w/AMjyP8Si4lhxwazkOka4ZiI?rlkey=rr1didm66re0pq4o2qmyxbq00&st=simnuvtm&e=1&dl=0",
        "password_env": "DROPBOX_STAHL_PASSWORD",
        "password_required": True,
    },
    "sumzero_ideas": {
        "label": "SumZero Ideas Dropbox folder",
        "url": "https://www.dropbox.com/scl/fo/kpbmt9407511o18vqsbty/AAna3Hs6SnwvT-98KEMQT9E/SumZero%20Ideas?dl=0&rlkey=5b6e02bqmw92hjpfvl38h8zv0&subfolder_nav_tracking=1",
        "password_env": "",
        "password_required": False,
    },
}

TEXT_EXTS = {".txt", ".md", ".html", ".htm", ".rtf", ".json", ".xml"}
TABLE_EXTS = {".csv", ".tsv"}
OFFICE_EXTS = {".docx", ".pptx", ".xlsx"}
ARCHIVE_EXTS = {".zip"}
PDF_EXTS = {".pdf"}
RAW_IGNORE_PARTS = {"archive"}
TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,24}$")
DATE_RE = re.compile(r"\b(20\d{2}|19\d{2})[-_. ]?([01]\d)[-_. ]?([0-3]\d)\b")


@dataclass
class Paths:
    base: Path
    sources: Path
    processed: Path
    index: Path
    summaries: Path
    library: Path


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        try:
            return str(path.relative_to(DEFAULT_LIBRARY_ROOT)).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")


def slugify(value: str, fallback: str = "item") -> str:
    value = re.sub(r"[^A-Za-z0-9.\-]+", "-", value).strip("-")
    value = re.sub(r"-{2,}", "-", value)
    return (value[:120].strip("-") or fallback)


def clean_text(value: str, *, max_chars: int | None = None) -> str:
    value = html.unescape(value or "")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    value = value.strip()
    if max_chars and len(value) > max_chars:
        return value[:max_chars].rstrip() + "\n\n[Truncated]"
    return value


def ensure_paths(base: Path) -> Paths:
    paths = Paths(
        base=base,
        sources=base / "00_sources" / "dropbox",
        library=base / "01_library",
        processed=base / "02_processed",
        index=base / "03_index",
        summaries=base / "04_summaries",
    )
    for path in (
        paths.sources,
        paths.library / "by_company",
        paths.library / "by_source",
        paths.library / "by_year",
        paths.library / "by_document_type",
        paths.processed / "text",
        paths.processed / "tables",
        paths.processed / "extracted_media",
        paths.index,
        paths.summaries / "by_document",
        paths.summaries / "by_company",
        paths.summaries / "by_theme",
        paths.summaries / "ingestion_reports",
    ):
        path.mkdir(parents=True, exist_ok=True)
    return paths


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def to_dropbox_download_url(url: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["dl"] = "1"
    return urlunparse(parsed._replace(query=urlencode(query)))


def download_file(url: str, dest: Path, *, password: str | None = None) -> tuple[bool, str]:
    """Download a Dropbox shared folder archive.

    Dropbox password-protected shared links require an interactive session token
    that is not available through the static shared URL. We still attempt a
    direct archive download and record a precise failure when Dropbox returns an
    HTML password gate instead of a zip.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = Request(
        to_dropbox_download_url(url),
        headers={
            "User-Agent": "single-stock-investments-dropbox-ingest/1.0",
            "Accept": "application/zip,application/octet-stream,text/html;q=0.8,*/*;q=0.5",
        },
    )
    if password:
        req.add_header("X-Dropbox-Password", password)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with urlopen(req, timeout=120) as response, tmp.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    except Exception as exc:  # noqa: BLE001 - surfaced in manifest/report
        if tmp.exists():
            tmp.unlink()
        return False, f"download failed: {exc}"

    head = tmp.read_bytes()[:512]
    if head.startswith(b"PK\x03\x04"):
        tmp.replace(dest)
        return True, "downloaded"
    text_head = head.decode("utf-8", errors="ignore").lower()
    tmp.replace(dest.with_suffix(dest.suffix + ".html"))
    if "password" in text_head or "dropbox" in text_head:
        return False, "Dropbox returned an HTML page instead of a zip; authenticate in browser or provide a pre-downloaded archive with --archive"
    return False, "download did not return a zip archive"


def extract_archive(archive: Path, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue
            target = dest / member.filename
            resolved = target.resolve()
            if not str(resolved).startswith(str(dest.resolve())):
                raise ValueError(f"unsafe zip path: {member.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted.append(target)
    return extracted


def extract_nested_archives(raw_root: Path) -> list[Path]:
    extracted: list[Path] = []
    for archive in sorted(raw_root.rglob("*.zip")):
        if any(part in RAW_IGNORE_PARTS for part in archive.parts):
            continue
        target = archive.with_suffix("") / "_extracted"
        try:
            extracted.extend(extract_archive(archive, target))
        except Exception:
            continue
    return extracted


def iter_raw_files(source_root: Path) -> Iterable[Path]:
    for path in sorted(source_root.rglob("*")):
        if path.name == ".gitkeep" or path.suffix.lower() in {".part", ".tmp"}:
            continue
        if path.is_file() and "archive" not in path.parts:
            yield path


def classify_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in PDF_EXTS:
        return "pdf"
    if suffix in OFFICE_EXTS:
        return suffix[1:]
    if suffix in TABLE_EXTS:
        return "table"
    if suffix in TEXT_EXTS:
        return "text"
    if suffix in ARCHIVE_EXTS:
        return "archive"
    return "binary"


def repo_tickers() -> set[str]:
    out = set()
    for child in ROOT.iterdir():
        if child.is_dir() and TICKER_RE.match(child.name) and not child.name.startswith("_"):
            out.add(child.name.upper())
    return out


def guess_tickers(path: Path, text: str, known_tickers: set[str]) -> list[str]:
    haystack = f"{path.name} {path.parent.name} {text[:5000]}".upper()
    hits = []
    for ticker in sorted(known_tickers, key=len, reverse=True):
        pattern = rf"(?<![A-Z0-9]){re.escape(ticker)}(?![A-Z0-9])"
        if re.search(pattern, haystack):
            hits.append(ticker)
    return hits[:8]


def guess_date(path: Path, text: str) -> str:
    candidate = f"{path.name} {text[:2000]}"
    match = DATE_RE.search(candidate)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date().isoformat()
    except OSError:
        return ""


def extract_pdf_text(path: Path) -> tuple[str, str]:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # noqa: BLE001
        return "", f"pypdf unavailable: {exc}"
    try:
        reader = PdfReader(str(path))
        pages = []
        for i, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages.append(f"\n\n--- Page {i} ---\n{page_text}")
        return clean_text("\n".join(pages)), "parsed"
    except Exception as exc:  # noqa: BLE001
        return "", f"pdf parse failed: {exc}"


def read_zip_xml(path: Path, names: Iterable[str]) -> list[str]:
    out: list[str] = []
    with zipfile.ZipFile(path) as zf:
        for name in names:
            if name not in zf.namelist():
                continue
            try:
                xml = zf.read(name)
                root = ElementTree.fromstring(xml)
                texts = [node.text for node in root.iter() if node.text and node.text.strip()]
                out.append("\n".join(texts))
            except Exception:
                continue
    return out


def extract_docx_text(path: Path) -> tuple[str, str]:
    try:
        parts = read_zip_xml(path, ["word/document.xml", "word/footnotes.xml", "word/endnotes.xml"])
        return clean_text("\n".join(parts)), "parsed" if parts else "no text found"
    except Exception as exc:  # noqa: BLE001
        return "", f"docx parse failed: {exc}"


def extract_pptx_text(path: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(path) as zf:
            names = sorted(n for n in zf.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
        parts = read_zip_xml(path, names)
        return clean_text("\n\n".join(parts)), "parsed" if parts else "no text found"
    except Exception as exc:  # noqa: BLE001
        return "", f"pptx parse failed: {exc}"


def extract_xlsx_text(path: Path, table_dest: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in names:
                root = ElementTree.fromstring(zf.read("xl/sharedStrings.xml"))
                for si in root.iter():
                    if si.tag.endswith("}si") or si.tag == "si":
                        texts = [n.text for n in si.iter() if n.text]
                        shared_strings.append("".join(texts))
            sheet_names = sorted(n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
            rows_out = []
            text_out = []
            for sheet in sheet_names:
                root = ElementTree.fromstring(zf.read(sheet))
                for row in root.iter():
                    if not row.tag.endswith("}row") and row.tag != "row":
                        continue
                    values = []
                    for cell in row:
                        if not cell.tag.endswith("}c") and cell.tag != "c":
                            continue
                        value_node = next((n for n in cell if n.tag.endswith("}v") or n.tag == "v"), None)
                        value = value_node.text if value_node is not None else ""
                        if cell.attrib.get("t") == "s" and value.isdigit():
                            idx = int(value)
                            value = shared_strings[idx] if idx < len(shared_strings) else value
                        values.append(value or "")
                    if any(values):
                        rows_out.append([sheet, *values])
                        text_out.append(" | ".join(values))
            if rows_out:
                table_dest.parent.mkdir(parents=True, exist_ok=True)
                with table_dest.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.writer(handle)
                    writer.writerows(rows_out)
            return clean_text("\n".join(text_out)), "parsed" if text_out else "no text found"
    except Exception as exc:  # noqa: BLE001
        return "", f"xlsx parse failed: {exc}"


def extract_table_text(path: Path, table_dest: Path) -> tuple[str, str]:
    try:
        delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
        rows = []
        with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            for row in reader:
                rows.append(row)
        table_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, table_dest)
        return clean_text("\n".join(" | ".join(row) for row in rows[:1000])), "parsed"
    except Exception as exc:  # noqa: BLE001
        return "", f"table parse failed: {exc}"


def extract_text_file(path: Path) -> tuple[str, str]:
    try:
        return clean_text(path.read_text(encoding="utf-8", errors="ignore")), "parsed"
    except Exception as exc:  # noqa: BLE001
        return "", f"text parse failed: {exc}"


def parse_file(path: Path, text_dest: Path, table_dest: Path) -> tuple[str, str, str]:
    doc_type = classify_type(path)
    if doc_type == "pdf":
        text, status = extract_pdf_text(path)
    elif doc_type == "docx":
        text, status = extract_docx_text(path)
    elif doc_type == "pptx":
        text, status = extract_pptx_text(path)
    elif doc_type == "xlsx":
        text, status = extract_xlsx_text(path, table_dest)
    elif doc_type == "table":
        text, status = extract_table_text(path, table_dest)
    elif doc_type == "text":
        text, status = extract_text_file(path)
    else:
        return "", "unsupported", doc_type
    if text:
        text_dest.parent.mkdir(parents=True, exist_ok=True)
        text_dest.write_text(text, encoding="utf-8")
    return text, status, doc_type


def extract_signal_lines(text: str, patterns: list[str], limit: int = 6) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    out = []
    for line in lines:
        low = line.lower()
        if any(p in low for p in patterns):
            out.append(line[:300])
        if len(out) >= limit:
            break
    return out


def summarize_document(record: dict, text: str) -> str:
    title = Path(record["original_path"]).name
    excerpt = clean_text(text, max_chars=1200) if text else "_No extracted text available._"
    thesis = extract_signal_lines(text, ["thesis", "variant perception", "mispriced", "undervalued", "overvalued"])
    catalysts = extract_signal_lines(text, ["catalyst", "inflection", "spin", "buyback", "re-rate", "rerate"])
    risks = extract_signal_lines(text, ["risk", "downside", "bear case", "concern", "headwind"])
    valuation = extract_signal_lines(text, ["valuation", "target price", "multiple", "ebitda", "fcf", "irr"])
    sections = [
        f"# {title}",
        "",
        f"- Source: {record['source_id']}",
        f"- Raw path: `{record['raw_rel_path']}`",
        f"- Type: {record['document_type']}",
        f"- SHA256: `{record['sha256']}`",
        f"- Date guess: {record.get('document_date') or 'unknown'}",
        f"- Ticker/company guess: {', '.join(record.get('ticker_guesses') or []) or 'unmatched'}",
        "",
        "## Extracted Signals",
        "",
        "### Thesis",
        "\n".join(f"- {line}" for line in thesis) or "- Not detected by heuristic.",
        "",
        "### Valuation",
        "\n".join(f"- {line}" for line in valuation) or "- Not detected by heuristic.",
        "",
        "### Catalysts",
        "\n".join(f"- {line}" for line in catalysts) or "- Not detected by heuristic.",
        "",
        "### Risks",
        "\n".join(f"- {line}" for line in risks) or "- Not detected by heuristic.",
        "",
        "## Text Preview",
        "",
        excerpt,
        "",
    ]
    return "\n".join(sections)


def theme_tags(text: str) -> list[str]:
    themes = {
        "shorts": ["short thesis", "short idea", "fraud", "overvalued", "bubble"],
        "special_situations": ["spin-off", "spinoff", "merger", "tender", "liquidation", "restructuring"],
        "compounders": ["compounder", "moat", "recurring revenue", "high returns", "reinvestment"],
        "valuation_gap": ["undervalued", "mispriced", "valuation gap", "discount to", "multiple expansion"],
        "catalysts": ["catalyst", "inflection", "activist", "buyback", "asset sale"],
        "risks": ["risk", "downside", "bear case", "leverage", "cyclical"],
    }
    low = text.lower()
    return [theme for theme, terms in themes.items() if any(term in low for term in terms)]


def manifest_record(source_id: str, source_root: Path, path: Path, text: str, parse_status: str, doc_type: str, known_tickers: set[str], text_rel: str, table_rel: str) -> dict:
    stat = path.stat()
    tickers = guess_tickers(path, text, known_tickers)
    return {
        "source_id": source_id,
        "source_label": SOURCE_CONFIGS.get(source_id, {}).get("label", source_id),
        "original_path": str(path.relative_to(source_root)).replace("\\", "/"),
        "raw_rel_path": rel(path),
        "text_rel_path": text_rel,
        "table_rel_path": table_rel,
        "filename": path.name,
        "extension": path.suffix.lower(),
        "file_size": stat.st_size,
        "modified_time": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "sha256": sha256_file(path),
        "document_type": doc_type,
        "parse_status": parse_status,
        "ticker_guesses": tickers,
        "document_date": guess_date(path, text),
        "theme_tags": theme_tags(text),
        "ingested_at": now_utc(),
    }


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_sqlite(db_path: Path, records: list[dict], text_lookup: dict[str, str]) -> None:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE documents (
                sha256 TEXT PRIMARY KEY,
                source_id TEXT,
                original_path TEXT,
                raw_rel_path TEXT,
                text_rel_path TEXT,
                filename TEXT,
                extension TEXT,
                file_size INTEGER,
                document_type TEXT,
                parse_status TEXT,
                document_date TEXT,
                ticker_guesses TEXT,
                theme_tags TEXT,
                ingested_at TEXT
            )
            """
        )
        conn.execute("CREATE VIRTUAL TABLE document_fts USING fts5(sha256, title, body)")
        for rec in records:
            conn.execute(
                """
                INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec["sha256"],
                    rec["source_id"],
                    rec["original_path"],
                    rec["raw_rel_path"],
                    rec["text_rel_path"],
                    rec["filename"],
                    rec["extension"],
                    rec["file_size"],
                    rec["document_type"],
                    rec["parse_status"],
                    rec["document_date"],
                    ",".join(rec.get("ticker_guesses") or []),
                    ",".join(rec.get("theme_tags") or []),
                    rec["ingested_at"],
                ),
            )
            body = text_lookup.get(rec["sha256"], "")
            if body:
                conn.execute("INSERT INTO document_fts VALUES (?, ?, ?)", (rec["sha256"], rec["filename"], body))
        conn.commit()
    finally:
        conn.close()


def write_library_views(paths: Paths, records: list[dict]) -> None:
    for view in ("by_company", "by_source", "by_year", "by_document_type"):
        view_dir = paths.library / view
        view_dir.mkdir(parents=True, exist_ok=True)
        for old in view_dir.glob("*.jsonl"):
            old.unlink()

    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for rec in records:
        tickers = rec.get("ticker_guesses") or ["UNMATCHED"]
        for ticker in tickers:
            buckets[("by_company", ticker)].append(rec)
        buckets[("by_source", rec["source_id"])].append(rec)
        year = (rec.get("document_date") or "unknown")[:4]
        buckets[("by_year", year if year.isdigit() else "unknown")].append(rec)
        buckets[("by_document_type", rec["document_type"])].append(rec)

    for (view, key), rows in buckets.items():
        write_jsonl(paths.library / view / f"{slugify(key)}.jsonl", rows)


def write_aggregate_summaries(paths: Paths, records: list[dict], text_lookup: dict[str, str]) -> None:
    for directory in (paths.summaries / "by_company", paths.summaries / "by_theme"):
        directory.mkdir(parents=True, exist_ok=True)
        for old in directory.glob("*.md"):
            old.unlink()

    by_company: dict[str, list[dict]] = defaultdict(list)
    by_theme: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        for ticker in rec.get("ticker_guesses") or ["UNMATCHED"]:
            by_company[ticker].append(rec)
        for theme in rec.get("theme_tags") or ["untagged"]:
            by_theme[theme].append(rec)

    for ticker, rows in sorted(by_company.items()):
        lines = [f"# {ticker}", "", f"Documents: {len(rows)}", ""]
        for rec in sorted(rows, key=lambda r: (r.get("document_date") or "", r["filename"]), reverse=True):
            themes = ", ".join(rec.get("theme_tags") or [])
            lines.append(f"- `{rec['raw_rel_path']}` ({rec['document_type']}, {rec.get('document_date') or 'unknown'}) {themes}")
        (paths.summaries / "by_company" / f"{slugify(ticker)}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    for theme, rows in sorted(by_theme.items()):
        lines = [f"# {theme.replace('_', ' ').title()}", "", f"Documents: {len(rows)}", ""]
        for rec in sorted(rows, key=lambda r: (r.get("document_date") or "", r["filename"]), reverse=True):
            tickers = ", ".join(rec.get("ticker_guesses") or [])
            lines.append(f"- `{rec['raw_rel_path']}` {tickers} ({rec.get('document_date') or 'unknown'})")
        (paths.summaries / "by_theme" / f"{slugify(theme)}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(paths: Paths, records: list[dict], download_status: dict[str, str]) -> Path:
    total = len(records)
    parsed = sum(1 for r in records if r["parse_status"] == "parsed")
    unsupported = sum(1 for r in records if r["parse_status"] == "unsupported")
    unmatched = sum(1 for r in records if not r.get("ticker_guesses"))
    by_type = Counter(r["document_type"] for r in records)
    by_source = Counter(r["source_id"] for r in records)
    duplicates = total - len({r["sha256"] for r in records})
    report = [
        f"# Dropbox Ingestion Report - {TODAY}",
        "",
        "## Source Status",
        "",
    ]
    for source_id, status in download_status.items():
        report.append(f"- {source_id}: {status}")
    report.extend(
        [
            "",
            "## Coverage",
            "",
            f"- Files discovered: {total}",
            f"- Files parsed successfully: {parsed}",
            f"- Unsupported files: {unsupported}",
            f"- Duplicate content hashes: {duplicates}",
            f"- Files without ticker/company match: {unmatched}",
            "",
            "## By Source",
            "",
        ]
    )
    report.extend(f"- {k}: {v}" for k, v in sorted(by_source.items()))
    report.extend(["", "## By Document Type", ""])
    report.extend(f"- {k}: {v}" for k, v in sorted(by_type.items()))
    report.extend(["", "## Retrieval Artifacts", ""])
    report.extend(
        [
            f"- Manifest: `{rel(paths.index / 'manifest.jsonl')}`",
            f"- SQLite/FTS index: `{rel(paths.index / 'documents.sqlite')}`",
            f"- Document summaries: `{rel(paths.summaries / 'by_document')}`",
            f"- Company summaries: `{rel(paths.summaries / 'by_company')}`",
            f"- Theme summaries: `{rel(paths.summaries / 'by_theme')}`",
        ]
    )
    out = paths.summaries / "ingestion_reports" / f"dropbox_ingestion_{TODAY}.md"
    out.write_text("\n".join(report) + "\n", encoding="utf-8")
    return out


def existing_archives(source_dir: Path) -> list[Path]:
    return sorted((source_dir / "archive").glob("*.zip")) if (source_dir / "archive").is_dir() else []


def run(args: argparse.Namespace) -> int:
    paths = ensure_paths(args.library_root)
    known_tickers = repo_tickers()
    download_status: dict[str, str] = {}

    archive_overrides = dict(item.split("=", 1) for item in args.archive or [])
    selected_sources = args.sources or list(SOURCE_CONFIGS)
    for source_id in selected_sources:
        if source_id not in SOURCE_CONFIGS:
            raise SystemExit(f"Unknown source: {source_id}")
        cfg = SOURCE_CONFIGS[source_id]
        source_dir = paths.sources / source_id
        archive_dir = source_dir / "archive"
        raw_dir = source_dir / "raw"
        archive_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)

        archive_path = Path(archive_overrides[source_id]).resolve() if source_id in archive_overrides else archive_dir / f"{source_id}_{TODAY}.zip"
        if archive_path.exists():
            download_status[source_id] = f"using archive {rel(archive_path)}"
        elif args.no_download:
            download_status[source_id] = "skipped download (--no-download)"
        else:
            password = os.getenv(cfg.get("password_env") or "") or (args.stahl_password if source_id == "stahl_private" else None)
            ok, status = download_file(cfg["url"], archive_path, password=password)
            download_status[source_id] = status
            if not ok and cfg.get("password_required"):
                download_status[source_id] += " (password-protected source)"

        if archive_path.exists():
            try:
                extracted = extract_archive(archive_path, raw_dir)
                download_status[source_id] += f"; extracted {len(extracted)} files"
            except Exception as exc:  # noqa: BLE001
                download_status[source_id] += f"; extract failed: {exc}"
        else:
            archives = existing_archives(source_dir)
            if archives:
                latest = archives[-1]
                try:
                    extracted = extract_archive(latest, raw_dir)
                    download_status[source_id] += f"; extracted existing archive {latest.name} ({len(extracted)} files)"
                except Exception as exc:  # noqa: BLE001
                    download_status[source_id] += f"; existing archive extract failed: {exc}"

        nested = extract_nested_archives(raw_dir)
        if nested:
            download_status[source_id] += f"; extracted {len(nested)} nested files"

    records: list[dict] = []
    text_lookup: dict[str, str] = {}
    for source_id in selected_sources:
        source_root = paths.sources / source_id / "raw"
        for raw_file in iter_raw_files(source_root):
            raw_rel_slug = slugify(str(raw_file.relative_to(source_root)).replace("\\", "__"))
            text_dest = paths.processed / "text" / source_id / f"{raw_rel_slug}.txt"
            table_dest = paths.processed / "tables" / source_id / f"{raw_rel_slug}.csv"
            text, parse_status, doc_type = parse_file(raw_file, text_dest, table_dest)
            text_rel = rel(text_dest) if text_dest.exists() else ""
            table_rel = rel(table_dest) if table_dest.exists() else ""
            record = manifest_record(source_id, source_root, raw_file, text, parse_status, doc_type, known_tickers, text_rel, table_rel)
            records.append(record)
            if text:
                text_lookup[record["sha256"]] = text
                summary = summarize_document(record, text)
                summary_path = paths.summaries / "by_document" / f"{record['sha256'][:12]}_{slugify(raw_file.stem)}.md"
                summary_path.write_text(summary, encoding="utf-8")

    write_jsonl(paths.index / "manifest.jsonl", records)
    build_sqlite(paths.index / "documents.sqlite", records, text_lookup)
    write_library_views(paths, records)
    write_aggregate_summaries(paths, records, text_lookup)
    report_path = write_report(paths, records, download_status)
    print(f"Ingested {len(records)} files")
    print(f"Report: {rel(report_path)}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download, parse, index, and summarize the two Dropbox research folders.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Examples:
              python _system/scripts/dropbox_ingest.py --stahl-password stahl
              python _system/scripts/dropbox_ingest.py --no-download --archive sumzero_ideas=C:\\Downloads\\sumzero.zip
            """
        ),
    )
    parser.add_argument("--library-root", type=Path, default=DEFAULT_LIBRARY_ROOT)
    parser.add_argument("--sources", nargs="+", choices=sorted(SOURCE_CONFIGS), help="Limit ingestion to selected source ids.")
    parser.add_argument("--archive", action="append", metavar="SOURCE=PATH", help="Use a pre-downloaded zip archive for a source.")
    parser.add_argument("--no-download", action="store_true", help="Parse existing raw/archive files without downloading.")
    parser.add_argument("--stahl-password", help="Password for the Stahl private Dropbox folder. Prefer DROPBOX_STAHL_PASSWORD.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run(parse_args(sys.argv[1:])))
