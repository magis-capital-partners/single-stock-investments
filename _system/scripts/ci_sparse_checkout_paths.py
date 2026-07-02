#!/usr/bin/env python3
"""Emit git sparse-checkout paths for CI profiles (one path per line).

Profiles:
  news         — portfolio news ingest (JSON only, no PDF trees)
  marvin-pick  — marvin_pick_ticker metadata (research md/json, manifests)
  darwin       — Darwin refresh + dashboard rebuild without PDF blobs
  dashboard    — same as darwin (alias)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"

SKIP_TICKER_DIRS = {"_system", "dashboard", "docs", ".github", ".git", ".cursor"}


def load_holdings() -> list[str]:
    if not REGISTRY_PATH.exists():
        return []
    reg = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return sorted((reg.get("holdings") or {}).keys())


def list_ticker_dirs() -> list[str]:
    tickers = set(load_holdings())
    for path in ROOT.iterdir():
        if not path.is_dir():
            continue
        name = path.name
        if name.startswith(".") or name in SKIP_TICKER_DIRS:
            continue
        tickers.add(name)
    return sorted(tickers)


def paths_for_profile(profile: str) -> list[str]:
    tickers = list_ticker_dirs()
    paths: list[str] = []

    if profile == "news":
        for ticker in tickers:
            paths.append(f"{ticker}/research/news")
        return paths

    if profile == "marvin-pick":
        for ticker in tickers:
            paths.extend(
                [
                    f"{ticker}/research/news",
                    f"{ticker}/research",
                    f"{ticker}/.onboard_status.json",
                    f"{ticker}/INDEX.csv",
                    f"{ticker}/_download_log.txt",
                    f"{ticker}/investor-documents/DOWNLOAD_MANIFEST.json",
                    f"{ticker}/investor-documents/TRANSCRIPT_MANIFEST.json",
                ]
            )
        return paths

    if profile in {"darwin", "dashboard"}:
        manifest_files = (
            "DOWNLOAD_MANIFEST.json",
            "TRANSCRIPT_MANIFEST.json",
        )
        for ticker in tickers:
            paths.extend(
                [
                    f"{ticker}/research",
                    f"{ticker}/.onboard_status.json",
                    f"{ticker}/INDEX.csv",
                    f"{ticker}/_download_log.txt",
                    f"{ticker}/README.md",
                    f"{ticker}/document-index.csv",
                    f"{ticker}/third-party-analyses/activist_reports_index.json",
                    f"{ticker}/third-party-analyses/activist_reports",
                ]
            )
            for name in manifest_files:
                paths.append(f"{ticker}/investor-documents/{name}")
        return paths

    raise SystemExit(f"Unknown sparse profile: {profile}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"Usage: {sys.argv[0]} <profile>")
    profile = sys.argv[1].strip()
    seen: set[str] = set()
    for path in paths_for_profile(profile):
        if path not in seen:
            seen.add(path)
            print(path)


if __name__ == "__main__":
    main()
