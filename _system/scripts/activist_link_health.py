"""Cached HTTP liveness checks for activist report source links.

Results are cached in _system/reference/activist-reports/link_health.json with a
TTL so repeated feed builds are free. A link is only marked dead on a definitive
HTTP >= 400 response; network errors leave the link in an unknown state so
transient outages never drop feed rows.
"""
from __future__ import annotations

import json
import os
import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "_system" / "reference" / "activist-reports" / "link_health.json"
CACHE_TTL_DAYS = 7
TIMEOUT_SECONDS = 8
UA = "MarvinActivistScan contact@example.com"


def link_check_enabled() -> bool:
    return os.environ.get("ACTIVIST_LINK_CHECK", "1").strip().lower() not in ("0", "false", "no")


def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cache_fresh(entry: dict) -> bool:
    checked_at = entry.get("checked_at")
    if not checked_at:
        return False
    try:
        dt = datetime.strptime(checked_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return _now() - dt < timedelta(days=CACHE_TTL_DAYS)


def _request_status(url: str, method: str) -> int | None:
    req = Request(url, method=method, headers={"User-Agent": UA, "Accept": "*/*"})
    ctx = ssl.create_default_context()
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS, context=ctx) as resp:
            return int(resp.status or 200)
    except HTTPError as err:
        return int(err.code)
    except (URLError, TimeoutError, OSError, ValueError):
        return None


def check_url(url: str) -> dict:
    """Return {"ok": bool | None, "status": int | None}. ok=None means unknown."""
    status = _request_status(url, "HEAD")
    if status in (403, 405, 501):
        # Some publishers reject HEAD; retry with GET before declaring dead.
        status = _request_status(url, "GET")
    if status is None:
        return {"ok": None, "status": None}
    return {"ok": status < 400, "status": status}


def check_links(urls: list[str], *, enabled: bool | None = None) -> dict[str, dict]:
    """Check liveness of unique URLs using the on-disk cache."""
    if enabled is None:
        enabled = link_check_enabled()
    cache = _load_cache()
    results: dict[str, dict] = {}
    dirty = False
    for url in sorted({u for u in urls if u}):
        entry = cache.get(url) or {}
        if _cache_fresh(entry):
            results[url] = entry
            continue
        if not enabled:
            results[url] = {"ok": None, "status": None, "checked_at": None}
            continue
        checked = check_url(url)
        entry = {**checked, "checked_at": _now().strftime("%Y-%m-%dT%H:%M:%SZ")}
        cache[url] = entry
        results[url] = entry
        dirty = True
    if dirty:
        _save_cache(cache)
    return results
