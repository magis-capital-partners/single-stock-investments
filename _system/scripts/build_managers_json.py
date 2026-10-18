#!/usr/bin/env python3
"""Build the public manager registry.

The registry stores a manager name and an SEC CIK. It does not store where a
name came from. Pass --match-csv only as a local input. That file is not
written into the repo.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from ownership_common import (
    CIK_REGISTRY_PATH,
    FUNDS_PATH,
    ROOT,
    cik_padded,
    fetch_submissions,
    latest_13f_filings,
    load_json,
    slug,
)

OWNERSHIP = ROOT / "_system" / "reference" / "market-data" / "ownership"
MANAGERS_PATH = OWNERSHIP / "managers.json"
TRACKED_FUNDS = OWNERSHIP / "tracked_funds.json"
TRACKED_CIKS = OWNERSHIP / "tracked_fund_cik_registry.json"
HOLDERS_PATH = ROOT / "dashboard" / "data" / "overlap_holders.json"
REVIEW_PATH = OWNERSHIP / "13f" / "review_queue.json"


_GENERIC_TOKENS = {
    "capital",
    "management",
    "partners",
    "advisors",
    "advisor",
    "advisers",
    "investment",
    "investments",
    "asset",
    "assets",
    "funds",
    "fund",
    "group",
    "holdings",
    "holding",
    "financial",
    "equity",
    "global",
    "street",
    "hidden",
    "armor",
    "company",
    "associates",
    "new",
    "the",
    "and",
    "for",
    "ltd",
    "llc",
    "inc",
    "corp",
    "plc",
    "llp",
}


def distinctive_tokens(firm: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", firm or "")
    return [word.lower() for word in words if word.lower() not in _GENERIC_TOKENS]


def _compact(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _sec_body(value: str | None) -> str:
    """Drop a trailing SEC country tag such as '/ CAN'."""
    return re.sub(r"\s*/\s*[A-Za-z]{2,3}\s*$", "", value or "")


def names_are_the_same_firm(firm: str, sec_name: str) -> bool:
    """True when the public name and the SEC name are the same manager.

    A sleeve in parentheses does not have to appear in the legal name. A legal
    tail may follow the brand (Absoluto Partners Gestao de Recursos). A different
    rare word on the SEC side (Greenlight Masters) is a different firm.
    """
    body = _sec_body(sec_name)
    brand = _compact(public_display_name(firm, ""))
    compact = _compact(body)
    if brand and len(brand) >= 6 and compact.startswith(brand):
        return True
    firm_tokens = distinctive_tokens(firm)
    sec_tokens = distinctive_tokens(body)
    if not firm_tokens or not sec_tokens:
        return False
    if any(token not in firm_tokens for token in sec_tokens):
        return False
    strong = [token for token in firm_tokens if len(token) >= 4]
    if strong:
        return any(token in compact for token in strong)
    return len(firm_tokens) >= 2 and all(token in compact for token in firm_tokens)


def plausible_name_ok(firm: str, submissions_name: str, sec_name: str) -> bool:
    """A partial match is kept when the live SEC name is the filing name and the same firm."""
    if not names_match(submissions_name, sec_name):
        return False
    return names_are_the_same_firm(firm, submissions_name)


def clean_filer_name(value: str) -> str:
    return re.sub(r"\s*\(CIK\s*\d+\)\s*$", "", value or "", flags=re.IGNORECASE).strip()


def pick_efts_cik(firm: str, hits: list[dict]) -> tuple[str, str] | None:
    """One CIK, or nothing when the search hits two firms or the wrong legal name."""
    found: dict[str, str] = {}
    for hit in hits:
        source = hit.get("_source") or {}
        ciks = source.get("ciks") or []
        names = source.get("display_names") or []
        if not ciks or not names:
            continue
        name = clean_filer_name(str(names[0]))
        if not names_are_the_same_firm(firm, name):
            continue
        found[cik_padded(str(ciks[0]))] = name
    if len(found) != 1:
        return None
    return next(iter(found.items()))


def names_match(left: str | None, right: str | None) -> bool:
    a, b = _compact(left), _compact(right)
    return bool(a) and a == b


def public_display_name(firm: str, sec_name: str) -> str:
    text = re.sub(r"\s*\([^)]*\)", "", firm or "")
    text = re.sub(r"\s+", " ", text).strip(" /")
    return text or (sec_name or "").strip()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _record(
    manager_id: str,
    display_name: str,
    *,
    sec_name: str = "",
    cik: str | None = None,
    roles: list[str],
    book: str,
    verified_at: str | None = None,
    cik_history: list | None = None,
) -> dict:
    return {
        "manager_id": manager_id,
        "display_name": display_name,
        "sec_name": sec_name or "",
        "cik": cik_padded(cik) if cik else None,
        "roles": sorted(set(roles)),
        "book": book,
        "files_13f": bool(cik),
        "verified_at": verified_at,
        "cik_history": cik_history or [],
    }


def structural_managers() -> tuple[list[dict], set[str]]:
    """Tracked funds, biotech specialists, and the passive overlap list."""
    by_cik: dict[str, dict] = {}
    no_cik: list[dict] = []
    overlap_ids: set[str] = set()

    tracked_names = {
        row.get("fund_id"): row.get("fund") or row.get("fund_id")
        for row in (load_json(TRACKED_FUNDS, {}).get("funds") or [])
    }
    for manager_id, row in (load_json(TRACKED_CIKS, {}).get("funds") or {}).items():
        cik = cik_padded(row.get("cik") or "")
        if not cik or cik == "0000000000":
            continue
        by_cik[cik] = _record(
            manager_id,
            tracked_names.get(manager_id) or row.get("cik_name") or manager_id,
            sec_name=row.get("cik_name") or "",
            cik=cik,
            roles=["tracked"],
            book="full",
            verified_at=row.get("last_verified"),
        )

    specialist_names = {
        row.get("fund_id"): row.get("fund") or row.get("fund_id")
        for row in (load_json(FUNDS_PATH, {}).get("funds") or [])
    }
    specialist_ciks = load_json(CIK_REGISTRY_PATH, {}).get("funds") or {}
    for manager_id, display in specialist_names.items():
        row = specialist_ciks.get(manager_id) or {}
        cik = str(row.get("cik") or "").strip()
        if not cik:
            no_cik.append(
                _record(manager_id, display or manager_id, roles=["biotech"], book="none", verified_at=None)
            )
            continue
        padded = cik_padded(cik)
        current = by_cik.get(padded)
        if current is None:
            by_cik[padded] = _record(
                manager_id,
                display or row.get("cik_name") or manager_id,
                sec_name=row.get("cik_name") or "",
                cik=padded,
                roles=["biotech"],
                book="full",
                verified_at=row.get("last_verified"),
            )
            continue
        current["roles"] = sorted(set(current["roles"]) | {"biotech"})
        if "tracked" not in current["roles"]:
            current["book"] = "full"

    holders = load_json(HOLDERS_PATH, {}).get("advisers") or []
    for adviser in holders:
        manager_id = adviser.get("id")
        cik = str(adviser.get("cik") or "").strip()
        if not manager_id or not cik:
            continue
        overlap_ids.add(manager_id)
        padded = cik_padded(cik)
        history = adviser.get("cik_history") or []
        current = by_cik.get(padded)
        if current is None:
            by_cik[padded] = _record(
                manager_id,
                adviser.get("name") or adviser.get("sec_name") or manager_id,
                sec_name=adviser.get("sec_name") or "",
                cik=padded,
                roles=["overlap"],
                book="overlap_only",
                verified_at=_today() if adviser.get("latest_period") else None,
                cik_history=history,
            )
            continue
        current["roles"] = sorted(set(current["roles"]) | {"overlap"})
        current["cik_history"] = history or current.get("cik_history") or []
        if current["book"] != "full":
            current["book"] = "overlap_only"
    return list(by_cik.values()) + no_cik, overlap_ids


def verified_from_csv(path: Path, existing: list[dict]) -> tuple[list[dict], list[dict]]:
    """Keep a row only when the SEC submissions name matches the filing name."""
    by_cik = {row["cik"]: row for row in existing if row.get("cik")}
    overlap_ids = {row["manager_id"] for row in existing if "overlap" in (row.get("roles") or [])}
    used_ids = {row["manager_id"] for row in existing}
    accepted: list[dict] = []
    review: list[dict] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            high = raw.get("match_conf") == "high" and raw.get("review") == "likely_correct"
            plausible = raw.get("review") == "plausible_verify_cik"
            if not high and not plausible:
                continue
            cik = str(raw.get("cik") or "").strip()
            if not cik:
                continue
            padded = cik_padded(cik)
            try:
                submissions = fetch_submissions(padded)
            except Exception as error:  # noqa: BLE001 — one bad CIK should not stop the list
                review.append(
                    {
                        "display_name": public_display_name(raw.get("firm") or "", raw.get("sec_name") or ""),
                        "cik": padded,
                        "reason": "submissions_failed",
                        "detail": str(error),
                    }
                )
                continue
            found = submissions.get("name") or ""
            expected = raw.get("sec_name") or ""
            display = public_display_name(raw.get("firm") or "", found or expected)
            name_ok = names_match(found, expected) if high else plausible_name_ok(raw.get("firm") or "", found, expected)
            if not name_ok:
                review.append(
                    {
                        "display_name": display,
                        "cik": padded,
                        "reason": "sec_name_mismatch",
                        "sec_name_expected": expected,
                        "sec_name_found": found,
                    }
                )
                continue
            current = by_cik.get(padded)
            if current is not None:
                current["roles"] = sorted(set(current["roles"]) | {"active"})
                current["verified_at"] = current.get("verified_at") or _today()
                if not current.get("sec_name"):
                    current["sec_name"] = found
                if current["manager_id"] in overlap_ids and "tracked" not in current["roles"] and "biotech" not in current["roles"]:
                    current["book"] = "overlap_only"
                continue
            manager_id = slug(display)
            if manager_id in used_ids:
                manager_id = f"{manager_id}-{padded[-4:]}"
            used_ids.add(manager_id)
            record = _record(
                manager_id,
                display,
                sec_name=found,
                cik=padded,
                roles=["active"],
                book="full",
                verified_at=_today(),
            )
            by_cik[padded] = record
            accepted.append(record)
    return accepted, review


OPERATIONAL_REVIEW = (
    {
        "display_name": "MIG Capital",
        "cik": "0001425649",
        "reason": "latest_own_book_before_2026Q2",
        "latest_quarter": "2025Q4",
        "detail": "Later periods are 13F notices naming Exchange Traded Concepts, LLC. That other firm's whole book was not copied.",
    },
    {
        "display_name": "Greenstone Partners",
        "cik": "0001494311",
        "reason": "latest_own_book_before_2026Q2",
        "latest_quarter": "2025Q3",
        "detail": "The latest own filing restates the September 2025 book. No later holdings report is on the SEC feed.",
    },
)


def attach_operational_review(managers: list[dict], review: list[dict]) -> list[dict]:
    present = {row.get("cik") for row in managers}
    seen = {(item.get("cik"), item.get("reason")) for item in review}
    for item in OPERATIONAL_REVIEW:
        key = (item["cik"], item["reason"])
        if item["cik"] in present and key not in seen:
            review.append(dict(item))
            seen.add(key)
    return review


# Public filers a name search can confirm. Kept only when the SEC legal name is that firm.
EXTRA_PUBLIC_FIRMS = (
    "Pershing Square Capital Management",
    "Greenlight Capital",
    "BAMCO",
    "Baron Capital Management",
)


def efts_hits(firm: str) -> list[dict]:
    from urllib.parse import urlencode

    from sec_client import get_json

    query = urlencode({"q": f'"{firm}"', "forms": "13F-HR"})
    payload = get_json(f"https://efts.sec.gov/LATEST/search-index?{query}")
    return ((payload.get("hits") or {}).get("hits") or [])[:8]


def _add_verified_firm(firm: str, managers: list[dict], used_ids: set[str]) -> dict | None:
    picked = pick_efts_cik(firm, efts_hits(firm))
    if picked is None:
        print(f"unresolved: {firm}")
        return None
    cik, _display = picked
    if any(row.get("cik") == cik for row in managers):
        print(f"already listed: {firm}")
        return None
    try:
        submissions = fetch_submissions(cik)
    except Exception as error:  # noqa: BLE001
        print(f"unresolved: {firm} ({error})")
        return None
    found = submissions.get("name") or ""
    if not names_are_the_same_firm(firm, found):
        print(f"unresolved: {firm} live name {found}")
        return None
    filings = latest_13f_filings(cik, limit=8)
    if not any(row.get("form") in {"13F-HR", "13F-HR/A"} for row in filings):
        print(f"unresolved: {firm} has no holdings report")
        return None
    display = public_display_name(firm, found)
    manager_id = slug(display)
    if manager_id in used_ids:
        manager_id = f"{manager_id}-{cik[-4:]}"
    used_ids.add(manager_id)
    record = _record(
        manager_id,
        display,
        sec_name=found,
        cik=cik,
        roles=["active"],
        book="full",
        verified_at=_today(),
    )
    print(f"accepted: {display} {cik} {found}")
    return record


def resolve_unmatched(path: Path, managers: list[dict]) -> list[dict]:
    """Search EDGAR for working-file names that had no CIK. Commit the name and CIK only."""
    used_ids = {row["manager_id"] for row in managers}
    added: list[dict] = []
    firms: list[str] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            if raw.get("review") != "no_match_in_2026_13f_sets":
                continue
            firm = (raw.get("firm") or "").strip()
            if firm:
                firms.append(firm)
    for firm in EXTRA_PUBLIC_FIRMS:
        if firm not in firms:
            firms.append(firm)
    for firm in firms:
        if not names_are_the_same_firm(firm, firm):
            # No rare word to search on. "Armor" is stopped. A one-letter brand is not enough.
            continue
        record = _add_verified_firm(firm, managers + added, used_ids)
        if record:
            added.append(record)
    return added


def build(match_csv: Path | None) -> dict:
    managers, _overlap_ids = structural_managers()
    review: list[dict] = []
    if match_csv is not None:
        accepted, review = verified_from_csv(match_csv, managers)
        managers.extend(accepted)
    managers.sort(key=lambda row: row["manager_id"])
    return {
        "schema_version": 1,
        "in_base_irr": False,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "context": "Manager name and SEC CIK only. Holdings are context and are not an input to the base return.",
        "managers": managers,
        "review_count": len(review),
    }, review


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--match-csv", type=Path, default=None, help="Local working file. Not committed.")
    parser.add_argument("--resolve-unmatched", action="store_true", help="EDGAR name search for rows with no CIK.")
    parser.add_argument("--out", type=Path, default=MANAGERS_PATH)
    args = parser.parse_args()
    document, review = build(args.match_csv)
    if args.resolve_unmatched and args.match_csv is not None:
        added = resolve_unmatched(args.match_csv, document["managers"])
        document["managers"].extend(added)
        document["managers"].sort(key=lambda row: row["manager_id"])
    review = attach_operational_review(document["managers"], review)
    document["review_count"] = len(review)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_PATH.write_text(
        json.dumps({"schema_version": 1, "in_base_irr": False, "items": review}, indent=2) + "\n",
        encoding="utf-8",
    )
    books = {}
    for row in document["managers"]:
        books[row["book"]] = books.get(row["book"], 0) + 1
    print(f"Wrote {args.out} managers={len(document['managers'])} books={books} review={len(review)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
