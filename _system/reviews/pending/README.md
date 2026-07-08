# Pending review queues

Human review artifacts land here when auto-triage cannot resolve a row.

| Pattern | Source | Status |
|---------|--------|--------|
| `activist_triage_{date}.md` | `activist_triage.py` | **Active** — SEC/activist hits needing human review |
| `filing_insights_{date}.md` | `auto_resolve_filing_events.py` | **Active** — filing parser metrics needing human review |
| `event_triage_{date}.md` | `event_triage.py` | **Active** — borderline What changed events needing human review |
| `activist_scan_{date}.md` | legacy | **Obsolete** — delete if found; replaced by triage queue |

Portfolio scan summaries (not review queues) live in `_system/research/activist_scan_{date}.md`.
