"""Live transmission arm. A validated live endpoint alone runs in shadow.

Shadow means: every gate, quote, borrow, claim check and the exact-stock WhatIf
run against the real account, and the would-be entry is journalled as an event,
but no SELL is transmitted. Covers of positions the journal already holds are
never shadowed: an exit must always be possible.

The arm is an owner-written JSON file bound to the account, client ID and the
policy hash, with an expiry. Any policy change disarms it.
"""

from __future__ import annotations

import json
from pathlib import Path

from .safety import SafetyError, timestamp

SCHEMA = "rs_live_arm.v1"


def arm_state(path, endpoint, policy, now):
    """Return (armed, reason). Paper endpoints transmit to paper unconditionally."""
    if not endpoint.live:
        return True, "paper"
    if not path:
        return False, "no arm file configured"
    p = Path(path)
    if not p.exists():
        return False, "arm file absent"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        checks = (
            (data.get("schema") == SCHEMA, "arm schema mismatch"),
            (data.get("account") == endpoint.account, "arm account mismatch"),
            (data.get("client_id") == endpoint.client_id, "arm client mismatch"),
            (data.get("policy_hash") == policy.digest, "arm policy hash mismatch"),
            (bool(str(data.get("armed_by") or "").strip()), "arm has no owner"),
        )
        for ok, reason in checks:
            if not ok:
                return False, reason
        if timestamp(data.get("valid_until")) <= timestamp(now):
            return False, "arm expired"
    except (OSError, ValueError, SafetyError) as exc:
        return False, "arm unreadable: " + type(exc).__name__
    return True, "armed"
