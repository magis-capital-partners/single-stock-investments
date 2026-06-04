#!/usr/bin/env python3
"""Render Marvin markdown equity report to PDF (fpdf2)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MD = ROOT / "research" / "equity_report_skeptical_2026-06-04.md"
DEFAULT_PDF = ROOT / "research" / "equity_report_skeptical_2026-06-04.pdf"


class ReportPDF(FPDF):
    def header(self) -> None:
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, "7176.T Simplex Financial Holdings - Skeptical Equity Report", align="R")
        self.ln(10)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")


def sanitize(text: str) -> str:
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    text = text.replace("\u00a5", "JPY ")
    text = text.replace("\u2022", "-")
    return text.encode("latin-1", "replace").decode("latin-1")


def write_wrapped(pdf: ReportPDF, text: str, size: int = 10, style: str = "") -> None:
    pdf.set_font("Helvetica", style, size)
    pdf.set_text_color(0, 0, 0)
    w = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.multi_cell(w, size * 0.45, sanitize(text))


def render_markdown(md_path: Path, pdf_path: Path) -> None:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    pdf = ReportPDF()
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_margins(18, 18, 18)

    in_table = False
    in_code = False
    table_rows: list[list[str]] = []

    def flush_table() -> None:
        nonlocal in_table, table_rows
        if not table_rows:
            return
        col_w = (pdf.w - 36) / max(len(table_rows[0]), 1)
        pdf.set_font("Helvetica", "B", 8)
        for i, row in enumerate(table_rows):
            if i == 1 and all(set(c) <= {"-", " ", "|", ":"} for c in "".join(row)):
                continue
            pdf.set_font("Helvetica", "B" if i == 0 else "", 8)
            for cell in row:
                pdf.cell(col_w, 6, sanitize(cell[:42]), border=1)
            pdf.ln()
        pdf.ln(2)
        table_rows = []
        in_table = False

    for raw in lines:
        line = raw.rstrip()
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if line.startswith("|") and "|" in line[1:]:
            in_table = True
            cells = [c.strip() for c in line.strip("|").split("|")]
            table_rows.append(cells)
            continue
        if in_table:
            flush_table()

        if not line.strip():
            pdf.ln(3)
            continue
        if line.startswith("```"):
            continue
        if line.startswith("# "):
            pdf.ln(4)
            write_wrapped(pdf, line[2:].strip(), size=16, style="B")
            pdf.ln(2)
        elif line.startswith("## "):
            pdf.ln(3)
            write_wrapped(pdf, line[3:].strip(), size=13, style="B")
            pdf.ln(1)
        elif line.startswith("### "):
            pdf.ln(2)
            write_wrapped(pdf, line[4:].strip(), size=11, style="B")
        elif line.startswith("- "):
            write_wrapped(pdf, "  - " + line[2:].strip(), size=9)
        elif re.match(r"^\d+\.\s", line):
            write_wrapped(pdf, "  " + line.strip(), size=9)
        else:
            write_wrapped(pdf, line.strip(), size=9)

    if in_table:
        flush_table()

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(pdf_path))
    print(f"Wrote {pdf_path} ({pdf_path.stat().st_size} bytes)")


def main() -> int:
    md = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MD
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PDF
    if not md.is_file():
        print(f"Missing {md}", file=sys.stderr)
        return 1
    render_markdown(md, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
