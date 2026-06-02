#!/usr/bin/env python3
"""Shared transcript paths, manifest, IR harvest, and metadata parsing."""
from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]

IR_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MarvinTranscripts/1.0"
SLEEP_SEC = 0.12

Q4_FEEDS = [
    "/feed/FinancialReport.svc/GetFinancialReportList?LanguageId=1&PageSize=-1",
    "/feed/Event.svc/GetEventList?LanguageId=1&PageSize=-1",
    "/feed/PressRelease.svc/GetPressReleaseList?LanguageId=1&PageSize=-1",
]

IR_PAGE_SUFFIXES = [
    "",
    "/events-and-presentations/default.aspx",
    "/events-and-presentations/presentations/default.aspx",
    "/news-events/press-releases/default.aspx",
    "/financials/default.aspx",
    "/news/default.aspx",
]

TRANSCRIPT_URL_RE = re.compile(
    r"transcript|corrected[-_]?transcript|earnings[-_]?call|earnings[-_]?script",
    re.I,
)

CORRECTED_TRANSCRIPT_RE = re.compile(r"corrected[-_]?transcript", re.I)
EARNINGS_SCRIPT_RE = re.compile(r"earnings[-_]?script", re.I)

FISCAL_PERIOD_RE = re.compile(r"\b(Q[1-4]|H[12]|FY)\b", re.I)
FISCAL_IN_NAME_RE = re.compile(r"\bq([1-4])[-_./]?(20\d{2})\b", re.I)
DATE_IN_NAME_RE = re.compile(
    r"(20\d{2})[-_./]?(0[1-9]|1[0-2])[-_./]?(0[1-9]|[12]\d|3[01])"
    r"|\b(\d{1,2})[-_](January|February|March|April|May|June|July|August|September|October|November|December)[-_](20\d{2})\b"
    r"|\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(20\d{2})",
    re.I,
)

MONTH_MAP = {
    "january": "01",
    "february": "02",
    "march": "03",
    "april": "04",
    "may": "05",
    "june": "06",
    "july": "07",
    "august": "08",
    "september": "09",
    "october": "10",
    "november": "11",
    "december": "12",
}


def transcripts_dir(ticker: str, market: str) -> Path:
    if market == "JP":
        return ROOT / ticker / "03_Events" / "Transcripts"
    if market in {"SE", "EU"}:
        return ROOT / ticker / "presentations-and-media" / "transcripts"
    return ROOT / ticker / "investor-documents" / "transcripts"


def manifest_path(ticker: str) -> Path:
    return ROOT / ticker / "investor-documents" / "TRANSCRIPT_MANIFEST.json"


def earnings_calendar_path(ticker: str) -> Path:
    return ROOT / ticker / "research" / "evidence" / "earnings_calendar.json"


