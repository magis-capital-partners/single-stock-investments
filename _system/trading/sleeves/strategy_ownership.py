"""Versioned ownership evidence from executed broker records, never order intents.

Identifiers are namespaced by account, contract, model and identifier domain.
The registry is private; only its hash and aggregate allocation reach the read
model. A universe is a fallback policy, not proof that a human lot is LS-owned.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import csv
from pathlib import Path
from datetime import datetime, timezone

VERSION = "strategy_ownership.v1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def reference_owner(ref, sec_type="STK"):
    ref = str(ref or "").upper().strip()
    if sec_type in {"OPT", "FOP"} and re.match(r"^ETF_LS\|MANUAL\|SELL(?:PUT|CALL)\|", ref):
        return {"owner": "drew", "strategy": "letf_option_overlay", "reason": "documented_manual_option_overlay"}
    if ref.startswith(("ETF_LS|", "B5P|")):
        return {"owner": "excluded", "strategy": "ls_algo", "reason": "executed_ls_order_reference"}
    for owner in ("drew", "michael"):
        if f"{owner.upper()}_SLEEVE" in ref or re.search(rf"^MAGIS\|[^|]+\|{owner.upper()}\|", ref):
            return {"owner": owner, "strategy": "single_stock", "reason": "executed_owner_order_reference"}
    return None


def _key(account, conid, model, domain, identity):
    return canonical([str(account), str(conid), str(model or ""), domain, str(identity)])


def _moment(value):
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[:14] if len(digits) >= 14 else ""


def dated_universes(root):
    """Candidate membership is review evidence only, never a filled-trade claim."""
    if not root:
        return []
    snapshots = []
    for path in sorted(Path(root).glob("????-??-??/etf_screened_today.csv")):
        raw = path.read_bytes()
        rows = csv.DictReader(raw.decode("utf-8-sig").splitlines())
        symbols = {str(row.get(key) or "").strip().upper().replace(".", "-") for row in rows for key in ("ETF", "Underlying")}
        snapshots.append({"date": path.parent.name, "symbols": sorted(symbols - {""}),
                          "source_sha": hashlib.sha256(raw).hexdigest()})
    return snapshots


class OwnershipRegistry:
    def __init__(self, payload):
        self.payload = payload
        self.version = digest({k: v for k, v in payload.items() if k != "prepared_at"})

    @classmethod
    def build(cls, events, *, account, through, sources=(), universes=()):
        identities, ls_contracts, moments = {}, {}, {}
        canceled = {("transaction", e["cancel_transaction_id"]) for e in events if e.get("cancel_transaction_id")}
        canceled |= {("trade", e["cancel_trade_id"]) for e in events if e.get("cancel_trade_id")}
        for event in events:
            if event.get("account") != account or event.get("event_type") == "TradeCancel":
                continue
            conid, model = str(event.get("conid") or ""), event.get("model") or ""
            ownership = reference_owner(event.get("order_ref"), event.get("sec_type", "STK"))
            invalid = any((domain, str(event.get(field) or "")) in canceled for domain, field in
                          (("transaction", "transaction_id"), ("trade", "trade_id")))
            evidence = {"ownership": ownership, "date": event.get("trade_date"),
                        "event_id": event.get("event_id"), "report_id": event.get("report_id"),
                        "quantity": event.get("quantity"), "canceled": invalid}
            moment = _moment(event.get("trade_time"))
            if moment:
                moments.setdefault(_key(account, conid, model, "moment", moment), []).append(evidence)
            if ownership and ownership["strategy"] == "ls_algo" and not invalid:
                key = _key(account, conid, model, "contract", "")
                first = event.get("trade_date") or "0000"
                ls_contracts[key] = min(ls_contracts.get(key, first), first)
            for domain, field in (("transaction", "transaction_id"), ("trade", "trade_id"), ("execution", "exec_id")):
                if event.get(field):
                    key = _key(account, conid, model, domain, event[field])
                    old = identities.get(key)
                    if old and old["ownership"] != evidence["ownership"]:
                        evidence = {**evidence, "canceled": True, "conflict": True}
                    identities[key] = evidence
        return cls({"schema_version": VERSION, "account": account, "through": through,
                    "sources": sorted(sources), "identities": identities, "ls_contracts": ls_contracts,
                    "moments": moments, "universes": list(universes)})

    def resolve(self, *, account, conid, model="", transaction_id="", trade_id="",
                opening_date=None, opening_time="", closing_ref="", sec_type="STK", symbol=""):
        if account != self.payload["account"]:
            raise ValueError("ownership account mismatch")
        matches = [self.payload["identities"].get(_key(account, conid, model, domain, identity))
                   for domain, identity in (("transaction", transaction_id), ("trade", trade_id)) if identity]
        matches = [m for m in matches if m]
        if not matches and _moment(opening_time):
            matches = self.payload.get("moments", {}).get(_key(account, conid, model, "moment", _moment(opening_time)), [])
        closing = reference_owner(closing_ref, sec_type)
        review = {"owner": "unallocated", "strategy": "ownership_review", "reason": "shared_ls_lot_requires_evidence"}
        if any(m.get("canceled") for m in matches):
            return {**review, "reason": "canceled_or_conflicting_opening_identity"}
        owners = {canonical(m["ownership"]) for m in matches if m["ownership"]}
        if len(owners) > 1:
            return {**review, "reason": "conflicting_opening_identities"}
        if owners and any(not m["ownership"] for m in matches):
            return {**review, "reason": "mixed_opening_evidence"}
        if owners:
            result = json.loads(next(iter(owners)))
            # The opening lot owns its realization, including a human exit of
            # an algorithmic lot. An algo exit of a human lot needs review.
            if result["owner"] != "excluded" and closing and closing["owner"] == "excluded":
                return {**review, "reason": "cross_strategy_close"}
            return {**result, "reason": "broker_matched_opening_order_reference"}
        if closing:
            return closing
        first_ls = self.payload["ls_contracts"].get(_key(account, conid, model, "contract", ""))
        dates = [m.get("date") for m in matches if m.get("date")]
        opened = min(dates) if dates else opening_date
        if first_ls and (not opened or opened >= first_ls):
            return review
        applicable = [u for u in self.payload.get("universes", []) if u["date"] <= (opened or self.payload["through"])]
        if applicable and str(symbol).upper().replace(".", "-") in applicable[-1]["symbols"]:
            return {**review, "reason": "dated_ls_universe_without_opening_evidence"}
        if symbol == "3905.T" and sec_type not in {"OPT", "FOP"}:
            if not opening_date:
                return {**review, "reason": "shared_security_missing_opening_date"}
            return {"owner": "drew" if opening_date >= "2026-09-13" else "michael", "strategy": "single_stock",
                    "reason": "dated_3905_lot_policy", "confidence": "legacy_inferred"}
        return None

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        immutable = path.with_name(f"ownership-{self.version}.json")
        if immutable.exists():
            existing = json.loads(immutable.read_text(encoding="utf-8"))
            self.payload["prepared_at"] = existing.get("prepared_at") or datetime.fromtimestamp(immutable.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
        else:
            self.payload["prepared_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        body = canonical(self.payload)
        if not immutable.exists():
            immutable.write_text(body, encoding="utf-8")
            immutable.chmod(0o600)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(body, encoding="utf-8")
        temporary.replace(path)
        path.chmod(0o600)

    @classmethod
    def load(cls, path, *, account=None, through=None):
        registry = cls(json.loads(Path(path).read_text(encoding="utf-8")))
        if registry.payload.get("schema_version") != VERSION:
            raise ValueError("unsupported ownership registry")
        if account and registry.payload["account"] != account:
            raise ValueError("ownership account mismatch")
        if through and registry.payload["through"] != through:
            raise ValueError("ownership registry does not cover position session")
        return registry


def configured_registry(*, account=None, through=None):
    path = os.environ.get("SLEEVE_OWNERSHIP_REGISTRY")
    if not path:
        if os.environ.get("SLEEVE_OWNERSHIP_REQUIRED") == "1":
            raise ValueError("required ownership registry is not configured")
        return None
    return OwnershipRegistry.load(path, account=account, through=through)


def annotate_lots(rows, registry, *, account):
    """Retain broker quantities and economics; attach only ownership evidence."""
    from _system.trading.portfolio_hub.flex import flex_date
    for row in rows:
        evidence = registry.resolve(account=account, conid=row.get("conid", row.get("conId")),
            model=row.get("model_code", row.get("model", "")),
            transaction_id=row.get("originatingTransactionID", ""), trade_id=row.get("openTradeID", ""),
            opening_date=flex_date(row.get("openDateTime")),
            opening_time=row.get("openDateTime", ""), symbol=row.get("symbol", ""),
            closing_ref=row.get("orderRef", row.get("order_ref", "")),
            sec_type=row.get("sec_type", row.get("secType", "STK")))
        if evidence:
            row["_ownership"] = evidence
        row["ownership_version"] = registry.version
    return rows
