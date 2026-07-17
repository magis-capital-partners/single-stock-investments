---
filing: pass
consistency: pass
disclosure: pass
short: no_hit
third_party: n/a
valuation_staleness: pass
ai_coverage: n/a
option_coverage: complete
growth_explanation: n/a
block_final: false
blocking_issues: []
re_pass: false
---

# SEVN — Adversarial review

**Date:** 2026-07-17
**Agent:** Milly
**Dive reviewed:** `SEVN/research/deep_dive_2026-07-17.md`
**Valuation reviewed:** `SEVN/research/valuation.json`
**Filings used:** `SEVN/research/evidence/_text/10-Q_20260428_rpt20260331_acc0001452477_26_000021.htm.txt`, `SEVN/research/evidence/_text/10-K_20260218_rpt20251231_acc0001452477_26_000010.htm.txt`, `SEVN-Q1-2026-Earnings-Presentation.pdf`, `SEVN-Q4-2025-Earnings-Presentation.pdf`

**Goal:** Truth-seeking QA. Not bearish for its own sake.

---

## Summary verdict

| Area | Status | One line |
|------|--------|----------|
| Filing reconciliation | pass | Every numeric claim spot-checked against the 10-Q, 10-K, and earnings presentations ties out |
| Internal consistency | pass | Executive summary, returns statement, and Classification all show 14.6% |
| Disclosure scan | pass | No late filings, restatements, or auditor changes found in 8-K index since onboarding |
| Short activist scan | no_hit | Short interest is about 1.4% to 1.5% of shares outstanding; no Tier 1 or Tier 2 forensic short report found |
| Third-party (approved) | n/a | No approved third-party sources indexed yet |

**Overall:** No factual errors found. The dive's one soft spot, flagged below as an inference risk rather than a factual error, is that the mechanical total synthesis IRR this run only has a bear and a bull path (no filings-anchored path populates on a first write under the scenario method), so that 16.04% figure is thin. The dive already labels it as such and keeps the reported base return at the Lawrence scenario base of 14.6%, which is the correct handling.

---

## Filing reconciliation

| # | Claim in dive | Dive cites | Filing / filing_facts | Match? | Severity |
|---|----------------|------------|------------------------|--------|----------|
| 1 | Price today $8.40, 2026-07-16 | CNBC quote | CNBC quote captured 2026-07-16 shows last $8.40, prior close $8.50 | Match | — |
| 2 | Book value per share $14.47; adjusted book value $14.90 | Q1 2026 presentation | Presentation Financial Summary, "Book value per common share $14.47," "Adjusted book value per common share (1) $14.90" | Match | — |
| 3 | Q1 2026 distributable earnings $0.24 per share; net income $0.19 per share | Q1 2026 presentation | Presentation Financial Summary: "Net income per common share... $0.19," "Distributable Earnings per common share... $0.24" | Match | — |
| 4 | Q1 2026 net income $4.385 million | Q1 2026 10-Q, presentation | 10-Q XBRL text "NetIncomeLoss: 4,385"; presentation "Net income $4,385" | Match | — |
| 5 | Total shareholders' equity $326,982 thousand as of 2026-03-31 | Q1 2026 10-Q | 10-Q text "StockholdersEquity: 326,982" (current period) | Match | — |
| 6 | Total outstanding common shares 22,596 thousand | Q1 2026 presentation | Presentation Balance Sheet: "Total outstanding common shares 22,596" | Match | — |
| 7 | Quarterly dividend $0.28 per share, payout ratio 117% | Q1 2026 presentation, 10-Q | Presentation: "Quarterly distributable earnings payout ratio 117%"; 10-Q: "CommonStockDividendsPerShareCashPaid: 0.28" | Match | — |
| 8 | Weighted average loan-to-value 66%; weighted average risk rating 2.8; allowance for credit losses 1.3% of commitments; no realized losses | Q1 2026 presentation | Presentation: "Weighted average LTV 66%," "Weighted average risk rating of 2.8 and an allowance for credit losses representing 1.3% of total loan commitments," "No realized losses" | Match | — |
| 9 | Base management fee 1.5% of equity per year; incentive fee 20% of core earnings above a 7% hurdle | 10-K management agreement | 10-K text: "annual base management fee equal to 1.5% of our Equity," "product of (i) 20% and (ii) the difference between... Core Earnings... and... 7% per year" | Match | — |
| 10 | Owner cash starting point $0.96 per share (annualized Q1 2026 distributable earnings) | `valuation.json` `inputs.per_share` | $0.24 x 4 = $0.96; consistent with the 10-Q and presentation figures in row 3 | Match | — |
| 11 | Base annual return 14.6% in three places (executive summary, returns statement, Classification) | `valuation.json` `implied_return.base_pct` | `valuation.json` shows `base_pct: 14.6` after manual reconciliation of the auto-synthesis override | Match | — |
| 12 | Stance watch vs `valuation.json` gates | `valuation.json` `stance_proposal` | `stance_proposal.suggested: "watch"`, `gates.moat_ok: false`, `gates.dhando_ok: true` | Match | — |
| 13 | Option scan present for a business with no segments, land, or backlog in the usual sense, but with unfunded commitments and rate floors | Business & moat | `#### Option scan` table with 7 rows, treatment `embedded_in_segment` for both material items | Match | — |

