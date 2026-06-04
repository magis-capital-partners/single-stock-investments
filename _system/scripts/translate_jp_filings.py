#!/usr/bin/env python3
"""Extract and translate Japanese ticker PDFs to English text caches.

Outputs under {TICKER}/research/evidence/_text_en/ and manifest
{TICKER}/research/evidence/translation_manifest_{date}.json

Usage:
  python3 _system/scripts/translate_jp_filings.py 7176.T
  python3 _system/scripts/translate_jp_filings.py 7176.T --max-docs 20
  python3 _system/scripts/translate_jp_filings.py 7176.T --force
"""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TODAY = date.today().isoformat()
CHUNK = 4500
SLEEP_S = 0.12


def safe_name(name: str) -> str:
    return re.sub(r"[^\w.\-]", "_", name)[:120]


def has_japanese(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", text))


def translate_chunks(text: str) -> str:
    from deep_translator import GoogleTranslator

    tr = GoogleTranslator(source="ja", target="en")
    text = text.strip()
    if not text:
        return ""
    if not has_japanese(text):
        return text
    parts: list[str] = []
    i = 0
    while i < len(text):
        block = text[i : i + CHUNK]
        for attempt in range(4):
            try:
                parts.append(tr.translate(block))
                break
            except Exception:
                time.sleep(2 ** attempt)
        else:
            parts.append(block)
        i += CHUNK
        time.sleep(SLEEP_S)
    return "\n".join(parts)


def extract_pdf(path: Path, *, max_pages: int, force_ocr: bool) -> str:
    import sys

    sys.path.insert(0, str(ROOT / "_system" / "scripts"))
    from pdf_ocr import extract_pdf_text

    r = extract_pdf_text(path, max_pages=max_pages, force_ocr=force_ocr)
    return (r.get("text") or "").strip()


def list_pdfs(ticker_dir: Path) -> list[Path]:
    out: list[Path] = []
    for p in ticker_dir.rglob("*.pdf"):
        rel = p.relative_to(ticker_dir).as_posix()
        if rel.startswith("research/") or "/." in rel:
            continue
        out.append(p)
    return sorted(out, key=lambda x: x.stat().st_mtime, reverse=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--max-docs", type=int, default=0, help="0 = all PDFs")
    parser.add_argument("--max-pages", type=int, default=40)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--ocr-if-short", action="store_true", default=True)
    args = parser.parse_args()

    ticker_dir = ROOT / args.ticker
    evidence = ticker_dir / "research" / "evidence"
    src_cache = evidence / "_text"
    en_dir = evidence / "_text_en"
    en_dir.mkdir(parents=True, exist_ok=True)

    pdfs = list_pdfs(ticker_dir)
    if args.max_docs:
        pdfs = pdfs[: args.max_docs]

    manifest: list[dict] = []
    for i, pdf in enumerate(pdfs, 1):
        rel = pdf.relative_to(ticker_dir).as_posix()
        out_name = safe_name(pdf.name) + ".en.txt"
        out_path = en_dir / out_name
        entry = {"path": rel, "en_path": f"research/evidence/_text_en/{out_name}", "status": "skip"}

        if out_path.exists() and not args.force and out_path.stat().st_size > 200:
            entry["status"] = "cached"
            manifest.append(entry)
            continue

        # Reuse Japanese extract cache if present
        ja_cached = src_cache / (safe_name(pdf.name) + ".txt")
        text = ""
        if ja_cached.exists() and not args.force:
            text = ja_cached.read_text(encoding="utf-8", errors="ignore")
        if len(text) < 400:
            force_ocr = args.ocr_if_short and len(text) < 200
            pages = 120 if "finfo" in pdf.name or "Governance" in rel else args.max_pages
            text = extract_pdf(pdf, max_pages=pages, force_ocr=force_ocr)
            if text:
                src_cache.mkdir(parents=True, exist_ok=True)
                ja_cached.write_text(text[:200_000], encoding="utf-8")

        if not text:
            stub = (
                f"# English translation\n# Source: {rel}\n# Generated: {TODAY}\n\n"
                "[No extractable text from PDF in automated pass — likely image-only scan. "
                "Re-run with OCR or obtain text layer.] [HUMAN REVIEW]\n"
            )
            out_path.write_text(stub, encoding="utf-8")
            entry["status"] = "no_text_stub"
            manifest.append(entry)
            print(f"[{i}/{len(pdfs)}] STUB no text {rel}")
            continue

        en = translate_chunks(text)
        header = f"# English translation\n# Source: {rel}\n# Generated: {TODAY}\n\n"
        out_path.write_text(header + en, encoding="utf-8")
        entry["status"] = "ok"
        entry["ja_chars"] = len(text)
        entry["en_chars"] = len(en)
        manifest.append(entry)
        print(f"[{i}/{len(pdfs)}] OK {rel} -> {out_name} ({len(en)} chars)")

    man_path = evidence / f"translation_manifest_{TODAY}.json"
    man_path.write_text(
        json.dumps(
            {"ticker": args.ticker, "as_of": TODAY, "count": len(manifest), "documents": manifest},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ok = sum(1 for m in manifest if m["status"] == "ok")
    print(f"Done {args.ticker}: translated/cached {ok}/{len(manifest)} -> {man_path}")


if __name__ == "__main__":
    main()
