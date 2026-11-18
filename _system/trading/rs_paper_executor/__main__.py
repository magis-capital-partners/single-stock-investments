"""Paper-only CLI. No network by default; no live-mode command exists."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from .engine import Executor
from .ibkr import PaperIBKR
from .inbox import proposals, read_https, read_json
from .journal import Journal
from .notify import deliver_alerts
from .policy import Policy
from .safety import PaperEndpoint, SafetyError


async def run(args, endpoint, policy):
    if not args.connect_paper:
        raise SafetyError("--connect-paper is required; no connection was opened")
    if not args.evidence or not (args.operations_file or args.operations_url):
        raise SafetyError("evidence and Box R operations source required")
    with_context = lambda: read_json(args.evidence)
    journal = Journal(args.state, policy.digest)
    broker = PaperIBKR(endpoint, with_context)
    broker.known_refs = {x["ref"] for x in journal.rows("orders")}

    async def connect_budgeted():
        # Persistent connect-event budget; supervisor restarts cannot reset it.
        day = (
            datetime.fromisoformat(broker.now())
            .astimezone(ZoneInfo("America/New_York"))
            .date()
            .isoformat()
        )
        key = "connection_attempts:" + day
        attempts = journal.get(key, 0)
        if attempts >= 3:
            raise SafetyError("daily paper connection budget exhausted")
        journal.set(key, attempts + 1)
        await broker.connect()

    try:
        await connect_budgeted()
        # Qualify saved position identities before recovery/quote subscriptions.
        for pos in journal.rows("positions"):
            if pos["shares"]:
                await broker.qualify(json.loads(pos["payload"]))
        executor = Executor(
            endpoint,
            policy,
            journal,
            broker,
            kill_switch=lambda: Path(args.kill_file).exists(),
        )
        if args.resume_entries:
            await executor.resume_entries(broker.now())
        while True:
            now = broker.now()
            if not broker.ib.isConnected():
                executor.halt(now, "paper_connection_lost")
                await asyncio.sleep(30)
                await connect_budgeted()
                now = broker.now()
            # Position protection runs even if the research snapshot is absent.
            await executor.tick([], now)
            if Path(args.kill_file).exists():
                journal.set("kill", True)
                await executor.tick([], broker.now())
            try:
                data = (
                    read_json(args.operations_file)
                    if args.operations_file
                    else read_https(
                        args.operations_url, os.environ["RS_OPERATIONS_READ_TOKEN"]
                    )
                )
                await executor.tick(
                    proposals(data, with_context(), broker.now()), broker.now()
                )
            except Exception as exc:
                journal.event(
                    broker.now(), "inbox_unavailable", {"type": type(exc).__name__}
                )
            wanted = {x["conid"] for x in journal.rows("positions") if x["shares"]}
            wanted |= {
                x["conid"]
                for x in journal.rows("orders")
                if x["state"] not in ("filled", "cancelled", "rejected")
            }
            broker.retain_quotes(wanted)
            if os.environ.get("RS_PAPER_SLACK_WEBHOOK"):
                try:
                    deliver_alerts(
                        journal, os.environ["RS_PAPER_SLACK_WEBHOOK"], broker.now()
                    )
                except Exception:
                    # Notification delivery cannot prevent position protection.
                    pass
            if args.once:
                break
            await asyncio.sleep(5)
    finally:
        broker.close()
        journal.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["preflight", "run", "status"])
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--state",
        default=str(Path.home() / ".local/state/rs-paper-executor/state.sqlite"),
    )
    parser.add_argument("--connect-paper", action="store_true")
    parser.add_argument("--operations-file")
    parser.add_argument("--operations-url")
    parser.add_argument("--evidence")
    parser.add_argument("--kill-file", default="RS_PAPER_FLATTEN")
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--resume-entries",
        action="store_true",
        help="operator acknowledgement after proven recovery",
    )
    args = parser.parse_args(argv)
    try:
        config = read_json(args.config)
        endpoint = PaperEndpoint(**config["endpoint"]).validate()
        policy = Policy(**config["policy"]).validate()
        if args.command == "preflight":
            print(
                json.dumps(
                    {
                        "paper_only": True,
                        "live_orders_allowed": False,
                        "connection_opened": False,
                        "policy_hash": policy.digest,
                        "policy": asdict(policy),
                    }
                )
            )
        elif args.command == "status":
            # A read-only status process does not compete for the writer lock.
            import sqlite3

            db = sqlite3.connect(
                Path(args.state).resolve().as_uri() + "?mode=ro", uri=True
            )
            count = db.execute(
                "SELECT count(*)FROM orders WHERE state NOT IN('filled','cancelled','rejected')"
            ).fetchone()[0]
            positions = db.execute(
                "SELECT count(*)FROM positions WHERE shares>0"
            ).fetchone()[0]
            print(
                json.dumps(
                    {
                        "paper_only": True,
                        "live_orders_allowed": False,
                        "unresolved_orders": count,
                        "open_paper_positions": positions,
                        "broker_connection_opened": False,
                    }
                )
            )
            db.close()
        else:
            asyncio.run(run(args, endpoint, policy))
    except (SafetyError, KeyError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "blocked", "reason": str(exc), "live_orders_allowed": False}
            )
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
