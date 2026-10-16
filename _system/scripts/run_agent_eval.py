#!/usr/bin/env python3
"""Golden-question agent eval: tests the repo from the reader's side.

Builds 30 questions across 10 tickers (base IRR in percent per year, stance,
canonical filing digest) from the canonical stores, then answers them using
only the reader path an external agent would take (``latest.json`` +
``thesis_card.json`` + context pack token size). Scores accuracy, stale reads
(card pointer disagreeing with ``latest.json``), and tokens consumed. This is
the regression test that would have caught the IRR unit ambiguity and the
dated digest pointer.

Usage:
  python _system/scripts/run_agent_eval.py --build-golden
  python _system/scripts/run_agent_eval.py
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

from agent_schema import estimate_tokens  # noqa: E402
from atomic_io import attach_envelope, write_json_if_changed  # noqa: E402

GOLDEN_PATH = ROOT / "_system" / "data" / "agent_eval" / "golden.json"
RESULT_PATH = ROOT / "_system" / "data" / "agent_eval" / "latest_eval.json"
EVAL_TICKER_COUNT = 10


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def candidate_tickers(*, root: Path = ROOT) -> list[str]:
    """Prefer L1-sharded tickers: they carry the effective stance an agent reads."""
    out: list[str] = []
    candidates: list[str] = []
    shard_dir = root / "dashboard" / "data" / "agent_shards"
    if shard_dir.is_dir():
        candidates.extend(p.stem for p in sorted(shard_dir.glob("*.json")))
    candidates.extend(p.parent.parent.name for p in sorted(root.glob("*/research/thesis_card.json")))
    seen: set[str] = set()
    for ticker in candidates:
        if ticker in seen:
            continue
        seen.add(ticker)
        research = root / ticker / "research"
        card = _load(research / "thesis_card.json")
        valuation = _load(research / "valuation.json")
        shard = _load(root / "dashboard" / "data" / "agent_shards" / f"{ticker}.json")
        returns = card.get("returns") or valuation.get("returns") or shard.get("returns") or {}
        stance = (shard.get("thesis_summary") or {}).get("stance") or card.get("stance") or (valuation.get("stance_proposal") or {}).get("stance")
        latest = _load(research / "latest.json")
        digest = ((latest.get("artifacts") or {}).get("filing_digest") or {}).get("path")
        if isinstance(returns.get("base_irr_pct"), (int, float)) and digest and stance:
            out.append(ticker)
        if len(out) >= EVAL_TICKER_COUNT:
            break
    return out


def _effective_stance(ticker: str, *, root: Path = ROOT) -> Any:
    research = root / ticker / "research"
    shard = _load(root / "dashboard" / "data" / "agent_shards" / f"{ticker}.json")
    card = _load(research / "thesis_card.json")
    valuation = _load(research / "valuation.json")
    return (shard.get("thesis_summary") or {}).get("stance") or card.get("stance") or (valuation.get("stance_proposal") or {}).get("stance")


def build_golden(*, root: Path = ROOT) -> dict[str, Any]:
    questions: list[dict[str, Any]] = []
    for ticker in candidate_tickers(root=root):
        research = root / ticker / "research"
        card = _load(research / "thesis_card.json")
        latest = _load(research / "latest.json")
        returns = card.get("returns") or {}
        digest = ((latest.get("artifacts") or {}).get("filing_digest") or {}).get("path")
        questions.append({"ticker": ticker, "question": "base_irr_pct", "expected": returns.get("base_irr_pct"), "unit": "percent_per_year", "citation": f"{ticker}/research/thesis_card.json"})
        questions.append({"ticker": ticker, "question": "stance", "expected": _effective_stance(ticker, root=root), "citation": f"dashboard/data/agent_shards/{ticker}.json"})
        questions.append({"ticker": ticker, "question": "filing_digest_path", "expected": digest, "citation": f"{ticker}/research/latest.json"})
    payload: dict[str, Any] = {
        "schema_version": "magis.agent_eval_golden.v1",
        "description": "30 golden questions across 10 tickers derived from canonical returns, stance, and latest.json digest resolution.",
        "questions": questions,
    }
    payload["generated_at"] = "derived-from-canonical-stores"
    return payload


def run_eval(*, root: Path = ROOT, golden: dict[str, Any] | None = None) -> dict[str, Any]:
    golden = golden or _load(GOLDEN_PATH) or build_golden(root=root)
    correct = 0
    stale = 0
    total_tokens = 0
    failures: list[dict[str, Any]] = []
    for question in golden.get("questions") or []:
        ticker = str(question.get("ticker") or "").upper()
        research = root / ticker / "research"
        card = _load(research / "thesis_card.json")
        latest = _load(research / "latest.json")
        pack_path = root / "dashboard" / "data" / "context_packs" / f"{ticker}.md"
        if pack_path.is_file():
            total_tokens += estimate_tokens(pack_path.read_text(encoding="utf-8", errors="ignore"))
        kind = question.get("question")
        if kind == "base_irr_pct":
            actual = (card.get("returns") or {}).get("base_irr_pct", card.get("base_irr_pct"))
            ok = isinstance(actual, (int, float)) and isinstance(question.get("expected"), (int, float)) and abs(float(actual) - float(question["expected"])) <= 0.011
            unit_ok = card.get("base_irr_unit") == "percent_per_year" or (card.get("returns") or {}).get("unit") == "percent_per_year"
            ok = ok and unit_ok
        elif kind == "stance":
            actual = _effective_stance(ticker, root=root)
            ok = actual == question.get("expected")
        else:
            actual = ((latest.get("artifacts") or {}).get("filing_digest") or {}).get("path")
            ok = actual == question.get("expected")
            if card.get("filing_digest") != actual:
                stale += 1
                ok = False
        if ok:
            correct += 1
        else:
            failures.append({"ticker": ticker, "question": kind, "expected": question.get("expected"), "actual": actual})
    total = len(golden.get("questions") or [])
    result: dict[str, Any] = {
        "schema_version": "magis.agent_eval_result.v1",
        "questions": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "stale_reads": stale,
        "context_tokens_for_eval_tickers": total_tokens,
        "failures": failures[:20],
        "pass": bool(total) and correct == total and stale == 0,
    }
    return attach_envelope(result, feed_id="agent-eval", row_count=total)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--build-golden", action="store_true")
    args = parser.parse_args(argv)
    if args.build_golden:
        golden = build_golden()
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        write_json_if_changed(GOLDEN_PATH, golden)
        print(f"OK golden eval set: questions={len(golden['questions'])} tickers={len({q['ticker'] for q in golden['questions']})}")
        return 0
    if not GOLDEN_PATH.is_file():
        golden = build_golden()
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        write_json_if_changed(GOLDEN_PATH, golden)
    result = run_eval()
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_json_if_changed(RESULT_PATH, result)
    print(f"Agent eval: {result['correct']}/{result['questions']} correct, stale={result['stale_reads']}, pass={result['pass']}")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
