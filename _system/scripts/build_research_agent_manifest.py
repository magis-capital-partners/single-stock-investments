#!/usr/bin/env python3
"""Build a stable, small evidence manifest for one research-agent decision."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def candidates(ticker: str) -> list[Path]:
    base = ROOT / ticker.upper()
    fixed = [
        base / "INDEX.csv",
        base / "investor-documents" / "DOWNLOAD_MANIFEST.json",
        base / "investor-documents" / "ir_adapter.json",
        base / "research" / "evidence_refresh.json",
        base / "research" / "news_refresh.json",
    ]
    globs = [
        base / "research" / "evidence",
        base / "third-party-analyses",
    ]
    rows = [path for path in fixed if path.is_file()]
    for directory in globs:
        if not directory.is_dir():
            continue
        matches = [path for path in directory.rglob("*.json") if path.is_file()]
        rows.extend(sorted(matches, key=lambda p: p.as_posix())[-20:])
    return sorted(set(rows), key=lambda p: p.as_posix())


def build_manifest(ticker: str, reason: str) -> dict:
    refs = []
    for path in candidates(ticker):
        raw = path.read_bytes()
        refs.append({
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        })
    canonical_evidence = {"ticker": ticker.upper(), "evidence": refs}
    evidence_hash = hashlib.sha256(json.dumps(canonical_evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "schema_version": "1.0",
        **canonical_evidence,
        "reason": reason,
        "evidence_hash": evidence_hash,
        "artifact_count": len(refs),
        "ready": bool(refs),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker", type=str.upper)
    parser.add_argument("--reason", default="manual_material_change")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = build_manifest(args.ticker, args.reason)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(value, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