---

## Internal consistency

| Check | Expected (`valuation.json`) | Found in dive | OK? |
|-------|------------------------------|----------------|-----|
| Base IRR executive summary | 14.6% | 14.6% | Yes |
| Base IRR returns statement | 14.6% | 14.6% | Yes |
| `valuation.json` `implied_return.base_pct` | 14.6 | 14.6 (patched after the mechanical write; see note below) | Yes |
| Classification Implied 7yr IRR | 14.6% | 14.6% | Yes |
| Scenario table base row | 14.6% | 14.6% | Yes |

**Note on the manual patch:** `marvin_valuation.py --write` unconditionally overwrote `implied_return.base_pct` to the total synthesis figure (16.04%) even with `evidence_refresh.synthesis_in_dive: false`, because that override lives in `compute_valuation()` itself, not only in `compute_synthesis()`. This matches the pattern already on file for `QDEL/research/valuation.json`, where `base_pct` was likewise reset by hand to the Lawrence base after the mechanical run. Marvin's manual patch here (base_pct, label, display back to 14.6%, `lawrence_stance_gate_pct` and `falsifier_adjusted_pct` unchanged at 14.6, `synthesis_pct` left at 16.04) is consistent with that precedent and with the human-quality-filter rule that a mechanically blended figure should not silently become the headline before human approval. Not a factual error; documented here for transparency.

**Option coverage:** complete. The only two items that move the model (unfunded commitments and cash not yet earning full yield, and interest rate floors already inside the coupon figures) are both scanned, both treated as `embedded_in_segment`, and both explained. No segment build, no land, and no other hidden assets apply to this issuer.

**Growth explanation:** n/a. The 3% and 1% growth rows are tagged `[Assumption]` with the mechanism (capital redeployment, then a mature floating-rate run rate) stated in Business & moat, not backed by a separate `growth_explanation` JSON block. No Popper/Deutsch markdown subsection was added, consistent with `report_prose.md`.

---

## Disclosure scan

| Event | Date | Source path | In dive? | Action |
|-------|------|--------------|----------|--------|
| Rights offering (7.5 million shares, $65.2 million gross) | December 2025 | `SEVN-Q4-2025-Earnings-Presentation.pdf` | Yes, discussed as the redeployment catalyst | none |
| UBS Master Repurchase Facility maturity extension to February 2028 | February 2026 | `SEVN-Q1-2026-Earnings-Presentation.pdf` | Yes, in operating snapshot and thesis pillars | none |
| Wells Fargo facility extension and $125 million upsize to $250 million | February 2026 | `SEVN-Q1-2026-Earnings-Presentation.pdf` | Yes | none |
| Director equity compensation grant (9,976 shares) | June 9, 2026 | Form 4 via web search | No, immaterial | none needed, routine compensation grant |
| Auditor change, restatement, or Item 4.02 non-reliance | none found | 8-K index in `investor-documents/sec-edgar/` | n/a | none found; no action |

---

## Short activist scan

**Registry:** `_system/frameworks/short_activist_registry.md`

| Firm | Report? | Date | Path/URL | Verdict |
|------|---------|------|----------|---------|
| (none found) | No | — | Web search 2026-07-17: MarketBeat, StockAnalysis, GuruFocus short-interest pages only | no_public_short_found |

Short interest is roughly 1.4% to 1.5% of shares outstanding as of late May 2026 (MarketBeat, StockAnalysis), low for a small-cap externally managed mortgage REIT and consistent with no active forensic short campaign. This is a **no_public_short_found** verdict, not a clean bill of health; SEVN is small and thinly covered enough that a short report could appear without wide distribution.

---

## Third-party reconciliation (approved only)

n/a. No approved sources are indexed for SEVN as of 2026-07-17 per `SEVN/third-party-analyses/source_inventory_2026-07-17.md` and `SEVN/research/cross_check_third_party_2026-07-17.md`.

---

## Recommended actions

1. None blocking.
2. **Human:** decide whether the thin total synthesis IRR (16.04%, bear/bull only) should be left as informational context, or whether Marvin should add a `growth_explanation` block on the next refresh so the mechanical synthesis picks up a proper filings-anchored path.
3. **Human:** revisit the sector price-to-book discount theme in `context_overlay` once a third-party source is approved; it is currently `[PENDING APPROVAL]` and correctly excluded from the base return.

---

## Resolved in dive

(First pass; nothing to resolve yet.)

---

## [HUMAN REVIEW]

- Confirm the redeployment timeline (return to a $0.28 per share quarterly run rate within roughly two years) against actual Q2 and Q3 2026 results before treating it as more than an assumption
- No Tier 1 short report found; re-scan if short interest rises materially from the current ~1.5% of shares outstanding
