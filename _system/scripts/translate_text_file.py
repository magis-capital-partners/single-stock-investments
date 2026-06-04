#!/usr/bin/env python3
"""Translate a Japanese text file to English paragraph-by-paragraph."""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import date
from pathlib import Path

CHUNK_MAX = 1200
SLEEP_S = 0.15


def has_japanese(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", text))


def translate_one(text: str, tr) -> str:
    text = text.strip()
    if not text or not has_japanese(text):
        return text
    if len(text) <= CHUNK_MAX:
        for attempt in range(5):
            try:
                out = tr.translate(text)
                if out and (not has_japanese(out) or len(out) < len(text) * 0.5):
                    return out
            except Exception:
                time.sleep(2**attempt)
        return text
    parts: list[str] = []
    i = 0
    while i < len(text):
        block = text[i : i + CHUNK_MAX]
        for attempt in range(5):
            try:
                parts.append(tr.translate(block))
                break
            except Exception:
                time.sleep(2**attempt)
        else:
            parts.append(block)
        i += CHUNK_MAX
        time.sleep(SLEEP_S)
    return "\n".join(parts)


def translate_document(body: str, tr) -> str:
    lines = body.splitlines()
    out_lines: list[str] = []
    buf: list[str] = []

    def flush_buf() -> None:
        nonlocal buf
        if not buf:
            return
        block = "\n".join(buf).strip()
        if block:
            out_lines.append(translate_one(block, tr))
        else:
            out_lines.extend(buf)
        buf = []

    for line in lines:
        if not line.strip():
            flush_buf()
            out_lines.append("")
            continue
        if has_japanese(line) or buf:
            buf.append(line)
        else:
            flush_buf()
            out_lines.append(line)
    flush_buf()
    return "\n".join(out_lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("src", type=Path, help="Japanese .txt source")
    parser.add_argument("dst", type=Path, help="English .en.txt output")
    parser.add_argument("--source-note", default="", help="PDF path for header")
    args = parser.parse_args()

    from deep_translator import GoogleTranslator

    raw = args.src.read_text(encoding="utf-8")
    # Strip old headers
    body = raw
    if body.startswith("# English"):
        body = re.sub(r"^#.*\n(?:#.*\n)*\n?", "", body, count=1)

    tr = GoogleTranslator(source="ja", target="en")
    en = translate_document(body, tr)

    header = (
        f"# English translation (full)\n"
        f"# Source: {args.source_note or args.src.name}\n"
        f"# Generated: {date.today().isoformat()}\n\n"
    )
    args.dst.parent.mkdir(parents=True, exist_ok=True)
    args.dst.write_text(header + en, encoding="utf-8")

    jp_after = len(re.findall(r"[\u3040-\u30ff\u4e00-\u9fff]", en))
    print(f"Wrote {args.dst} ({len(en)} chars, {jp_after} JP chars remaining)")
    return 0 if jp_after < len(en) * 0.05 else 1


if __name__ == "__main__":
    raise SystemExit(main())
