#!/usr/bin/env python3
"""Lint the agent data layer against ``_system/schemas/`` and unit rules.

Checks, per ticker: thesis_card and valuation validate, card and valuation
agree on base IRR (percent_per_year), card digest pointer matches the
canonical ``latest.json`` resolution, and every ``latest.json`` artifact path
exists with a matching content hash. Also checks L0 size budgets and L1 shard
schema when shards exist.

Usage:
  python _system/scripts/lint_agent_data.py
  python _system/scripts/lint_agent_data.py GOOGL TPL
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from agent_schema import canonical_returns, validate  # noqa: E402
from atomic_io import semantic_text_sha256  # noqa: E402

L0_BUDGET_BYTES = 102_400


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def lint_ticker(ticker: str, *, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    research = root / ticker / "research"
    valuation = _load(research / "valuation.json")
    card = _load(research / "thesis_card.json")
    latest = _load(research / "latest.json")

    if valuation:
        errors += [f"{ticker} valuation: {e}" for e in validate(valuation, "valuation")]
    if card:
        errors += [f"{ticker} thesis_card: {e}" for e in validate(card, "thesis_card")]
        if card.get("base_irr_unit") != "percent_per_year":
            errors.append(f"{ticker} thesis_card: base_irr_unit must be percent_per_year")
    if valuation and card:
        expected = canonical_returns(valuation, card)
        card_base = (card.get("returns") or {}).get("base_irr_pct", card.get("base_irr_pct"))
        if isinstance(expected.get("base_irr_pct"), (int, float)) and isinstance(card_base, (int, float)):
            if abs(float(card_base) - float(expected["base_irr_pct"])) > 0.011:
                errors.append(
                    f"{ticker}: card base_irr_pct {card_base} disagrees with valuation {expected['base_irr_pct']} (percent_per_year)"
                )
        display = str((valuation.get("implied_return") or {}).get("display") or "")
        base = expected.get("base_irr_pct")
        if display and isinstance(base, (int, float)):
            import re as _re

            match = _re.match(r"^(-?\d+(?:\.\d+)?)%", display)
            if not match or abs(float(match.group(1)) - float(base)) > 0.06:
                errors.append(f"{ticker}: implied_return.display {display!r} does not match canonical percent value {base}%")

    if latest:
        errors += [f"{ticker} latest: {e}" for e in validate(latest, "ticker_latest")]
        for key, artifact in (latest.get("artifacts") or {}).items():
            if not isinstance(artifact, dict) or not artifact.get("path"):
                continue
            target = root / artifact["path"]
            if not target.is_file():
                errors.append(f"{ticker} latest: {key} path missing: {artifact['path']}")
                continue
            recorded = str(artifact.get("sha256") or "")
            if recorded.startswith("sha256:"):
                actual = f"sha256:{semantic_text_sha256(target.read_text(encoding='utf-8', errors='ignore'))}"
                if actual != recorded:
                    errors.append(f"{ticker} latest: {key} hash mismatch for {artifact['path']}")
        digest = (latest.get("artifacts") or {}).get("filing_digest") or {}
        if card and digest.get("path") and card.get("filing_digest") != digest["path"]:
            errors.append(f"{ticker}: thesis_card filing_digest {card.get('filing_digest')} != latest {digest['path']}")
    else:
        errors.append(f"{ticker}: missing research/latest.json (run build_ticker_latest.py)")

    shard_path = root / "dashboard" / "data" / "agent_shards" / f"{ticker}.json"
    if shard_path.is_file():
        shard = _load(shard_path)
        if shard.get("schema_version") == "magis.agent_shard.v2":
            errors += [f"{ticker} shard: {e}" for e in validate(shard, "agent_shard")]
    return errors


def ticker_dirs(root: Path = ROOT) -> list[str]:
    return sorted(
        entry.name
        for entry in root.iterdir()
        if entry.is_dir()
        and not entry.name.startswith((".", "_"))
        and entry.name not in ("dashboard", "docs", "tmp", "terminals")
        and (entry / "research").is_dir()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tickers", nargs="*")
    args = parser.parse_args(argv)
    targets = [t.upper() for t in args.tickers] if args.tickers else ticker_dirs()
    errors: list[str] = []
    for ticker in targets:
        errors.extend(lint_ticker(ticker))
    for rel in (
        "dashboard/data/portfolio_summary.json",
        "dashboard/data/research_manifest.json",
        "dashboard/data/kpi_summary.json",
        "dashboard/data/document_catalog_summary.json",
    ):
        path = ROOT / rel
        if path.is_file() and path.stat().st_size >= L0_BUDGET_BYTES:
            errors.append(f"L0 budget exceeded: {rel} ({path.stat().st_size} bytes)")
    if errors:
        print(f"FAIL agent data lint: {len(errors)} errors")
        for error in errors[:80]:
            print(f" - {error}")
        return 1
    print(f"OK agent data lint: tickers={len(targets)} errors=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
