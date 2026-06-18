#!/usr/bin/env python3
"""Local, user-triggered VIC page intake.

This helper is intentionally not a crawler. It accepts one browser bookmarklet
capture at a time from a page the user is already viewing, writes a pending
third-party note, and refreshes the ticker source inventory.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_MAX_EXCERPT_CHARS = 2000
DEFAULT_QUEUE = ROOT / "_system" / "data" / "vic_intake_queue.csv"
DEFAULT_ACTIVE = ROOT / "_system" / "data" / "vic_active_ticker.json"
DEFAULT_DOWNLOADS = Path.home() / "Downloads"
DEFAULT_PDF_MAX_AGE_MINUTES = 720
TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,24}$")
QUEUE_FIELDS = [
    "ticker",
    "status",
    "priority",
    "notes",
    "created_at",
    "updated_at",
    "last_captured_at",
    "captured_count",
    "last_note",
    "search_url",
]
QUEUE_STATUSES = {"pending", "active", "captured", "reviewed", "skipped"}

sys.path.insert(0, str(SCRIPTS))
from third_party_inventory import write_inventory  # noqa: E402


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def clean_text(value: Any, *, max_chars: int | None = None) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n\n[Truncated by local VIC intake cap.]"
    return text


def md_escape(value: Any) -> str:
    text = clean_text(value)
    return text.replace("|", "\\|").replace("\n", " ")


def quote_block(text: str) -> str:
    if not text:
        return "_No selected excerpt captured._"
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def validate_vic_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host != "valueinvestorsclub.com" and not host.endswith(".valueinvestorsclub.com"):
        raise ValueError("Capture URL must be on valueinvestorsclub.com.")


def normalize_ticker(raw: Any) -> str:
    ticker = str(raw or "").strip().upper()
    if not ticker or not TICKER_RE.match(ticker):
        raise ValueError("Ticker is required and may only contain letters, numbers, dots, or hyphens.")
    return ticker


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def safe_slug(text: str, *, fallback: str = "vic") -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    slug = re.sub(r"-{2,}", "-", slug)
    return (slug[:70].strip("-") or fallback)


def file_sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_pdf(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"PDF file not found: {path}")
    if path.stat().st_size < 1024:
        raise ValueError(f"PDF file is too small to be valid: {path}")
    with path.open("rb") as handle:
        head = handle.read(5)
    if head != b"%PDF-":
        raise ValueError(f"File does not look like a PDF: {path}")


def find_latest_pdf(downloads_path: Path, *, max_age_minutes: int) -> Path:
    if not downloads_path.is_dir():
        raise ValueError(f"Downloads folder not found: {downloads_path}")
    candidates = [
        p
        for p in downloads_path.glob("*.pdf")
        if p.is_file() and not p.name.lower().endswith((".crdownload", ".part", ".tmp"))
    ]
    if not candidates:
        raise ValueError(f"No PDF files found in {downloads_path}")
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    age_seconds = datetime.now(timezone.utc).timestamp() - latest.stat().st_mtime
    if max_age_minutes > 0 and age_seconds > max_age_minutes * 60:
        raise ValueError(
            f"Newest PDF is older than {max_age_minutes} minutes: {latest.name}. "
            "Download the VIC PDF again or raise --pdf-max-age-minutes."
        )
    verify_pdf(latest)
    return latest


def ensure_ticker_exists(ticker: str) -> Path:
    ticker_dir = ROOT / ticker
    if not ticker_dir.is_dir():
        raise ValueError(f"{ticker} is not a ticker folder in this repo. Scaffold/onboard it first.")
    return ticker_dir


def resolve_repo_path(path: Path | str | None, *, default: Path) -> Path:
    if path is None:
        return default
    out = Path(path)
    if not out.is_absolute():
        out = ROOT / out
    return out


def split_tickers(raw: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for part in re.split(r"[\s,;]+", raw or ""):
        if not part.strip():
            continue
        ticker = normalize_ticker(part)
        if ticker not in seen:
            out.append(ticker)
            seen.add(ticker)
    return out


def default_search_url(ticker: str) -> str:
    return f"https://www.google.com/search?q=site%3Avalueinvestorsclub.com%2Fidea+{quote_plus(ticker)}"


def vic_atoz_url(ticker: str) -> str:
    first = ticker[:1].upper()
    if first.isalpha():
        return f"https://www.valueinvestorsclub.com/ideas/atoz#{first}"
    return "https://www.valueinvestorsclub.com/ideas/atoz#0-9"


def count_vic_notes(ticker: str) -> int:
    vic_dir = ROOT / ticker / "third-party-analyses" / "vic"
    if not vic_dir.is_dir():
        return 0
    return len(list(vic_dir.glob("*.md")))


def list_vic_notes(ticker: str) -> list[dict[str, str]]:
    vic_dir = ROOT / ticker / "third-party-analyses" / "vic"
    if not vic_dir.is_dir():
        return []
    rows: list[dict[str, str]] = []
    for path in sorted(vic_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        text = path.read_text(encoding="utf-8", errors="ignore")
        title = path.stem
        url = ""
        captured = ""
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
            elif line.startswith("**URL:**"):
                url = line.split("**URL:**", 1)[1].strip()
            elif line.startswith("**Captured:**"):
                captured = line.split("**Captured:**", 1)[1].strip()
        rows.append(
            {
                "title": title,
                "path": rel(path),
                "url": url,
                "captured": captured,
            }
        )
    return rows


def empty_queue_row(ticker: str) -> dict[str, str]:
    timestamp = now_utc()
    return {
        "ticker": ticker,
        "status": "pending",
        "priority": "",
        "notes": "",
        "created_at": timestamp,
        "updated_at": timestamp,
        "last_captured_at": "",
        "captured_count": "0",
        "last_note": "",
        "search_url": default_search_url(ticker),
    }


def load_queue(queue_path: Path) -> list[dict[str, str]]:
    if not queue_path.exists():
        return []
    rows: list[dict[str, str]] = []
    with queue_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            try:
                ticker = normalize_ticker(raw.get("ticker"))
            except ValueError:
                continue
            row = empty_queue_row(ticker)
            for field in QUEUE_FIELDS:
                if raw.get(field) is not None:
                    row[field] = clean_text(raw.get(field), max_chars=1000)
            if row["status"] not in QUEUE_STATUSES:
                row["status"] = "pending"
            actual_count = count_vic_notes(ticker)
            if actual_count:
                row["captured_count"] = str(actual_count)
            rows.append(row)
    rows.sort(key=lambda r: (r.get("status") == "reviewed", r.get("status") == "skipped", r.get("ticker", "")))
    return rows


def save_queue(queue_path: Path, rows: list[dict[str, str]]) -> None:
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with queue_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUEUE_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in QUEUE_FIELDS})


def add_tickers_to_queue(queue_path: Path, raw_tickers: str, *, notes: str = "") -> list[str]:
    rows = load_queue(queue_path)
    by_ticker = {row["ticker"]: row for row in rows}
    added: list[str] = []
    for ticker in split_tickers(raw_tickers):
        ensure_ticker_exists(ticker)
        if ticker in by_ticker:
            if notes:
                by_ticker[ticker]["notes"] = notes
                by_ticker[ticker]["updated_at"] = now_utc()
            continue
        row = empty_queue_row(ticker)
        row["notes"] = clean_text(notes, max_chars=1000)
        by_ticker[ticker] = row
        rows.append(row)
        added.append(ticker)
    save_queue(queue_path, rows)
    return added


def update_queue_row(queue_path: Path, ticker: str, updates: dict[str, Any]) -> None:
    ticker = normalize_ticker(ticker)
    rows = load_queue(queue_path)
    row = next((r for r in rows if r["ticker"] == ticker), None)
    if row is None:
        row = empty_queue_row(ticker)
        rows.append(row)
    for key in ("status", "priority", "notes", "search_url"):
        if key not in updates:
            continue
        value = clean_text(updates.get(key), max_chars=1000)
        if key == "status" and value not in QUEUE_STATUSES:
            continue
        row[key] = value
    row["updated_at"] = now_utc()
    save_queue(queue_path, rows)


def remove_queue_row(queue_path: Path, ticker: str) -> None:
    ticker = normalize_ticker(ticker)
    rows = [row for row in load_queue(queue_path) if row["ticker"] != ticker]
    save_queue(queue_path, rows)


def mark_queue_captured(queue_path: Path, ticker: str, note_rel: str, captured_at: str) -> None:
    ticker = normalize_ticker(ticker)
    rows = load_queue(queue_path)
    row = next((r for r in rows if r["ticker"] == ticker), None)
    if row is None:
        row = empty_queue_row(ticker)
        rows.append(row)
    row["status"] = "captured"
    row["captured_count"] = str(count_vic_notes(ticker))
    row["last_captured_at"] = captured_at
    row["last_note"] = note_rel
    row["updated_at"] = now_utc()
    save_queue(queue_path, rows)


def load_active(active_path: Path) -> dict[str, str]:
    if not active_path.exists():
        return {}
    try:
        raw = json.loads(active_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    try:
        ticker = normalize_ticker(raw.get("ticker"))
    except ValueError:
        return {}
    return {
        "ticker": ticker,
        "note": clean_text(raw.get("note"), max_chars=1000),
        "set_at": clean_text(raw.get("set_at")),
    }


def save_active(active_path: Path, ticker: str, *, note: str = "") -> dict[str, str]:
    ticker = normalize_ticker(ticker)
    ensure_ticker_exists(ticker)
    active = {"ticker": ticker, "note": clean_text(note, max_chars=1000), "set_at": now_utc()}
    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_text(json.dumps(active, indent=2) + "\n", encoding="utf-8")
    return active


def upsert_pending(ticker: str, note_rel: str, title: str, capture_date: str) -> None:
    pending = ROOT / ticker / "third-party-analyses" / "pending.md"
    pending.parent.mkdir(parents=True, exist_ok=True)
    row = (
        f"| `{note_rel}` | Pending VIC intake captured {capture_date}; "
        "human approval required before IRR/stance use |"
    )
    if not pending.exists():
        pending.write_text(
            "\n".join(
                [
                    f"# {ticker} - Pending third-party sources",
                    "",
                    f"**Updated:** {capture_date}",
                    "",
                    "Approve in `_system/frameworks/third_party_sources.md` before using in base IRR.",
                    "",
                    "| File | Status |",
                    "|------|--------|",
                    row,
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return

    text = pending.read_text(encoding="utf-8", errors="ignore")
    if note_rel in text:
        return
    text = re.sub(r"\*\*Updated:\*\* [0-9]{4}-[0-9]{2}-[0-9]{2}", f"**Updated:** {capture_date}", text)
    none_row = re.compile(r"^\| \(none\) \| [^|\n]+ \|\s*$", re.M)
    if none_row.search(text):
        text = none_row.sub(row, text)
    else:
        lines = text.rstrip().splitlines()
        insert_at = len(lines)
        for idx, line in enumerate(lines):
            if line.startswith("|") and idx > 0:
                insert_at = idx + 1
        lines.insert(insert_at, row)
        text = "\n".join(lines) + "\n"
    pending.write_text(text, encoding="utf-8")


def upsert_references(ticker: str, note_rel: str, title: str, url: str, capture_date: str) -> None:
    references = ROOT / ticker / "third-party-analyses" / "references.md"
    references.parent.mkdir(parents=True, exist_ok=True)
    row = (
        f"| VIC: {md_escape(title)[:90]} | {capture_date} | {md_escape(url)} | "
        f"**Pending** - local single-page intake `{note_rel}`; not in base IRR |"
    )
    if not references.exists():
        references.write_text(
            "\n".join(
                [
                    f"# {ticker} - Third-party references",
                    "",
                    "| Source | Date | URL | Use in Marvin work |",
                    "|--------|------|-----|-------------------|",
                    row,
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return

    text = references.read_text(encoding="utf-8", errors="ignore")
    if note_rel in text or url in text:
        return
    lines = text.rstrip().splitlines()
    insert_at = len(lines)
    for idx, line in enumerate(lines):
        if line.startswith("|") and idx > 0:
            insert_at = idx + 1
    lines.insert(insert_at, row)
    references.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_vic_note(
    payload: dict[str, Any], *, max_excerpt_chars: int, queue_path: Path | None = None
) -> dict[str, str]:
    url = clean_text(payload.get("url"))
    validate_vic_url(url)
    ticker = normalize_ticker(payload.get("ticker"))
    ticker_dir = ensure_ticker_exists(ticker)

    title = clean_text(payload.get("title"), max_chars=180) or "VIC idea"
    human_note = clean_text(payload.get("note"), max_chars=1200)
    selected = clean_text(payload.get("selectedText") or payload.get("selected_text"), max_chars=max_excerpt_chars)
    captured_at = clean_text(payload.get("capturedAt") or payload.get("captured_at")) or now_utc()
    capture_date = captured_at[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", captured_at) else today_utc()

    digest = hashlib.sha1(f"{ticker}\n{url}\n{title}\n{captured_at}".encode("utf-8")).hexdigest()[:10]
    filename = f"vic_{capture_date}_{safe_slug(title)}_{digest}.md"
    out_dir = ticker_dir / "third-party-analyses" / "vic"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / filename
    note_rel = rel(out_path)

    body = [
        f"# VIC intake - {ticker} - {title}",
        "",
        "**Source:** Value Investors Club",
        f"**URL:** {url}",
        f"**Captured:** {captured_at}",
        "**Status:** pending third-party approval",
        "**Capture method:** local single-page bookmarklet; no automated navigation or crawl",
        "**Use rule:** Do not use in base IRR or stance until approved in `_system/frameworks/third_party_sources.md`.",
        "",
        "## Human note",
        "",
        human_note or "_No human note entered._",
        "",
        "## Selected excerpt",
        "",
        quote_block(selected),
        "",
        "## Review checklist",
        "",
        "- Confirm ticker, author/date, and thesis directly against the VIC page.",
        "- Add an approved-registry row only if this should influence base IRR or stance.",
        "- Keep this as pending/context if it is only a variant perception check.",
        "",
    ]
    out_path.write_text("\n".join(body), encoding="utf-8")

    upsert_pending(ticker, note_rel, title, capture_date)
    upsert_references(ticker, note_rel, title, url, capture_date)
    json_path, md_path = write_inventory(ticker, capture_date)
    if queue_path is not None:
        mark_queue_captured(queue_path, ticker, note_rel, captured_at)

    return {
        "ticker": ticker,
        "note": note_rel,
        "pending": rel(ROOT / ticker / "third-party-analyses" / "pending.md"),
        "references": rel(ROOT / ticker / "third-party-analyses" / "references.md"),
        "inventory_json": rel(json_path),
        "inventory_md": rel(md_path),
    }


def write_vic_pdf_import(
    *,
    ticker: str,
    source_pdf: Path,
    queue_path: Path | None = None,
    title: str = "",
    source_url: str = "",
    note: str = "",
) -> dict[str, str]:
    ticker = normalize_ticker(ticker)
    ticker_dir = ensure_ticker_exists(ticker)
    verify_pdf(source_pdf)

    captured_at = now_utc()
    capture_date = captured_at[:10]
    digest = file_sha1(source_pdf)
    title = clean_text(title, max_chars=180) or source_pdf.stem
    source_url = clean_text(source_url, max_chars=500)
    note = clean_text(note, max_chars=1200)

    out_dir = ticker_dir / "third-party-analyses" / "vic"
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_name = f"vic_pdf_{capture_date}_{safe_slug(title)}_{digest[:10]}.pdf"
    pdf_path = out_dir / pdf_name
    if not pdf_path.exists():
        shutil.copy2(source_pdf, pdf_path)
    verify_pdf(pdf_path)

    pdf_rel = rel(pdf_path)
    md_path = pdf_path.with_suffix(".md")
    md_rel = rel(md_path)
    body = [
        f"# VIC PDF intake - {ticker} - {title}",
        "",
        "**Source:** Value Investors Club",
        f"**PDF:** `{pdf_rel}`",
        f"**Original file:** `{source_pdf.name}`",
        f"**Captured:** {captured_at}",
        f"**SHA1:** `{digest}`",
        "**Status:** pending third-party approval",
        "**Capture method:** user-downloaded PDF imported from local Downloads folder",
        "**Use rule:** Do not use in base IRR or stance until approved in `_system/frameworks/third_party_sources.md`.",
        "",
        "## Source URL",
        "",
        source_url or "_Not provided._",
        "",
        "## Human note",
        "",
        note or "_No human note entered._",
        "",
        "## Review checklist",
        "",
        "- Confirm ticker, author/date, and thesis directly against the VIC page.",
        "- Add an approved-registry row only if this should influence base IRR or stance.",
        "- Keep this as pending/context if it is only a variant perception check.",
        "",
    ]
    md_path.write_text("\n".join(body), encoding="utf-8")

    upsert_pending(ticker, pdf_rel, title, capture_date)
    upsert_references(ticker, pdf_rel, title, source_url or pdf_rel, capture_date)
    json_path, md_path_inventory = write_inventory(ticker, capture_date)
    if queue_path is not None:
        mark_queue_captured(queue_path, ticker, pdf_rel, captured_at)

    return {
        "ticker": ticker,
        "pdf": pdf_rel,
        "note": md_rel,
        "pending": rel(ROOT / ticker / "third-party-analyses" / "pending.md"),
        "references": rel(ROOT / ticker / "third-party-analyses" / "references.md"),
        "inventory_json": rel(json_path),
        "inventory_md": rel(md_path_inventory),
    }


def bookmarklet(port: int) -> str:
    js = f"""javascript:(async()=>{{let active={{}};try{{const a=await fetch('http://127.0.0.1:{port}/active');active=await a.json();}}catch(_){{}}const ticker=active.ticker||prompt('Ticker folder for this VIC idea?');if(!ticker)return;const note=active.note||prompt('Short note for this VIC intake?','');const selected=String(window.getSelection?window.getSelection():'');if(!selected&&!confirm('No text is selected. Capture metadata only?'))return;const payload={{url:location.href,title:document.title,ticker,note,selectedText:selected,capturedAt:new Date().toISOString()}};try{{const r=await fetch('http://127.0.0.1:{port}/capture',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload)}});alert(await r.text());}}catch(e){{const text=JSON.stringify(payload,null,2);console.log(payload);try{{await navigator.clipboard.writeText(text);}}catch(_){{}}alert('Capture failed. The payload was logged and copied if clipboard access was allowed. Save it as JSON and import with --from-json. '+e);}}}})()"""
    return js


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def status_options(current: str) -> str:
    return "\n".join(
        f'<option value="{esc(status)}"{" selected" if status == current else ""}>{esc(status.title())}</option>'
        for status in ["pending", "active", "captured", "reviewed", "skipped"]
    )


def dashboard_html(queue_path: Path, active_path: Path, port: int) -> str:
    rows = load_queue(queue_path)
    active = load_active(active_path)
    bm = bookmarklet(port)
    queue_rel = rel(queue_path) if queue_path.is_relative_to(ROOT) else str(queue_path)
    active_ticker = active.get("ticker", "")
    row_html: list[str] = []
    for row in rows:
        ticker = row["ticker"]
        capture_count = count_vic_notes(ticker)
        status = "captured" if capture_count and row.get("status") == "pending" else row.get("status", "pending")
        active_class = " is-active" if ticker == active_ticker else ""
        row_html.append(
            f"""
            <tr class="{active_class}">
              <td class="ticker"><a href="/ticker/{esc(ticker)}">{esc(ticker)}</a></td>
              <td>
                <form method="post" action="/active" class="inline">
                  <input type="hidden" name="ticker" value="{esc(ticker)}">
                  <input type="hidden" name="note" value="{esc(row.get('notes'))}">
                  <button title="Set active ticker" class="icon-btn" type="submit">Target</button>
                </form>
              </td>
              <td>
                <form method="post" action="/queue/update" class="row-form">
                  <input type="hidden" name="ticker" value="{esc(ticker)}">
                  <select name="status" title="Status">{status_options(status)}</select>
                  <input name="priority" value="{esc(row.get('priority'))}" placeholder="P" class="priority" title="Priority">
                  <input name="notes" value="{esc(row.get('notes'))}" placeholder="Note" title="Note">
                  <input name="search_url" value="{esc(row.get('search_url') or default_search_url(ticker))}" title="Search URL">
                  <button title="Save row" class="icon-btn" type="submit">Save</button>
                </form>
              </td>
              <td class="count">{capture_count}</td>
              <td class="links">
                <a href="{esc(vic_atoz_url(ticker))}" target="_blank" rel="noopener">VIC A-Z</a>
                <a href="{esc(row.get('search_url') or default_search_url(ticker))}" target="_blank" rel="noopener">Search</a>
                <a href="/ticker/{esc(ticker)}">Captures</a>
                <form method="post" action="/pdf/import-latest" class="inline">
                  <input type="hidden" name="ticker" value="{esc(ticker)}">
                  <input type="hidden" name="title" value="{esc(ticker + ' VIC PDF')}">
                  <input type="hidden" name="note" value="{esc(row.get('notes'))}">
                  <input type="hidden" name="source_url" value="{esc(row.get('search_url') or default_search_url(ticker))}">
                  <button title="Import newest PDF from Downloads" class="icon-btn" type="submit">Import PDF</button>
                </form>
              </td>
              <td class="last">{esc(row.get('last_captured_at'))}</td>
              <td>
                <form method="post" action="/queue/delete" class="inline">
                  <input type="hidden" name="ticker" value="{esc(ticker)}">
                  <button title="Remove from queue" class="icon-btn danger" type="submit">Remove</button>
                </form>
              </td>
            </tr>
            """
        )
    rows_markup = "\n".join(row_html) if row_html else '<tr><td colspan="7" class="empty">No tickers queued.</td></tr>'
    active_markup = (
        f"""<strong>{esc(active_ticker)}</strong><span>{esc(active.get("note"))}</span>
        <form method="post" action="/pdf/import-latest" class="inline">
          <input type="hidden" name="ticker" value="{esc(active_ticker)}">
          <input type="hidden" name="title" value="{esc(active_ticker + ' VIC PDF')}">
          <input type="hidden" name="note" value="{esc(active.get("note"))}">
          <button title="Import newest PDF from Downloads" class="icon-btn" type="submit">Import Latest PDF</button>
        </form>"""
        if active_ticker
        else "<span>No active ticker</span>"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VIC Intake Queue</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --ink: #17202a;
      --muted: #667085;
      --line: #d9dee7;
      --panel: #ffffff;
      --blue: #285f9f;
      --green: #18794e;
      --red: #a33a32;
      --amber: #946200;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 14px/1.45 "Segoe UI", Arial, sans-serif;
    }}
    header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 16px 22px;
      background: #ffffff;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{ margin: 0; font-size: 20px; font-weight: 650; letter-spacing: 0; }}
    main {{ padding: 18px 22px 28px; }}
    .toolbar {{
      display: grid;
      grid-template-columns: minmax(260px, 1.2fr) minmax(260px, .8fr);
      gap: 14px;
      align-items: stretch;
      margin-bottom: 16px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
    }}
    .panel h2 {{
      margin: 0 0 10px;
      font-size: 14px;
      font-weight: 650;
      color: #263445;
    }}
    .active-line {{ display: flex; align-items: center; gap: 10px; min-height: 32px; }}
    .active-line strong {{ color: var(--green); font-size: 18px; }}
    .active-line span {{ color: var(--muted); }}
    .add-form {{ display: grid; grid-template-columns: 1fr 140px; gap: 8px; }}
    textarea, input, select {{
      width: 100%;
      border: 1px solid #c7ceda;
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      min-height: 32px;
      padding: 6px 8px;
      font: inherit;
    }}
    textarea {{ resize: vertical; min-height: 72px; grid-column: 1 / -1; }}
    button, .button, .bookmarklet {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 32px;
      border: 1px solid #9fb2cc;
      border-radius: 6px;
      background: #eef4fb;
      color: #173a64;
      padding: 6px 10px;
      text-decoration: none;
      cursor: pointer;
      font: inherit;
      white-space: nowrap;
    }}
    button:hover, .button:hover, .bookmarklet:hover {{ background: #e0edf9; }}
    .icon-btn {{ min-width: 64px; }}
    .danger {{ border-color: #d3aaa5; background: #fff1ef; color: var(--red); }}
    .bookmark-actions {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
    .queue-meta {{ color: var(--muted); font-size: 12px; margin-top: 8px; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      background: #fff;
      border: 1px solid var(--line);
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 8px;
      vertical-align: middle;
    }}
    th {{ text-align: left; color: #42526b; background: #f0f3f7; font-size: 12px; font-weight: 650; }}
    tr.is-active td {{ background: #eef8f3; }}
    td.ticker {{ width: 90px; font-weight: 700; }}
    td.count {{ width: 60px; text-align: right; font-variant-numeric: tabular-nums; }}
    td.links {{ width: 210px; }}
    td.last {{ width: 170px; color: var(--muted); font-size: 12px; }}
    .row-form {{ display: grid; grid-template-columns: 120px 56px minmax(160px, .8fr) minmax(190px, 1fr) 70px; gap: 6px; align-items: center; }}
    .row-form .priority {{ text-align: center; }}
    .inline {{ display: inline; }}
    .links a {{ display: inline-block; margin-right: 10px; color: var(--blue); }}
    .empty {{ color: var(--muted); text-align: center; padding: 24px; }}
    code {{ background: #eef1f5; border: 1px solid #d8dde6; border-radius: 4px; padding: 1px 4px; }}
    @media (max-width: 1000px) {{
      .toolbar {{ grid-template-columns: 1fr; }}
      table, thead, tbody, tr, th, td {{ display: block; }}
      thead {{ display: none; }}
      tr {{ border-bottom: 1px solid var(--line); }}
      td {{ border-bottom: 0; }}
      .row-form {{ grid-template-columns: 1fr 60px; }}
      td.links, td.last, td.ticker, td.count {{ width: auto; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>VIC Intake Queue</h1>
    <div class="bookmark-actions">
      <a class="bookmarklet" href="{esc(bm)}">VIC Capture</a>
      <button type="button" onclick="navigator.clipboard.writeText(window.BOOKMARKLET)">Copy Bookmarklet</button>
      <a class="button" href="https://www.valueinvestorsclub.com/ideas/atoz" target="_blank" rel="noopener">VIC A-Z</a>
    </div>
  </header>
  <main>
    <section class="toolbar">
      <div class="panel">
        <h2>Active</h2>
        <div class="active-line">{active_markup}</div>
        <div class="queue-meta">Queue: <code>{esc(queue_rel)}</code></div>
      </div>
      <form method="post" action="/queue/add" class="panel add-form">
        <h2>Add Tickers</h2>
        <textarea name="tickers" placeholder="AMD, NVDA, TPL"></textarea>
        <input name="notes" placeholder="Default note">
        <button type="submit">Add</button>
      </form>
    </section>
    <table>
      <thead>
        <tr>
          <th>Ticker</th>
          <th>Active</th>
          <th>Status / Notes / Search</th>
          <th>Saved</th>
          <th>Links</th>
          <th>Last Capture</th>
          <th>Remove</th>
        </tr>
      </thead>
      <tbody>
        {rows_markup}
      </tbody>
    </table>
  </main>
  <script>
    window.BOOKMARKLET = {json.dumps(bm)};
  </script>
</body>
</html>"""


