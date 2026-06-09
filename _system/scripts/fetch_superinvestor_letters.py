#!/usr/bin/env python3
"""Fetch superinvestor letter PDFs from configured Dropbox shared folders.

Dropbox shared folders support bulk download as zip when dl=1 is appended.

Usage:
  python _system/scripts/fetch_superinvestor_letters.py --all
  python _system/scripts/fetch_superinvestor_letters.py --quarter 2026Q2
  python _system/scripts/fetch_superinvestor_letters.py --all --build
  python _system/scripts/fetch_superinvestor_letters.py --all --max-files 5  # smoke test
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
LETTERS_ROOT = ROOT / "_system" / "reference" / "superinvestor-letters"
SOURCES_PATH = LETTERS_ROOT / "sources.json"
INCOMING = LETTERS_ROOT / "INCOMING"
FETCH_LOG = LETTERS_ROOT / "fetch_log.jsonl"

USER_AGENT = "MarvinResearch/1.0 (+single-stock-investments; superinvestor-letters)"


def load_sources() -> list[dict]:
    doc = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    return doc.get("sources") or []


def ensure_dl1(url: str) -> str:
    if "dl=1" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}dl=1"


def safe_name(name: str) -> str:
    base = Path(name).name
    base = re.sub(r'[<>:"/\\|?*]', "_", base)
    base = re.sub(r"\s+", " ", base).strip()
    return base or "letter.pdf"


def log_event(event: dict) -> None:
    LETTERS_ROOT.mkdir(parents=True, exist_ok=True)
    event["ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with FETCH_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")


def download_zip(url: str, dest: Path, *, timeout: int = 600) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = Request(ensure_dl1(url), headers={"User-Agent": USER_AGENT})
    print(f"  Downloading {dest.name} …", flush=True)
    with urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    dest.write_bytes(data)
    size = len(data)
    if size < 1024 or not data[:2] == b"PK":
        preview = data[:200].decode("utf-8", errors="replace")
        raise RuntimeError(f"Download is not a zip ({size} bytes): {preview[:120]}")
    print(f"  Saved {size / 1_048_576:.1f} MB -> {dest}")
    log_event({"action": "download", "path": str(dest.relative_to(ROOT)), "bytes": size})
    return {"bytes": size, "path": str(dest)}


def extract_zip(zip_path: Path, quarter_dir: Path) -> list[Path]:
    quarter_dir.mkdir(parents=True, exist_ok=True)
    pdfs: list[Path] = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if not name.lower().endswith(".pdf"):
                continue
            target = quarter_dir / safe_name(name)
            # zip-slip guard
            if not str(target.resolve()).startswith(str(quarter_dir.resolve())):
                continue
            if target.exists() and target.stat().st_size == info.file_size:
                pdfs.append(target)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                dst.write(src.read())
            pdfs.append(target)
    print(f"  Extracted {len(pdfs)} PDFs -> {quarter_dir}")
    log_event({"action": "extract", "quarter": quarter_dir.name, "pdf_count": len(pdfs)})
    return sorted(pdfs)


def extract_texts(pdfs: list[Path], *, max_pages: int = 40, max_files: int | None = None) -> int:
    sys.path.insert(0, str(SCRIPTS))
    from pdf_ocr import extract_pdf_text  # noqa: WPS433

    n = 0
    todo = pdfs[:max_files] if max_files else pdfs
    for i, pdf in enumerate(todo, 1):
        txt = pdf.with_suffix(".txt")
        if txt.exists() and txt.stat().st_mtime >= pdf.stat().st_mtime:
            continue
        if i % 10 == 1 or i == len(todo):
            print(f"  Text extract {i}/{len(todo)}: {pdf.name}", flush=True)
        result = extract_pdf_text(pdf, max_pages=max_pages)
        text = (result.get("text") or "").strip()
        if len(text) < 50:
            result = extract_pdf_text(pdf, max_pages=max_pages, force_ocr=True)
            text = (result.get("text") or "").strip()
        txt.write_text(text + "\n", encoding="utf-8")
        n += 1
    if n:
        log_event({"action": "text_extract", "new_or_updated": n, "total": len(todo)})
    print(f"  Wrote/updated {n} .txt extracts")
    return n


def process_source(src: dict, *, skip_download: bool, max_files: int | None) -> dict:
    quarter = src["quarter"]
    quarter_dir = LETTERS_ROOT / quarter
    zip_path = INCOMING / f"{quarter}.zip"

    if not skip_download or not zip_path.exists():
        download_zip(src["url"], zip_path)
    elif zip_path.exists():
        print(f"  Reusing {zip_path.name}")

    pdfs = extract_zip(zip_path, quarter_dir)
    text_n = extract_texts(pdfs, max_files=max_files)
    return {"quarter": quarter, "pdf_count": len(pdfs), "text_updated": text_n}


def run_build_pipeline() -> None:
    py = sys.executable
    steps = [
        ("superinvestor insights", SCRIPTS / "build_superinvestor_insights.py", []),
        ("insights merge", SCRIPTS / "build_insights.py", []),
        ("relevance calibration", SCRIPTS / "relevance_calibration_check.py", []),
    ]
    for label, script, args in steps:
        print(f"  {label}...", flush=True)
        r = subprocess.run([py, str(script), *args], cwd=str(ROOT))
        if r.returncode != 0:
            raise SystemExit(f"FAIL: {label}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch superinvestor letters from Dropbox")
    parser.add_argument("--all", action="store_true", help="Process all sources in sources.json")
    parser.add_argument("--quarter", help="Single quarter id e.g. 2026Q1")
    parser.add_argument("--skip-download", action="store_true", help="Reuse existing INCOMING/*.zip")
    parser.add_argument("--skip-text", action="store_true", help="Skip PDF -> txt extraction")
    parser.add_argument("--max-files", type=int, help="Limit text extraction count (smoke test)")
    parser.add_argument("--build", action="store_true", help="Run build_superinvestor_insights + build_insights after fetch")
    args = parser.parse_args()

    sources = load_sources()
    if args.quarter:
        sources = [s for s in sources if s.get("quarter") == args.quarter or s.get("id") == args.quarter]
    elif not args.all:
        parser.error("Provide --all or --quarter 2026Q1")

    if not sources:
        print("No matching sources in sources.json")
        return 1

    print(f"=== fetch_superinvestor_letters ({len(sources)} source(s)) ===")
    results = []
    for src in sources:
        print(f"\n[{src['id']}] {src.get('label', '')}")
        if args.skip_text:
            quarter_dir = LETTERS_ROOT / src["quarter"]
            zip_path = INCOMING / f"{src['quarter']}.zip"
            if not args.skip_download or not zip_path.exists():
                download_zip(src["url"], zip_path)
            pdfs = extract_zip(zip_path, quarter_dir)
            results.append({"quarter": src["quarter"], "pdf_count": len(pdfs), "text_updated": 0})
        else:
            results.append(process_source(src, skip_download=args.skip_download, max_files=args.max_files))

    if args.build:
        print("\n=== build pipeline ===")
        run_build_pipeline()

    print("\nDone:", json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
