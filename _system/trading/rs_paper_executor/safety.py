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


PREFIX = "RSPAPER|"
LIVE_PREFIX = "RSLIVE|"
RS_SYSTEM = "reverse-split"
LIVE_APPROVAL = Path("/etc/rs-live-approved")
BOX_R_HOSTS = {"magis-collector-3", "magis-collector-2"}
# NY4 answers to several names (SSH alias spx-ny4, provider name FXVPS374628).
# Paper must never run there: a paper Gateway beside the live one is route B,
# which the owner declined on 2026-11-18. The SPX install path is a second proof.
NY4_HOSTS = {"ny4", "spx-ny4", "fxvps374628"}
NY4_MARKERS = (Path("/home/spx/spx-0dte"), Path("/home/spx/.config/spx-0dte"))
# Names other systems in this account trade as products or deliverables. An RS
# order or position here would switch off that product's delivery attribution
# in spx-0dte (order_ownership foreign-share rule); never an RS name.
PROTECTED_SYMBOLS = frozenset(
    {"SPX", "SPXW", "XSP", "VIX", "SPY", "QQQ", "TSLA", "NVDA", "AMZN"}
)


def _refuse_box_r():
    import socket

    host = socket.gethostname().lower()
    if (
        host in BOX_R_HOSTS
        or os.environ.get("RS_COLLECTOR_HOST")
        or Path("/etc/reverse-split-live.env").exists()
    ):
        raise SafetyError("broker adapter may not run on Box R")
    return host


@dataclass(frozen=True)
class PaperEndpoint:
    account: str
    client_id: int
    port: int
    host: str = "127.0.0.1"
    mode: str = "paper"
    deployment_role: str = "isolated_paper_executor"
    prefix = PREFIX
    live = False

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
        host = _refuse_box_r()
        if host.split(".")[0] in NY4_HOSTS or any(m.exists() for m in NY4_MARKERS):
            raise SafetyError("paper broker adapter may not run on Box R or NY4")


@dataclass(frozen=True)
class LiveEndpoint:
    """The shared NY4 Gateway, as the registered reverse-split system.

    Connectable only when the canonical registry (hash-pinned) allocates
    ``client_id`` to ``reverse-split`` as an active transmit executor and lists
    ``RSLIVE|`` as its only order prefix, the port is the registry's Gateway
    live port on loopback, the account is the pinned ``U`` account, and the host
    carries the operator approval file. Transmission is a further, separate arm
    (see ``arm.py``): a validated live endpoint alone only runs in shadow.
    """

    account: str
    client_id: int
    port: int
    host: str = "127.0.0.1"
    mode: str = "live"
    deployment_role: str = "ny4_reverse_split_live"
    prefix = LIVE_PREFIX
    live = True

    def validate(self):
        if self.mode != "live" or self.deployment_role != "ny4_reverse_split_live":
            raise SafetyError("live endpoint requires the ny4_reverse_split_live role")
        if not re.fullmatch(r"U[0-9]+", self.account or ""):
            raise SafetyError("explicit pinned U live account required")
        registry, _ = load_registry()
        if self.host != "127.0.0.1" or self.port != int(registry["gateway"]["live_port"]):
            raise SafetyError("live endpoint must be the registry Gateway port on loopback")
        client = integer(self.client_id, "live client ID", minimum=1)
        allocation = allocation_index(registry).get(client)
        if (
            allocation is None
            or allocation.system != RS_SYSTEM
            or allocation.access != "transmit"
            or not allocation.connectable
            or "executor" not in allocation.role
            or "watchdog" in allocation.role
        ):
            raise SafetyError("client ID is not the registered reverse-split executor")
        prefixes = registry["systems"][RS_SYSTEM].get("order_ref_prefixes")
        if prefixes != [LIVE_PREFIX]:
            raise SafetyError("registry reverse-split prefixes do not match RSLIVE|")
        return self

    def prove_session(self, managed_accounts, actual_client):
        # The shared Gateway may list other managed accounts (see SPX's account
        # pin); every request here is account-scoped, so only presence is proven.
        self.validate()
        if self.account not in tuple(managed_accounts):
            raise SafetyError("pinned live account not offered by this session")
        if actual_client != self.client_id:
            raise SafetyError("broker client identity mismatch")

    def runtime_guard(self):
        _refuse_box_r()
        if not LIVE_APPROVAL.exists():
            raise SafetyError("live host approval file is absent")


def endpoint_from_config(block):
    mode = (block or {}).get("mode")
    if mode == "live":
        return LiveEndpoint(**block).validate()
    return PaperEndpoint(**block).validate()


def owned_order(row, endpoint, known_refs):
    prefix = re.escape(endpoint.prefix)
    return (
        row.get("account") == endpoint.account
        and row.get("client_id") == endpoint.client_id
        and row.get("ref") in known_refs
        and re.fullmatch(prefix + r"[a-f0-9]{20}", row.get("ref", "")) is not None
    )
