"""Paper-only counterpart of SPX's explicit profile/account/ownership guards."""

from __future__ import annotations

import math
import os
from pathlib import Path
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from _system.trading.ib_gateway_registry import (
    allocation_index,
    load_registry,
    retired_client_ids,
)


class SafetyError(ValueError):
    pass


def number(value, label="number", *, minimum=None):
    if isinstance(value, bool):
        raise SafetyError(label + " cannot be boolean")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise SafetyError(label + " missing or invalid") from exc
    if not math.isfinite(result) or abs(result) >= 1e100:
        raise SafetyError(label + " is an unset/sentinel value")
    if minimum is not None and result < minimum:
        raise SafetyError(label + " is below its minimum")
    return result


def integer(value, label="integer", *, minimum=0):
    result = number(value, label, minimum=minimum)
    if result != int(result):
        raise SafetyError(label + " must be integral")
    return int(result)


def timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError("timezone missing")
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError) as exc:
        raise SafetyError("timezone-aware clock required") from exc


def fresh(value, now, max_age):
    age = (timestamp(now) - timestamp(value)).total_seconds()
    if age < -2 or age > max_age:
        raise SafetyError("stale or future evidence")


@dataclass(frozen=True)
class PaperEndpoint:
    account: str
    client_id: int
    port: int
    host: str = "127.0.0.1"
    mode: str = "paper"
    deployment_role: str = "isolated_paper_executor"

    def validate(self):
        if self.mode != "paper" or self.deployment_role != "isolated_paper_executor":
            raise SafetyError("only an isolated paper executor is supported")
        if self.host != "127.0.0.1" or self.port not in (4002, 7497):
            raise SafetyError("only loopback paper Gateway/TWS ports are permitted")
        if not re.fullmatch(r"DU[0-9]+", self.account or ""):
            raise SafetyError("explicit DU paper account required")
        client = integer(self.client_id, "paper client ID", minimum=1)
        registry, _ = load_registry()
        if client in allocation_index(registry) or client in retired_client_ids(
            registry
        ):
            raise SafetyError("production/reserved client IDs cannot be used")
        return self

    def prove_session(self, managed_accounts, actual_client):
        self.validate()
        accounts = tuple(managed_accounts)
        if self.account not in accounts or any(
            not re.fullmatch(r"DU[0-9]+", x) for x in accounts
        ):
            raise SafetyError("broker session is not exclusively paper")
        if actual_client != self.client_id:
            raise SafetyError("broker client identity mismatch")

    def runtime_guard(self):
        import socket

        host = socket.gethostname().lower()
        if (
            host in {"ny4", "magis-collector-3", "magis-collector-2"}
            or os.environ.get("RS_COLLECTOR_HOST")
            or Path("/etc/reverse-split-live.env").exists()
        ):
            raise SafetyError("paper broker adapter may not run on Box R or NY4")


PREFIX = "RSPAPER|"


def owned_order(row, endpoint, known_refs):
    return (
        row.get("account") == endpoint.account
        and row.get("client_id") == endpoint.client_id
        and row.get("ref") in known_refs
        and re.fullmatch(r"RSPAPER\|[a-f0-9]{20}", row.get("ref", "")) is not None
    )
