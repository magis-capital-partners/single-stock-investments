"""Read-only bridge from Box R's existing operations snapshot; no collector changes."""

from __future__ import annotations

import json
from pathlib import Path
import urllib.request
import urllib.parse

from .safety import SafetyError, fresh, timestamp


def read_json(path):
    data = Path(path).read_bytes()
    if len(data) > 16_000_000:
        raise SafetyError("snapshot exceeds input limit")
    return json.loads(data)


def read_https(url, token):
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "api.cloudflare.com"
        or parsed.username
        or parsed.fragment
        or parsed.query
        or parsed.port not in (None, 443)
        or not parsed.path.endswith(
            "/r2/buckets/single-stock-reverse-splits-evidence/objects/collector-dashboard/operations.json"
        )
    ):
        raise SafetyError(
            "only the configured private Cloudflare HTTPS read is supported"
        )

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise SafetyError("snapshot redirect forbidden")

    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
        data = response.read(16_000_001)
    if len(data) > 16_000_000:
        raise SafetyError("snapshot exceeds input limit")
    return json.loads(data)


def proposals(operations, evidence, now):
    fresh(operations.get("generated_at"), now, 120)
    result = []
    for candidate in operations.get("candidates", []):
        ticker = candidate.get("ticker")
        identity = evidence.get("identities", {}).get(ticker)
        if not identity or candidate.get("cik") != identity.get("cik"):
            continue
        if not identity.get("source_sha256") or not identity.get("source_url"):
            continue
        try:
            fresh(identity.get("at"), now, 86400)
            if timestamp(identity.get("valid_until")) < timestamp(now):
                continue
        except SafetyError:
            continue
        checks = candidate.get("checks", {})
        financials = candidate.get("financials", {})
        if (
            checks.get("announcement", {}).get("state") != "pass"
            or checks.get("repeat", {}).get("state") != "pass"
        ):
            continue
        if candidate.get("status") != "scheduled" or candidate.get(
            "implementation_conditions"
        ):
            continue
        sources = candidate.get("source_urls", [])
        if not sources:
            continue
        if identity.get("action_source_sha256") not in {
            x.get("sha256") for x in sources
        }:
            continue
        # Reviewed mapping is a new dated input; it never upgrades an old quote
        # or rewrites the saved candidate/decision in Box R's immutable ledger.
        result.append(
            {
                "id": candidate["id"],
                "action_id": identity.get("action_id", candidate["id"]),
                "cik": candidate["cik"],
                "ticker": ticker,
                "expected_conid": identity.get("conid"),
                "primary_exchange": identity.get("primary_exchange", ""),
                "status": candidate["status"],
                "ratio": identity.get("ratio"),
                "action_day": identity.get("action_day"),
                "instrument_type": identity.get("type"),
                "currency": identity.get("currency"),
                "identity_verified": identity.get("verified") is True,
                "conditions_resolved": identity.get("conditions_resolved") is True,
                "identity_known_at": identity.get("at"),
                "source_sha256": sources[0].get("sha256"),
                "published_at": candidate.get("published_at"),
                "first_seen_at": candidate.get("first_seen_at"),
                "terms_known_at": max(candidate.get("analyzed_at", ""), identity["at"]),
                "history_known_at": candidate.get("analyzed_at"),
                "financial_known_at": operations["generated_at"],
                "ordinal_min": candidate.get("ordinal_min"),
                "score": financials.get("score"),
                "signal_count": financials.get("signal_count"),
                "period": financials.get("period"),
            }
        )
    return result