def ticker_html(ticker: str) -> str:
    ticker = normalize_ticker(ticker)
    notes = list_vic_notes(ticker)
    rows = []
    for note in notes:
        source_link = (
            f'<a href="{esc(note["url"])}" target="_blank" rel="noopener">VIC</a>' if note.get("url") else ""
        )
        rows.append(
            f"""
            <tr>
              <td>{esc(note.get("captured"))}</td>
              <td>{esc(note.get("title"))}</td>
              <td><code>{esc(note.get("path"))}</code></td>
              <td>{source_link}</td>
            </tr>
            """
        )
    body = "\n".join(rows) if rows else '<tr><td colspan="4" class="empty">No captures yet.</td></tr>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(ticker)} VIC Captures</title>
  <style>
    body {{ margin: 0; background: #f7f8fa; color: #17202a; font: 14px/1.45 "Segoe UI", Arial, sans-serif; }}
    header {{ display: flex; align-items: center; justify-content: space-between; padding: 16px 22px; background: #fff; border-bottom: 1px solid #d9dee7; }}
    h1 {{ margin: 0; font-size: 20px; letter-spacing: 0; }}
    main {{ padding: 18px 22px; }}
    a {{ color: #285f9f; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #d9dee7; table-layout: fixed; }}
    th, td {{ padding: 8px; border-bottom: 1px solid #d9dee7; text-align: left; vertical-align: top; }}
    th {{ background: #f0f3f7; color: #42526b; font-size: 12px; }}
    code {{ background: #eef1f5; border: 1px solid #d8dde6; border-radius: 4px; padding: 1px 4px; overflow-wrap: anywhere; }}
    .empty {{ color: #667085; text-align: center; padding: 24px; }}
  </style>
</head>
<body>
  <header>
    <h1>{esc(ticker)} VIC Captures</h1>
    <a href="/">Queue</a>
  </header>
  <main>
    <table>
      <thead><tr><th>Captured</th><th>Title</th><th>Path</th><th>Source</th></tr></thead>
      <tbody>{body}</tbody>
    </table>
  </main>
</body>
</html>"""


class IntakeHandler(BaseHTTPRequestHandler):
    server_version = "VicLocalIntake/1.0"

    def _send(self, status: int, body: str, *, content_type: str = "text/plain; charset=utf-8") -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS, GET")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status: int, payload: dict[str, Any] | list[Any]) -> None:
        self._send(status, json.dumps(payload, indent=2), content_type="application/json; charset=utf-8")

    def _redirect(self, location: str = "/") -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def _payload(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return json.loads(raw.decode("utf-8")) if raw else {}
        parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
        return {key: values[-1] if values else "" for key, values in parsed.items()}

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, "")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/dashboard"):
            self._send(
                200,
                dashboard_html(self.server.queue_path, self.server.active_path, self.server.server_port),  # type: ignore[attr-defined]
                content_type="text/html; charset=utf-8",
            )
            return
        if path == "/bookmarklet":
            bm = bookmarklet(self.server.server_port)  # type: ignore[attr-defined]
            self._send(
                200,
                "\n".join(
                    [
                        "VIC local intake is running.",
                        "",
                        "Create a browser bookmark with this URL, then click it while viewing one VIC idea page:",
                        "",
                        bm,
                        "",
                    ]
                ),
            )
            return
        if path == "/active":
            self._send_json(200, load_active(self.server.active_path))  # type: ignore[attr-defined]
            return
        if path == "/queue.json":
            rows = load_queue(self.server.queue_path)  # type: ignore[attr-defined]
            for row in rows:
                row["captured_count"] = str(count_vic_notes(row["ticker"]))
            self._send_json(200, rows)
            return
        if path.startswith("/ticker/"):
            try:
                ticker = normalize_ticker(path.rsplit("/", 1)[-1])
                self._send(200, ticker_html(ticker), content_type="text/html; charset=utf-8")
            except ValueError as exc:
                self._send(400, str(exc))
            return
        self._send(404, "Not found.")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            payload = self._payload()
            if path == "/capture":
                result = write_vic_note(
                    payload,
                    max_excerpt_chars=self.server.max_excerpt_chars,  # type: ignore[attr-defined]
                    queue_path=self.server.queue_path,  # type: ignore[attr-defined]
                )
                self._send(200, f"Captured VIC note for {result['ticker']}: {result['note']}")
                return
            if path == "/queue/add":
                add_tickers_to_queue(
                    self.server.queue_path,  # type: ignore[attr-defined]
                    str(payload.get("tickers", "")),
                    notes=str(payload.get("notes", "")),
                )
                self._redirect("/")
                return
            if path == "/queue/update":
                update_queue_row(self.server.queue_path, str(payload.get("ticker", "")), payload)  # type: ignore[attr-defined]
                self._redirect("/")
                return
            if path == "/queue/delete":
                remove_queue_row(self.server.queue_path, str(payload.get("ticker", "")))  # type: ignore[attr-defined]
                self._redirect("/")
                return
            if path == "/active":
                active = save_active(
                    self.server.active_path,  # type: ignore[attr-defined]
                    str(payload.get("ticker", "")),
                    note=str(payload.get("note", "")),
                )
                update_queue_row(self.server.queue_path, active["ticker"], {"status": "active"})  # type: ignore[attr-defined]
                if "application/json" in self.headers.get("Content-Type", ""):
                    self._send_json(200, active)
                else:
                    self._redirect("/")
                return
            if path == "/pdf/import-latest":
                ticker = str(payload.get("ticker") or load_active(self.server.active_path).get("ticker", ""))  # type: ignore[attr-defined]
                latest_pdf = find_latest_pdf(
                    self.server.downloads_path,  # type: ignore[attr-defined]
                    max_age_minutes=self.server.pdf_max_age_minutes,  # type: ignore[attr-defined]
                )
                result = write_vic_pdf_import(
                    ticker=ticker,
                    source_pdf=latest_pdf,
                    queue_path=self.server.queue_path,  # type: ignore[attr-defined]
                    title=str(payload.get("title", "")),
                    source_url=str(payload.get("source_url", "")),
                    note=str(payload.get("note", "")),
                )
                if "application/json" in self.headers.get("Content-Type", ""):
                    self._send_json(200, result)
                else:
                    self._redirect(f"/ticker/{result['ticker']}")
                return
            self._send(404, "Not found.")
        except Exception as exc:  # pragma: no cover - exercised by manual browser use
            self._send(400, f"VIC intake request failed: {exc}")

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def serve(
    host: str,
    port: int,
    *,
    max_excerpt_chars: int,
    queue_path: Path,
    active_path: Path,
    downloads_path: Path,
    pdf_max_age_minutes: int,
) -> None:
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    if not queue_path.exists():
        save_queue(queue_path, [])
    server = ThreadingHTTPServer((host, port), IntakeHandler)
    server.max_excerpt_chars = max_excerpt_chars  # type: ignore[attr-defined]
    server.queue_path = queue_path  # type: ignore[attr-defined]
    server.active_path = active_path  # type: ignore[attr-defined]
    server.downloads_path = downloads_path  # type: ignore[attr-defined]
    server.pdf_max_age_minutes = pdf_max_age_minutes  # type: ignore[attr-defined]
    print(f"VIC local intake listening on http://{host}:{port}/")
    print(f"Queue: {queue_path}")
    print(f"Downloads: {downloads_path}")
    print("Bookmarklet:")
    print(bookmarklet(port))
    print("\nUse the dashboard to set an active ticker, then click the bookmarklet on a VIC idea page.")
    server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description="Local, single-page VIC intake into third-party pending notes")
    parser.add_argument("--serve", action="store_true", help="Start localhost capture server")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--max-excerpt-chars", type=int, default=DEFAULT_MAX_EXCERPT_CHARS)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE, help="CSV queue path")
    parser.add_argument("--active-file", type=Path, default=DEFAULT_ACTIVE, help="Active ticker JSON path")
    parser.add_argument("--downloads", type=Path, default=DEFAULT_DOWNLOADS, help="Folder to scan for latest PDF")
    parser.add_argument(
        "--pdf-max-age-minutes",
        type=int,
        default=DEFAULT_PDF_MAX_AGE_MINUTES,
        help="Only import latest PDF if it is this recent; 0 disables the age check",
    )
    parser.add_argument("--tickers", help="Comma/space/newline separated tickers to add to the queue")
    parser.add_argument("--print-bookmarklet", action="store_true", help="Print the bookmarklet and exit")
    parser.add_argument("--from-json", type=Path, help="Import a saved bookmarklet payload JSON file")
    args = parser.parse_args()
    queue_path = resolve_repo_path(args.queue, default=DEFAULT_QUEUE)
    active_path = resolve_repo_path(args.active_file, default=DEFAULT_ACTIVE)
    downloads_path = resolve_repo_path(args.downloads, default=DEFAULT_DOWNLOADS)

    if args.print_bookmarklet:
        print(bookmarklet(args.port))
        return 0
    if args.tickers:
        added = add_tickers_to_queue(queue_path, args.tickers)
        print(f"Queued {len(added)} new ticker(s): {', '.join(added) if added else '(none)'}")
    if args.from_json:
        payload = json.loads(args.from_json.read_text(encoding="utf-8"))
        result = write_vic_note(payload, max_excerpt_chars=args.max_excerpt_chars, queue_path=queue_path)
        print(json.dumps(result, indent=2))
        return 0
    if args.serve:
        serve(
            args.host,
            args.port,
            max_excerpt_chars=args.max_excerpt_chars,
            queue_path=queue_path,
            active_path=active_path,
            downloads_path=downloads_path,
            pdf_max_age_minutes=args.pdf_max_age_minutes,
        )
        return 0
    if args.tickers:
        return 0

    parser.error("Choose --serve, --print-bookmarklet, --tickers, or --from-json.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
