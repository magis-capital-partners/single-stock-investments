# CONTEXT — research-equity hub

> Copied from `C:\Users\drewg\Projects\.agent-memory\hubs\research-equity\CONTEXT.md` on 2026-10-12 (UTF-8 BOM and cp1252 mojibake re-decoded; nothing rewritten). This repo copy is the one bots read and write.

Shared by: **single-stock-investments** ↔ **research-vault**.

## Domain language

- **SSI** = ticker-centric research workspace (per-ticker folders, IC votes, dashboard).
- **Research vault** = manager meetings + superinvestor letters + licensed idea corpora (SumZero, VIC).
- **Approved beliefs** live primarily in SSI `_system/memory/MEMORY.md` (human-promoted).
- This hub holds **cross-repo** working context, bridges, and daily proposals that affect both.

## Current truths

- SSI path: `C:\Users\drewg\Projects\dashboards\single-stock-investments`
- Vault path: `C:\Users\drewg\Projects\dashboards\research-vault`
- Vault contents of note: `manager-meetings/`, `superinvestor-letters/`, `investment-wisdom/`, `sumzero-research/`, `vic-research/`
- SSI already has Marvin-style memory under `_system/memory/` — keep that as the equity-belief source of truth.
- Intake playbook: SSI `_system/agents/MICHAEL.md`. Letters → Drive `Letters/{YYYY Qn}/`. Books → `Research Sources/Investment Wisdom/{author}/`. VIC → Drive `Admin/Intake/VIC/` then vault `vic-research/`. Other ticker PDFs → `Admin/Intake`. Do not mix.

### Valuation authority (do not mix)

| Canonical (production) | Legacy reference (not actionable) |
|------------------------|-----------------------------------|
| Power Zone route → proof-first economic-value contract → IC → `human_decision.json` | Marvin/Lawrence `implied_return`, `stance_proposal`, classification “Thesis IRR” fallbacks |

- Resolver: SSI `_system/scripts/decision_authority.py` (`human_decision` → `investment_committee` → `valuation_contract` → `legacy_reference`)
- Normative: SSI `_system/frameworks/proof_first_valuation.md` § *Do not mix two valuation languages*
- Cutover: SSI `_system/proposals/power_zone_committee_valuation_cutover_2026-07-18.md`
- Lawrence owner-cash IRR may still appear as a **specialist** module inside fitting Power Zones; it is **not** the universal stance gate.


### Magis desks (Grok Bot)

- Desk lines (one per desk) sit under `## Desk` at the end of this file; mandates in full are SSI `_system/agents/DESKS.md`.
- Session start for Magis equity work: mesh `GRAPH.md` -> this `CONTEXT.md` -> skim `daily/` (14d) -> SSI `_system/memory/MEMORY.md` when invariants matter.

## Update rules

- Meeting/letter ingestion insights that should affect both repos → `daily/` here.
- Framework/belief promotions → SSI `_system/memory` flow (human promote).
- Do not pull borrow-etf or spx-0dte context into this hub.

## Agent diligence (2026-07-23)

- Agents close research gaps themselves (pull SEC/IR, reconcile, document `[Assumption]`).
- Do **not** use `[HUMAN REVIEW]` as a parking lot for fetchable work.
- Human gates: MEMORY promote, live capital, new framework files only.
- SSI rule: `single-stock-investments/.cursor/rules/human-quality-filter.mdc`

## Desk

One line per desk. A bot may append one desk line here per session (`README.md`). Mandates in full: SSI `_system/agents/DESKS.md`. Since 2026-10-12 ranked desk output goes to `_system/data/desk_briefs/<desk>/<YYYY-MM-DD>.json` (see `_system/data/desk_briefs/README.md`); `daily/` here stays the place for `[PROPOSED]` lessons. The six lines below are the original mandates, verbatim.

- **Special Situations** owns forced-seller / odd-security screens on SSI (spin/orphan, CVR/merger securities, no-vote, topping-bid lost, warrant terms, capital-structure shock). Writes proposals only to this hub `daily/`. Does not invent hubs or edit `MEMORY.md`.
- **Activism** owns 13D/A, 13G/A (including 13G-to-13D switches), control/founder filings, proxy solicitations, and short reports on SSI activist_feed plus _system/reference/activist-reports. Writes proposals only to this hub `daily/`. Does not invent hubs or edit `MEMORY.md`. Identity from cover page / reporting_persons; firm_name is a display guess.
- **Fundamental Analyst** owns going-concern story breaks on SSI (guidance/KPI inflections from kpi_trends, capital-structure changes that stay with the ongoing business, news-vs-filing disagreements, CEO/CFO/accounting/legal events). Writes proposals only to this hub `daily/`. Does not invent hubs or edit `MEMORY.md`. Room posts = ticker + one number or named person; stubs/warrants/spins hand off to Special Situations.
- **NOL and Tax Assets** owns NOL / Section 382 / DTA triage from SSI `dashboard/data/nol_screener.json` and `nol_382_facts.json` (actionable rows, large NOL vs mcap, prior ownership change, rights plans, ownership-change risk, needs_review). Writes proposals only to this hub `daily/`. Does not invent hubs or edit `MEMORY.md`. Room posts = ticker + one tax number; never invent a 382 annual limit or treat DTA as cash.
- **Technical Analyst** owns index adds/deletes/migrations and stored-tape thresholds on SSI (breakouts, RSI/stretch/trend/CMF extremes, capitulation flags from technical_summary / index_membership / capitulation_daily). Writes proposals only to this hub `daily/`. Does not invent hubs or edit `MEMORY.md`. Room posts = ticker + one flow or tape number; never recompute indicators or override fundamental/special-sit conclusions.
- **Murray Stahl** owns Horizon Kinetics / Stahl-category reads on SSI (royalties and scarce assets, true croupiers/exchanges, crypto monetary asset vs croupier vs miner, FRMO/HKHC look-through, predictive attributes / equity yield curve). Writes proposals only to this hub `daily/`. Does not invent hubs or edit `MEMORY.md`. Room posts = ticker + one dated fact when structure or HK commentary moved; silent if nothing; disclose TPL/Sites board conflicts; never promote HK assumptions into base IRR.
- **Short Selling** owns reverse-split announcements, dilution / ATM / convertible supply, going-concern language, activist short reports, and borrow readings with source and date on SSI `short_alpha.json`, `reverse_splits.json` (arriving), `activist_feed.json`, and `portfolio_news.json` (capital_raise / restructuring / forward_split). Writes desk briefs and `[PROPOSED]` lessons only to the SSI desk-brief and hub paths. Hands spins, stubs, and CVRs to Special Situations. Never tags fraud. Added 2026-10-12 with `DESKS.md`.
