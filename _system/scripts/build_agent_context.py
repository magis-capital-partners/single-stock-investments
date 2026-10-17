#!/usr/bin/env python3
"""Build deterministic, token-budgeted agent context packs per ticker.

One pack replaces manual assembly of L0 feed + L1 shard + valuation + digest
+ claims. Ordering is stable-first (identity, thesis, returns, claims) and
volatile-last (digest excerpt, generated stamp in the JSON manifest) so
prompt caching works across rebuilds. Everything left out is in ``excluded``.

Usage:
  python _system/scripts/build_agent_context.py GOOGL
  python _system/scripts/build_agent_context.py GOOGL --task cross-check --budget 4000
  python _system/scripts/build_agent_context.py --all-active
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

from agent_schema import estimate_tokens, validate  # noqa: E402
from atomic_io import now_iso, write_json_if_changed, write_text_if_changed  # noqa: E402

TASK_BUDGETS = {"deep-dive": 16000, "cross-check": 8000, "triage": 4000, "general": 8000}
MAX_CLAIMS_IN_PACK = 12
MAX_DIGEST_CHARS = 6000


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _claims_for(ticker: str, *, root: Path = ROOT) -> list[dict[str, Any]]:
    claims_path = root / "_system" / "data" / "claims.jsonl"
    out: list[dict[str, Any]] = []
    if claims_path.is_file():
        for line in claims_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("ticker", "")).upper() == ticker.upper():
                out.append(row)
                if len(out) >= MAX_CLAIMS_IN_PACK:
                    break
        if out:
            return out
    verified = _load(root / ticker / "research" / "evidence" / "ssi_verified_claims.json")
    for claim in (verified.get("verified_claims") or [])[:MAX_CLAIMS_IN_PACK]:
        if isinstance(claim, dict):
            ref = claim.get("evidence_ref") or {}
            out.append({
                "statement": claim.get("statement", ""),
                "claim_type": "fact",
                "status": "verified",
                "confidence": claim.get("confidence"),
                "source_path": ref.get("source_path") if isinstance(ref, dict) else None,
            })
    return out


def build_pack(ticker: str, *, task: str = "general", budget: int | None = None, root: Path = ROOT) -> dict[str, Any]:
    ticker = ticker.upper()
    budget = budget or TASK_BUDGETS.get(task, 8000)
    shard = _load(root / "dashboard" / "data" / "agent_shards" / f"{ticker}.json")
    research = root / ticker / "research"
    card = _load(research / "thesis_card.json")
    valuation = _load(research / "valuation.json")
    latest = _load(research / "latest.json")
    returns = valuation.get("returns") or card.get("returns") or shard.get("returns") or {}
    thesis = shard.get("thesis_summary") or {}
    if not thesis.get("thesis") and card:
        thesis = {
            "thesis": card.get("thesis", ""),
            "why_market_wrong": card.get("why_market_wrong", ""),
            "stance": card.get("stance"),
            "archetype": (card.get("classification") or {}).get("archetype"),
            "key_assumptions": card.get("key_assumptions") or [],
            "open_questions": card.get("open_questions") or [],
        }
    claims = _claims_for(ticker, root=root)

    digest_text = ""
    digest_rel = ((latest.get("artifacts") or {}).get("filing_digest") or {}).get("path") or card.get("filing_digest")
    if digest_rel and (root / digest_rel).is_file():
        digest_text = (root / digest_rel).read_text(encoding="utf-8", errors="ignore")[:MAX_DIGEST_CHARS]

    included = ["identity", "thesis", "returns"]
    if claims:
        included.append("claims")
    if digest_text:
        included.append("filing_digest_excerpt")
    excluded = [
        f"{ticker}/research/valuation.json (full; returns block included, open only for assumption audit)",
        f"{ticker}/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)",
        "dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)",
    ]

    lines: list[str] = []
    lines.append(f"# Agent context pack: {ticker} ({shard.get('company') or ticker})")
    lines.append("")
    lines.append("## Identity (stable)")
    lines.append(f"- Ticker: {ticker}")
    lines.append(f"- Company: {shard.get('company') or ticker}")
    lines.append(f"- Book: {shard.get('book') or 'research'}")
    lines.append(f"- Stance: {thesis.get('stance') or card.get('stance') or 'watch'}")
    lines.append(f"- Archetype: {thesis.get('archetype') or (card.get('classification') or {}).get('archetype') or 'unknown'}")
    lines.append("")
    lines.append("## What this business is (stable)")
    lines.append(thesis.get("thesis") or card.get("thesis") or "")
    lines.append("")
    lines.append("## Why the market might be wrong (stable)")
    lines.append(thesis.get("why_market_wrong") or card.get("why_market_wrong") or "")
    lines.append("")
    lines.append("## Returns (stable, percent per year)")
    if returns.get("base_irr_pct") is not None:
        lines.append(f"- Base return: {returns.get('base_irr_pct')}% per year ({returns.get('label') or returns.get('display') or 'base case'})")
    else:
        lines.append("- Base return: pending")
    scenarios = returns.get("scenarios_pct") or {}
    if scenarios:
        lines.append(f"- Scenarios (percent per year): bear {scenarios.get('bear')}, base {scenarios.get('base')}, bull {scenarios.get('bull')}")
    lines.append("")
    lines.append("## Key assumptions (stable)")
    for row in (thesis.get("key_assumptions") or [])[:8]:
        if isinstance(row, dict):
            lines.append(f"- {row.get('input')}: {row.get('value')} (source: {row.get('source') or 'see valuation assumption ledger'})")
    lines.append("")
    lines.append("## Open questions (stable)")
    for question in (thesis.get("open_questions") or [])[:6]:
        lines.append(f"- {question}")
    lines.append("")
    if claims:
        lines.append("## Verified claims (stable, cited)")
        for claim in claims:
            lines.append(f"- [{claim.get('status')}] {claim.get('statement')} (source: {claim.get('source_path')})")
        lines.append("")
    if digest_text:
        lines.append("## Filing digest excerpt (semi-stable)")
        lines.append(digest_text.strip())
        lines.append("")
    lines.append("## Canonical pointers (open only when needed)")
    artifacts = latest.get("artifacts") or {}
    for key in ("deep_dive", "filing_digest", "adversarial", "valuation", "thesis_card", "cross_check"):
        if artifacts.get(key):
            lines.append(f"- {key}: {artifacts[key]['path']} (sha256 {str(artifacts[key].get('sha256', ''))[:23]}...)")
    lines.append("")
    lines.append("## Excluded from this pack")
    for item in excluded:
        lines.append(f"- {item}")
    lines.append("")
    text = "\n".join(lines).strip() + "\n"

    truncated = False
    if estimate_tokens(text) > budget and "## Filing digest excerpt" in text:
        truncated = True
        head, _, tail = text.partition("## Filing digest excerpt (semi-stable)")
        _, _, after = tail.partition("## Canonical pointers")
        text = head + "## Filing digest excerpt (semi-stable)\n[trimmed to token budget; open filing_digest via canonical pointers]\n\n## Canonical pointers" + after
    if estimate_tokens(text) > budget:
        truncated = True
        text = text[: budget * 4].rsplit("\n", 1)[0] + "\n[pack truncated to token budget]\n"

    manifest: dict[str, Any] = {
        "schema_version": "magis.context_pack.v1",
        "ticker": ticker,
        "task": task,
        "token_budget": budget,
        "token_estimate": estimate_tokens(text),
        "included": included,
        "excluded": excluded,
        "truncated": truncated,
        "pack_md": f"dashboard/data/context_packs/{ticker}.md",
        "pack_json": f"dashboard/data/context_packs/{ticker}.json",
    }
    manifest["generated_at"] = now_iso()
    errors = validate({k: v for k, v in manifest.items() if k != "generated_at"}, "context_pack")
    if errors:
        raise ValueError(f"context pack manifest invalid for {ticker}: {errors}")
    return {"manifest": manifest, "text": text}


def write_pack(ticker: str, *, task: str = "general", budget: int | None = None, root: Path = ROOT) -> dict[str, Any]:
    pack = build_pack(ticker, task=task, budget=budget, root=root)
    out_dir = root / "dashboard" / "data" / "context_packs"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_text_if_changed(out_dir / f"{ticker.upper()}.md", pack["text"])
    write_json_if_changed(out_dir / f"{ticker.upper()}.json", pack["manifest"])
    return pack["manifest"]


def active_tickers(root: Path = ROOT) -> list[str]:
    summary = _load(root / "dashboard" / "data" / "portfolio_summary.json")
    return sorted({str(r.get("ticker")) for r in summary.get("rows") or [] if r.get("ticker")})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tickers", nargs="*")
    parser.add_argument("--task", choices=sorted(TASK_BUDGETS), default="general")
    parser.add_argument("--budget", type=int, default=None)
    parser.add_argument("--all-active", action="store_true", help="Build packs for every active-book ticker")
    args = parser.parse_args(argv)
    targets = active_tickers() if args.all_active else [t.upper() for t in args.tickers]
    if not targets:
        parser.error("ticker required (or --all-active)")
    for ticker in targets:
        manifest = write_pack(ticker, task=args.task, budget=args.budget)
        print(f"OK context pack {ticker}: ~{manifest['token_estimate']} tokens (budget {manifest['token_budget']}, truncated={manifest['truncated']})")
    print(f"OK context packs: written={len(targets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
