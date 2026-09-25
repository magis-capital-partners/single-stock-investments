from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
import urllib.request
from typing import Any


# A signing domain is a lowercase tag. It must never start with a digit: the
# undomained message starts with the 10-digit timestamp, and that is what keeps
# a domained signature from ever validating as an undomained one (or the
# reverse) -- see verifyPortfolioHmac in dashboard/functions/_lib/portfolio.js.
_DOMAIN = re.compile(r"[a-z][a-z_]{0,31}")


def signed_headers(token: str, body: bytes, now: int | None = None, domain: str | None = None) -> dict[str, str]:
    """HMAC headers for the portfolio ingest routes.

    `domain` binds the signature to one purpose: the message becomes
    "<domain>\n<timestamp>\n<nonce>\n<body>". The read-only peek signs with
    domain "peek" because it reserves no nonce; without the tag, a captured peek
    was a valid, never-used signature on the claim routes for its whole 300s
    window. Every other route signs without a domain, exactly as before.
    """
    if domain is not None and not _DOMAIN.fullmatch(domain):
        raise ValueError("signing domain must be a short lowercase tag")
    timestamp = str(now or int(time.time()))
    nonce = secrets.token_hex(16)
    prefix = f"{domain}\n" if domain else ""
    signature = hmac.new(token.encode(), f"{prefix}{timestamp}\n{nonce}\n".encode() + body, hashlib.sha256).hexdigest()
    return {
        "content-type": "application/json",
        "user-agent": "MagisPortfolioHub/1.0",
        "x-portfolio-timestamp": timestamp,
        "x-portfolio-nonce": nonce,
        "x-portfolio-signature": signature,
    }


def publish_payload(url: str, token: str, payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    if not url.startswith("https://") and not url.startswith("http://127.0.0.1"):
        raise ValueError("portfolio ingest requires HTTPS outside loopback")
    if len(token) < 32:
        raise ValueError("portfolio ingest token must be at least 32 characters")
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    request = urllib.request.Request(url, data=body, method="POST", headers=signed_headers(token, body))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())
