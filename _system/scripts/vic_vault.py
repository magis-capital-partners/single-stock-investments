#!/usr/bin/env python3
"""Stage Value Investors Club writeups into research-vault like SumZero.

Drive Intake still drops the original PDF on Shared Drive and imports a working
copy into `{TICKER}/third-party-analyses/vic/`. This module copies that file into
`research-vault/vic-research/{TICKER}/` and writes a `.txt` extract. PDFs stay
gitignored in the vault; extracts are the committed artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from vault_paths import research_vault_root, vic_ref, vic_root  # noqa: E402

SKIP_TICKER_DIRS = {"_system", "dashboard", ".git", ".github", ".cursor", "_external"}


def safe_filename(value: str, fallback: str = "document.pdf") -> str:
    name = Path(value or fallback).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", name).strip(" .-")
    if not name:
        name = fallback
    return name[:140]


def extract_vic_text(pdf_path: Path) -> str:
    from pdf_ocr import extract_pdf_text

    result = extract_pdf_text(pdf_path, max_pages=30, force_ocr=False)
    return (result.get("text") or "").strip()


def stage_vic_to_vault(
    ticker: str,
    *,
    pdf_path: Path | None = None,
    data: bytes | None = None,
    filename: str | None = None,
    extract_text=None,
) -> dict:
    """Copy a VIC PDF (or markdown note) into the vault and extract text."""
    ticker = str(ticker or "").strip()
    if not ticker:
        return {"status": "error", "error": "missing_ticker"}
    vault = research_vault_root(create=False)
    if vault is None:
        return {"status": "skipped_no_vault", "ticker": ticker}

    name = safe_filename(filename or (pdf_path.name if pdf_path else "document.pdf"))
    dest_dir = vic_root(create=True) / ticker
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name

    if data is None and pdf_path is not None:
        data = Path(pdf_path).read_bytes()
    if data is None:
        return {"status": "error", "error": "missing_bytes", "ticker": ticker}

    digest = hashlib.sha256(data).hexdigest()
    if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() == digest:
        pdf_status = "already_present"
    else:
        dest.write_bytes(data)
        pdf_status = "copied"

    text_status = "skipped"
    dest_txt: Path | None = None
    suffix = dest.suffix.lower()
    if suffix == ".md":
        dest_txt = dest
        text_status = "markdown"
    elif suffix == ".pdf":
        dest_txt = dest.with_suffix(".txt")
        extractor = extract_text if extract_text is not None else extract_vic_text
        if dest_txt.exists() and dest_txt.stat().st_mtime >= dest.stat().st_mtime:
            text_status = "already_present"
        else:
            text = extractor(dest) or ""
            if text:
                dest_txt.write_text(text, encoding="utf-8")
                text_status = "extracted"
            else:
                text_status = "empty"
                dest_txt = dest_txt if dest_txt.exists() else None

    return {
        "status": pdf_status,
        "text_status": text_status,
        "ticker": ticker,
        "sha256": digest,
        "vault_pdf": str(dest),
        "vault_txt": str(dest_txt) if dest_txt and dest_txt.exists() else None,
        "vault_ref": vic_ref(f"{ticker}/{name}"),
    }


def backfill_existing_vic(
    *,
    ssi_root: Path = ROOT,
    extract_text=None,
) -> dict:
    """Copy existing SSI ticker VIC files into the vault. Idempotent."""
    copied = 0
    present = 0
    skipped = 0
    errors: list[dict] = []
    if research_vault_root(create=False) is None:
        return {"copied": 0, "already_present": 0, "skipped": 0, "errors": [], "status": "skipped_no_vault"}

    for vic_dir in sorted(ssi_root.glob("*/third-party-analyses/vic")):
        ticker = vic_dir.parent.parent.name
        if ticker in SKIP_TICKER_DIRS or ticker.startswith((".", "_")):
            continue
        if not vic_dir.is_dir():
            continue
        for path in sorted(vic_dir.iterdir()):
            if not path.is_file() or path.suffix.lower() not in {".pdf", ".md"}:
                continue
            try:
                result = stage_vic_to_vault(
                    ticker,
                    pdf_path=path,
                    filename=path.name,
                    extract_text=extract_text,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append({"ticker": ticker, "path": str(path), "error": str(exc)})
                continue
            status = result.get("status")
            if status == "copied":
                copied += 1
            elif status == "already_present":
                present += 1
            else:
                skipped += 1
    return {
        "copied": copied,
        "already_present": present,
        "skipped": skipped,
        "error_count": len(errors),
        "errors": errors[:50],
        "status": "ok",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage VIC writeups into research-vault.")
    parser.add_argument("--backfill", action="store_true", help="Copy existing ticker VIC files into the vault.")
    args = parser.parse_args(argv)
    if not args.backfill:
        parser.error("pass --backfill")
    result = backfill_existing_vic()
    print(result)
    return 0 if result.get("status") in {"ok", "skipped_no_vault"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
