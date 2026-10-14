#!/usr/bin/env python3
"""Discover separations on EDGAR full-text search (fail-soft).

Searches Form 10 (10-12B), S-4 / 424B3 exchange-offer prospectuses, issuer
tender offers (SC TO-I) and 8-Ks for split-off, spin-off and clean-up
language, and appends accession-locked rows to
``_system/data/separations/separation_events.jsonl``.  Nothing here writes a
registry record: terms are locked by a human reading the filing, and the
event row stays ``unreviewed`` until a registry record names its accession.

Exit code is 0 even when EDGAR is down; ``discovery_state.json`` carries the
consecutive-failure streak that ``check_separation_universe.py`` turns into
``unhealthy``.  Daily cap and rate limiting match ``refresh_cvr_universe.py``.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from separation_common import (  # noqa: E402
    DISCOVERY_STATE_PATH,
    EVENTS_PATH,
    append_jsonl,
    latest_registry,
    load_jsonl,
    read_json,
    stable_id,
    today,
    utc_now,
    write_json,
)

UA = os.environ.get(
    "SEPARATION_SEC_USER_AGENT",
    "MagisResearchBot/1.0 (separation research; contact: research@magiscapital.com)",
)
EFTS = "https://efts.sec.gov/LATEST/search-index"
SLEEP_SEC = 0.5

# (query family, query, forms, kind hint)
SEARCHES: list[tuple[str, str, str, str]] = [
    ("split_off_exchange", '"exchange offer" "split-off"', "SC TO-I,SC TO-I/A,424B3", "split_off"),
    ("split_off_s4", '"exchange offer" "split-off" "upper limit" "odd-lot"', "S-4,S-4/A", "split_off"),
    ("split_off_upper_limit", '"exchange offer" "upper limit" "odd-lot" "proration"', "SC TO-I,SC TO-I/A,424B3,8-K", "split_off"),
    ("spin_off_form10", '"spin-off" "distribution ratio"', "10-12B,10-12B/A", "spin_off"),
    ("spin_off_info_statement", '"information statement" "when-issued"', "10-12B,10-12B/A,8-K", "spin_off"),
    ("clean_up", '"clean-up" "remaining interest" "spin-off"', "8-K,424B3", "clean_up_spin"),
    ("retained_stake", '"retained" "shares of common stock of" "debt-for-equity exchange"', "8-K", "retained_stake_sale"),
]

# Fund and trust issuer tenders that match the exchange-offer words but are
# not corporate separations.
_NOISE = re.compile(r"\b(fund|trust|lending|capital corp|capital investment|acquisition corp|merger corp|bdc|reit|portfolio|income|cayman)\b", re.I)


def http_get_json(url: str, timeout: int = 45) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "ignore"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def sec_search(query: str, *, days: int, forms: str, end: str | None = None) -> tuple[list[dict], bool]:
    end_s = end or today()
    start = date.fromordinal(date.fromisoformat(end_s).toordinal() - days).isoformat()
    params = urllib.parse.urlencode(
        {"q": query, "dateRange": "custom", "startdt": start, "enddt": end_s, "forms": forms}
    )
    payload = http_get_json(f"{EFTS}?{params}")
    if payload is None:
        return [], False
    hits = (payload.get("hits") or {}).get("hits") or []
    return [h for h in hits if isinstance(h, dict)], True


def _ticker_from_display(names: list[str] | None) -> str | None:
    for name in names or []:
        m = re.search(r"\(([A-Z][A-Z0-9.\-]{0,9})\)\s*\(CIK", str(name))
        if m:
            return m.group(1)
    return None


def _entity_from_display(names: list[str] | None) -> str | None:
    for name in names or []:
        return re.split(r"\s+\(", str(name), maxsplit=1)[0].strip() or None
    return None


def row_from_hit(hit: dict, *, family: str, kind_hint: str) -> dict | None:
    src = hit.get("_source") or hit
    form = str(src.get("form") or "")
    adsh = str(src.get("adsh") or "").strip()
    if not adsh:
        return None
    ciks = src.get("ciks") or []
    cik = str(ciks[0]).zfill(10) if ciks else None
    names = src.get("display_names") or []
    entity = _entity_from_display(names)
    if entity and _NOISE.search(entity) and kind_hint in {"split_off", "clean_up_spin"}:
        return None
    ticker = _ticker_from_display(names)
    doc_id = str(hit.get("_id") or "")
    doc = doc_id.split(":", 1)[1] if ":" in doc_id else ""
    url = None
    if cik:
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/{doc}".rstrip("/")
    return {
        "event_id": "sepev:" + stable_id(adsh, cik, family),
        "discovered_at": utc_now(),
        "cik": cik,
        "entity_name": entity,
        "ticker": ticker,
        "form": form or None,
        "accession": adsh,
        "filed": str(src.get("file_date") or "")[:10] or None,
        "url": url,
        "query_family": family,
        "kind_hint": kind_hint,
        "status": "unreviewed",
        "separation_id": None,
    }


def known_accessions() -> set[str]:
    out: set[str] = set()
    for rec in latest_registry():
        for src in rec.get("sources") or []:
            if src.get("accession"):
                out.add(str(src["accession"]))
    for row in load_jsonl(EVENTS_PATH):
        if row.get("accession"):
            out.add(str(row["accession"]))
    return out


def discover(*, days: int, limit: int, end: str | None = None) -> tuple[list[dict], int, int]:
    """Return (new rows, searches ok, searches attempted)."""
    seen = known_accessions()
    new_rows: list[dict] = []
    ok = 0
    for family, query, forms, kind_hint in SEARCHES:
        hits, success = sec_search(query, days=days, forms=forms, end=end)
        if success:
            ok += 1
        for hit in hits:
            if len(new_rows) >= limit:
                break
            row = row_from_hit(hit, family=family, kind_hint=kind_hint)
            if not row or row["accession"] in seen:
                continue
            seen.add(row["accession"])
            new_rows.append(row)
        time.sleep(SLEEP_SEC)
    return new_rows, ok, len(SEARCHES)


def update_state(*, ok: int, attempted: int, added: int) -> dict:
    state = read_json(DISCOVERY_STATE_PATH, {}) or {}
    failed = ok == 0 and attempted > 0
    streak = int(state.get("consecutive_failures") or 0)
    streak = streak + 1 if failed else 0
    state.update(
        {
            "last_run_at": utc_now(),
            "last_run_ok": not failed,
            "searches_ok": ok,
            "searches_attempted": attempted,
            "rows_added": added,
            "consecutive_failures": streak,
            "unhealthy": streak >= 3,
        }
    )
    if not failed:
        state["last_success_at"] = state["last_run_at"]
    write_json(DISCOVERY_STATE_PATH, state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover", action="store_true", help="run the EDGAR searches")
    parser.add_argument("--discover-days", type=int, default=14)
    parser.add_argument("--discover-limit", type=int, default=25)
    parser.add_argument("--end", default=None, help="search end date (YYYY-MM-DD), default today")
    args = parser.parse_args()
    if not args.discover:
        parser.print_help()
        return 0
    rows, ok, attempted = discover(days=args.discover_days, limit=args.discover_limit, end=args.end)
    added = append_jsonl(EVENTS_PATH, rows, identity_key="event_id")
    state = update_state(ok=ok, attempted=attempted, added=added)
    print(
        f"separation discovery: searches_ok={ok}/{attempted} new_events={added} "
        f"consecutive_failures={state['consecutive_failures']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
