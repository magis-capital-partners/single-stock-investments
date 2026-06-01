# Horizon Kinetics cross-reference workflow

**Purpose:** Ensure deep dives and cross-checks for HK-relevant holdings (TPL, ICE, MSB, SJT, royalty trusts, exchanges) **cite all material third-party HK / Stahl material** before stance is proposed.

**Related:** `third_party_sources.md` (approval tiers), `external_view_blend.md` (when to blend), `mental_models.md` (Tier 3 HK models).

---

## Source tiers

| Tier | Location | Marvin use |
|------|----------|--------------|
| **In-repo extracts** | `_system/reference/investment-wisdom/horizon-kinetics/*.txt` | Always searchable; primary agent-readable HK text |
| **Stahl shelf PDFs** | `_system/reference/investment-wisdom/stahl/` | Croupier / exchange / diversification essays |
| **Full HK vault** | `HK_PDFS_ROOT` or Windows `hk_pdfs/` (400+ PDFs) | Filename + `book/build/text/` scan when path available |
| **Approved Substacks** | `{TICKER}/third-party-analyses/references.md` | SSI / LCI per `approved_substacks.md` |
| **Approved cross-checks** | `_system/reviews/approved/` | Human-approved HK lens vs filings (e.g. SJT) |

**HK commentaries = context tier by default.** Cite in narrative, Business & moat (mental models), and cross-check files. Do **not** put HK assumptions into `valuation.json` base IRR without human approval in `third_party_sources.md`.

---

## Mandatory steps (HK-indexed tickers)

Tickers in `hk_ticker_index.json` (today: **TPL, SJT, MSB, ICE**):

1. **Before narrative** — run HK scan:
   ```bash
   python _system/scripts/scan_hk_sources.py {TICKER} --write-references
   ```
2. **Read** `{TICKER}/third-party-analyses/hk_scan_{date}.md` and every curated source listed.
3. **If HK thesis is material** — write or update `{TICKER}/research/cross_check_{date}.md` using `external_view_blend.md` (agreements, divergences, synthesis).
4. **Deep dive** — Primary sources section must include the auto-generated `### Horizon Kinetics cross-reference` block (injected by refresh or `--inject-dive`).
5. **After refresh** — Milly checks that HK-indexed tickers have a non-empty HK scan file.

---

## Adding a new ticker

1. Add entry to `_system/reference/investment-wisdom/hk_ticker_index.json` (patterns, mental_models, curated rows).
2. Run `scan_hk_sources.py {TICKER} --write-references`.
3. Promote recurring hits from `source: scan` into `curated` in the index.
4. When human approves an HK blend, add row to `third_party_sources.md` **Approved registry**.

---

## Full vault on cloud / Linux

Set environment variable before scan or refresh:

```bash
export HK_PDFS_ROOT="/path/to/Horizon Kinetics/hk_pdfs"
python _system/scripts/scan_hk_sources.py TPL MSB SJT ICE --write-references
```

On Windows workspace the default path in `hk_paths.json` is used automatically.

**Refresh extracts** when new commentaries land in the vault (see `horizon-kinetics/README.md`).

---

## Cross-check template (HK vs filings)

When HK has a dated thesis (e.g. SJT dividend reinstatement by May 2025):

| Lens | Claim | Primary-source check | Weight |
|------|-------|----------------------|--------|
| HK Q1 2025 | … | 10-K / 10-Q fact | … |
| Marvin floor | … | Filing-derived | … |
| **Synthesis** | … | Best estimate | stance input |

Record material synthesis in `valuation.json` → `estimates.external[]` only after human approval.

---

## Pipeline integration

| Step | Script |
|------|--------|
| HK scan | `scan_hk_sources.py` |
| Full refresh | `marvin_cloud_refresh.py` (runs HK scan first for indexed tickers) |
| Dive inject | `refresh_deep_dive_v2.py` (reads latest `hk_scan_*.json`) |
| QA | `make hk-scan TICKER=TPL` |
