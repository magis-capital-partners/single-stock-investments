"""CI shell scripts stay plain ASCII.

A round trip through a cp1252 console turned an em dash into U+FFFD in
ci_resolve_checkout_ref.sh and test_ci_checkout_workspace.sh, and the damage
was committed. ASCII-only files cannot be damaged that way.
"""
from __future__ import annotations

from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ASCII_ONLY = (
    "ci_checkout_workspace.sh",
    "ci_resolve_checkout_ref.sh",
    "test_ci_checkout_workspace.sh",
)


def test_ci_checkout_scripts_are_plain_ascii():
    for name in ASCII_ONLY:
        data = (SCRIPTS / name).read_bytes()
        bad = [number for number, line in enumerate(data.split(b"\n"), start=1) if any(b > 127 for b in line)]
        assert not bad, f"{name}: non-ASCII bytes on line(s) {bad}"
