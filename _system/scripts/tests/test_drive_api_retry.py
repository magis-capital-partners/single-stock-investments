"""Drive 403 userRateLimitExceeded must back off. Permission and daily quota must not."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from drive_api_retry import (  # noqa: E402
    drive_retry_delay,
    execute_with_retry,
    is_drive_rate_limit,
    transient_drive_failure,
)


class _Resp(dict):
    def __init__(self, status: int, headers: dict | None = None):
        super().__init__(headers or {})
        self.status = status


class DriveError(Exception):
    def __init__(self, status: int, body: dict | str | bytes, headers: dict | None = None):
        if isinstance(body, dict):
            content = json.dumps(body).encode()
        elif isinstance(body, str):
            content = body.encode()
        else:
            content = body
        self.resp = _Resp(status, headers)
        self.content = content
        self.error_details = ""
        super().__init__(f"HttpError {status}")


def _error(status: int, reason: str, message: str, headers: dict | None = None) -> DriveError:
    return DriveError(
        status,
        {
            "error": {
                "errors": [{"domain": "usageLimits", "reason": reason, "message": message}],
                "code": status,
                "message": message,
            }
        },
        headers,
    )


class DriveApiRetryTests(unittest.TestCase):
    def test_letter_backfill_403_is_a_short_window_rate_limit(self):
        # Body shape from Letter Backfill run 38622851293, publish-dashboard.
        exc = _error(403, "userRateLimitExceeded", "User rate limit exceeded.")
        self.assertTrue(is_drive_rate_limit(exc))
        self.assertTrue(transient_drive_failure(exc))
        self.assertEqual(drive_retry_delay(exc, 1), 20)
        self.assertEqual(drive_retry_delay(exc, 2), 40)
        self.assertEqual(drive_retry_delay(exc, 3), 80)
        self.assertEqual(drive_retry_delay(exc, 4), 90)

    def test_rate_limit_message_without_machine_reason_still_retries(self):
        exc = DriveError(403, b"User rate limit exceeded.")
        self.assertTrue(transient_drive_failure(exc))
        self.assertEqual(drive_retry_delay(exc, 1), 20)

    def test_sharing_rate_limit_retries(self):
        exc = _error(403, "sharingRateLimitExceeded", "Sharing rate limit exceeded.")
        self.assertTrue(transient_drive_failure(exc))

    def test_permission_403_fails_immediately(self):
        exc = _error(
            403,
            "insufficientFilePermissions",
            "The user does not have sufficient permissions for this file.",
        )
        self.assertFalse(is_drive_rate_limit(exc))
        self.assertFalse(transient_drive_failure(exc))

    def test_daily_quota_403_is_not_retried(self):
        exc = _error(403, "dailyLimitExceeded", "Daily Limit Exceeded")
        self.assertFalse(is_drive_rate_limit(exc))
        self.assertFalse(transient_drive_failure(exc))

    def test_429_uses_the_rate_limit_wait_and_500_stays_short(self):
        rate = _error(429, "rateLimitExceeded", "Rate Limit Exceeded")
        server = DriveError(500, b"backend error")
        self.assertTrue(transient_drive_failure(rate))
        self.assertEqual(drive_retry_delay(rate, 1), 20)
        self.assertTrue(transient_drive_failure(server))
        self.assertFalse(is_drive_rate_limit(server))
        self.assertEqual(drive_retry_delay(server, 1), 1)
        self.assertEqual(drive_retry_delay(server, 2), 2)

    def test_read_timeout_is_still_transient(self):
        exc = TimeoutError("The read operation timed out")
        self.assertTrue(transient_drive_failure(exc))
        self.assertEqual(drive_retry_delay(exc, 1), 1)

    def test_retry_after_is_honored_and_capped(self):
        short = _error(403, "userRateLimitExceeded", "User rate limit exceeded.", {"retry-after": "45"})
        huge = _error(403, "userRateLimitExceeded", "User rate limit exceeded.", {"retry-after": "900"})
        self.assertEqual(drive_retry_delay(short, 1), 45)
        self.assertEqual(drive_retry_delay(huge, 1), 120)

    def test_execute_retries_the_letter_backfill_403_then_succeeds(self):
        sleeps: list[int] = []
        rate_limit = _error(403, "userRateLimitExceeded", "User rate limit exceeded.")

        class Request:
            def __init__(self):
                self.calls = 0

            def execute(self):
                self.calls += 1
                if self.calls == 1:
                    raise rate_limit
                return {"files": [{"id": "ok"}]}

        request = Request()
        result = execute_with_retry(request, label="index Shared Drive test", sleeper=sleeps.append)
        self.assertEqual(result, {"files": [{"id": "ok"}]})
        self.assertEqual(request.calls, 2)
        self.assertEqual(sleeps, [20])

    def test_execute_does_not_retry_a_permission_403(self):
        sleeps: list[int] = []
        denied = _error(403, "insufficientFilePermissions", "Insufficient permissions")

        class Request:
            def execute(self):
                raise denied

        with self.assertRaises(DriveError):
            execute_with_retry(Request(), label="preflight", sleeper=sleeps.append)
        self.assertEqual(sleeps, [])

    def test_execute_gives_up_after_the_attempt_budget(self):
        sleeps: list[int] = []
        rate_limit = _error(403, "userRateLimitExceeded", "User rate limit exceeded.")

        class Request:
            def __init__(self):
                self.calls = 0

            def execute(self):
                self.calls += 1
                raise rate_limit

        request = Request()
        with self.assertRaises(DriveError):
            execute_with_retry(
                request,
                label="index Shared Drive test",
                attempts=3,
                sleeper=sleeps.append,
            )
        self.assertEqual(request.calls, 3)
        self.assertEqual(sleeps, [20, 40])


if __name__ == "__main__":
    unittest.main()
