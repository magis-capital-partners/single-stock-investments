"""Owner attestations of corporate-action terms, append-only.

One JSON object per line (``rs_identity_review.v1``)::

    {"schema": "rs_identity_review.v1", "candidate_id": "...", "cik": "...",
     "ticker": "ABC", "action_source_sha256": "<64 hex>", "ratio": 10,
     "action_day": "2026-11-25", "conditions_resolved": true,
     "conid": 123 (optional), "reviewed_by": "<initials>",
     "reviewed_at": "<UTC ISO>"}

A review is bound to the candidate ID, its CIK and one of its primary-source
hashes. If Box R later re-sources the candidate so none of its hashes match,
the review no longer applies and a new one is needed. The newest matching line
wins; lines are never edited or deleted.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re

from _system.trading.rs_paper_executor.safety import SafetyError, number, timestamp

from .sources import SYMBOL

SCHEMA = "rs_identity_review.v1"


def validate(row):
    if not isinstance(row, dict) or row.get("schema") != SCHEMA:
        raise SafetyError("review schema mismatch")
    if not isinstance(row.get("candidate_id"), str) or not row["candidate_id"]:
        raise SafetyError("review candidate ID required")
    if not re.fullmatch(r"\d{1,10}", str(row.get("cik", ""))):
        raise SafetyError("review CIK required")
    if not SYMBOL.fullmatch(row.get("ticker") or ""):
        raise SafetyError("review ticker invalid")
    if not re.fullmatch(r"[a-f0-9]{64}", row.get("action_source_sha256") or ""):
        raise SafetyError("review must bind a primary-source hash")
    number(row.get("ratio"), "review ratio", minimum=1.000001)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row.get("action_day") or ""):
        raise SafetyError("review action day required")
    if row.get("conditions_resolved") is not True:
        raise SafetyError("a review attests resolved conditions or is not written")
    if row.get("conid") is not None and (
        isinstance(row["conid"], bool) or not isinstance(row["conid"], int) or row["conid"] < 1
    ):
        raise SafetyError("review conid invalid")
    if not isinstance(row.get("reviewed_by"), str) or not row["reviewed_by"].strip():
        raise SafetyError("reviewer required")
    timestamp(row.get("reviewed_at"))
    return row


class Reviews:
    def __init__(self, rows):
        self.rows = rows

    @classmethod
    def load(cls, path):
        if path is None or not Path(path).exists():
            return cls([])
        rows = []
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(validate(json.loads(line)))
            except (SafetyError, ValueError):
                # A malformed line attests nothing; it never blocks other lines.
                continue
        return cls(rows)

    def match(self, candidate):
        hashes = {
            s.get("sha256") for s in candidate.get("source_urls", []) if isinstance(s, dict)
        }
        matches = [
            r
            for r in self.rows
            if r["candidate_id"] == candidate.get("id")
            and str(r["cik"]) == str(candidate.get("cik"))
            and r["ticker"] == candidate.get("ticker")
            and r["action_source_sha256"] in hashes
        ]
        if not matches:
            return None
        return max(matches, key=lambda r: timestamp(r["reviewed_at"]))


def append(path, row):
    validate(row)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return row
