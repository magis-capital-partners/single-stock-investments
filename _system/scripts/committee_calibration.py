#!/usr/bin/env python3
"""Score committee methods only from explicitly recorded, dividend-aware outcomes."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize(rows: list[dict]) -> dict:
    valid = [r for r in rows if r.get("return_status") == "complete" and r.get("total_return_pct") is not None]
    by_persona: dict[str, list[dict]] = defaultdict(list)
    for row in valid:
        for vote in row.get("votes", []):
            by_persona[vote["persona"]].append({**vote, "total_return_pct": float(row["total_return_pct"])})
    methods = {}
    for persona, votes in sorted(by_persona.items()):
        actionable = [v for v in votes if v.get("vote") in ("approve", "reject")]
        correct = [v for v in actionable if (v["vote"] == "approve") == (v["total_return_pct"] > 0)]
        methods[persona] = {
            "completed_outcomes": len(votes),
            "actionable_votes": len(actionable),
            "directional_accuracy_pct": round(100 * len(correct) / len(actionable), 1) if actionable else None,
            "mean_total_return_pct": round(sum(v["total_return_pct"] for v in votes) / len(votes), 2),
        }
    return {
        "status": "ready" if valid else "insufficient_outcomes",
        "completed_outcomes": len(valid),
        "excluded_rows": len(rows) - len(valid),
        "methods": methods,
        "warning": "Calibration is descriptive until each method has at least 20 completed, dividend-aware outcomes.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=ROOT / "_system" / "research" / "committee_outcomes.jsonl")
    parser.add_argument("--out", type=Path, default=ROOT / "_system" / "research" / "committee_calibration.json")
    args = parser.parse_args()
    result = summarize(load_jsonl(args.ledger))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
