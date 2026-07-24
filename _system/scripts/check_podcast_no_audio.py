#!/usr/bin/env python3
"""Fail if podcast audio/media is tracked under the podcasts corpus."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))
from vault_paths import podcasts_root  # noqa: E402

MEDIA_SUFFIXES = {".mp3", ".m4a", ".mp4", ".wav", ".ogg", ".flac", ".aac"}


def main() -> int:
    root = podcasts_root(create=False)
    bad: list[str] = []
    if root.is_dir():
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in MEDIA_SUFFIXES:
                bad.append(str(path))
            if "audio-cache" in path.parts and path.suffix.lower() in MEDIA_SUFFIXES:
                bad.append(str(path))
    # Also guard accidental media under SSI reference/podcasts
    ref = ROOT / "_system" / "reference" / "podcasts"
    if ref.is_dir():
        for path in ref.rglob("*"):
            if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES:
                bad.append(str(path))
    if bad:
        print("ERROR: podcast media files must not be committed:", file=sys.stderr)
        for b in bad[:50]:
            print(f"  {b}", file=sys.stderr)
        return 1
    print("OK: no podcast media files under corpus/config")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