def log(log_file: Path, msg: str) -> None:
    line = f"{datetime.now().isoformat()} {msg}"
    print(line)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_manifest(ticker: str) -> dict:
    path = manifest_path(ticker)
    if not path.exists():
        return {"schema_version": 1, "ticker": ticker, "entries": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(ticker: str, manifest: dict) -> None:
    manifest["schema_version"] = 1
    manifest["ticker"] = ticker
    manifest["updated_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = manifest_path(ticker)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_date_from_text(text: str) -> str | None:
    m = DATE_IN_NAME_RE.search(text)
    if not m:
        return None
    groups = m.groups()
    if groups[0]:
        return f"{groups[0]}-{groups[1]}-{groups[2]}"
    if groups[3] and groups[4] and groups[5]:
        month = MONTH_MAP.get(groups[4].lower(), "01")
        return f"{groups[5]}-{month}-{int(groups[3]):02d}"
    if groups[6] and groups[7] and groups[8]:
        month = MONTH_MAP.get(groups[6].lower(), "01")
        return f"{groups[8]}-{month}-{int(groups[7]):02d}"
    return None


def parse_event_metadata(url: str, filename: str, title: str = "") -> dict:
    blob = f"{url} {filename} {title}".lower()
    event_type = "other"
    if "investor day" in blob or "investor_day" in blob:
        event_type = "investor_day"
    elif re.search(r"\b(acquisition|merger|m&a)\b", blob):
        event_type = "m_and_a"
    elif re.search(r"\bconference\b|\bsummit\b|\bberstein\b|\bgoldman\b", blob):
        event_type = "conference"
    elif re.search(r"\bearnings\b|\bresults\b|\bquarterly\b", blob):
        event_type = "earnings"

    subtype = "full_qa"
    if EARNINGS_SCRIPT_RE.search(blob):
        subtype = "script"
    elif CORRECTED_TRANSCRIPT_RE.search(blob):
        subtype = "full_qa"

    fiscal_period = None
    m = FISCAL_PERIOD_RE.search(blob.upper())
    if m:
        fiscal_period = m.group(1).upper()
    else:
        m2 = FISCAL_IN_NAME_RE.search(blob)
        if m2:
            fiscal_period = f"Q{m2.group(1)}"

    call_date = parse_date_from_text(f"{filename} {title} {url}")
    if not call_date:
        m3 = FISCAL_IN_NAME_RE.search(blob)
        if m3:
            # Year-only anchor when day/month absent (e.g. bn-q1-2026-transcript.pdf)
            call_date = None
    is_corrected = bool(CORRECTED_TRANSCRIPT_RE.search(blob))

    return {
        "event_type": event_type,
        "subtype": subtype,
        "fiscal_period": fiscal_period,
        "call_date": call_date,
        "is_corrected": is_corrected,
    }


def canonical_filename(
    *,
    call_date: str | None,
    event_type: str,
    fiscal_period: str | None,
    source_hash: str,
    ext: str,
) -> str:
    date_part = call_date or "undated"
    period_part = fiscal_period or "unknown"
    return f"{date_part}_{event_type}_{period_part}_{source_hash[:8]}{ext}"


def is_transcript_candidate(url: str, filename: str = "") -> bool:
    return bool(TRANSCRIPT_URL_RE.search(f"{url} {filename}"))


def walk_json_for_pdfs(obj, pdfs: set[str]) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, str):
                if v.lower().endswith(".pdf") or "doc_downloads" in v.lower():
                    pdfs.add(v)
                for m in re.findall(r"https?://[^\s\"'<>]+\.pdf", v, re.I):
                    pdfs.add(m)
            walk_json_for_pdfs(v, pdfs)
    elif isinstance(obj, list):
        for item in obj:
            walk_json_for_pdfs(item, pdfs)


def normalize_pdf_url(u: str, base: str) -> str | None:
    if not u:
        return None
    u = u.replace("/files/files/", "/files/")
    if u.startswith("//"):
        u = "https:" + u
    if u.startswith("/"):
        u = urllib.parse.urljoin(base, u)
    if not u.lower().startswith("http"):
        return None
    if not u.lower().endswith(".pdf"):
        return None
    return u


def harvest_transcript_urls(ir_roots: list[str], log_file: Path) -> set[str]:
    import time

    pdfs: set[str] = set()
    for root in ir_roots:
        root = root.rstrip("/")
        for feed in Q4_FEEDS:
            feed_url = root + feed
            try:
                req = urllib.request.Request(feed_url, headers={"User-Agent": IR_UA, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    walk_json_for_pdfs(json.load(r), pdfs)
            except Exception:
                pass
            time.sleep(SLEEP_SEC)

        for suffix in IR_PAGE_SUFFIXES:
            page = root + suffix if suffix else root
            try:
                req = urllib.request.Request(page, headers={"User-Agent": IR_UA})
                with urllib.request.urlopen(req, timeout=60) as r:
                    html = r.read().decode("utf-8", errors="ignore")
            except Exception:
                continue
            for m in re.findall(r"https?://[^\s\"'<>]+\.pdf", html, re.I):
                if u := normalize_pdf_url(m, root):
                    pdfs.add(u)
            for m in re.findall(r'href=(["\'])(.*?)\1', html, re.I):
                if ".pdf" not in m[1].lower():
                    continue
                if u := normalize_pdf_url(m[1], root):
                    pdfs.add(u)
            time.sleep(SLEEP_SEC)

    return {u for u in pdfs if is_transcript_candidate(u)}


def download_file(url: str, dest: Path, log_file: Path) -> bool:
    import time

    if dest.exists() and dest.stat().st_size > 512:
        log(log_file, f"SKIP exists -> {dest}")
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": IR_UA})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as exc:
        log(log_file, f"FAIL {url} -> {exc}")
        return False
    if len(data) < 512:
        log(log_file, f"FAIL tiny/corrupt {len(data)} bytes -> {url}")
        return False
    if not data[:4].startswith(b"%PDF"):
        log(log_file, f"FAIL not PDF -> {url}")
        return False
    dest.write_bytes(data)
    log(log_file, f"OK {len(data):,} bytes -> {dest}")
    time.sleep(SLEEP_SEC)
    return True


def manifest_has_period(manifest: dict, fiscal_period: str | None, fiscal_year, call_date: str | None) -> bool:
    for entry in manifest.get("entries") or []:
        if entry.get("event_type") not in ("earnings", "other"):
            continue
        if fiscal_period and entry.get("fiscal_period") == fiscal_period:
            if fiscal_year is None or entry.get("fiscal_year") == fiscal_year:
                return True
        if call_date and entry.get("call_date") == call_date:
            return True
    return False


def add_manifest_entry(
    manifest: dict,
    *,
    canonical_path: str,
    original_url: str,
    original_filename: str,
    meta: dict,
    source: str,
    bytes_count: int,
    file_id: str,
    migrated_from: str | None = None,
    fiscal_year=None,
) -> bool:
    entries = manifest.setdefault("entries", [])
    for e in entries:
        if e.get("id") == file_id or e.get("original_url") == original_url:
            return False
        if e.get("canonical_path") == canonical_path:
            return False

    entry = {
        "id": file_id,
        "canonical_path": canonical_path,
        "original_url": original_url,
        "original_filename": original_filename,
        "event_type": meta.get("event_type", "other"),
        "subtype": meta.get("subtype", "full_qa"),
        "fiscal_period": meta.get("fiscal_period"),
        "fiscal_year": fiscal_year,
        "call_date": meta.get("call_date"),
        "source": source,
        "format": "pdf",
        "is_corrected": meta.get("is_corrected", False),
        "supersedes": None,
        "downloaded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bytes": bytes_count,
        "verified": True,
    }
    if migrated_from:
        entry["migrated_from"] = migrated_from
    entries.append(entry)
    return True


def register_existing_file(
    ticker: str,
    path: Path,
    *,
    market: str,
    source: str = "legacy_index",
    migrated_from: str | None = None,
) -> bool:
    manifest = load_manifest(ticker)
    rel = str(path.relative_to(ROOT / ticker)).replace("\\", "/")
    file_id = f"sha256:{file_sha256(path)}"
    meta = parse_event_metadata("", path.name)
    if add_manifest_entry(
        manifest,
        canonical_path=rel,
        original_url="",
        original_filename=path.name,
        meta=meta,
        source=source,
        bytes_count=path.stat().st_size,
        file_id=file_id,
        migrated_from=migrated_from or rel,
    ):
        save_manifest(ticker, manifest)
        return True
    return False


def scan_legacy_transcripts(ticker: str, market: str) -> int:
    """Register existing transcript PDFs anywhere in ticker tree."""
    ticker_dir = ROOT / ticker
    if not ticker_dir.is_dir():
        return 0
    manifest = load_manifest(ticker)
    known_ids = {e.get("id") for e in manifest.get("entries") or []}
    count = 0
    for pdf in ticker_dir.rglob("*.pdf"):
        rel = str(pdf.relative_to(ticker_dir)).replace("\\", "/")
        if rel.split("/")[0] in {"research", "_system"}:
            continue
        if not is_transcript_candidate(pdf.name, pdf.name):
            continue
        file_id = f"sha256:{file_sha256(pdf)}"
        if file_id in known_ids:
            continue
        meta = parse_event_metadata("", pdf.name)
        if add_manifest_entry(
            manifest,
            canonical_path=rel,
            original_url="",
            original_filename=pdf.name,
            meta=meta,
            source="legacy_index",
            bytes_count=pdf.stat().st_size,
            file_id=file_id,
            migrated_from=rel,
        ):
            count += 1
            known_ids.add(file_id)
    if count:
        save_manifest(ticker, manifest)
    return count


def write_vicki_brief(
    ticker: str,
    *,
    earnings_event: dict | None,
    ir_roots: list[str],
    reason: str,
) -> Path:
    shopbot = ROOT / ticker / "research" / "shopbot"
    shopbot.mkdir(parents=True, exist_ok=True)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    path = shopbot / f"transcript_harvest_{today}.md"
    if path.exists():
        return path

    ev = earnings_event or {}
    lines = [
        f"# Transcript harvest brief — {ticker}",
        "",
        f"**Date:** {today}  ",
        f"**Agent:** Marvin transcript pipeline  ",
        f"**Reason:** {reason}  ",
        "",
        "## Context",
        "",
        f"- Portfolio ticker: **{ticker}**",
        f"- IR roots: {', '.join(ir_roots) or '*(none configured)*'}",
    ]
    if ev:
        lines.extend([
            "",
            "## Polygon earnings (verified reported)",
            "",
            f"- Date: {ev.get('date')}",
            f"- Fiscal period: {ev.get('fiscal_period')} FY{ev.get('fiscal_year') or ''}",
            f"- Verification: {ev.get('verification_reason')}",
        ])
    lines.extend([
        "",
        "## Vicki task",
        "",
        "1. Open IR events / earnings page (handle JS if needed).",
        "2. Download latest earnings call **transcript PDF** (or save HTML if PDF unavailable).",
        "3. Place file in:",
        f"   - `{transcripts_dir(ticker, 'US').relative_to(ROOT / ticker)}/` (US)",
        "   - or market-appropriate transcripts folder.",
        "4. Re-run: `python _system/scripts/download_transcripts.py " + ticker + "`",
        "",
        "## [HUMAN REVIEW]",
        "",
        "- Confirm transcript matches the reported earnings period before citing in research.",
        "",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def make_period_checker(manifest: dict) -> Callable:
    def _check(fiscal_period, fiscal_year, call_date) -> bool:
        return manifest_has_period(manifest, fiscal_period, fiscal_year, call_date)

    return _check
