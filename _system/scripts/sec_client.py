#!/usr/bin/env python3
"""Polite SEC EDGAR HTTP client.

Fair-access policy: at most 10 requests a second, with a declared User-Agent.
This client targets about 5 requests a second and backs off on 403 and 429.
"""
from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request

DEFAULT_SEC_USER_AGENT = "Magis Capital Research drew@magiscapitalpartners.com"
# 0.20s between requests is 5/s before the small jitter below.
MIN_INTERVAL_SEC = 0.20


def sec_user_agent() -> str:
    """Contact string SEC requires. Override with the SEC_USER_AGENT env var."""
    raw = (os.environ.get("SEC_USER_AGENT") or DEFAULT_SEC_USER_AGENT).strip()
    if not raw or "example.com" in raw:
        return DEFAULT_SEC_USER_AGENT
    return raw


class SecClient:
    def __init__(self, *, min_interval: float = MIN_INTERVAL_SEC, max_attempts: int = 4) -> None:
        self.min_interval = min_interval
        self.max_attempts = max_attempts
        self._last = 0.0

    def _pause(self) -> None:
        elapsed = time.monotonic() - self._last
        wait = self.min_interval - elapsed
        if wait > 0:
            time.sleep(wait)
        time.sleep(random.uniform(0.0, 0.04))
        self._last = time.monotonic()

    def get_bytes(self, url: str, *, accept: str | None = None, timeout: int = 120) -> bytes:
        headers = {"User-Agent": sec_user_agent()}
        if accept:
            headers["Accept"] = accept
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            self._pause()
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.read()
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code in {403, 429, 503} and attempt + 1 < self.max_attempts:
                    time.sleep(min(30.0, 2.0 ** attempt) + random.uniform(0.0, 0.5))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    time.sleep(min(15.0, 1.5 ** attempt))
                    continue
                raise
        if last_error:
            raise last_error
        raise RuntimeError(f"SEC fetch failed: {url}")

    def get_json(self, url: str, *, timeout: int = 90) -> dict:
        raw = self.get_bytes(url, accept="application/json", timeout=timeout)
        return json.loads(raw.decode("utf-8"))


_DEFAULT = SecClient()


def get_bytes(url: str, *, accept: str | None = None, timeout: int = 120) -> bytes:
    return _DEFAULT.get_bytes(url, accept=accept, timeout=timeout)


def get_json(url: str, *, timeout: int = 90) -> dict:
    return _DEFAULT.get_json(url, timeout=timeout)
