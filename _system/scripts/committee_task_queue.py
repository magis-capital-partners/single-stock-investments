#!/usr/bin/env python3
"""Return the next isolated Cloud Agent tasks for one committee packet."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def task(ticker: str, as_of: str, task_id: str, prompt: Path, output: Path) -> dict:
    return {
        "ticker": ticker,
        "as_of": as_of,
        "task_id": task_id,
        "task_key": f"IC-{ticker}-{as_of}-{task_id}",
        "prompt_path": prompt.relative_to(ROOT).as_posix(),
        "output_path": output.relative_to(ROOT).as_posix(),
    }


def next_tasks(ticker: str, as_of: str) -> list[dict]:
    ticker = ticker.upper()
    work = ROOT / ticker / "research" / "committee_work" / as_of
    manifest = read_json(work / "manifest.json")
    raters = manifest.get("selected_raters") or []

    first = []
    for name in ("proposer", "pre_mortem"):
        output = work / f"{name}.json"
        if not output.exists():
            first.append(task(ticker, as_of, name, work / f"{name}.prompt.md", output))
    for row in raters:
        persona = row["persona"]
        output = work / "round_1" / f"{persona}.json"
        if not output.exists():
            first.append(task(ticker, as_of, f"round1-{persona}", work / "round_1" / f"{persona}.prompt.md", output))
    if first:
        return first

    tribunal = work / "evidence_tribunal.json"
    if not tribunal.exists():
        return [task(ticker, as_of, "evidence-tribunal", work / "evidence_tribunal.prompt.md", tribunal)]

    response = work / "research_response.json"
    if not response.exists():
        return [task(ticker, as_of, "research-response", work / "research_response.prompt.md", response)]

    second = []
    for row in raters:
        persona = row["persona"]
        output = work / "round_2" / f"{persona}.json"
        if not output.exists():
            second.append(task(ticker, as_of, f"round2-{persona}", work / "round_2" / f"{persona}.prompt.md", output))
    if second:
        return second

    reconciliation = work / "valuation_reconciliation.json"
    adversarial = work / "adversarial_review.json"
    parallel = []
    if not reconciliation.exists():
        parallel.append(task(ticker, as_of, "valuation-reconciliation", work / "valuation_reconciliation.prompt.md", reconciliation))
    if not adversarial.exists():
        parallel.append(task(ticker, as_of, "adversarial-review", work / "adversarial_review.prompt.md", adversarial))
    if parallel:
        return parallel

    chair = work / "chair_synthesis.json"
    if not chair.exists():
        return [task(ticker, as_of, "chair-synthesis", work / "chair_synthesis.prompt.md", chair)]
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker", type=str.upper)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    print(json.dumps(next_tasks(args.ticker, args.date), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
