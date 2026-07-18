#!/usr/bin/env python3
"""Admit Vicki only after deterministic IR handling is absent or has failed."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def evaluate(ticker: str, *, force: bool = False) -> dict:
    ticker = ticker.upper()
    base = ROOT / ticker
    onboard = read_json(base / ".onboard_status.json")
    adapter_path = base / "investor-documents" / "ir_adapter.json"
    adapter = read_json(adapter_path)
    evidence_paths = [base / ".onboard_status.json", adapter_path]
    evidence_paths.extend(sorted(base.glob("investor-documents/download_*.py")))
    evidence_paths.extend(sorted(base.glob("download_*.py")))
    refs = []
    for path in evidence_paths:
        if path.is_file():
            refs.append({
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
    evidence_hash = hashlib.sha256(json.dumps(refs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    deterministic_status = str(adapter.get("deterministic_status") or adapter.get("status") or "missing").lower()
    download_detail = str(onboard.get("download_detail") or "").lower()
    if deterministic_status in {"working", "verified", "active"} and not force:
        return {"ticker": ticker, "eligible": False, "reason": "deterministic_adapter_working", "evidence_hash": evidence_hash, "adapter_path": adapter_path.relative_to(ROOT).as_posix()}
    if download_detail != "ir_gap" and deterministic_status not in {"failed", "broken"} and not force:
        return {"ticker": ticker, "eligible": False, "reason": "no_active_ir_gap", "evidence_hash": evidence_hash, "adapter_path": adapter_path.relative_to(ROOT).as_posix()}
    return {
        "ticker": ticker,
        "eligible": True,
        "reason": "manual_override" if force else ("adapter_failed" if deterministic_status in {"failed", "broken"} else "ir_gap"),
        "evidence_hash": evidence_hash,
        "adapter_path": adapter_path.relative_to(ROOT).as_posix(),
        "evidence": refs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker", type=str.upper)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args()
    result = evaluate(args.ticker, force=args.force)
    if args.github_output and os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as handle:
            for key in ("eligible", "reason", "evidence_hash", "adapter_path"):
                value = result.get(key)
                if isinstance(value, bool):
                    value = str(value).lower()
                handle.write(f"{key}={value}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
