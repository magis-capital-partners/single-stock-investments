"""Small HTTP helper. Adapters never open a socket during tests."""
from __future__ import annotations

import urllib.error
import urllib.request

USER_AGENT = "single-stock-investments research pipeline (contact: dag5wd@virginia.edu)"


def http_get(url: str, *, timeout: int = 60) -> tuple[int, bytes, str | None]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read(), None
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp else b""
        return int(exc.code), body, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, b"", str(exc)
