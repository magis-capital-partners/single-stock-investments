#!/usr/bin/env python3
"""Extract text from Darwin 1Q26 PDF into darwin_source_notes (requires pdf in repo)."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PDF = ROOT / "_system" / "reference" / "quant-evolution" / "Darwin_AI_Investments_1Q26.pdf"
OUT = ROOT / "_system" / "reference" / "quant-evolution" / "darwin_source_notes.md"
EXTRACT = ROOT / "_system" / "reference" / "quant-evolution" / "Darwin_AI_Investments_1Q26_extract.txt"


def extract_text() -> str:
    if not PDF.exists():
        print(f"Missing PDF. Run copy_darwin_investor_pdf.ps1 first.\n  Expected: {PDF}", file=sys.stderr)
        sys.exit(1)
    try:
        import pypdf  # type: ignore

        reader = pypdf.PdfReader(str(PDF))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except ImportError:
        pass
    if subprocess.run(["which", "pdftotext"], capture_output=True).returncode == 0:
        subprocess.run(["pdftotext", str(PDF), str(EXTRACT)], check=True)
        return EXTRACT.read_text(encoding="utf-8", errors="ignore")
    print("Install pypdf: pip install pypdf", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    text = extract_text()
    EXTRACT.write_text(text, encoding="utf-8")
    bullets = []
    for line in text.splitlines():
        line = line.strip()
        if len(line) > 40 and re.search(r"(reinforc|neural|portfolio|return|risk|turnover|equity)", line, re.I):
            bullets.append(line[:200])
    bullet_md = "\n".join(f"- {b}" for b in bullets[:25]) or "- _(no auto bullets — review extract file)_"

    header = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    if "## Claims extracted (fill from PDF)" in header:
        new_section = f"""## Claims extracted (auto-ingest)

{bullet_md}

Full text: `Darwin_AI_Investments_1Q26_extract.txt` ({len(text)} chars).
"""
        header = re.sub(
            r"## Claims extracted \(fill from PDF\).*?(?=\n## |\Z)",
            new_section + "\n",
            header,
            flags=re.DOTALL,
        )
    else:
        header += "\n\n" + bullet_md
    OUT.write_text(header, encoding="utf-8")
    print(f"Wrote extract ({len(text)} chars) and updated {OUT.name}")


if __name__ == "__main__":
    main()
