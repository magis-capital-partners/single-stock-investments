"""Private SQLite history and immutable compressed source evidence."""
from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .realized import build_history, canonical, digest, normalize_event, read_report

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS realized_reports (
 report_id TEXT PRIMARY KEY, account TEXT NOT NULL, period_from TEXT NOT NULL,
 period_through TEXT NOT NULL, generated TEXT NOT NULL, manifest TEXT NOT NULL,
 archive_path TEXT NOT NULL, received_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS realized_report_period ON realized_reports(account, period_through, generated);
CREATE TABLE IF NOT EXISTS realized_events (
 account TEXT NOT NULL, event_id TEXT NOT NULL, trade_date TEXT, generated TEXT NOT NULL,
 report_id TEXT NOT NULL, active INTEGER NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(account,event_id));
CREATE INDEX IF NOT EXISTS realized_event_dates ON realized_events(account,trade_date);
CREATE TABLE IF NOT EXISTS realized_revisions (
 account TEXT NOT NULL, event_id TEXT NOT NULL, content_sha TEXT NOT NULL,
 report_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(account,event_id,content_sha));
CREATE TABLE IF NOT EXISTS realized_details (
 report_id TEXT NOT NULL, family TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(report_id,family), FOREIGN KEY(report_id) REFERENCES realized_reports(report_id));
CREATE TABLE IF NOT EXISTS realized_ownership (
 revision INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT NOT NULL,
 selector TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS realized_publications (
 generation_id TEXT PRIMARY KEY, account TEXT NOT NULL, manifest TEXT NOT NULL,
 published_at TEXT);
CREATE TABLE IF NOT EXISTS realized_policies (
 policy_id TEXT PRIMARY KEY, effective_from TEXT NOT NULL, payload TEXT NOT NULL,
 captured_at TEXT NOT NULL);
"""


class RealizedStore:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        (root / "reports").mkdir(exist_ok=True)
        root.chmod(0o700)
        (root / "reports").chmod(0o700)
        self.db = sqlite3.connect(root / "history.sqlite", timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        (root / "history.sqlite").chmod(0o600)

    def close(self):
        self.db.close()

    def ingest(self, path: Path, *, account: str, role: str | None = None) -> dict:
        report = read_report(path, account=account)
        if role == "closed_lots" and report["events"] and not report["lots"]:
            raise ValueError("configured Closed Lots query returned executions only; enable Closed Lots on a separate query")
        if self.db.execute("SELECT 1 FROM realized_reports WHERE report_id=?", (report["report_id"],)).fetchone():
            return {"duplicate": True, "report_id": report["report_id"]}
        events = [normalize_event(row, report) for row in report["events"]]
        ids = [e["event_id"] for e in events]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate event identifiers within one execution report; refusing ambiguous import")
        archive = self.root / "reports" / (report["report_id"] + ".xml.gz")
        temporary = archive.with_suffix(".tmp")
        archived_sha = hashlib.sha256()
        with path.open("rb") as source, temporary.open("wb") as target:
            # Fixed gzip timestamp makes a replay byte-identical.
            with gzip.GzipFile(fileobj=target, mode="wb", mtime=0, filename="") as compressed:
                while block := source.read(1024 * 1024):
                    archived_sha.update(block)
                    compressed.write(block)
        if archived_sha.hexdigest() != report["report_id"]:
            temporary.unlink(missing_ok=True)
            raise ValueError("report changed before archival; refusing inconsistent source evidence")
        temporary.replace(archive)
        archive.chmod(0o600)
        families = {k: report.pop(k) for k in ("events", "lots", "positions", "summaries", "actions")}
        report["has_executions"] = role != "closed_lots" and (bool(events) or (
            "Trades" in report["sections"] and not report["trade_levels"] and not families["lots"]))
        report["role"] = role or ("executions" if report["has_executions"] else "supplement")
        report["event_count"] = len(events)
        now = datetime.now(timezone.utc).isoformat()
        with self.db:
            self.db.execute("INSERT INTO realized_reports VALUES (?,?,?,?,?,?,?,?)", (
                report["report_id"], account, report["from"], report["through"], report["generated"], canonical(report), str(archive), now))
            for family in ("lots", "positions", "summaries", "actions"):
                if families[family]:
                    self.db.execute("INSERT INTO realized_details VALUES (?,?,?)", (report["report_id"], family, canonical(families[family])))
            # A complete later execution statement is authoritative for its own
            # covered dates. Missing events become inactive, with prior versions
            # retained. A Closed Lots-only query never retires executions.
            if report["has_executions"]:
                self.db.execute("UPDATE realized_events SET active=0 WHERE account=? AND trade_date BETWEEN ? AND ? AND generated<=?", (
                    account, report["from"], report["through"], report["generated"]))
            for event in events:
                payload = canonical(event)
                business = {k: v for k, v in event.items() if k != "report_id"}
                self.db.execute("INSERT OR IGNORE INTO realized_revisions VALUES (?,?,?,?,?)", (
                    account, event["event_id"], digest(business), report["report_id"], payload))
                self.db.execute("""INSERT INTO realized_events VALUES (?,?,?,?,?,1,?)
                  ON CONFLICT(account,event_id) DO UPDATE SET trade_date=excluded.trade_date,
                  generated=excluded.generated,report_id=excluded.report_id,active=1,payload=excluded.payload
                  WHERE excluded.generated>=realized_events.generated""", (
                    account, event["event_id"], event["trade_date"], report["generated"], report["report_id"], payload))
        return {"duplicate": False, "report_id": report["report_id"], "from": report["from"],
                "through": report["through"], "events": len(events), "closed_lots": len(families["lots"])}

    def assign(self, rule: dict) -> dict:
        if rule.get("owner") not in {"drew", "michael", "excluded", "unallocated"}:
            raise ValueError("invalid owner")
        if not all(rule.get(k) for k in ("account", "author", "reason")):
            raise ValueError("ownership changes require account, author and evidence/reason")
        if not rule.get("record_id") and not all(rule.get(k) for k in ("conid", "opening_from", "opening_through")):
            raise ValueError("provide a record ID or an exact contract and opening-date interval")
        with self.db:
            cursor = self.db.execute("INSERT INTO realized_ownership(account,selector,payload,created_at) VALUES (?,?,?,?)", (
                rule["account"], rule.get("record_id") or rule["conid"], canonical(rule), datetime.now(timezone.utc).isoformat()))
        return {**rule, "revision": cursor.lastrowid}

    def build(self, *, account: str, ls_symbols: set[str], blacklist: set[str]) -> dict:
        reports = [json.loads(r[0]) for r in self.db.execute(
            "SELECT manifest FROM realized_reports WHERE account=? ORDER BY generated,report_id", (account,))]
        if not reports:
            raise ValueError("no imported reports for configured account")
        events = [json.loads(r[0]) for r in self.db.execute(
            "SELECT payload FROM realized_events WHERE account=? AND active=1", (account,))]
        # Keep latest detail for each covered period, then resolve overlapping
        # closed-lot windows newest-first by closing business identifier.
        details = self.db.execute("""SELECT d.family,d.payload,r.manifest FROM realized_details d
          JOIN realized_reports r USING(report_id) WHERE r.account=? ORDER BY r.generated DESC,r.report_id DESC""", (account,)).fetchall()
        positions, summaries, lots, actions = [], [], [], []
        seen_lot_closes: set[str] = set()
        seen_actions: set[str] = set()
        summary_ranges: list[tuple[str, str]] = []
        positions_found = False
        used_reports = {e["report_id"] for e in events}
        for detail in details:
            family, rows = detail["family"], json.loads(detail["payload"])
            manifest = json.loads(detail["manifest"])
            if family == "positions" and not positions_found:
                positions, positions_found = rows, True
                used_reports.add(manifest["report_id"])
            elif family == "summaries" and not any(a <= manifest["from"] and b >= manifest["through"] for a, b in summary_ranges):
                summaries.extend({**r, "_period_from": manifest["from"], "_period_through": manifest["through"]} for r in rows)
                summary_ranges.append((manifest["from"], manifest["through"]))
                used_reports.add(manifest["report_id"])
            elif family == "lots":
                grouped = {}
                for row in rows:
                    row = {**row, "_date_order": manifest.get("date_order")}
                    key = row.get("closingTransactionID") or row.get("closingTradeID") or row.get("tradeID") or digest(row)
                    grouped.setdefault(key, []).append(row)
                for key, group in grouped.items():
                    if key not in seen_lot_closes:
                        lots.extend(group)
                        seen_lot_closes.add(key)
                        used_reports.add(manifest["report_id"])
            elif family == "actions":
                for action in rows:
                    key = str(action.get("actionID") or action.get("tradeID") or digest(action)) + ":" + action.get("conid", "")
                    if key not in seen_actions:
                        actions.append({**action, "_source_report_id": manifest["report_id"]})
                        seen_actions.add(key)
                        used_reports.add(manifest["report_id"])
        overrides = [{**json.loads(r["payload"]), "revision": r["revision"]} for r in self.db.execute(
            "SELECT revision,payload FROM realized_ownership WHERE account=? ORDER BY revision", (account,))]
        policy_content = {"ls_symbols": sorted(ls_symbols), "blacklist": sorted(blacklist)}
        policies = [json.loads(r[0]) for r in self.db.execute("SELECT payload FROM realized_policies ORDER BY effective_from,captured_at")]
        if not policies or any(policy_content[k] != policies[-1][k] for k in policy_content):
            stamp = datetime.now(ZoneInfo("America/New_York"))
            policy = {**policy_content, "effective_from": stamp.date().isoformat() if policies else "0001-01-01",
                      "basis": "dated_policy_capture" if policies else "initial_historical_inference"}
            policy["policy_id"] = digest(policy)
            with self.db:
                self.db.execute("INSERT INTO realized_policies VALUES (?,?,?,?)", (policy["policy_id"], policy["effective_from"], canonical(policy), stamp.isoformat()))
            policies.append(policy)
        # An explicit reported amount on an otherwise unlinked corporate or
        # option action can be shown. Proceeds/market value never stand in for
        # missing realized P&L, and linked Trade/EAE representations count once.
        known_ids = {e["trade_id"] for e in events if e["trade_id"]}
        unmatched_actions = {digest(a): a for a in actions if a.get("tradeID") not in known_ids}
        action_events = []
        for action in unmatched_actions.values():
            if action.get("fifoPnlRealized") in (None, "") and action.get("realizedPnl") in (None, ""):
                continue
            action_id = action.get("actionID") or action.get("tradeID") or digest(action)
            raw = {**action, "transactionID": f"action:{action_id}:{action.get('conid', '')}",
                   "transactionType": "CorporateAction" if action.get("event_section") == "CorporateAction" else "OptionBooking",
                   "tradeDate": action.get("dateTime") or action.get("date") or action.get("reportDate"), "openCloseIndicator": "C"}
            source = next(r for r in reports if r["report_id"] == action["_source_report_id"])
            action_events.append(normalize_event(raw, source))
        history = build_history(events, lots, reports=reports, positions=positions,
                                ls_symbols=ls_symbols, blacklist=blacklist, overrides=overrides, summaries=summaries, policies=policies)
        if action_events:
            history = build_history(events + action_events, lots, reports=reports, positions=positions,
                                    ls_symbols=ls_symbols, blacklist=blacklist, overrides=overrides, summaries=summaries, policies=policies)
        # Corporate actions/EAE without a linked trade stay visible as coverage
        # exceptions. No disappearance-based profit or synthetic sale is made.
        missing_action_pnl = sum(a.get("fifoPnlRealized") in (None, "") and a.get("realizedPnl") in (None, "") for a in unmatched_actions.values())
        if missing_action_pnl:
            history["reconciliation"]["status"] = "needs_review"
            history["reconciliation"]["unmatched_action_count"] = missing_action_pnl
        # A YTD snapshot supersedes contained periods. Keep only sources needed
        # to reproduce the active records/detail/coverage in each manifest;
        # otherwise daily cumulative reports would eventually exceed D1 limits.
        covered_through = ""
        for report in sorted((r for r in reports if r["has_executions"]),
                             key=lambda r: (r["from"], -date.fromisoformat(r["through"]).toordinal())):
            if report["through"] > covered_through:
                used_reports.add(report["report_id"])
                covered_through = report["through"]
        history.update({"account": account, "storage_version": "packed_v1", "source_reports": [{k: r[k] for k in
                        ("report_id", "from", "through", "generated", "source_name", "has_executions")} for r in reports if r["report_id"] in used_reports]})
        history["generation_id"] = digest(history)
        return history
