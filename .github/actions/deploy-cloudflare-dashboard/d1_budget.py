#!/usr/bin/env python3
"""Today's D1 usage for the whole account, from Cloudflare's GraphQL analytics.

The Workers Free plan allows 100k rows written and 5M rows read per UTC day,
account-wide. A deploy that starts its write stages above 70% of either limit
defers them until the quota resets, instead of discovering the limit mid-stage
(code 7500) with a partial retention pass behind it.

Analytics may lag real usage by a few minutes; the 30% headroom covers that
and one incremental seed. When the API token cannot read analytics, or the API
does not answer, the guard is UNAVAILABLE: the deploy warns once and proceeds,
and the quota error remains the backstop.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql"
WRITE_LIMIT = 100_000
READ_LIMIT = 5_000_000
WRITE_THRESHOLD = 70_000
READ_THRESHOLD = 3_500_000

QUERY = """
query D1DailyUsage($accountTag: string!, $date: Date!) {
  viewer {
    accounts(filter: { accountTag: $accountTag }) {
      d1AnalyticsAdaptiveGroups(limit: 10000, filter: { date_geq: $date, date_leq: $date }) {
        sum { rowsRead rowsWritten }
      }
    }
  }
}
""".strip()

# (status, body) for a POST of ``body`` with ``headers`` to ``url``.
Poster = Callable[[str, dict, bytes], "tuple[int, str]"]


@dataclass(frozen=True)
class Budget:
    available: bool
    rows_read: int = 0
    rows_written: int = 0
    reason: str = ""

    @property
    def over(self) -> bool:
        return self.available and (
            self.rows_written > WRITE_THRESHOLD or self.rows_read > READ_THRESHOLD
        )

    def describe(self) -> str:
        if not self.available:
            return f"budget guard unavailable: {self.reason}"
        return (
            f"today {self.rows_written:,} rows written (defer above {WRITE_THRESHOLD:,} "
            f"of {WRITE_LIMIT:,}), {self.rows_read:,} rows read (defer above "
            f"{READ_THRESHOLD:,} of {READ_LIMIT:,})"
        )


def _post(url: str, headers: dict, body: bytes) -> tuple[int, str]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed https URL
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def _unauthorized(messages: list[str]) -> bool:
    text = " ".join(messages).lower()
    return any(word in text for word in ("auth", "permission", "not authorized", "access", "forbidden"))


def check(account_id: str, token: str, date: str, post: Poster | None = None) -> Budget:
    """Rows read/written across all of the account's D1 databases on ``date`` (UTC)."""
    if not account_id or not token:
        return Budget(False, reason="CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN is not set")
    body = json.dumps({"query": QUERY, "variables": {"accountTag": account_id, "date": date}}).encode()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        status, text = (post or _post)(GRAPHQL_URL, headers, body)
    except (OSError, ValueError) as error:  # network, TLS, timeout
        return Budget(False, reason=f"analytics request failed ({type(error).__name__})")
    if status in (401, 403):
        return Budget(False, reason=f"HTTP {status}: the API token cannot read Account Analytics")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return Budget(False, reason=f"HTTP {status}: analytics returned non-JSON")
    errors = [str(item.get("message", item)) for item in (payload.get("errors") or []) if item]
    if errors:
        kind = "the API token cannot read Account Analytics" if _unauthorized(errors) else "analytics error"
        return Budget(False, reason=f"{kind}: {errors[0][:160]}")
    if status != 200:
        return Budget(False, reason=f"HTTP {status} from analytics")
    accounts = (((payload.get("data") or {}).get("viewer") or {}).get("accounts")) or []
    if not accounts:
        return Budget(False, reason="the API token cannot see this account's analytics")
    rows_read = rows_written = 0
    for group in accounts[0].get("d1AnalyticsAdaptiveGroups") or []:
        totals = group.get("sum") or {}
        rows_read += int(totals.get("rowsRead") or 0)
        rows_written += int(totals.get("rowsWritten") or 0)
    return Budget(True, rows_read=rows_read, rows_written=rows_written)
