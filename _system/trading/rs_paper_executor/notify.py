"""Optional redacted Slack delivery from the local durable event outbox."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .safety import SafetyError, timestamp

KINDS = {
    "entry_halt", "submission_uncertain", "cover_trigger", "inbox_unavailable",
    "shadow_entry", "paper_order_submitted", "operator_resume",
}


def slack_post(url, body):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise SafetyError("alert redirect forbidden")

    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.build_opener(NoRedirect).open(request, timeout=5) as response:
        if response.status != 200:
            raise SafetyError("alert delivery unconfirmed")


def deliver_alerts(journal, url, now, post=slack_post):
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"hooks.slack.com", "hooks.slack-gov.com"}
        or not parsed.path.startswith("/services/")
        or parsed.username
        or parsed.query
        or parsed.fragment
        or parsed.port not in (None, 443)
    ):
        raise SafetyError("only an HTTPS Slack webhook is supported")
    last = journal.get("alert_delivery_attempt")
    if last and (timestamp(now) - timestamp(last)).total_seconds() < 60:
        return
    journal.set("alert_delivery_attempt", now)
    cursor = journal.get("alert_cursor", 0)
    rows = journal.db.execute(
        "SELECT id,at,kind FROM events WHERE id>?ORDER BY id LIMIT 200", (cursor,)
    ).fetchall()
    for row in rows:
        if row["kind"] in KINDS:
            # No free-form broker errors, account IDs, webhook URLs, source
            # payloads or credentials are ever included in the alert body.
            post(
                url,
                {
                    "text": "RS executor (" + getattr(journal, "prefix", "RSPAPER|").rstrip("|") + "): "
                    + row["kind"]
                    + " at "
                    + row["at"]
                    + ". Inspect the local status/journal."
                },
            )
        journal.set("alert_cursor", row["id"])
