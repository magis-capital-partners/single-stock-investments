"""Exact missing fields: what in the evidence file blocks an entry, per name.

Read-only. It names every field of the evidence file that the executor's
checks would refuse: `inbox.proposals`, `engine.validate_signal`,
`Executor.eligibility` and `PaperIBKR.borrow`. Limits are the executor's
defaults: identity 24 h, borrow 1800 s, eligibility 30 s.

An empty ``blocked_by`` never means "enterable". The live gates are not
visible here: quote, shortable tick, WhatIf, reserve, cushion and book margin.
Borrow rows are public indications, never an allocation (owner 2026-11-19).
"""

from __future__ import annotations

from collections import Counter

from _system.trading.rs_paper_executor.safety import SafetyError, fresh, timestamp

IDENTITY_MAX, BORROW_MAX, ELIGIBILITY_MAX = 86400, 1800, 30
NOT_CHECKED_HERE = ("live_quote", "shortable_tick_89", "whatif_margin",
                    "spx_reserve_and_cushion", "book_margin", "symbol_claims")


def _age(row, now, limit, name, gaps):
    try:
        fresh(row.get("at"), now, limit)
    except SafetyError:
        gaps.append(name + ".stale_or_missing_at")


def _identity(row, now, gaps):
    if row.get("verified") is not True:
        gaps += ["identity." + r for r in (row.get("refusals") or ["unverified"])]
    expected = {"type": "CS", "currency": "USD", "conditions_resolved": True}
    for field, value in expected.items():
        if row.get(field) != value:
            gaps.append("identity." + field)
    for field in ("cik", "conid", "action_day", "action_source_sha256",
                  "source_url", "source_sha256"):
        if not row.get(field):
            gaps.append("identity." + field)
    ratio = row.get("ratio")
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or ratio <= 1.000001:
        gaps.append("identity.ratio")
    _age(row, now, IDENTITY_MAX, "identity", gaps)
    try:
        if timestamp(row.get("valid_until")) < timestamp(now):
            gaps.append("identity.valid_until_passed")
    except SafetyError:
        gaps.append("identity.valid_until")


def entry_gaps(evidence, now):
    borrow, eligibility = evidence.get("borrow", {}), evidence.get("eligibility", {})
    names = {}
    for ticker, row in sorted(evidence.get("identities", {}).items()):
        gaps = []
        _identity(row, now, gaps)
        conid = row.get("conid")
        loan = borrow.get(str(conid)) if conid else None
        if not loan:
            gaps.append("borrow.row_absent")
        else:
            _age(loan, now, BORROW_MAX, "borrow", gaps)
            if not isinstance(loan.get("apr"), (int, float)):
                gaps.append("borrow.apr")
            if not isinstance(loan.get("available_shares"), int):
                gaps.append("borrow.available_shares")
        proof = eligibility.get(str(conid)) if conid else None
        if not proof:
            gaps.append("eligibility.row_absent")
        else:
            _age(proof, now, ELIGIBILITY_MAX, "eligibility", gaps)
            if proof.get("halted") is True:
                gaps.append("eligibility.halted")
            if proof.get("ssr") is True:
                gaps.append("eligibility.ssr_restricted")
            if proof.get("complete") is not True or proof.get("source_verified") is not True:
                gaps += ["eligibility." + m for m in (proof.get("missing") or ["incomplete"])]
        names[ticker] = {
            "conid": conid,
            "blocked_by": sorted(set(gaps)),
            "borrow_is_indication_not_allocation": True,
            "not_checked_here": list(NOT_CHECKED_HERE),
        }
    tally = Counter(g for n in names.values() for g in n["blocked_by"])
    return {"names": names, "blocking_fields": dict(tally.most_common()),
            "unblocked_by_evidence": sorted(t for t, n in names.items() if not n["blocked_by"])}
