#!/usr/bin/env python3
"""Promote independently approved forecast drafts into immutable sidecars."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from check_falsifier_history import promotion_errors
from epistemic_loop_controller import (STATE_REL, TERMINAL, _jsonl, _state_projection,
                                       _work_id, transition)
from falsifier_evidence_adapters import preflight_spec
from falsifier_specs import calibration_eligibility, read_json, spec_errors, spec_payload_hash

ROOT = Path(__file__).resolve().parents[2]
BLOCKED_STATE = "needs_semantic_review"
ACTOR = "falsifier-promoter"


def _component_fingerprint(component: dict) -> str:
    raw = json.dumps(component, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


_SECRET_PRAGMA = re.compile(r"\s*//\s*pragma:\s*allowlist secret\s*,?\s*$")


def _strip_secret_pragma(text: str) -> str:
    """Drop detect-secrets' inline pragma, which is not legal JSON.

    The cloud agents that author these drafts run a secret scanner that appends
    `// pragma: allowlist secret` to any line holding a long hex string -- and
    every draft carries `evidence_hash`, `epistemic_input_sha` and
    `contract_hash`. JSON has no comments, so the pragma made the file
    unparseable and the whole draft was blocked as "invalid draft JSON".

    On 2026-09-06 that was 8 of 19 drafts across ALB, ASML, AVGO, AXP and CEG,
    and because the promoter exits non-zero on blocked drafts the falsifier lane
    had not gone green in 104 hours -- long enough to fall out of its P3
    freshness window and turn the graph-invariants gate red on every open PR.
    Repairing the files fixes today; the writer is a cloud agent this repo does
    not control, so it would come straight back.

    Deliberately narrow: only this exact trailing pragma, only at end of line.
    Anything else that makes a draft unparseable must still be reported rather
    than quietly swallowed.
    """
    if "allowlist secret" not in text:
        return text
    return "\n".join(
        _SECRET_PRAGMA.sub("", line) if "allowlist secret" in line else line
        for line in text.splitlines()
    )


def _publish_work_id(ticker: str, draft: dict, path: Path) -> str:
    # The identity epistemic_loop_controller gives the draft's publish_forecast item.
    return _work_id("publish_forecast", ticker, str(draft.get("draft_id") or path.stem))


def _record_block(root: Path, path: Path, ticker: str, draft: dict, reasons: list[str]) -> None:
    """Leave the refusal where the next reader looks.

    On the draft (``promotion_blockers``), and as the state of its
    publish_forecast item in the epistemic work queue, which otherwise lists
    an approved draft that can never publish as plainly ``queued``. Both writes
    are idempotent, so a draft held back for weeks costs one diff, not one a run.
    """
    if (draft.get("promotion_blockers") or {}).get("reasons") != reasons:
        draft["promotion_blockers"] = {
            "reasons": reasons,
            "recorded_on": datetime.now(timezone.utc).date().isoformat(),
        }
        path.write_text(json.dumps(draft, indent=2) + "\n", encoding="utf-8")
    work_id = _publish_work_id(ticker, draft, path)
    reason = "promotion_blocked: " + "; ".join(reasons)
    prior = _state_projection(_jsonl(root / STATE_REL)).get(work_id) or {}
    if (prior.get("state"), prior.get("reason")) != (BLOCKED_STATE, reason):
        transition(root, work_id, BLOCKED_STATE, reason, ACTOR)


def _clear_block(root: Path, path: Path, ticker: str, draft: dict) -> None:
    work_id = _publish_work_id(ticker, draft, path)
    prior = _state_projection(_jsonl(root / STATE_REL)).get(work_id)
    if prior and prior.get("state") not in TERMINAL:
        transition(root, work_id, "succeeded", "promoted", ACTOR)


def promote(root: Path = ROOT, write: bool = True) -> dict:
    promoted, blocked = [], []
    # Each draft is judged by the rule check_falsifier_history.py applies after
    # this pass, against the sidecar as found (``committed``) plus whatever this
    # pass already promoted (``working``). A draft that would break that rule is
    # held back here. Before, it was appended, the history check rejected the
    # tree, and the lane died before its commit step: one CEG draft stamped
    # revision 1 while superseding a revision 1 did that to every run from
    # 2026-09-07, with every other approval stuck behind it.
    committed: dict[str, dict] = {}
    working: dict[str, dict] = {}
    for path in sorted(root.glob("*/research/falsifier_drafts/*.json")):
        try:
            draft = json.loads(_strip_secret_pragma(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            blocked.append({
                "draft": str(path.relative_to(root)).replace("\\", "/"),
                "reasons": [f"invalid draft JSON: {exc}"],
            })
            continue
        if draft.get("status") != "approved":
            continue
        ticker = path.parents[2].name.upper()
        spec = draft.get("spec") or {}
        contract = read_json(root / ticker / "research/valuation_contract.json")
        components = {str(row.get("component_id")): row
                      for row in contract.get("economic_ownership_map") or [] if isinstance(row, dict)}
        component = components.get(str(spec.get("component_id") or ""))
        reasons = list(spec_errors(spec))
        if not component or _component_fingerprint(component) != draft.get("component_fingerprint"):
            reasons.append("component fingerprint changed after authoring")
        eligible, eligibility_reason = calibration_eligibility(spec)
        if not eligible:
            reasons.append(f"not calibration eligible: {eligibility_reason}")
        preflight = preflight_spec(ticker, spec, root)
        if not preflight.get("ok"):
            reasons.append(f"source preflight failed: {preflight.get('reason')}")
        review = spec.get("review") or {}
        if review.get("reviewer") == spec.get("author"):
            reasons.append("reviewer must differ from author")
        sidecar_path = root / ticker / "research/falsifier_specs.json"
        if ticker not in working:
            working[ticker] = (read_json(sidecar_path)
                               or {"schema_version": "3.0", "ticker": ticker, "specs": []})
            committed[ticker] = json.loads(json.dumps(working[ticker]))
        sidecar = working[ticker]
        identities = {(str(row.get("spec_id")), int(row.get("spec_revision") or 1))
                      for row in sidecar.get("specs") or []}
        identity = (str(spec.get("spec_id")), int(spec.get("spec_revision") or 1))
        if identity not in identities:
            reasons.extend(f"immutable history: {error}" for error in
                           promotion_errors(ticker, committed[ticker], sidecar, spec))
        if reasons:
            blocked.append({"draft": str(path.relative_to(root)).replace("\\", "/"),
                            "reasons": reasons})
            if write:
                _record_block(root, path, ticker, draft, reasons)
            continue
        if identity not in identities:
            sidecar.setdefault("specs", []).append(spec)
        draft["status"] = "published"
        draft.pop("promotion_blockers", None)
        draft["published_at"] = datetime.now(timezone.utc).isoformat()
        draft["published_spec_hash"] = spec_payload_hash(spec)
        if write:
            sidecar_path.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
            path.write_text(json.dumps(draft, indent=2) + "\n", encoding="utf-8")
            _clear_block(root, path, ticker, draft)
        promoted.append({"ticker": ticker, "spec_id": spec.get("spec_id"),
                         "spec_hash": draft["published_spec_hash"]})
    return {"promoted": promoted, "blocked": blocked}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = promote(args.root, not args.dry_run)
    print(json.dumps({"promoted": len(result["promoted"]),
                      "blocked": len(result["blocked"]),
                      "blocked_details": result["blocked"]}, indent=2))
    # Held-back drafts are reported above, recorded on the draft and in the work
    # queue, and never fail the lane. Exiting 1 here let one bad draft stop every
    # other approval, resolution and control-plane refresh from landing: 104
    # hours over unparseable pragmas on 2026-09-06, then 17 days over CEG.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
