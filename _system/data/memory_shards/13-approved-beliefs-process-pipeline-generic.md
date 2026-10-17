## Approved beliefs — process & pipeline (GENERIC)

*Section opened 2026-08-09. Lens tag: `[PROPOSED GENERIC]`. Pipeline **errors** belong in
`_system/memory/corrections.md`; this section holds standing rules about how the system is
allowed to speak.*

### Valuation authority

- The authority chain is: Power Zone route → proof-first universal contract → Investment Committee → `{TICKER}/research/human_decision.json`. Resolver: `_system/scripts/decision_authority.py`. Only the human decision is capital-actionable. — `_system/memory/daily/2026-07-24.md` `[active 2026-08-09 · agent]`
- Marvin/Lawrence `implied_return`, `stance_proposal` and classification Thesis IRR are **legacy reference** — a specialist cross-check inside a fitting Power Zone at most. Never call them house IRR. — `_system/memory/daily/2026-07-24.md` `[active 2026-08-09 · agent]`
- World Model / Magis / Santa Fe are claim and context layers. They must not rewrite contracts, IC packets, or human decisions, and the two valuation languages must not be mixed. — `_system/frameworks/proof_first_valuation.md`; `_system/memory/daily/2026-07-24.md` `[active 2026-08-09 · agent]`
- Do not merge foresight (World Model) and complexity economics (Santa Fe) into one simulator. Gate what agents and the morning strip may assert with a thin `predictability_class` (P0–P4). — `_system/memory/daily/2026-07-24.md` `[active 2026-08-09 · agent]`
- Dashboard context series — the BTC demand power-law is the live example — are context-only, and must not enter a Lawrence base IRR without human review. — `_system/memory/daily/2026-08-04.md`; `dashboard/data/hk_snowball_model.json` `[active 2026-08-09 · agent]`

### Pipeline order of operations

- After an SEC download for scaffolded names, rebuild `INDEX.csv` **before** `build_filing_evidence` — a stale INDEX yields `docs=0` with no error. — `_system/memory/daily/2026-07-28.md` `[active 2026-08-09 · agent]`
- CI roles: the Data Pipeline workflow is the scheduled writer, Darwin is manual-only, and deploy is deploy-only — it runs after upstream commits land and never rebuilds. — `_system/memory/daily/2026-07-12.md` `[active 2026-08-09 · agent]`

---
