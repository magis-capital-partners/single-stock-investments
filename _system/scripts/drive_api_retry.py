"""Retry policy for Google Drive API calls.

Drive's per-user limit is HTTP 403 with reason ``userRateLimitExceeded``
(or ``rateLimitExceeded``), not HTTP 429. Letter Backfill publish lists the
same shared drive twice back to back (filename index, then registry sync).
On 2026-10-14 run 38622851293 the second listing died on the first 403
because the sync script only retried 429 and 5xx.

A permission 403 and a daily-quota 403 (``dailyLimitExceeded``) are not
the same failure. Those still fail immediately.
"""
from __future__ import annotations

import time

TRANSIENT_DRIVE_STATUS = frozenset({429, 500, 502, 503, 504})

# Machine reasons and the sentences Drive puts in the 403 body.
# dailyLimitExceeded is absent on purpose: that is the daily quota.
_RATE_LIMIT_MARKERS = (
    "userratelimitexceeded",
    "ratelimitexceeded",
    "sharingratelimitexceeded",
    "user rate limit exceeded",
    "rate limit exceeded",
    "sharing rate limit exceeded",
)


def http_status(exc: BaseException) -> int | None:
    resp = getattr(exc, "resp", None)
    if resp is None:
        return None
    status = getattr(resp, "status", None)
    try:
        return int(status)
    except (TypeError, ValueError):
        return None


def error_text(exc: BaseException) -> str:
    parts: list[str] = []
    content = getattr(exc, "content", None)
    if isinstance(content, bytes):
        parts.append(content.decode("utf-8", errors="replace"))
    elif isinstance(content, str):
        parts.append(content)
    details = getattr(exc, "error_details", None)
    if details:
        parts.append(str(details))
    reason = getattr(exc, "reason", None)
    if isinstance(reason, str):
        parts.append(reason)
    return "\n".join(parts)


def is_drive_rate_limit(exc: BaseException) -> bool:
    """True for the short per-user window, including Drive's 403 form of it."""
    status = http_status(exc)
    if status == 429:
        return True
    if status != 403:
        return False
    text = error_text(exc).lower()
    compact = "".join(text.split())
    for marker in _RATE_LIMIT_MARKERS:
        if marker in text or marker.replace(" ", "") in compact:
            return True
    return False


def transient_drive_failure(exc: BaseException) -> bool:
    """429/5xx, Drive's 403 rate limit, and socket read timeouts.

    Not a missing file, a 404, a permission 403, or a daily quota 403.
    """
    status = http_status(exc)
    if status in TRANSIENT_DRIVE_STATUS:
        return True
    if status == 403 and is_drive_rate_limit(exc):
        return True
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    return isinstance(exc, OSError) and "timed out" in str(exc).lower()


def retry_after_seconds(exc: BaseException) -> float | None:
    resp = getattr(exc, "resp", None)
    getter = getattr(resp, "get", None)
    if not callable(getter):
        return None
    raw = getter("retry-after")
    if raw is None:
        raw = getter("Retry-After")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    return value


def drive_retry_delay(exc: BaseException, attempt: int) -> int:
    """Seconds to wait after a failed attempt. ``attempt`` is 1-based.

    Rate-limit waits start at 20s. Drive's per-user window is about 100
    seconds, and the old 1s/2s/4s schedule retried inside that window.
    """
    if attempt < 1:
        attempt = 1
    if is_drive_rate_limit(exc):
        computed = min(90, 20 * (2 ** (attempt - 1)))
    else:
        computed = min(30, 2 ** (attempt - 1))
    retry_after = retry_after_seconds(exc)
    if retry_after is not None:
        computed = max(computed, retry_after)
    return int(min(120, computed))


def execute_with_retry(request, *, label: str, attempts: int = 5, sleeper=time.sleep):
    """Retry only transient Drive API failures. The same request is reused.

    List and get requests have no media body, so ``execute()`` can run again
    after a 403. Uploads rebuild the request in the caller instead.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    for attempt in range(1, attempts + 1):
        try:
            return request.execute()
        except Exception as exc:
            if not transient_drive_failure(exc) or attempt == attempts:
                raise
            delay = drive_retry_delay(exc, attempt)
            status = http_status(exc)
            detail = f"HTTP {status}" if status else type(exc).__name__
            if is_drive_rate_limit(exc):
                detail += " rate limit"
            print(
                f"Transient Drive {detail} during {label}; "
                f"retrying in {delay}s ({attempt}/{attempts})...",
                flush=True,
            )
            sleeper(delay)
    raise RuntimeError("execute_with_retry fell through")  # pragma: no cover
