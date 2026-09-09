"""Canonical IB Gateway client-ID registry access for SSI.

Every SSI socket path calls :func:`assert_ssi_client_id` immediately before
connecting.  The registry is also pinned to the hash embedded in this repo so a
locally edited allocation cannot silently become authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


REGISTRY_PATH = Path(__file__).with_name("ib_gateway_client_registry.v1.json")
EXPECTED_SCHEMA_VERSION = "ib_gateway_client_registry.v1"
EXPECTED_REGISTRY_VERSION = "2026-09-09.1"
EXPECTED_REGISTRY_HASH = "3d2ba10bda3a577696e8e85ae5a6efd1a934e33341ade782506b79f0bad82abd"
REGISTRY_HASH_ALGORITHM = "sha256-canonical-json-without-registry_hash"
SSI_SYSTEM = "single-stock-investments"

SSI_HUB_BRIDGE_ROLE = "portfolio hub order bridge"
SSI_LEGACY_DREW_ROLE = "legacy Drew sleeve"
SSI_LEGACY_MICHAEL_ROLE = "legacy Michael sleeve"
SSI_LEGACY_SYNC_ROLE = "legacy sleeve synchronization"
SSI_DISABLED_COLLECTOR_ROLE = "retired portfolio collector"
SSI_RESERVED_OBSERVER_ROLE = "future master observer"
SSI_LEGACY_ROLES = frozenset({
    SSI_LEGACY_DREW_ROLE,
    SSI_LEGACY_MICHAEL_ROLE,
    SSI_LEGACY_SYNC_ROLE,
})

CONNECTABLE_STATUS = "active"
CONNECTABLE_ACCESS = frozenset({"transmit", "read_only"})


class RegistryError(ValueError):
    """The registry or a requested client allocation is unsafe."""


@dataclass(frozen=True)
class ClientAllocation:
    client_id: int
    system: str
    role: str
    access: str
    status: str
    pooled: bool = False

    @property
    def connectable(self) -> bool:
        return self.status == CONNECTABLE_STATUS and self.access in CONNECTABLE_ACCESS


def canonical_hash(raw: Mapping[str, Any]) -> str:
    """Hash canonical JSON after omitting the self-referential hash field."""
    payload = dict(raw)
    payload.pop("registry_hash", None)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _coerce_client_id(value: Any, *, label: str = "client ID") -> int:
    if isinstance(value, bool):
        raise RegistryError(f"{label} must be an integer, not {value!r}")
    try:
        client_id = int(value)
    except (TypeError, ValueError) as exc:
        raise RegistryError(f"{label} must be an integer, got {value!r}") from exc
    if client_id < 0:
        raise RegistryError(f"{label} cannot be negative: {client_id}")
    return client_id


def _ids_in_range(start: Any, end: Any, *, label: str) -> Iterable[int]:
    first = _coerce_client_id(start, label=f"{label}.start")
    last = _coerce_client_id(end, label=f"{label}.end")
    if last < first:
        raise RegistryError(f"{label}: invalid range {first}-{last}")
    return range(first, last + 1)


def _entry_allocation(
    client_id: int,
    system: str,
    entry: Any,
    *,
    pooled: bool,
) -> ClientAllocation:
    if not isinstance(entry, Mapping):
        raise RegistryError(f"{system}: client ID {client_id} entry must be an object")
    role = str(entry.get("role") or "").strip()
    access = str(entry.get("access") or "").strip()
    status = str(entry.get("status") or "").strip()
    if not role or not access or not status:
        raise RegistryError(
            f"{system}: client ID {client_id} needs role, access, and status"
        )
    return ClientAllocation(
        client_id=client_id,
        system=system,
        role=role,
        access=access,
        status=status,
        pooled=pooled,
    )


def validate_registry_data(
    raw: Any,
    *,
    source: str = "<registry>",
    expected_hash: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Validate schema, self-hash, allocation uniqueness, and retired overlap."""
    if not isinstance(raw, dict):
        raise RegistryError(f"{source}: registry root must be an object")
    if raw.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        raise RegistryError(f"{source}: unsupported schema_version")
    if not str(raw.get("registry_version") or "").strip():
        raise RegistryError(f"{source}: registry_version is required")
    if raw.get("registry_hash_algorithm") != REGISTRY_HASH_ALGORITHM:
        raise RegistryError(f"{source}: unsupported registry_hash_algorithm")

    digest = canonical_hash(raw)
    stored_hash = str(raw.get("registry_hash") or "")
    if stored_hash != digest:
        raise RegistryError(
            f"{source}: registry_hash mismatch; stored={stored_hash!r}, "
            f"computed={digest!r}"
        )
    if expected_hash is not None and digest != expected_hash:
        raise RegistryError(
            f"{source}: embedded registry hash mismatch; expected={expected_hash!r}, "
            f"computed={digest!r}"
        )

    systems = raw.get("systems")
    if not isinstance(systems, Mapping) or not systems:
        raise RegistryError(f"{source}: systems must be a non-empty object")

    claimed: dict[int, ClientAllocation] = {}
    for system, block in systems.items():
        if not isinstance(block, Mapping):
            raise RegistryError(f"{source}: system {system!r} must be an object")
        clients = block.get("clients") or {}
        if not isinstance(clients, Mapping):
            raise RegistryError(f"{source}: {system}.clients must be an object")
        for raw_id, entry in clients.items():
            client_id = _coerce_client_id(raw_id, label=f"{system} client ID")
            allocation = _entry_allocation(
                client_id, str(system), entry, pooled=False
            )
            if client_id in claimed:
                raise RegistryError(
                    f"client ID {client_id} belongs to both "
                    f"{claimed[client_id].system} and {system}"
                )
            claimed[client_id] = allocation

        pools = block.get("pools") or []
        if not isinstance(pools, list):
            raise RegistryError(f"{source}: {system}.pools must be an array")
        for index, pool in enumerate(pools):
            if not isinstance(pool, Mapping):
                raise RegistryError(f"{source}: {system}.pools[{index}] must be an object")
            for client_id in _ids_in_range(
                pool.get("start"),
                pool.get("end"),
                label=f"{system}.pools[{index}]",
            ):
                allocation = _entry_allocation(
                    client_id, str(system), pool, pooled=True
                )
                if client_id in claimed:
                    raise RegistryError(
                        f"client ID {client_id} belongs to both "
                        f"{claimed[client_id].system} and {system}.pools[{index}]"
                    )
                claimed[client_id] = allocation

    retired = retired_client_ids(raw)
    overlap = sorted(retired.intersection(claimed))
    if overlap:
        raise RegistryError(f"active/reserved IDs also marked retired: {overlap}")
    if SSI_SYSTEM not in systems:
        raise RegistryError(f"{source}: missing {SSI_SYSTEM} system allocation")

    return raw, digest


