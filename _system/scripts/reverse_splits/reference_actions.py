"""Optional Massive structured split census inside the documented free window.

Uses an existing key only. Never purchases, upgrades or requests older data
than the public Basic entitlement. Access errors remain coverage gaps.
https://massive.com/docs/rest/stocks/corporate-actions/splits
"""

from __future__ import annotations
import gzip
import hashlib
import json
import os
import time
from datetime import date, timedelta
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

import requests
from .expansion import location, utcnow
from .ledger import write_json, read_json

URL = "https://api.massive.com/stocks/v1/splits"


def collect(cfg, start, end, *, offline=False, key=None, session=None):
    year = end.year - 2
    try:
        floor = end.replace(year=year) + timedelta(days=1)
    except ValueError:
        floor = date(year, 3, 1)
    first = max(start, floor)
    root = location(cfg) / "reference_actions"
    root.mkdir(exist_ok=True)
    key = (
        key
        or os.environ.get("MASSIVE_API_KEY")
        or os.environ.get("POLYGON_API_KEY")
        or os.environ.get("POLYGON_IO_API_KEY")
    )
    session = session or requests.Session()
    if key:
        session.headers.update({"Authorization": "Bearer " + key})
    url = (
        URL
        + "?"
        + urlencode(
            {
                "execution_date.gte": first.isoformat(),
                "execution_date.lte": end.isoformat(),
                "adjustment_type": "reverse_split",
                "sort": "execution_date.asc",
                "limit": 1000,
            }
        )
    )
    actions = {
        r["event_id"].removeprefix("reference/"): r
        for r in read_json(root / "actions.json", [])
    }
    visited = set()
    error = None
    complete = False
    while url:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "api.massive.com":
            error = "Unexpected pagination host"
            break
        # Cursor links may embed authentication. Strip it before cache keys,
        # manifests or logging; the key is carried only in the HTTP header.
        url = urlunparse(
            parsed._replace(
                query=urlencode(
                    [
                        (k, v)
                        for k, v in parse_qsl(parsed.query)
                        if k.lower() != "apikey"
                    ]
                )
            )
        )
        if url in visited:
            error = "Repeated pagination cursor"
            break
        visited.add(url)
        path = root / (hashlib.sha256(url.encode()).hexdigest() + ".json.gz")
        if path.exists():
            body = json.loads(gzip.decompress(path.read_bytes()))
        else:
            if offline or not key:
                error = "reference_key_or_cached_page_unavailable"
                break
            response = session.get(url, timeout=(15, 45))
            if response.status_code != 200:
                error = f"reference_source_HTTP_{response.status_code}"
                break
            body = response.json()
            if not isinstance(body.get("results", []), list):
                error = "Unexpected reference response"
                break
            path.write_bytes(gzip.compress(json.dumps(body).encode(), mtime=0))
            # Basic permits five requests per minute. This collector is
            # deliberately paced even when the existing key has a paid plan.
            time.sleep(12.1)
        for r in body.get("results", []):
            try:
                ratio = float(r["split_to"]) / float(r["split_from"])
                ex = date.fromisoformat(r["execution_date"]).isoformat()
                ticker = str(r["ticker"])
                if not 0 < ratio < 1 or not first.isoformat() <= ex <= end.isoformat():
                    continue
            except (KeyError, ValueError, ZeroDivisionError):
                continue
            identity = str(
                r.get("id")
                or hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()[
                    :24
                ]
            )
            actions[identity] = {
                "event_id": "reference/" + identity,
                "ticker": ticker,
                "ex_date": ex,
                "ratio": ratio,
                "verification": "structured_corporate_action",
                "security_id": "unresolved/" + ticker,
                "exchange_class": "unknown",
                "security_type": "unknown",
                "source": "massive_structured_split",
                "source_url": "https://massive.com/docs/rest/stocks/corporate-actions/splits",
                "available_at": None,
                "clock_basis": "historical_action_record_not_a_dated_announcement",
            }
        url = body.get("next_url")
        if not url:
            complete = True
    result = {
        "built_at": utcnow(),
        "requested_start": start.isoformat(),
        "served_start": first.isoformat(),
        "end": end.isoformat(),
        "actions": len(actions),
        "pages": len(visited),
        "complete_within_declared_free_window": complete,
        "error": error,
        "older_history": "not_requested_without_an_entitlement_decision",
        "announcement_clock": "not_established",
    }
    write_json(root / "actions.json", list(actions.values()))
    write_json(root / "coverage.json", result)
    return result
