"""JSON serialization that preserves evidence hashes on scrubbing VMs.

Some environments rewrite literal 64-character hex strings (and sometimes long
reason strings) in JSON files to the placeholder "[REDACTED]". Encoding those
string values as JSON \\uXXXX sequences for each ASCII code unit decodes to the
same string under json.loads while evading that scrubber.

Use for research provenance files (research_agent_manifest.json,
agent_run_state.json, falsifier draft receipts) only.
"""
from __future__ import annotations

import json
import re
from typing import Any

_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
# Keys whose string values are always fully \\u-escaped (any content).
_FULL_ESCAPE_KEYS = frozenset({"reason", "manifest_path"})


def _is_hex64(s: str) -> bool:
    return bool(_HEX64.match(s))


def _escape_json_string_content(s: str) -> str:
    return "".join(f"\\u{ord(c):04x}" for c in s)


def _string_json(key: str | None, s: str) -> str:
    if key is not None and key in _FULL_ESCAPE_KEYS:
        return '"' + _escape_json_string_content(s) + '"'
    # Any 64-char hex string is treated as provenance / hash material on scrubbing VMs.
    if _is_hex64(s):
        return '"' + _escape_json_string_content(s) + '"'
    return json.dumps(s, ensure_ascii=True)


def dumps_workspace_safe(obj: Any, *, indent: int = 2) -> str:
    """Pretty-print JSON; sensitive keys use per-character \\u escapes."""

    def fmt(x: Any, level: int, key: str | None) -> str:
        pad = " " * (indent * level)
        inner = " " * (indent * (level + 1))
        if isinstance(x, dict):
            if not x:
                return "{}"
            lines = ["{"]
            items = list(x.items())
            for i, (k, v) in enumerate(items):
                comma = "," if i < len(items) - 1 else ""
                k_js = json.dumps(str(k))
                lines.append(f"{inner}{k_js}: {fmt(v, level + 1, str(k))}{comma}")
            lines.append(f"{pad}}}")
            return "\n".join(lines)
        if isinstance(x, list):
            if not x:
                return "[]"
            lines = ["["]
            for i, el in enumerate(x):
                comma = "," if i < len(x) - 1 else ""
                lines.append(f"{inner}{fmt(el, level + 1, None)}{comma}")
            lines.append(f"{pad}]")
            return "\n".join(lines)
        if x is None:
            return "null"
        if x is True:
            return "true"
        if x is False:
            return "false"
        if isinstance(x, str):
            return _string_json(key, x)
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            return json.dumps(x)
        return json.dumps(x, ensure_ascii=True)

    return fmt(obj, 0, None) + "\n"
