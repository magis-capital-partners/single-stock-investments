#!/usr/bin/env python3
"""Harvest IR + rebuild equity model outputs for registry-enabled tickers."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
PY = sys.executable
REGISTRY = ROOT / "_system" / "portfolio" / "equity_model_registry.json"
SUBENV = {**dict(__import__("os").environ), "PYTHONIOENCODING": "utf-8"}


def safe_print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))

TICKER_STEPS: dict[str, dict] = {
    "7176.T": {
        "ir_script": "7176.T/_scripts/download_sfh_ir.py",
        "mandate_script": "7176.T/_scripts/download_mandate_nav.py",
        "model_dir": "7176.T/research/model",
        "pipeline": ("build_panel.py", "model.py", "model_diagnostics.py"),
    },
}


def load_enabled() -> list[str]:
    if not REGISTRY.exists():
        return []
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return list(data.get("enabled") or [])


def safe_name(name: str) -> str:
    return re.sub(r"[^\w.\-]", "_", name)[:120]


def extract_jp_pdfs(ticker: str) -> int:
    """Extract new/changed PDFs to research/evidence/_text (no translation)."""
    sys.path.insert(0, str(SCRIPTS))
    from pdf_ocr import extract_pdf_text

    ticker_dir = ROOT / ticker
    evidence = ticker_dir / "research" / "evidence" / "_text"
    evidence.mkdir(parents=True, exist_ok=True)
    n = 0
    for pdf in sorted(ticker_dir.rglob("*.pdf")):
        rel = pdf.relative_to(ticker_dir).as_posix()
        if rel.startswith("research/"):
            continue
        out = evidence / (safe_name(pdf.name) + ".txt")
        if out.exists() and out.stat().st_mtime >= pdf.stat().st_mtime:
            continue
        pages = 120 if "finfo" in pdf.name or "発行者" in pdf.name else 40
        result = extract_pdf_text(pdf, max_pages=pages, force_ocr=False)
        text = (result.get("text") or "").strip()
        if len(text) < 100:
            result = extract_pdf_text(pdf, max_pages=pages, force_ocr=True)
            text = (result.get("text") or "").strip()
        if not text:
            continue
        out.write_text(text[:200_000], encoding="utf-8")
        n += 1
        safe_print(f"  extract {rel} -> {out.name} ({len(text)} chars)")
    return n


def run_script(rel: str, label: str) -> None:
    path = ROOT / rel
    if not path.exists():
        print(f"[skip] {label}: missing {rel}")
        return
    print(f"\n=== {label} ===")
    subprocess.run([PY, str(path)], cwd=ROOT, check=False, env=SUBENV)


def refresh_ticker(ticker: str) -> None:
    cfg = TICKER_STEPS.get(ticker)
    if not cfg:
        print(f"[skip] no refresh config for {ticker}")
        return
    print(f"\n--- equity model refresh: {ticker} ---")
    if cfg.get("ir_script"):
        run_script(cfg["ir_script"], f"{ticker} IR harvest")
    if cfg.get("mandate_script"):
        run_script(cfg["mandate_script"], f"{ticker} mandate NAV scrape")
    extracted = extract_jp_pdfs(ticker)
    print(f"  extracted {extracted} PDF(s) to evidence/_text")
    model_dir = ROOT / cfg["model_dir"]
    for script in cfg.get("pipeline") or ():
        print(f"\n=== {ticker} {script} ===")
        subprocess.run([PY, script], cwd=model_dir, check=False, env=SUBENV)


def main() -> None:
    tickers = [t for t in load_enabled() if t in TICKER_STEPS]
    if not tickers:
        print("No equity-model tickers with refresh config.")
        return
    for ticker in tickers:
        refresh_ticker(ticker)
    print("\nEquity model refresh finished.")


if __name__ == "__main__":
    main()
