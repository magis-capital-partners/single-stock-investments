#!/usr/bin/env python3
"""Extract text from biotech-quant PDFs into _text/."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "_system" / "reference" / "biotech-quant"
PAPERS = BASE / "papers"
TEXT = BASE / "_text"


def main() -> int:
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader  # type: ignore

    TEXT.mkdir(parents=True, exist_ok=True)
    count = 0
    for pdf in sorted(PAPERS.glob("**/*.pdf")):
        reader = PdfReader(str(pdf))
        txt = "\n".join((p.extract_text() or "") for p in reader.pages)
        out = TEXT / f"{pdf.stem}.txt"
        out.write_text(txt, encoding="utf-8")
        print(f"Wrote {out.relative_to(ROOT)} ({len(reader.pages)} pages, {len(txt)} chars)")
        count += 1
    print(f"OK: {count} PDF extract(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
