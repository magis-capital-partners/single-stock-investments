"""Identity producer: Box R candidate -> reviewed common-share IB contract.

What is automated (each value has one named public reference, cross-checked):

* CIK <-> ticker: SEC ``company_tickers_exchange.json`` must list the
  candidate's ticker under the candidate's CIK, on an exchange, not OTC.
* ticker -> conid, USD: IBKR's public short-stock file must hold exactly one
  USD row for the ticker. The executor re-proves it at entry: ``qualify()``
  refuses unless IB's own contract ID equals this one.
* common share (``CS``): Nasdaq Trader's symbol directory must name it a
  common/ordinary share, not a test issue, ETF, ADS, unit, warrant, right or
  preferred. Anything unnamed is ``UNRESOLVED``, never ``CS``.
* ``action_source_sha256``: copied from the candidate's own source list, so the
  executor binds the identity to the exact primary object Box R analysed.
* ``action_day``: the EARLIEST of Box R's clause-bound effective, legal and
  trading dates (a split can change the conid; earliest is the safe side of
  ``pre_action_exit``).

What stays a decision (``terms_mode``, owner's call; default ``owner_review``):

* ``ratio`` and ``conditions_resolved`` are terms of the corporate action. In
  ``owner_review`` they come only from an owner attestation bound to the
  candidate ID, CIK and primary-source hash (``reviews.py``). Without one the
  row is written with ``verified: false`` and the proposed terms, so the
  shadow refusal histogram names the missing review.
* ``box_r_auto`` accepts Box R's own extraction: ``status: scheduled``, both
  announcement and repeat checks pass, no implementation conditions, and a
  single-valued ``ratio`` in the candidate. Box R computes that ratio but does
  not yet export it in ``operations.json``; until it does, auto rows have no
  ratio and the executor refuses them.

Every row the producer writes is new dated evidence. A row whose content is
unchanged keeps its first ``at``, so ``at`` truthfully says when the mapping
became known and the 24 h expiry is not renewed by re-stamping.

Only the FIRST live record of an action is an opportunity (owner 2026-11-19):

* ``publication_clock`` must be Box R's ``timestamp``. A date-only SEC
  daily-index record (``date_only_next_day``), an undated archive catch-up
  (``unverified_archive``) or an ``unknown`` clock gets ``verified: false``.
  The executor's 15-minute window trusts ``published_at``, and a date-only
  clock can look fresh the next morning.
* A later scheduled record for the same issuer and action day is a duplicate
  publisher record. It gets no row and is reported, so it cannot open a
  second entry window. If either action day is unknown, the later record is
  treated as a possible duplicate.
* A labelled synthetic control (``synthetic_control`` or a
  ``synthetic-control:`` id) never gets an identity row.
"""

from __future__ import annotations

from datetime import timedelta
import re

from _system.trading.rs_paper_executor.safety import (
    PROTECTED_SYMBOLS,
    SafetyError,
    timestamp,
)

from .sources import ET_ZONE, IBKR_FTP_URL, SYMBOL, security_class
from .store import canonical, sha256_bytes

VERSION = "rs_identity_producer.v1"
TERMS_MODES = ("owner_review", "box_r_auto")
DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def _first_seen(candidate):
    try:
        return timestamp(candidate.get("first_seen_at")).isoformat()
    except SafetyError:
        return ""


def earliest_action_day(candidate):
    days = [
        candidate.get(k)
        for k in ("effective_date", "legal_effective_date", "trading_date")
        if isinstance(candidate.get(k), str) and DAY.fullmatch(candidate.get(k))
    ]
    return min(days) if days else None


CLOCK = re.compile(r"[a-z_]{1,40}")


