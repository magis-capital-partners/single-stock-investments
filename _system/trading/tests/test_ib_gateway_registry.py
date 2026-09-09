from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from _system.trading.ib_gateway_registry import (
    EXPECTED_REGISTRY_HASH,
    EXPECTED_REGISTRY_VERSION,
    REGISTRY_PATH,
    SSI_HUB_BRIDGE_ROLE,
    SSI_LEGACY_DREW_ROLE,
    SSI_LEGACY_MICHAEL_ROLE,
    SSI_LEGACY_SYNC_ROLE,
    RegistryError,
    allocation_index,
    assert_ssi_client_id,
    canonical_hash,
    load_registry,
    ssi_client_id_for_role,
    validated_hub_bridge_client_id,
    validated_legacy_sleeve_client_id,
)


def _raw_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _write_registry(tmp_path: Path, raw: dict, *, refresh_hash: bool = True) -> Path:
    payload = deepcopy(raw)
    if refresh_hash:
        payload["registry_hash"] = canonical_hash(payload)
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def test_embedded_registry_version_hash_and_host_facts_are_pinned():
    raw, digest = load_registry()
    assert raw["registry_version"] == EXPECTED_REGISTRY_VERSION
    assert digest == EXPECTED_REGISTRY_HASH
    assert raw["gateway"]["live_port"] == 7496
    assert raw["gateway"]["host_vcpu"] == 2
    client_zero = allocation_index(raw)[0]
    assert client_zero.system == "ls-algo"
    assert client_zero.access == "none"
    assert client_zero.status == "disabled_reserved"
    assert "auto-bind" in client_zero.role
    client_eighty_three = allocation_index(raw)[83]
    assert client_eighty_three.system == "ls-algo"
    assert client_eighty_three.access == "read_only"
    assert "interlock" in client_eighty_three.role
    etf_spy = allocation_index(raw)[50]
    assert etf_spy.system == "etf-0dte"
    assert etf_spy.access == "transmit"
    assert allocation_index(raw)[51].system == "etf-0dte"
    assert allocation_index(raw)[130].system == "etf-0dte"
    assert allocation_index(raw)[131].system == "etf-0dte"


def test_duplicate_allocation_fails_even_with_a_recomputed_hash(tmp_path):
    raw = _raw_registry()
    raw["systems"]["ls-algo"]["clients"]["91"] = {
        "role": "collision",
        "access": "transmit",
        "status": "active",
    }
    path = _write_registry(tmp_path, raw)
    with pytest.raises(RegistryError, match="belongs to both"):
        load_registry(path, expected_hash=None)


def test_bad_self_hash_fails(tmp_path):
    raw = _raw_registry()
    raw["gateway"]["host_vcpu"] = 99
    path = _write_registry(tmp_path, raw, refresh_hash=False)
    with pytest.raises(RegistryError, match="registry_hash mismatch"):
        load_registry(path, expected_hash=None)


def test_embedded_hash_pin_rejects_a_self_consistent_local_fork(tmp_path):
    raw = _raw_registry()
    raw["gateway"]["host_vcpu"] = 99
    path = _write_registry(tmp_path, raw)
    with pytest.raises(RegistryError, match="embedded registry hash mismatch"):
        load_registry(path, expected_hash=EXPECTED_REGISTRY_HASH)


@pytest.mark.parametrize("client_id", [0, 17, 50, 51, 77, 90, 130, 198, 100])
def test_foreign_ids_fail_ssi_validation(client_id):
    with pytest.raises(RegistryError, match="belongs to"):
        assert_ssi_client_id(client_id, SSI_HUB_BRIDGE_ROLE, readonly=False)


@pytest.mark.parametrize("client_id", [92, 197, 207, 551, 241, 1041])
def test_retired_ids_fail_ssi_validation(client_id):
    with pytest.raises(RegistryError, match="retired"):
        assert_ssi_client_id(client_id, SSI_HUB_BRIDGE_ROLE, readonly=False)


@pytest.mark.parametrize(
    ("client_id", "role", "status"),
    [
        (81, "retired portfolio collector", "disabled_reserved"),
        (82, "future master observer", "reserved"),
    ],
)
def test_disabled_and_reserved_ssi_ids_refuse_connection(client_id, role, status):
    with pytest.raises(RegistryError, match=status):
        assert_ssi_client_id(client_id, role, readonly=True)


def test_hub_bridge_is_exactly_client_91():
    assert ssi_client_id_for_role(SSI_HUB_BRIDGE_ROLE) == 91
    assert assert_ssi_client_id(
        91, SSI_HUB_BRIDGE_ROLE, readonly=False
    ).access == "transmit"
    with pytest.raises(RegistryError, match="not 'portfolio hub order bridge'"):
        assert_ssi_client_id(71, SSI_HUB_BRIDGE_ROLE, readonly=False)


def test_legacy_sleeve_ids_remain_role_specific():
    assert ssi_client_id_for_role(SSI_LEGACY_DREW_ROLE) == 71
    assert ssi_client_id_for_role(SSI_LEGACY_MICHAEL_ROLE) == 72
    assert ssi_client_id_for_role(SSI_LEGACY_SYNC_ROLE) == 73
    assert_ssi_client_id(71, SSI_LEGACY_DREW_ROLE, readonly=False)
    assert_ssi_client_id(72, SSI_LEGACY_MICHAEL_ROLE, readonly=False)
    assert_ssi_client_id(73, SSI_LEGACY_SYNC_ROLE, readonly=True)
    with pytest.raises(RegistryError, match="readonly=True"):
        assert_ssi_client_id(73, SSI_LEGACY_SYNC_ROLE, readonly=False)


def test_socket_validators_return_frozen_ids_and_reject_cross_role_use():
    assert validated_hub_bridge_client_id(91) == 91
    assert validated_legacy_sleeve_client_id(
        71, role=SSI_LEGACY_DREW_ROLE, readonly=False
    ) == 71
    with pytest.raises(RegistryError, match="not an approved legacy sleeve"):
        validated_legacy_sleeve_client_id(
            91, role=SSI_HUB_BRIDGE_ROLE, readonly=False
        )
    with pytest.raises(RegistryError, match="not 'legacy Drew sleeve'"):
        validated_legacy_sleeve_client_id(
            72, role=SSI_LEGACY_DREW_ROLE, readonly=False
        )
