# Biotech Quant Research Library

Curated research on **quantitative biotech investing**: specialist 13F consensus,
spend-based value, insider/short signals, and peer (clinical-trial) momentum.

**Path:** `_system/reference/biotech-quant/`

Supports Strategies → **Biotech Quant** and the ownership
pipeline under `_system/reference/market-data/ownership/`. See:

- `_system/proposals/verdad_biotech_quant_methodology_2026-07-09.md`
- `FACTOR_SPEC.json` (machine-readable factor weights and gates)
- `SYNTHESIS.md` (distilled findings; **not** promoted to `MEMORY.md`)

## Layout

```
biotech-quant/
├── README.md              ← this file (catalog + how to use)
├── SYNTHESIS.md           ← distilled Verdad + podcast rules
├── FACTOR_SPEC.json       ← factor defs, weights, banned metrics, status
├── papers/                ← primary PDFs + download helpers
│   └── secondary/         ← HTML/markdown digests (attribution only)
├── methodology/           ← our factor cookbook notes
└── _text/                 ← text extracts for grep/build scripts
```

Regenerate text extracts after adding a PDF:

```bash
python _system/scripts/extract_biotech_quant_text.py
```

## Primary sources (`papers/`)

| File | Cite | Contribution | Status |
|------|------|--------------|--------|
| `verdad_biotech_investing_2026.pdf` | Obenshain, Rasmussen & Wintner, Verdad Capital 2026 | Full white paper: specialist quality, spend value, peer momentum, L/S construction | download via `_download.sh` |
| `verdad_the_waste_land.md` | Verdad serial essay | Sector structure: failure rates, low correlation, why quant can work | archived |
| `verdad_the_inferno.md` | Verdad serial essay | Specialist / insider / short “expert” signals | archived |
| `verdad_the_golden_tree_of_life.md` | Verdad serial essay | Rebuild value + momentum; blended factor model | archived |

## Secondary digests (`papers/secondary/`)

| File | Cite | Contribution | Status |
|------|------|--------------|--------|
| `biotechedge_verdad_part1.md` | BiotechEdge digest of Verdad Part 1 | Quintile tables for specialist / insider / short | context only |
| `biotechedge_verdad_part2.md` | BiotechEdge digest of Verdad Part 2 | Spend value, peer momentum, blended 38 ppt spread | context only |
| `buysidedigest_verdad_podcast.md` | Buyside Digest / YAVP transcript notes | Specialist definition (>50% biotech), consensus > hero-picking | context only |
| `swedroe_verdad_digest.md` | Larry Swedroe Substack digest | Accessible summary of Verdad factors | context only |

## Tier

All materials in this library are **context tier** until a human adds an approved
row in `_system/frameworks/third_party_sources.md`. They may inform
`biotech_overlay` and methodology claims; they must **not** enter base Lawrence IRR
without approval.


## Strategy workbench and reproducible research

The strategy is at `#/strategies/biotech-quant/overview`. The canonical plan is
`_system/proposals/research_insights_strategy_reorganization_2026-10-29.md`.
`strategy_protocol.v1.json` freezes the initial ownership/spend-value baseline.
Changes require a new identifier: the registry rejects edits under an existing ID.

Rebuild from existing local evidence (no network or broker calls):

```powershell
python _system/scripts/build_biotech_strategy.py --as-of 2026-10-29 --record-paper
```

Use `--source-root` for an authorized evidence checkout, and `--history-root`
when the public SEC history is in a separate checkout. Missing ownership inputs
cannot replace a previous complete strategy publication. The normal insights
and full rebuild profiles also publish the strategy and append paper decisions.

Historical observations and marks can be supplied as CSV, JSON arrays, or JSONL:

```powershell
python _system/scripts/build_biotech_strategy.py --observations observations.jsonl --marks marks.jsonl --record-paper
```

An observation needs `ticker`, `as_of` (observation date), `known_at` (original
publication date), `identity_status: verified`, `consensus_score`, and
`spend_value`. Optional `factor_dates` maps factor IDs to their own observation
dates. Each required factor has its own staleness limit. No same-day publication
is available at a historical selection close. Revisions are separate vintages.
`eligible: false` excludes an issuer. Include independently listed eligible
issuers with zero specialist holders: the current specialist-derived universe
has selection bias and is unsuitable as a complete historical universe.
Historical identity must use security/CUSIP and corporate-action history, rather
than back-projecting today's ticker. Delisted issuers and cash merger proceeds
must remain in marks. Retain the original filing acceptance and amendment clocks.

A mark needs `date`, `ticker`, and `total_return` (a decimal close-to-close total
return, including distributions and corporate actions). Paper accounting also
requires an actual `close` on the paper date. Individual shorts require
`borrow_available: true` and a nonnegative `borrow_apr` on that date; short
interest is not borrow evidence. Optional `dollar_volume_20d`,
`cash_runway_months`, `indication`, and `next_catalyst` populate risk diagnostics.
A missing return or borrow mark withholds complete performance. A missing paper
mark retains the open position and withholds its account value.

The engine compares long-only, XBI-hedged, individual long/short, eligible-universe,
and XBI portfolios with costs, calendar-day borrow carry, monthly close rebalances,
and next-session returns. Unused allocation stays in cash. Existing paper
positions are marked between monthly rebalances; loss of feature coverage does
not silently remove them. Orders and fills are explicitly simulated.

`clinical_peer_momentum` accepts dated clinical tags and prior 12-month returns.
It excludes the issuer's own return and future descriptors, requires three peers,
and uses descriptor-set similarity weights. It does not infer clinical peers
from company names. Factor additions require a separate registered protocol.

The publication records input hashes, protocol hash, source-history hash, missing
coverage, risk inputs, and account events. Paper decisions are append-only,
idempotent, chronologically checked, and linked by hashes in
`_system/data/biotech_quant/paper_ledger.jsonl`. Preserve this ledger and protocol
registry on rebuilds. No order or broker integration exists.

The October 29 archive extension contains 20 dated quarters across the specialist
registry, with fund-level gaps visible in Risk & Data. Existing current ownership
publications are unchanged. This archive is raw research evidence, not an audited
point-in-time feature panel. Spend-value vintages, independent biotech membership,
security histories, release clocks, total-return marks, clinical peer returns,
and observed borrow still require coverage before an empirical test is credible.
The saved insider zero scores are recorded zeros with unverified coverage.

All supplied historical dates are exploratory until an independently protected
validation window is designated before its outcomes are inspected. Freeze the
chosen protocol before collecting forward outcomes. Evaluate five years of
coverage, at least 12 validation months, 90 independent forward days, positive
net excess return, drawdown below the registered limit, capacity and tail-risk
constraints. Record failed hypotheses and abstentions. Future outcomes are never
fabricated to fill a dashboard. Trading authority remains a separate decision.
