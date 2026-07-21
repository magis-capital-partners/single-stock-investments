#!/usr/bin/env python3
"""Build the contract_backfill dispatch queue and authorize evidence packets.

Priority inside the queue:
  1. Almost-there names (component map present, still evidence_blocked)
  2. Remaining evidence_blocked holdings, holdings/core/hold first then alpha

Writes:
  - _system/data/contract_backfill_queue.json
  - {TICKER}/research/authorized_evidence.json for each queued ticker so the
    evidence hash differs from a prior deep-dive hash (daily lane stays gated).
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT / "_system" / "data" / "contract_backfill_queue.json"
REGISTRY = ROOT / "_system" / "portfolio" / "registry.json"


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {} if default is None else default


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def is_almost_there(contract: dict) -> bool:
    if contract.get("status") != "evidence_blocked":
        return False
    cc = contract.get("component_coverage") or {}
    return bool(cc.get("all_material_components_identified")) and int(cc.get("additive_component_count") or 0) > 0


def stance_rank(entry: dict) -> int:
    stance = str(entry.get("stance") or entry.get("approved_stance") or "").lower()
    order = {"core": 0, "accumulate": 1, "hold": 2, "watch": 3, "pass": 4, "trim": 5, "exit": 6}
    return order.get(stance, 7)


def authorize(ticker: str, contract: dict, *, cohort: str) -> dict:
    blockers = ((contract.get("evidence") or {}).get("blockers") or [])[:12]
    packet = {
        "schema_version": "1.0",
        "purpose": "contract_backfill",
        "ticker": ticker,
        "authorized_at": now(),
        "cohort": cohort,
        "contract_status": contract.get("status"),
        "component_coverage": contract.get("component_coverage") or {},
        "blockers": blockers,
        "instruction": (
            "Upgrade this ticker's universal valuation contract toward decision_grade. "
            "Read research/thesis_card.json and the latest research/evidence/filing_digest_*.md first. "
            "Attach valid calculation_proof graphs (approved method_id@version) to every additive "
            "component, keep overlap_keys non-overlapping, and reconcile owner-cash/NAV plus downside "
            "capital claims to primary filings. Do not invent a human capital decision."
        ),
    }
    write_json(ROOT / ticker / "research" / "authorized_evidence.json", packet)
    return packet


def build_queue(
    *,
    wave_size: int,
    authorize_packets: bool,
    exclude_tickers: set[str] | None = None,
) -> dict:
    registry = read_json(REGISTRY)
    holdings = registry.get("holdings") or {}
    excluded = {t.upper() for t in (exclude_tickers or set())}
    almost: list[str] = []
    unmapped: list[tuple[int, str]] = []
    for ticker in sorted(holdings):
        if ticker.upper() in excluded:
            continue
        contract = read_json(ROOT / ticker / "research" / "valuation_contract.json")
        if not contract or contract.get("status") == "decision_grade":
            continue
        if contract.get("status") != "evidence_blocked":
            continue
        if is_almost_there(contract):
            almost.append(ticker)
        else:
            unmapped.append((stance_rank(holdings.get(ticker) or {}), ticker))
    unmapped.sort()
    ordered = almost + [t for _, t in unmapped]
    wave = ordered[:wave_size]
    authorized = 0
    if authorize_packets:
        for ticker in wave:
            contract = read_json(ROOT / ticker / "research" / "valuation_contract.json")
            cohort = "almost_there" if ticker in almost else "unmapped"
            authorize(ticker, contract, cohort=cohort)
            authorized += 1
    payload = {
        "updated": now(),
        "source": "build_contract_backfill_queue.py",
        "reason": "contract_backfill",
        "max_parallel": 3,
        "total_pending": len(ordered),
        "almost_there_count": len(almost),
        "unmapped_count": len(unmapped),
        "wave_size": len(wave),
        "authorized_packets": authorized,
        "tickers": wave,
        "almost_there": almost,
    }
    write_json(QUEUE, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wave-size", type=int, default=40, help="Tickers to authorize and queue now")
    parser.add_argument("--no-authorize", action="store_true", help="Write queue without authorized_evidence packets")
    parser.add_argument(
        "--exclude-ticker",
        action="append",
        default=[],
        help="Ticker to skip (repeatable); used to avoid open Cursor PRs",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    exclude = {t.strip().upper() for t in args.exclude_ticker if t.strip()}
    if args.dry_run:
        payload = build_queue(wave_size=args.wave_size, authorize_packets=False, exclude_tickers=exclude)
        print(json.dumps({k: payload[k] for k in ("total_pending", "almost_there_count", "unmapped_count", "wave_size", "tickers")}, indent=2))
        return 0
    payload = build_queue(
        wave_size=args.wave_size,
        authorize_packets=not args.no_authorize,
        exclude_tickers=exclude,
    )
    print(json.dumps({k: payload[k] for k in ("total_pending", "almost_there_count", "wave_size", "authorized_packets", "tickers")}, indent=2))
    print(f"Wrote {QUEUE.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
