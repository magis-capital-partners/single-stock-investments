"""RS executor CLI. No network by default.

Paper connects only with --connect-paper. The live endpoint (the shared NY4
Gateway, registered reverse-split client) connects only with --connect-live and
then runs in SHADOW unless the owner arm file is valid (see arm.py).
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from .arm import arm_state
from .book import BookMargin
from .claims import ClaimBook
from .engine import Executor
from .ibkr import PaperIBKR
from .inbox import proposals, read_https, read_json
from .journal import Journal
from .notify import deliver_alerts
from .policy import Policy
from .probe import probe, require_local_ib_listener
from .safety import RS_SYSTEM, SafetyError, endpoint_from_config

# Owner decisions a live config must state explicitly (never template defaults).
LIVE_REQUIRED_POLICY = (
    "target_notional", "max_name_notional", "max_gross_notional", "max_names",
    "spx_reserve", "cash_buffer", "daily_loss_limit", "cushion_halt",
    "cushion_flatten",
)
LIVE_REQUIRED_PATHS = ("claims_dir", "book_margin_root", "book_publish_root", "arm_file")


def check_live_config(config, endpoint):
    if not endpoint.live:
        return
    missing = [k for k in LIVE_REQUIRED_POLICY if config["policy"].get(k) is None]
    live = config.get("live") or {}
    missing += [k for k in LIVE_REQUIRED_PATHS if not live.get(k)]
    if live.get("spx_book_reserve_fraction") is None:
        missing.append("spx_book_reserve_fraction")
    if missing:
        raise SafetyError("live config must state: " + ", ".join(missing))
    if config["policy"].get("pre_action_exit") is not True:
        # Holding through the split can change the conid; SPX's ETF stock proof
        # holds entries on unidentified stock rows (2026-11-09 incident shape).
        raise SafetyError("live requires pre_action_exit: true")


def account_guards(config, endpoint, policy):
    live = config.get("live") or {}
    if not live.get("claims_dir"):
        return None, None
    claims = ClaimBook(live["claims_dir"], RS_SYSTEM, endpoint.account)
    book = BookMargin(
        live["book_margin_root"], live["book_publish_root"], policy,
        live["spx_book_reserve_fraction"],
        limit_fraction=live.get("book_margin_limit_fraction", 1.0),
    )
    return claims, book


async def run(args, endpoint, policy, config):
    if endpoint.live and not args.connect_live:
        raise SafetyError("--connect-live is required; no connection was opened")
    if not endpoint.live and not args.connect_paper:
        raise SafetyError("--connect-paper is required; no connection was opened")
    if not args.evidence or not (args.operations_file or args.operations_url):
        raise SafetyError("evidence and Box R operations source required")
    with_context = lambda: read_json(args.evidence)
    claims, book = account_guards(config, endpoint, policy)
    if claims is not None:
        claims.publish_current(datetime.now(ZoneInfo("UTC")).isoformat())
    arm_file = (config.get("live") or {}).get("arm_file")
    journal = Journal(args.state, policy.digest, endpoint.prefix)
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
        # A loopback port may be an SSH forward; prove the listener first.
        require_local_ib_listener(endpoint.port)
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
            transmit=lambda: arm_state(arm_file, endpoint, policy, broker.now()),
            claims=claims,
            book=book,
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
    parser.add_argument("command", choices=["preflight", "run", "status", "probe", "integration-test"])
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--state",
        default=str(Path.home() / ".local/state/rs-paper-executor/state.sqlite"),
    )
    parser.add_argument("--connect-paper", action="store_true")
    parser.add_argument(
        "--connect-live",
        action="store_true",
        help="shared NY4 Gateway as the registered reverse-split client; shadow unless armed",
    )
    parser.add_argument("--operations-file")
    parser.add_argument("--operations-url")
    parser.add_argument("--evidence")
    parser.add_argument("--kill-file", default="RS_PAPER_FLATTEN")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--symbol", help="probe: reviewed common-share symbol")
    parser.add_argument("--conid", type=int, help="probe: reviewed IB conid")
    parser.add_argument("--shares", type=int, default=1, help="probe: WhatIf size")
    parser.add_argument("--report", help="probe/integration-test: write the JSON report here")
    parser.add_argument(
        "--journal", help="integration-test: a NEW *.integration.sqlite file"
    )
    parser.add_argument(
        "--resume-entries",
        action="store_true",
        help="operator acknowledgement after proven recovery",
    )
    args = parser.parse_args(argv)
    try:
        config = read_json(args.config)
        endpoint = endpoint_from_config(config["endpoint"])
        check_live_config(config, endpoint)
        policy = Policy(**config["policy"]).validate()
        if args.command == "preflight":
            print(
                json.dumps(
                    {
                        "paper_only": not endpoint.live,
                        "live_orders_allowed": False,
                        "mode": endpoint.mode,
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
        elif args.command == "probe":
            if not (args.connect_live if endpoint.live else args.connect_paper):
                raise SafetyError("--connect-paper/--connect-live is required; no connection was opened")
            broker = PaperIBKR(endpoint, lambda: {"borrow": {}, "eligibility": {}})
            report = asyncio.run(
                probe(endpoint, policy, broker, symbol=args.symbol,
                      conid=args.conid, shares=args.shares)
            )
            text = json.dumps(report, indent=1, sort_keys=True)
            if args.report:
                Path(args.report).write_text(text + "\n", encoding="utf-8")
            print(text)
            return 0 if report["pass"] else 3
        elif args.command == "integration-test":
            if endpoint.live or not args.connect_paper:
                raise SafetyError("integration-test needs a paper endpoint and --connect-paper")
            if not (args.symbol and args.conid and args.journal):
                raise SafetyError("integration-test needs --symbol, --conid and --journal")
            from .integration import dumps, run_integration

            async def stage6():
                broker = PaperIBKR(endpoint, lambda: {"borrow": {}, "eligibility": {}})
                require_local_ib_listener(endpoint.port)
                await broker.connect()
                try:
                    return await run_integration(
                        endpoint, policy, broker, args.journal,
                        symbol=args.symbol, conid=args.conid,
                    )
                finally:
                    broker.close()

            report = asyncio.run(stage6())
            if args.report:
                Path(args.report).write_text(dumps(report) + "\n", encoding="utf-8")
            print(dumps(report))
            return 0 if report["pass"] else 3
        else:
            asyncio.run(run(args, endpoint, policy, config))
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
