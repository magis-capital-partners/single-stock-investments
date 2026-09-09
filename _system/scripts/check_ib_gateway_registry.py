#!/usr/bin/env python3
"""Validate the shared IB Gateway client-ID registry and mirrored copies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _system.trading.ib_gateway_registry import (  # noqa: E402
    EXPECTED_REGISTRY_HASH,
    REGISTRY_PATH,
    RegistryError,
    canonical_hash,
    load_registry,
)


DEFAULT_REGISTRY = REPO_ROOT / "_system" / "trading" / "ib_gateway_client_registry.v1.json"
DEFAULT_MIRRORS = (
    REPO_ROOT.parent.parent / "options-trading" / "spx-0dte" / "config"
    / "ib_gateway_client_registry.v1.json",
    REPO_ROOT.parent.parent / "quant" / "ls-algo" / "config"
    / "ib_gateway_client_registry.v1.json",
)


def validate_registry(
    path: Path,
    *,
    expected_hash: str | None = None,
) -> tuple[dict, str]:
    """Compatibility wrapper around the reusable runtime validator."""
    return load_registry(path, expected_hash=expected_hash)


def validate_mirrors(
    primary: Path,
    mirrors: Iterable[Path],
    *,
    expected_hash: str | None = None,
) -> str:
    primary_raw, registry_hash = validate_registry(
        primary, expected_hash=expected_hash
    )
    expected_version = primary_raw["registry_version"]
    for mirror in mirrors:
        mirror_raw, mirror_hash = validate_registry(mirror)
        if mirror_raw["registry_version"] != expected_version or mirror_hash != registry_hash:
            raise RegistryError(
                f"{mirror}: shared registry differs from {primary}; "
                f"expected version/hash {expected_version}/{registry_hash}, got "
                f"{mirror_raw['registry_version']}/{mirror_hash}"
            )
    return registry_hash


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="primary registry JSON",
    )
    parser.add_argument(
        "--mirror",
        action="append",
        type=Path,
        default=None,
        help="mirrored registry to compare (repeatable)",
    )
    parser.add_argument(
        "--print-computed-hash",
        action="store_true",
        help="print the canonical hash even when the stored hash is stale",
    )
    parser.add_argument(
        "--skip-mirrors",
        action="store_true",
        help="validate only the primary copy",
    )
    parser.add_argument(
        "--expected-hash",
        default=None,
        help="pin the primary registry to this canonical hash",
    )
    parser.add_argument(
        "--scan-ssi",
        action="store_true",
        help="also scan active SSI code/config for unsafe Gateway IDs and calls",
    )
    parser.add_argument(
        "--scan-root",
        action="append",
        type=Path,
        default=None,
        help="scanner root (repeatable; defaults to _system/trading)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.print_computed_hash:
        raw = json.loads(args.registry.read_text(encoding="utf-8"))
        print(canonical_hash(raw))
        return 0

    expected_hash = args.expected_hash
    if expected_hash is None and args.registry.resolve() == REGISTRY_PATH.resolve():
        expected_hash = EXPECTED_REGISTRY_HASH

    mirrors = tuple(args.mirror or DEFAULT_MIRRORS)
    if args.skip_mirrors:
        raw, digest = validate_registry(args.registry, expected_hash=expected_hash)
    else:
        digest = validate_mirrors(
            args.registry, mirrors, expected_hash=expected_hash
        )
        raw = json.loads(args.registry.read_text(encoding="utf-8"))
    print(f"OK {raw['registry_version']} sha256:{digest}")

    if args.scan_ssi:
        from _system.scripts.scan_ib_gateway_clients import (  # noqa: PLC0415
            format_violations,
            scan_paths,
        )

        roots = tuple(args.scan_root or (REPO_ROOT / "_system" / "trading",))
        violations = scan_paths(roots, registry=raw)
        if violations:
            print(format_violations(violations), file=sys.stderr)
            return 1
        print(f"OK SSI Gateway scanner ({len(roots)} root(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
