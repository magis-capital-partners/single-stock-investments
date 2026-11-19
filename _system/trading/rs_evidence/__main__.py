"""CLI for the RS evidence producers. Nothing here connects to a broker.

    python -m _system.trading.rs_evidence once   --config <producers.json> [--only identity,borrow]
    python -m _system.trading.rs_evidence run    --config <producers.json> --max-seconds 25200
    python -m _system.trading.rs_evidence status --config <producers.json>
    python -m _system.trading.rs_evidence review --config <producers.json> \
        --candidate <Box R candidate id> --ratio 10 --action-day 2026-11-25 --by DG [--conid N]

``review`` writes one owner attestation of a candidate's terms (see
``reviews.py``); it refuses a candidate that is not in the current operations
snapshot, and binds the review to that candidate's primary-source hash.
"""

from __future__ import annotations

import argparse
import json
import sys

from _system.trading.rs_paper_executor.safety import SafetyError, timestamp

from . import reviews
from .runner import Producers, load_config, run_forever
from .sources import utc_now


def _status(config, now):
    store = Producers(config).store
    evidence = store.read()
    out = {"evidence": str(store.path), "now": now, "sections": {}}
    for section in ("identities", "borrow", "eligibility"):
        rows = evidence.get(section, {})
        ages = [
            (timestamp(now) - timestamp(r["at"])).total_seconds()
            for r in rows.values()
            if isinstance(r, dict) and r.get("at")
        ]
        out["sections"][section] = {
            "rows": len(rows),
            "oldest_seconds": max(ages) if ages else None,
            "producer": evidence.get("producers", {}).get(section, {}),
        }
    out["identities_verified"] = sorted(
        t for t, r in evidence.get("identities", {}).items() if r.get("verified") is True
    )
    out["eligibility_complete"] = sorted(
        k for k, r in evidence.get("eligibility", {}).items() if r.get("complete") is True
    )
    return out


def _review(config, args, now):
    producers = Producers(config)
    operations = producers.fetchers.operations()
    match = [c for c in operations.get("candidates", []) if c.get("id") == args.candidate]
    if len(match) != 1:
        raise SafetyError("candidate is not in the current operations snapshot")
    candidate = match[0]
    hashes = [s.get("sha256") for s in candidate.get("source_urls", []) if s.get("sha256")]
    if not hashes:
        raise SafetyError("candidate has no primary-source hash to bind")
    row = {
        "schema": reviews.SCHEMA,
        "candidate_id": candidate["id"],
        "cik": str(candidate["cik"]),
        "ticker": candidate["ticker"],
        "action_source_sha256": hashes[0],
        "ratio": float(args.ratio) if "." in args.ratio else int(args.ratio),
        "action_day": args.action_day,
        "conditions_resolved": True,
        "reviewed_by": args.by,
        "reviewed_at": now,
    }
    if args.conid is not None:
        row["conid"] = args.conid
    if not config.get("reviews"):
        raise SafetyError("config has no reviews path")
    return reviews.append(config["reviews"], row)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="rs_evidence", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("once", "run", "status", "review"):
        p = sub.add_parser(name)
        p.add_argument("--config", required=True)
        if name == "once":
            p.add_argument("--only", help="comma list of steps")
        if name == "run":
            p.add_argument("--max-seconds", type=int, default=7 * 3600)
        if name == "review":
            p.add_argument("--candidate", required=True)
            p.add_argument("--ratio", required=True)
            p.add_argument("--action-day", required=True)
            p.add_argument("--by", required=True)
            p.add_argument("--conid", type=int)
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        now = utc_now()
        if args.command == "once":
            only = set(args.only.split(",")) if args.only else None
            producers = Producers(config)
            print(json.dumps({"ran": producers.step(now, only=only)}))
        elif args.command == "run":
            run_forever(Producers(config), max_seconds=args.max_seconds)
        elif args.command == "status":
            print(json.dumps(_status(config, now), indent=1, sort_keys=True, default=str))
        else:
            print(json.dumps(_review(config, args, now), sort_keys=True))
    except SafetyError as exc:
        print(json.dumps({"refused": str(exc)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
