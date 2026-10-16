# Agent proposals inbox

Structured agent write-back lands in `inbox.jsonl` (created on first submit)
with status `pending_human_review`. Submit and inspect with:

```bash
python _system/scripts/agent_proposals.py submit proposal.json
python _system/scripts/agent_proposals.py list --ticker GOOGL
```

Proposals never edit `valuation.json`, thesis cards, or memory directly. A
human promotes approved items through `_system/reviews/approved/`. Schema:
`_system/schemas/agent_proposal.schema.json`.
