"""Account-wide position ownership reconciliation (no socket, no client ID).

One IBKR account holds several systems' books, and IB nets every contract per
account. Each system keeps its own ledger; this check puts the account's actual
positions next to the declared owners and raises an alarm for:

* a position no rule claims (``unowned``);
* a position two systems claim (``double_owned``);
* an RS (or other ledger-backed) quantity that differs from the broker's
  (``ledger_mismatch``), in either direction, including a ledger position the
  broker does not show.

Inputs are files: an IBKR Flex statement (``OpenPosition`` rows; run it after
the Flex day closes) or a JSON list of positions, the ownership rules, the
symbol-claims directory, and optional per-system ledgers. Rules, in order:

    {"system": "spx-0dte", "asset": ["OPT", "FOP"], "underlyings": ["SPX", "SPXW", "XSP"]}
    {"system": "reverse-split", "claims": true}          # from <claims_dir>/reverse-split.json
    {"system": "ls-algo", "symbols_file": "/path/one-symbol-per-line.txt"}
    {"system": "portfolio-hub", "residual": true}         # optional catch-all owner

A residual rule only takes what no explicit rule claimed; without one, such
positions are alarms. Usage::

    python -m _system.trading.account_ownership --positions flex.xml \
        --rules rules.json --claims-dir /var/lib/ib-account-claims \
        --ledger reverse-split=/var/lib/rs-live/state.sqlite --report out.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
import xml.etree.ElementTree as ET

from _system.trading.rs_paper_executor.claims import _validate as validate_claims
from _system.trading.rs_paper_executor.claims import active


class OwnershipError(ValueError):
    pass


def read_positions(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if text.lstrip().startswith("<"):
        rows = []
        for el in ET.fromstring(text).iter("OpenPosition"):
            if el.get("levelOfDetail", "SUMMARY").upper() not in ("SUMMARY", ""):
                continue  # lot rows would double count
            rows.append({
                "conid": int(el.get("conid")), "symbol": el.get("symbol", ""),
                "sec_type": el.get("assetCategory", ""),
                "underlying": el.get("underlyingSymbol") or el.get("symbol", ""),
                "position": float(el.get("position")), "account": el.get("accountId"),
            })
        return rows
    rows = json.loads(text)
    if not isinstance(rows, list):
        raise OwnershipError("positions JSON must be a list")
    return [{**r, "underlying": r.get("underlying") or r.get("symbol", "")} for r in rows]


def claimed_conids(claims_dir, system, now):
    path = Path(claims_dir) / (system + ".json")
    if not path.exists():
        return {}, {}
    data = validate_claims(json.loads(path.read_text(encoding="utf-8")), system)
    rows = data["claims"]
    by_conid = {r["conid"]: s for s, r in rows.items()}
    # Released claims still own a position the broker shows: a late fill or a
    # recall must not turn into someone else's or nobody's position.
    return by_conid, {s for s, r in rows.items() if active(r, now)}


def ledger_quantities(path):
    """Signed broker-equivalent quantity per conid from an RS journal (read-only)."""
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        rows = db.execute("SELECT conid, shares FROM positions WHERE shares>0").fetchall()
    finally:
        db.close()
    out = {}
    for conid, shares in rows:
        out[conid] = out.get(conid, 0) - shares  # RS holds shorts
    return out


def reconcile(positions, rules, *, claims_dir=None, ledgers=None, now, account=None):
    ledgers = ledgers or {}
    owners, report = {}, {"unowned": [], "double_owned": [], "ledger_mismatch": [],
                          "owned": {}}
    claim_maps = {}
    for rule in rules:
        if rule.get("claims"):
            claim_maps[rule["system"]] = claimed_conids(claims_dir, rule["system"], now)[0]
    symbol_sets = {r["system"]: {x.strip().upper() for x in Path(r["symbols_file"])
                                 .read_text(encoding="utf-8").splitlines()
                                 if x.strip() and not x.startswith("#")}
                   for r in rules if r.get("symbols_file")}
    residual = [r["system"] for r in rules if r.get("residual")]
    if len(residual) > 1:
        raise OwnershipError("at most one residual owner")
    for pos in positions:
        if account and pos.get("account") not in (None, account):
            continue
        if not pos.get("position"):
            continue
        hits = []
        for rule in rules:
            system = rule["system"]
            if rule.get("claims") and pos["conid"] in claim_maps.get(system, {}):
                hits.append(system)
            elif "underlyings" in rule and pos.get("sec_type") in rule.get("asset", []) \
                    and pos["underlying"].upper() in {u.upper() for u in rule["underlyings"]}:
                hits.append(system)
            elif rule.get("symbols_file") and pos["symbol"].upper() in symbol_sets[system]:
                hits.append(system)
        hits = sorted(set(hits))
        row = {"conid": pos["conid"], "symbol": pos["symbol"], "sec_type": pos.get("sec_type"),
               "position": pos["position"]}
        if len(hits) > 1:
            report["double_owned"].append({**row, "systems": hits})
            continue
        owner = hits[0] if hits else (residual[0] if residual else None)
        if owner is None:
            report["unowned"].append(row)
            continue
        owners[pos["conid"]] = (owner, pos["position"])
        report["owned"].setdefault(owner, []).append(row)
    for system, quantities in ledgers.items():
        for conid, qty in quantities.items():
            broker_owner, broker_qty = owners.get(conid, (None, 0))
            if broker_owner != system or broker_qty != qty:
                report["ledger_mismatch"].append({"system": system, "conid": conid,
                                                  "ledger": qty, "broker": broker_qty,
                                                  "broker_owner": broker_owner})
        for conid, (owner, qty) in owners.items():
            if owner == system and conid not in quantities:
                report["ledger_mismatch"].append({"system": system, "conid": conid,
                                                  "ledger": 0, "broker": qty,
                                                  "broker_owner": owner})
    report["status"] = ("alarm" if report["unowned"] or report["double_owned"]
                        or report["ledger_mismatch"] else "ok")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--positions", required=True)
    parser.add_argument("--rules", required=True)
    parser.add_argument("--claims-dir")
    parser.add_argument("--ledger", action="append", default=[], help="system=journal.sqlite")
    parser.add_argument("--account")
    parser.add_argument("--now", required=False)
    parser.add_argument("--report")
    args = parser.parse_args(argv)
    from datetime import datetime, timezone
    now = args.now or datetime.now(timezone.utc).isoformat()
    ledgers = {}
    for item in args.ledger:
        system, _, path = item.partition("=")
        ledgers[system] = ledger_quantities(path)
    try:
        report = reconcile(read_positions(args.positions),
                           json.loads(Path(args.rules).read_text(encoding="utf-8")),
                           claims_dir=args.claims_dir, ledgers=ledgers, now=now,
                           account=args.account)
    except (OSError, ValueError) as exc:
        report = {"status": "alarm", "error": type(exc).__name__ + ": " + str(exc)}
    text = json.dumps(report, indent=1, sort_keys=True)
    if args.report:
        Path(args.report).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
