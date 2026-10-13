# Bridges — research-equity shared data

## Repos

| Role | Path |
|------|------|
| Theses / IC / ticker folders | `Projects/dashboards/single-stock-investments` |
| Letters + manager meetings | `Projects/dashboards/research-vault` |
| Approved belief library | `single-stock-investments/_system/memory/MEMORY.md` |
| Daily SSI proposals | `single-stock-investments/_system/memory/daily/` |

## Typical share patterns

- Letter/meeting → ticker evidence: cite vault relative path inside the ticker’s `research/` notes in SSI.
- SSI framework change that should guide vault tagging → propose here + update vault README/conventions if needed.
- Both repos may read this hub’s `CONTEXT.md` / `MEMORY.md` / `daily/`.

## Intake contract (Drive ↔ vault)

Michael's bot (`SSI/_system/agents/MICHAEL.md`) classifies then writes both stores. Cloud Grok VIC-only: `SSI/_system/agents/GROK.md` + `drive_intake_drop.py` (Drive `Admin/Intake/VIC/{TICKER}/`). Daily import also stages vault `vic-research/{TICKER}/` like SumZero.

| Kind | Drive | Vault |
|------|-------|-------|
| Fund letter | `Letters/{YYYY Qn}/` | `superinvestor-letters/{YYYY}Q{n}/` |
| Book / wisdom | `Research Sources/Investment Wisdom/{author}/` | `investment-wisdom/{author}/` |
| Manager meeting | `Manager Meetings/{YYYY-MM-DD}/` | `manager-meetings/{YYYY-MM-DD}/` |
| Ticker VIC | `Admin/Intake/VIC/{TICKER}/` | `vic-research/{TICKER}/` + SSI `{TICKER}/third-party-analyses/vic/` |
| Ticker research/company/activist | `Admin/Intake/{Kind}/{TICKER}/` | SSI `{TICKER}/` (not the vault) |

SSI JSON keeps logical refs `_system/reference/superinvestor-letters/...` and `_system/reference/investment-wisdom/...`; `vault_paths.py` resolves them.

## Valuation language (SSI)

When writing cross-repo notes, keep these distinct:

1. **Canonical value / stance** — Power Zone + universal contract + IC + human decision (SSI `decision_authority.py`).
2. **Legacy Lawrence IRR** — reference / specialist only; never describe as “house IRR” or actionable stance.
3. **World Model / Magis / Santa Fe** — foresight or mental-model context; never security value.

## Isolation

No bridges to `borrow-etf`, `diamond-creek`, or `spx-0dte` unless the human explicitly creates one.