def _cik(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def synthetic_control(candidate):
    return candidate.get("synthetic_control") is True or str(
        candidate.get("id", "")
    ).startswith("synthetic-control:")


def duplicate_records(candidates):
    """``{later id: (first id, basis)}`` for later scheduled records of an
    issuer's action already seen in an earlier record. All candidates are
    compared, including those older than the lookback, so a duplicate cannot
    reopen a window the first record already used."""
    by_issuer = {}
    for c in candidates:
        if c.get("status") != "scheduled" or synthetic_control(c):
            continue
        cik = _cik(c.get("cik"))
        if cik is not None:
            by_issuer.setdefault(cik, []).append(c)
    found = {}
    for rows in by_issuer.values():
        rows.sort(key=lambda c: (_first_seen(c) or "~", str(c.get("id"))))
        for i, later in enumerate(rows):
            day = earliest_action_day(later)
            for first in rows[:i]:
                other = earliest_action_day(first)
                if day is None or other is None or day == other:
                    basis = "same_action_day" if day is not None and day == other else "action_day_unknown"
                    found[later.get("id")] = (first.get("id"), basis)
                    break
    return found


def box_r_ratio(candidate):
    """Only a single-valued ratio Box R itself bound to the selected clause."""
    ratio = candidate.get("ratio")
    alternatives = candidate.get("ratio_candidates")
    if alternatives is not None and (
        not isinstance(alternatives, list) or len(set(map(str, alternatives))) != 1
    ):
        return None
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or ratio <= 1:
        return None
    return ratio


def _instrument(candidate, refs):
    """Cross-check one candidate against the three references. Returns
    (fields, refusals, references)."""
    ticker = candidate["ticker"]
    refusals, fields, used = [], {}, {}

    sec = refs.get("sec")
    if sec is None:
        refusals.append("sec_reference_unavailable")
    else:
        used["sec"] = {k: sec[k] for k in ("source_url", "source_sha256", "as_of")}
        rows = sec["by_ticker"].get(ticker, [])
        try:
            cik = int(str(candidate.get("cik")))
        except ValueError:
            cik = None
        match = [r for r in rows if r["cik"] == cik]
        if not match:
            refusals.append("sec_ticker_cik_mismatch")
        elif any((r["exchange"] or "").upper() in ("", "OTC") for r in match):
            refusals.append("sec_not_exchange_listed")

    listing_refs = refs.get("listings")
    if listing_refs is None:
        refusals.append("listing_directory_unavailable")
        cls, listing = "UNRESOLVED", None
    else:
        used["listings"] = [
            {k: d[k] for k in ("source_url", "source_sha256", "as_of")}
            for d in listing_refs
        ]
        found = [d["rows"][ticker] for d in listing_refs if ticker in d["rows"]]
        listing = found[0] if len(found) == 1 else None
        if len(found) > 1:
            refusals.append("ticker_listed_twice")
        cls = security_class(listing)
        if cls != "CS":
            refusals.append("security_class_" + cls.lower())
        if listing:
            fields["primary_exchange"] = listing["primary_exchange"]
            fields["security_name"] = listing["security_name"]
    fields["type"] = cls

    ibkr = refs.get("ibkr")
    if ibkr is None:
        refusals.append("ibkr_reference_unavailable")
    else:
        used["ibkr"] = {k: ibkr[k] for k in ("source_url", "source_sha256", "as_of")}
        rows = [r for r in ibkr["by_symbol"].get(ticker, []) if r["currency"] == "USD"]
        conids = {r["conid"] for r in rows}
        if len(conids) != 1:
            refusals.append(
                "ibkr_conid_missing" if not conids else "ibkr_conid_ambiguous"
            )
        else:
            row = rows[0]
            fields.update(conid=row["conid"], currency="USD", isin=row["isin"])
    fields.setdefault("currency", None)
    fields.setdefault("conid", None)
    return fields, refusals, used


def build_identities(operations, refs, reviews, now, *, terms_mode, previous=None,
                     lookback_seconds=3600):
    """Return ``(rows, report)``: rows keyed by ticker for the evidence file."""
    if terms_mode not in TERMS_MODES:
        raise SafetyError("unknown terms mode")
    previous = previous or {}
    rows, report = {}, []
    horizon = timestamp(now) - timedelta(seconds=lookback_seconds)
    candidates = sorted(
        (c for c in operations.get("candidates", []) if isinstance(c, dict)),
        key=_first_seen,
        reverse=True,  # one row per ticker: the newest candidate wins
    )
    duplicates = duplicate_records(candidates)
    for candidate in candidates:
        ticker = candidate.get("ticker")
        if not isinstance(ticker, str) or not SYMBOL.fullmatch(ticker):
            continue
        if ticker in rows or candidate.get("status") != "scheduled":
            continue
        try:
            if timestamp(candidate.get("first_seen_at")) < horizon:
                continue
        except SafetyError:
            continue
        sources = [
            s.get("sha256")
            for s in candidate.get("source_urls", [])
            if isinstance(s, dict) and re.fullmatch(r"[a-f0-9]{64}", s.get("sha256") or "")
        ]
        if not sources:
            report.append({"ticker": ticker, "skipped": "no_primary_source_hash"})
            continue
        if synthetic_control(candidate):
            report.append({"ticker": ticker, "skipped": "synthetic_control"})
            continue
        if candidate.get("id") in duplicates:
            first, basis = duplicates[candidate.get("id")]
            report.append({"ticker": ticker, "skipped": "duplicate_publisher_record",
                           "candidate_id": candidate.get("id"), "duplicate_of": first,
                           "basis": basis})
            continue  # the first record keeps the ticker's row

        fields, refusals, used = _instrument(candidate, refs)
        if ticker in PROTECTED_SYMBOLS:
            refusals.append("protected_symbol")
        clock = candidate.get("publication_clock")
        if clock != "timestamp":
            refusals.append("publication_clock_" + (
                clock if isinstance(clock, str) and CLOCK.fullmatch(clock) else "missing"))

        checks = candidate.get("checks", {})
        box_ok = (
            checks.get("announcement", {}).get("state") == "pass"
            and checks.get("repeat", {}).get("state") == "pass"
            and not candidate.get("implementation_conditions")
        )
        proposed = {
            "ratio": box_r_ratio(candidate),
            "action_day": earliest_action_day(candidate),
            "conditions_resolved": box_ok,
        }
        review = reviews.match(candidate) if reviews is not None else None
        if review is not None:
            terms, basis = (
                {
                    "ratio": review["ratio"],
                    "action_day": review["action_day"],
                    "conditions_resolved": review["conditions_resolved"] is True,
                },
                "owner_review",
            )
            if review.get("conid") not in (None, fields["conid"]):
                refusals.append("review_conid_differs_from_reference")
        elif terms_mode == "box_r_auto":
            terms, basis = proposed, "box_r_auto"
            if not box_ok:
                refusals.append("box_r_checks_or_conditions_open")
            if proposed["ratio"] is None:
                refusals.append("ratio_not_exported_by_box_r")
        else:
            terms, basis = (
                {"ratio": None, "action_day": None, "conditions_resolved": False},
                "awaiting_owner_review",
            )
            refusals.append("owner_review_required")
        if terms["action_day"] is None and basis != "awaiting_owner_review":
            refusals.append("action_day_unknown")

        verified = not refusals
        proof = {
            "producer": VERSION,
            "candidate_id": candidate.get("id"),
            "cik": candidate.get("cik"),
            "ticker": ticker,
            "references": used,
            "terms_basis": basis,
            "review": review,
        }
        proof_sha = sha256_bytes(canonical(proof).encode())
        row = {
            "cik": candidate.get("cik"),
            "conid": fields["conid"],
            "type": fields["type"],
            "currency": fields["currency"],
            "primary_exchange": fields.get("primary_exchange", ""),
            "isin": fields.get("isin"),
            "security_name": fields.get("security_name"),
            "verified": verified,
            "action_id": candidate.get("id"),
            "publication_clock": clock,
            "ratio": terms["ratio"],
            "action_day": terms["action_day"],
            "action_source_sha256": sources[0],
            "conditions_resolved": terms["conditions_resolved"] is True and verified,
            "terms_basis": basis,
            "proposed_terms": proposed,
            "refusals": sorted(set(refusals)),
            "source_url": IBKR_FTP_URL,
            "source_sha256": proof_sha,
            "proof": proof,
            "producer": VERSION,
        }
        stable = {k: v for k, v in row.items() if k not in ("proof", "source_sha256")}
        digest = sha256_bytes(canonical(stable).encode())
        old = previous.get(ticker)
        known = old.get("at") if old and old.get("content_sha256") == digest else now
        row["content_sha256"] = digest
        row["at"] = known
        expiry = timestamp(known) + timedelta(hours=24)
        if terms["action_day"]:
            from datetime import datetime

            start = datetime.fromisoformat(terms["action_day"]).replace(tzinfo=ET_ZONE)
            expiry = min(expiry, start)
        row["valid_until"] = expiry.isoformat()
        rows[ticker] = row
        report.append({"ticker": ticker, "verified": verified, "refusals": row["refusals"]})
    return rows, report
