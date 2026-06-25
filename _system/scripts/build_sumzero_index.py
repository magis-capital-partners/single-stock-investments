#!/usr/bin/env python3
"""Build a compact, dashboard-safe index for the local SumZero Ideas archive."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARCHIVE = Path.home() / "Downloads" / "SumZero Ideas.zip"
OUTPUT = ROOT / "_system" / "reference" / "data-sources" / "sumzero_ideas_index.json"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
STAGING_DIR = ROOT / "_system" / "reference" / "sumzero-research"

LEGAL_SUFFIXES = {
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "company",
    "co",
    "limited",
    "ltd",
    "plc",
    "group",
    "holdings",
    "holding",
    "trust",
    "partners",
    "partner",
    "lp",
    "llc",
    "sa",
    "nv",
    "ag",
}

GENERIC_SINGLE_TOKENS = LEGAL_SUFFIXES | {
    "capital",
    "cloud",
    "consensus",
    "deutsche",
    "devices",
    "digital",
    "electric",
    "energy",
    "exchange",
    "financial",
    "finance",
    "global",
    "indian",
    "industries",
    "industry",
    "infrastructure",
    "international",
    "japan",
    "japanese",
    "limited",
    "london",
    "medical",
    "micro",
    "mining",
    "natural",
    "payments",
    "pharma",
    "power",
    "resource",
    "resources",
    "royalty",
    "seigniorage",
    "software",
    "solutions",
    "stock",
    "systems",
}

THEME_PATTERNS = {
    "short": ("short", "overvalued", "fraud", "bubble", "downside"),
    "long": ("long", "undervalued", "mispriced", "compounder", "pitch", "thesis", "write up"),
    "special_situation": ("spin", "spinoff", "stub", "merger", "restructuring", "liquidation"),
    "valuation": ("valuation", "target", "multiple", "fcf", "ebitda"),
    "catalyst": ("catalyst", "activist", "buyback", "inflection", "rerate", "re-rate"),
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize(value: str) -> str:
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def contains_phrase(haystack: str, needle: str) -> bool:
    if not needle:
        return False
    return bool(re.search(rf"(^| ){re.escape(needle)}( |$)", haystack))


def rel_or_hint(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        home = Path.home()
        try:
            return "~/" + str(path.relative_to(home)).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")


def safe_filename(value: str) -> str:
    name = Path(value).name.strip() or "sumzero-document.pdf"
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        return "sumzero-document.pdf"
    suffix = Path(name).suffix
    stem = Path(name).stem
    max_len = 120
    if len(name) > max_len:
        room = max_len - len(suffix)
        name = f"{stem[:room].rstrip(' .')}{suffix}"
    return name


def staged_pdf_path(doc_id: str, filename: str, staging_dir: Path = STAGING_DIR) -> Path:
    return staging_dir / doc_id / safe_filename(filename)


def extract_pdf_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, target: Path) -> None:
    if target.exists() and target.stat().st_size == info.file_size:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with zf.open(info) as src, target.open("wb") as dst:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            dst.write(chunk)


def load_registry_rows() -> list[dict]:
    if not REGISTRY_PATH.exists():
        return []
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for section in ("holdings", "watchlist"):
        for ticker, meta in (registry.get(section) or {}).items():
            rows.append(
                {
                    "ticker": str(ticker).upper(),
                    "company": str((meta or {}).get("company") or ticker),
                    "section": section,
                }
            )
    return rows


def company_aliases(company: str) -> list[dict]:
    words = [w for w in normalize(company).split() if w not in LEGAL_SUFFIXES]
    aliases: list[dict] = []
    if not words:
        return aliases

    distinctive = [w for w in words if w not in GENERIC_SINGLE_TOKENS and len(w) >= 5]
    if len(words) >= 2 and distinctive:
        phrase = " ".join(words[: min(len(words), 4)])
        aliases.append({"value": phrase, "type": "company_phrase", "score": 0.9})
    for token in distinctive:
        aliases.append({"value": token, "type": "company_token", "score": 0.84})

    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for alias in aliases:
        key = (alias["value"], alias["type"])
        if key not in seen:
            seen.add(key)
            out.append(alias)
    return out


def ticker_aliases(ticker: str) -> list[dict]:
    ticker_norm = normalize(ticker.replace(".", " ").replace("-", " "))
    aliases = [{"value": ticker_norm, "type": "exact_ticker", "score": 1.0}]
    if "." not in ticker and "-" not in ticker and len(ticker) >= 3:
        aliases.append({"value": ticker.lower(), "type": "exact_ticker", "score": 1.0})
    return aliases


def build_alias_rows(registry_rows: list[dict]) -> list[dict]:
    aliases: list[dict] = []
    for row in registry_rows:
        for alias in ticker_aliases(row["ticker"]):
            aliases.append({**row, **alias})
        for alias in company_aliases(row["company"]):
            aliases.append({**row, **alias})
    aliases.sort(key=lambda a: (a["score"], len(a["value"])), reverse=True)
    return aliases


def entry_date(info: zipfile.ZipInfo) -> str:
    try:
        return datetime(*info.date_time).date().isoformat()
    except (TypeError, ValueError):
        return ""


def guess_document_date(title: str, fallback: str) -> str:
    text = title.replace("_", " ").replace("-", " ")
    m = re.search(r"\b(20\d{2}|19\d{2})[. _-]?([01]\d)[. _-]?([0-3]\d)\b", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"\b([01]?\d)[. _-]([0-3]?\d)[. _-](20\d{2}|\d{2})\b", text)
    if m:
        year = m.group(3)
        if len(year) == 2:
            year = "20" + year if int(year) < 40 else "19" + year
        return f"{int(year):04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    m = re.search(r"\b(20\d{2}|19\d{2})\b", text)
    if m:
        return f"{m.group(1)}-01-01"
    return fallback


def direction_and_tags(title: str) -> tuple[str, list[str]]:
    low = title.lower()
    tags = [tag for tag, terms in THEME_PATTERNS.items() if any(term in low for term in terms)]
    if "short" in tags:
        return "bearish", tags
    if "long" in tags or any(tag in tags for tag in ("valuation", "catalyst", "special_situation")):
        return "bullish", tags
    return "neutral", tags


def document_type(name: str) -> str:
    suffix = Path(name).suffix.lower().lstrip(".")
    return suffix or "unknown"


def document_id(info: zipfile.ZipInfo) -> str:
    raw = f"{info.filename}|{info.file_size}|{info.CRC}|{info.date_time}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def match_entry(title: str, aliases: list[dict]) -> dict | None:
    norm_title = normalize(title)
    candidates: list[dict] = []
    for alias in aliases:
        if contains_phrase(norm_title, alias["value"]):
            candidates.append(alias)
    if not candidates:
        return None
    candidates.sort(key=lambda a: (a["score"], len(a["value"])), reverse=True)
    best = candidates[0]
    confidence = "high" if best["type"] == "exact_ticker" else "med"
    return {
        "ticker": best["ticker"],
        "company": best["company"],
        "portfolio_section": best["section"],
        "match_type": best["type"],
        "matched_alias": best["value"],
        "match_score": best["score"],
        "confidence": confidence,
    }


def build_index(archive: Path, extract_pdfs: bool = True, staging_dir: Path = STAGING_DIR) -> dict:
    generated_at = now_utc()
    registry_rows = load_registry_rows()
    aliases = build_alias_rows(registry_rows)

    if not archive.exists():
        return {
            "schema_version": 1,
            "source": "sumzero_ideas",
            "source_label": "SumZero Ideas",
            "generated_at": generated_at,
            "status": "missing",
            "archive": {"path": rel_or_hint(archive), "exists": False},
            "summary": {
                "documents": 0,
                "matched_documents": 0,
                "matched_ticker_count": 0,
            },
            "documents": [],
            "matched_documents": [],
        }

    documents: list[dict] = []
    matched: list[dict] = []
    latest_modified = ""
    total_bytes = 0

    extracted_pdf_count = 0

    with zipfile.ZipFile(archive) as zf:
        entries = [info for info in zf.infolist() if not info.is_dir() and info.file_size > 0]
        for info in entries:
            full_name = info.filename
            filename = Path(full_name).name
            doc_id = document_id(info)
            title = Path(filename).stem.strip() or filename
            modified = entry_date(info)
            latest_modified = max(latest_modified, modified)
            total_bytes += info.file_size
            doc_date = guess_document_date(title, modified)
            direction, tags = direction_and_tags(title)
            local_pdf_path = None
            if document_type(filename) == "pdf":
                target = staged_pdf_path(doc_id, filename, staging_dir)
                if extract_pdfs:
                    extract_pdf_member(zf, info, target)
                    extracted_pdf_count += 1
                if target.exists():
                    local_pdf_path = rel_or_hint(target)
            doc = {
                "id": doc_id,
                "archive_member": full_name,
                "filename": filename,
                "title": title,
                "document_type": document_type(filename),
                "file_size": info.file_size,
                "last_modified": modified,
                "document_date": doc_date,
                "direction": direction,
                "theme_tags": tags,
            }
            if local_pdf_path:
                doc["local_pdf_path"] = local_pdf_path
            match = match_entry(title, aliases)
            if match:
                doc["match"] = match
                matched.append(doc)
            documents.append(doc)

    by_ticker = Counter(d["match"]["ticker"] for d in matched)
    by_match_type = Counter(d["match"]["match_type"] for d in matched)
    by_direction = Counter(d["direction"] for d in matched)

    return {
        "schema_version": 1,
        "source": "sumzero_ideas",
        "source_label": "SumZero Ideas",
        "generated_at": generated_at,
        "status": "ok",
        "archive": {
            "path": rel_or_hint(archive),
            "exists": True,
            "entry_count": len(documents),
            "total_bytes": total_bytes,
            "latest_modified": latest_modified,
        },
        "match_policy": {
            "front_scope": "portfolio holdings plus watchlist only",
            "exact_ticker": "strong evidence",
            "company_phrase_or_distinctive_token": "medium evidence; generic financial terms are suppressed",
            "raw_documents": "not committed; index links back to the local archive member",
        },
        "summary": {
            "documents": len(documents),
            "matched_documents": len(matched),
            "matched_ticker_count": len(by_ticker),
            "extracted_pdfs": extracted_pdf_count,
            "by_ticker": dict(sorted(by_ticker.items())),
            "by_match_type": dict(sorted(by_match_type.items())),
            "by_direction": dict(sorted(by_direction.items())),
        },
        "documents": documents,
        "matched_documents": matched,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Index local SumZero Ideas archive for dashboard insights.")
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE, help="Path to SumZero Ideas.zip")
    parser.add_argument("--output", type=Path, default=OUTPUT, help="Output JSON path")
    parser.add_argument("--staging-dir", type=Path, default=STAGING_DIR, help="Gitignored folder for extracted SumZero PDFs")
    parser.add_argument("--no-extract-pdfs", action="store_true", help="Only index the archive; do not refresh staged PDFs")
    args = parser.parse_args()

    doc = build_index(args.archive.expanduser(), extract_pdfs=not args.no_extract_pdfs, staging_dir=args.staging_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    summary = doc.get("summary") or {}
    print(
        f"Wrote {args.output} "
        f"({summary.get('documents', 0)} docs, {summary.get('matched_documents', 0)} portfolio matches)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
