## Belief format

One bullet, one belief, ending in `— \`source/path\`` and a status tag:

| Tag | Meaning |
|-----|---------|
| `[active YYYY-MM-DD]` | Believed, last affirmed on that date |
| `[superseded YYYY-MM-DD]` | Replaced by newer evidence; the replacement follows as an indented line |
| `[disproven YYYY-MM-DD]` | Checked and found wrong; kept so the error is not re-learned |

Add ` · agent` to the tag when an agent, not the human, approved it. Retire a belief by
changing the tag and adding an indented line with the evidence path that retired it — never
by deleting the bullet, because a silently deleted belief gets re-proposed.

Beliefs are **not** capital authority. The only capital-actionable artifact is
`{TICKER}/research/human_decision.json` (resolver `_system/scripts/decision_authority.py`).

---
