#!/usr/bin/env python3
"""Regression: automatic refresh must preserve third-party synthesis blends."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from valuation_synthesis import (  # noqa: E402
    _has_custom_synthesis_paths,
    _third_party_proxies_bull,
    compute_synthesis,
    resolve_synthesis_paths,
)


def test_vtrs_custom_paths_preserved() -> None:
    path = ROOT / "VTRS" / "research" / "valuation.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    before = copy.deepcopy(data.get("synthesis", {}).get("paths", []))
    assert _has_custom_synthesis_paths(before)
    resolved = resolve_synthesis_paths(data)
    assert any(p.get("id") == "rosen_operating_7yr" for p in resolved)
    assert any(abs((p.get("weight") or 0) - 0.4) < 0.01 for p in resolved if p.get("id") == "rosen_operating_7yr")
    compute_synthesis(data)
    assert data["synthesis"]["total_synthesis_pct"] == 13.61
    assert any(p.get("id") == "rosen_operating_7yr" for p in data["synthesis"]["paths"])


def test_cmsg_no_bull_proxy_after_refresh() -> None:
    path = ROOT / "CMSG" / "research" / "valuation.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    paths = data.get("synthesis", {}).get("paths", [])
    assert any(p.get("id") == "third_party_context" for p in paths)
    resolved = resolve_synthesis_paths(data)
    assert not _third_party_proxies_bull(resolved, data)
    assert any(p.get("id") == "blended_best_primary" for p in resolved)
    data["synthesis"] = {**(data.get("synthesis") or {}), "paths": resolved}
    compute_synthesis(data)
    total = data["synthesis"]["total_synthesis_pct"]
    bb = (data.get("estimates") or {}).get("blended_best", {}).get("return_pct")
    assert bb is not None
    assert total < 14.0, f"CMSG synthesis {total}% should stay near blended_best {bb}%, not bull-proxy ~15.6%"


def main() -> int:
    test_vtrs_custom_paths_preserved()
    test_cmsg_no_bull_proxy_after_refresh()
    print("OK test_third_party_synthesis_preserve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
