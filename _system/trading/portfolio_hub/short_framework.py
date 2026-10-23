"""Validate a private framework handoff without contacting any broker service."""
from __future__ import annotations

from decimal import Decimal
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def validate_framework_order(ticket: dict, binding: str | None, *, ledger_path: str | None = None) -> None:
    """Fail closed unless the shared engine revalidates the exact private ticket.

    Node reads the local immutable decision/evidence journal. This does not open
    a Gateway connection; the existing order service still owns preview,
    approval, account isolation, transmission and cancellation.
    """
    if ticket.get("strategy") != "short_framework":
        return
    match = re.fullmatch(r"SF1:([a-f0-9]{64}):([a-f0-9]{64})", str(binding or ""))
    if not match:
        raise ValueError("Short framework requires a private reviewed decision binding")
    executable = os.environ.get("SHORT_FRAMEWORK_NODE") or shutil.which("node")
    if not executable:
        raise ValueError("Shared framework runtime unavailable; entry is closed")
    root = Path(__file__).resolve().parents[3]
    command = [executable, str(root / "_system/scripts/short_framework.cjs"),
               "verify-handoff", "--request-hash", match[2]]
    if ledger_path:
        command.extend(["--hub-ledger", ledger_path])
    if ticket.get("intent_uuid"):
        command.extend(["--exclude-intent", str(ticket["intent_uuid"])])
    try:
        result = subprocess.run(command, cwd=root, capture_output=True, text=True,
                                timeout=15, check=False)
        if result.returncode:
            raise ValueError("Private framework decision is missing, expired or no longer eligible")
        verified = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise ValueError("Private framework validation unavailable; entry is closed") from exc
    request = verified.get("request") or {}
    if verified.get("valid") is not True or request.get("framework_decision_id") != match[1]:
        raise ValueError("Framework decision identity mismatch")
    if not verified.get("account_reference") or verified["account_reference"] != ticket.get("account_alias"):
        raise ValueError("Framework handoff is not bound to this account")
    comparisons = {"conid": int, "action": str, "mode": str, "tif": str,
                   "quantity": Decimal, "limit_price": Decimal}
    for key, convert in comparisons.items():
        actual = ticket.get(key, ticket.get(key + "_decimal"))
        expected = request.get(key)
        if actual is None or expected is None or convert(str(actual)) != convert(str(expected)):
            raise ValueError("Framework handoff changed: " + key)
    if bool(ticket.get("outside_rth")) != bool(request.get("outside_rth")):
        raise ValueError("Framework session instruction changed")
    if ticket.get("action") == "SELL" and ticket.get("reduce_only") is not False:
        raise ValueError("Framework entry must be an explicitly identified short sale")
    if ticket.get("action") == "BUY" and ticket.get("reduce_only") is not True:
        raise ValueError("Framework covers must reduce an existing short")