def load_registry(
    path: Path = REGISTRY_PATH,
    *,
    expected_hash: str | None = EXPECTED_REGISTRY_HASH,
) -> tuple[dict[str, Any], str]:
    """Read and validate a registry.

    Pass ``expected_hash=None`` only for tests or explicit mirror comparison.
    Production SSI callers use the default embedded hash pin.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError(f"{path}: cannot read valid JSON: {exc}") from exc
    return validate_registry_data(raw, source=str(path), expected_hash=expected_hash)


def retired_client_ids(raw: Mapping[str, Any]) -> set[int]:
    block = raw.get("retired_client_ids") or {}
    if not isinstance(block, Mapping):
        raise RegistryError("retired_client_ids must be an object")
    singles = block.get("singles") or []
    if not isinstance(singles, list):
        raise RegistryError("retired_client_ids.singles must be an array")
    retired = {
        _coerce_client_id(value, label="retired client ID")
        for value in singles
    }
    ranges = block.get("ranges") or []
    if not isinstance(ranges, list):
        raise RegistryError("retired_client_ids.ranges must be an array")
    for index, entry in enumerate(ranges):
        if not isinstance(entry, Mapping):
            raise RegistryError(f"retired_client_ids.ranges[{index}] must be an object")
        retired.update(
            _ids_in_range(
                entry.get("start"),
                entry.get("end"),
                label=f"retired_client_ids.ranges[{index}]",
            )
        )
    return retired


def allocation_index(raw: Mapping[str, Any]) -> dict[int, ClientAllocation]:
    """Return every fixed and pooled allocation after validating uniqueness."""
    # The self-hash is already checked by load_registry in production.  This
    # helper accepts an in-memory mapping so scanner tests can use fixtures.
    claimed: dict[int, ClientAllocation] = {}
    for system, block in (raw.get("systems") or {}).items():
        for raw_id, entry in (block.get("clients") or {}).items():
            client_id = _coerce_client_id(raw_id, label=f"{system} client ID")
            if client_id in claimed:
                raise RegistryError(f"duplicate client ID {client_id}")
            claimed[client_id] = _entry_allocation(
                client_id, str(system), entry, pooled=False
            )
        for index, pool in enumerate(block.get("pools") or []):
            for client_id in _ids_in_range(
                pool.get("start"),
                pool.get("end"),
                label=f"{system}.pools[{index}]",
            ):
                if client_id in claimed:
                    raise RegistryError(f"duplicate client ID {client_id}")
                claimed[client_id] = _entry_allocation(
                    client_id, str(system), pool, pooled=True
                )
    return claimed


def client_allocation(
    client_id: Any,
    raw: Mapping[str, Any] | None = None,
) -> ClientAllocation | None:
    if raw is None:
        raw, _ = load_registry()
    return allocation_index(raw).get(_coerce_client_id(client_id))


def assert_ssi_client_id(
    client_id: Any,
    role: str,
    *,
    readonly: bool | None = None,
    raw: Mapping[str, Any] | None = None,
) -> ClientAllocation:
    """Fail before a socket opens unless this is the active SSI ID for ``role``."""
    if raw is None:
        raw, _ = load_registry()
    numeric_id = _coerce_client_id(client_id)
    if numeric_id in retired_client_ids(raw):
        raise RegistryError(f"client ID {numeric_id} is retired and may not connect")
    allocation = allocation_index(raw).get(numeric_id)
    if allocation is None:
        raise RegistryError(f"client ID {numeric_id} is unregistered")
    if allocation.system != SSI_SYSTEM:
        raise RegistryError(
            f"client ID {numeric_id} belongs to {allocation.system}, not {SSI_SYSTEM}"
        )
    if not allocation.connectable:
        raise RegistryError(
            f"client ID {numeric_id} is {allocation.status}/{allocation.access} "
            "and may not connect"
        )
    if allocation.role != role:
        raise RegistryError(
            f"client ID {numeric_id} is registered for {allocation.role!r}, "
            f"not {role!r}"
        )
    if allocation.access == "read_only" and readonly is not True:
        raise RegistryError(
            f"client ID {numeric_id} requires an explicit readonly=True connection"
        )
    if readonly is False and allocation.access != "transmit":
        raise RegistryError(
            f"client ID {numeric_id} is {allocation.access}; transmitting connect refused"
        )
    return allocation


def validated_hub_bridge_client_id(client_id: Any) -> int:
    """Freeze one candidate as the sole transmitting hub client ID."""
    allocation = assert_ssi_client_id(
        client_id,
        SSI_HUB_BRIDGE_ROLE,
        readonly=False,
    )
    return allocation.client_id


def validated_legacy_sleeve_client_id(
    client_id: Any,
    *,
    role: str,
    readonly: bool,
) -> int:
    """Freeze one candidate as a role-scoped legacy sleeve client ID."""
    if role not in SSI_LEGACY_ROLES:
        raise RegistryError(
            f"{role!r} is not an approved legacy sleeve connection role"
        )
    allocation = assert_ssi_client_id(
        client_id,
        role,
        readonly=readonly,
    )
    return allocation.client_id


def ssi_client_id_for_role(role: str) -> int:
    raw, _ = load_registry()
    matches = [
        allocation
        for allocation in allocation_index(raw).values()
        if allocation.system == SSI_SYSTEM and allocation.role == role
    ]
    if len(matches) != 1:
        raise RegistryError(f"expected one SSI allocation for {role!r}, found {len(matches)}")
    allocation = matches[0]
    assert_ssi_client_id(
        allocation.client_id,
        role,
        readonly=True if allocation.access == "read_only" else False,
        raw=raw,
    )
    return allocation.client_id


def gateway_live_port() -> int:
    raw, _ = load_registry()
    try:
        port = int((raw.get("gateway") or {})["live_port"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RegistryError("gateway.live_port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise RegistryError(f"gateway.live_port is invalid: {port}")
    return port
