"""Resumable public FINRA OTC action census, independent of today's tickers.

No price, borrow or execution permission is inferred from a corporate action.
Raw responses remain in the ignored workbench. Failed pages stay incomplete.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import re
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from .expansion import connect, job, location, utcnow
from .ledger import write_json, read_json

URL = "https://api.finra.org/data/group/otcMarket/name/otcDailyList"
SOURCE = "https://otce.finra.org/otce/dailyList"
PAGE_SIZE = 5000


def reverse_ratio(value):
    if value is None or not str(value).strip():
        return None
    text = str(value).strip().lower().replace(",", "")
    pair = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:-|:|/|for|to)\s*(\d+(?:\.\d+)?)", text)
    if pair:
        new, old = map(float, pair.groups())
        return new / old if 0 < new < old else None
    try:
        ratio = float(text)
    except ValueError:
        return None
    return ratio if math.isfinite(ratio) and 0 < ratio < 1 else None


def action(row, *, include_unresolved=False):
    raw_rate = row.get("reverseSplitRate")
    ratio = reverse_ratio(raw_rate)
    if ratio is None and not include_unresolved:
        return None
    ex = str(row.get("exDate") or "")[:10]
    published = str(row.get("calendarDay") or row.get("dailyListDatetime") or "")[:10]
    try:
        ex = date.fromisoformat(ex).isoformat()
        filed = date.fromisoformat(published)
    except ValueError:
        return None
    old, new = (
        str(row.get("oldSymbolCode") or "").strip(),
        str(row.get("newSymbolCode") or "").strip(),
    )
    if not old and not new:
        return None
    description = str(
        row.get("newSecurityDescription") or row.get("oldSecurityDescription") or ""
    )
    lower = description.lower()
    kind = (
        "fund"
        if any(s in lower for s in ("etf", "exchange traded", "fund"))
        else "preferred"
        if "preferred" in lower
        else "common"
        if any(s in lower for s in ("common", "ordinary"))
        else "unknown"
    )
    identifier = str(row.get("OTCDailyListID") or row.get("dividendMasterID") or "")
    # A public list's publication day is known; exact dissemination is not.
    at = datetime.combine(
        filed + timedelta(days=1), datetime.min.time(), ZoneInfo("America/New_York")
    ).isoformat()
    return {
        "event_id": "finra/"
        + (
            identifier
            or hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:20]
        ),
        "security_id": "finra_action/" + (identifier or old + "/" + ex),
        "ticker": old or new,
        "new_ticker": new or old,
        "ex_date": ex,
        "ratio": ratio,
        "available_at": at,
        "publication_date": published,
        "clock_basis": "next_day_after_finra_publication_day",
        "exchange_class": "otc",
        "security_type": kind,
        "company": description,
        "source": "finra_otc_daily_list",
        "source_url": SOURCE,
        "verification": "structured_corporate_action"
        if ratio is not None
        else "action_ratio_requires_review",
        "raw_reverse_rate": str(raw_rate),
        "terminal_outcome": None,
    }


def collect(cfg, start: date, end: date, *, offline=False, session=None):
    if end < start:
        raise ValueError("end precedes start")
    conn = connect(cfg)
    cache = location(cfg) / "otc_daily"
    cache.mkdir(exist_ok=True)
    vintage = cache / end.isoformat()
    vintage.mkdir(exist_ok=True)
    legacy_end = read_json(cache / "coverage.json", {}).get("end")
    session = session or requests.Session()
    session.headers.update(
        {"Accept": "application/json", "User-Agent": cfg.section("edgar")["user_agent"]}
    )
    seen, record_ids, actions, malformed, source_duplicates = set(), set(), {}, 0, 0
    unresolved = []
    offset, total, complete, error = 0, None, False, None
    try:
        while total is None or offset < total:
            path = vintage / f"{offset:09d}.json.gz"
            # Preserve the first migrated snapshot; subsequent dates get a
            # new census rather than presenting stale cached pages as fresh.
            legacy = cache / f"{offset:09d}.json.gz"
            if not path.exists() and legacy.exists() and end.isoformat() == legacy_end:
                import shutil

                shutil.copy2(legacy, path)
            try:
                if path.exists():
                    payload = json.loads(gzip.decompress(path.read_bytes()))
                else:
                    if offline:
                        raise ValueError("FINRA page not cached")
                    response = session.get(
                        URL,
                        params={"limit": PAGE_SIZE, "offset": offset},
                        timeout=(15, 60),
                    )
                    response.raise_for_status()
                    rows = response.json()
                    if not isinstance(rows, list):
                        raise ValueError("FINRA response is not a record list")
                    payload = {
                        "rows": rows,
                        "total": int(response.headers["record-total"]),
                        "offset": offset,
                        "fetched_at": utcnow(),
                        "sha256": hashlib.sha256(response.content).hexdigest(),
                    }
                    temporary = path.with_suffix(".part")
                    temporary.write_bytes(
                        gzip.compress(json.dumps(payload).encode(), mtime=0)
                    )
                    temporary.replace(path)
                    time.sleep(0.25)
                if total is not None and payload["total"] != total:
                    raise ValueError(
                        "FINRA total changed during paging; census requires a fresh consistent snapshot"
                    )
                total = payload["total"]
                rows = payload["rows"]
                if not rows and offset < total:
                    raise ValueError(
                        "FINRA page ended before the reported record total"
                    )
                for row in rows:
                    raw_id = str(
                        row.get("OTCDailyListID")
                        or hashlib.sha256(
                            json.dumps(row, sort_keys=True).encode()
                        ).hexdigest()
                    )
                    record_hash = hashlib.sha256(
                        json.dumps(row, sort_keys=True).encode()
                    ).hexdigest()
                    if raw_id in record_ids:
                        source_duplicates += 1
                    record_ids.add(raw_id)
                    if record_hash in seen:
                        continue
                    seen.add(record_hash)
                    parsed = action(row)
                    if row.get("reverseSplitRate") and parsed is None:
                        malformed += 1
                        unresolved.append(
                            {
                                "source_record_id": raw_id,
                                "ticker": row.get("oldSymbolCode")
                                or row.get("newSymbolCode"),
                                "ex_date": str(row.get("exDate") or "")[:10],
                                "raw_rate": row.get("reverseSplitRate"),
                                "reason": "ratio_or_date_requires_review",
                                "source_url": SOURCE,
                            }
                        )
                        parsed = action(row, include_unresolved=True)
                    if (
                        parsed
                        and start.isoformat() <= parsed["ex_date"] <= end.isoformat()
                    ):
                        # Repeated FINRA IDs with different contents remain
                        # separate source records for later adjudication.
                        if (
                            parsed["event_id"] in actions
                            and actions[parsed["event_id"]] != parsed
                        ):
                            parsed["event_id"] += "/" + record_hash[:12]
                        actions[parsed["event_id"]] = parsed
                job(
                    conn,
                    "otc_page",
                    str(offset),
                    "completed",
                    {
                        "rows": len(rows),
                        "reported_total": total,
                        "source_sha256": payload["sha256"],
                    },
                )
                offset += len(rows)
                print(
                    f"OTC records {offset:,}/{total:,}; reverse-split actions {len(actions):,}",
                    flush=True,
                )
            except (requests.RequestException, ValueError, KeyError) as exc:
                error = str(exc)[:300]
                job(conn, "otc_page", str(offset), "unavailable", {"error": error})
                break
        complete = bool(total is not None and offset >= total and error is None)
        result = {
            "schema_version": "otc_census.v1",
            "built_at": utcnow(),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "source_url": SOURCE,
            "reported_records": total,
            "unique_records": len(seen),
            "unique_record_ids": len(record_ids),
            "actions": sum(a["ratio"] is not None for a in actions.values()),
            "candidate_records": len(actions),
            "complete": complete,
            "unparsed_reverse_rates": malformed,
            "error": error,
            "unparsed_in_study_period": sum(
                a["ratio"] is None for a in actions.values()
            ),
            "repeated_source_record_ids": source_duplicates,
            "limits": [
                "No OTC prices or historical borrow are supplied by this action list",
                "Publication-day clock is conservative; exact dissemination is not established",
            ],
        }
        write_json(
            cache / "actions.json",
            sorted(actions.values(), key=lambda a: (a["ex_date"], a["event_id"])),
        )
        write_json(cache / "coverage.json", result)
        write_json(cache / "unresolved.json", unresolved)
        job(
            conn,
            "otc_census",
            f"{start}/{end}",
            "completed" if complete else "incomplete",
            result,
        )
        return result
    finally:
        conn.close()
