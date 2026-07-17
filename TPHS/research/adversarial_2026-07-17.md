---
filing: pass
consistency: pass
disclosure: pass
short: no_hit
third_party: n/a
block_final: false
blocking_issues: []
re_pass: false
option_coverage: complete
growth_explanation: n/a
---

# TPHS — Adversarial review

**Date:** 2026-07-17
**Agent:** Milly
**Dive reviewed:** `TPHS/research/deep_dive_2026-07-17.md`
**Valuation reviewed:** `TPHS/research/valuation.json`
**Filings used:** `TPHS/research/evidence/filing_facts_2026-07-17.json`, `TPHS/research/evidence/filing_digest_2026-07-17.md`, and the IR press releases in `TPHS/investor-documents/ir-tphs/`

**Goal:** Truth-seeking QA. Not bearish for its own sake.

---

## Summary verdict

| Area | Status | One line |
|------|--------|----------|
| Filing reconciliation | pass | Balance sheet, NOL, and Steel Promissory Note figures in the dive match the Q1 2026 and FY2025 IR press releases |
| Internal consistency | pass | Base 14.4% matches exec summary, returns statement, and Classification |
| Disclosure scan | pass | 8-K 2025-02-05 (Steel Partners SPA) and the May 2025 Trust Agreement are both reflected in the dive |
| Short activist scan | no_hit | No Tier-1 forensic short found for a sub-$2 million OTC Pink shell |
| Third-party (approved) | n/a | No approved or pending sources indexed (`source_inventory_2026-07-17.md`) |

**Overall:** No blocking factual errors. The dive is appropriately cautious about the speculative nature of the net-operating-loss option and correctly separates the transferred Greenwich joint-venture interest (now in TPHGreenwich Trust) from the current common stock.

---

## Filing reconciliation

| # | Claim in dive | Dive cites | Filing value | Match? | Severity |
|---|---------------|------------|---------------|--------|----------|
| 1 | Price $0.023, 2026-07-17 | OTC Pink aggregator quotes | Investing.com / YCharts closes in the $0.020-$0.025 range for early-to-mid July 2026 | Match (aggregator only; no primary OTC Markets confirmation) | Inference risk — flagged [HUMAN REVIEW] in dive |
| 2 | Shares outstanding 64,947,266 | Q1 2026 press release | `TPHS/investor-documents/ir-tphs/3-31-26-TPHS-Financials-Press-Release-v5.14.26.pdf` balance sheet | Match | — |
| 3 | Cash $54 thousand at 2026-03-31 | Q1 2026 press release | Same source, balance sheet | Match | — |
| 4 | Stockholders' deficit ($1.534) million | Q1 2026 press release | Same source, balance sheet | Match | — |
| 5 | Note payable $1.372 million at 2026-03-31 | Q1 2026 press release | Same source, balance sheet | Match | — |
| 6 | Federal NOL $329.9 million, state NOL $337.4 million | Q1 2026 press release NOL note | Same source | Match | — |
| 7 | Steel Partners bought 25,862,245 shares for $2,586,200 | 8-K filed 2025-02-05 | `TPHS/investor-documents/sec-edgar/8-K_20250205_rpt20250205_acc0001104659_25_009671.htm` | Match | — |
| 8 | Greenwich JV interest transferred to TPHGreenwich Trust 2025-05-20, non-transferable beneficial interests | Trust Agreement | `TPHS/investor-documents/ir-tphs/Executed-TPHGreenwich-Trust-Trust-Agreement-For-Website.pdf` Sections 2.2, 3.3 | Match | — |
| 9 | Base / blended IRR in three places | Executive summary "14%", Returns statement "14.4%", Classification "14.4%" | `valuation.json` implied_return.base_pct = 14.4 | Match (exec summary rounds to whole percent, within tolerance) | — |
| 10 | Stance vs valuation.json gates | Dive states watch | `valuation.json` stance_proposal.suggested = watch, approved_stance = watch | Match | — |

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|----------------|-----|
| Returns statement | 14.4% | 14.4% | Yes |
| Classification IRR | 14.4% (base_pct) | 14.4% (5yr dated payoff) | Yes |
| Stance | watch | watch | Yes |
| Method | yield_curve | yield_curve | Yes |
| Payoff lens | asset | asset | Yes |

**Lint notes:** `lint_deep_dive.py TPHS` passes with no errors. `lint_deep_dive_depth.py TPHS` scores 19/24 or higher (adequate), no archetype errors for `optionality` (GAAP-vs-economic-floor language present in Optionality overlay subsection).

---

## Option coverage

The dive's `#### Option scan` table (7 rows) and `valuation.json` `nav_overlay.options[]` (4 rows) both correctly identify the net operating loss carryforward as the only unresolved material option, and both explicitly zero out the Greenwich joint-venture interest (already transferred out of the company) and the Steel Promissory Note (a liability, not an asset). No GAAP book value is used as a floor; the dive states plainly that book value is already negative. `option_coverage: complete`.

---

## Disclosure scan

| Event | Date | Source | In dive? | Action |
|-------|------|--------|----------|--------|
| Steel Partners Stock Purchase Agreement, board change | 2025-02-05 | 8-K | Yes, in Business & moat and Risks | None |
| TPHGreenwich Trust formation / JV transfer | 2025-05-20 | Trust Agreement (IR PDF) | Yes, in What/Why and Option scan | None |
| Pension plan termination and reversion | 2025 (completed July 2025) | FY2025 press release | Yes, in Run-rate vs one-off | None |
| FY2025 10-K, 2025-2026 10-Qs | Not yet filed/downloaded locally | — | Flagged as [HUMAN REVIEW] and in Primary sources table | Re-run `build_filing_evidence.py TPHS` once downloaded |

No late-filing notice (NT 10-K/Q), restatement, or auditor-change 8-K found in the local `investor-documents/sec-edgar/` folder through 2025-02-05.

---

## Short activist scan

No Tier-1 or Tier-2 forensic short report found for TPHS in `_system/frameworks/short_activist_registry.md` categories or in a local `TPHS/third-party-analyses/short_reports/` folder (none exists). Given the sub-$2 million OTC Pink market value and near-zero trading volume, this is expected: `no_public_short_found`, not a clean bill of health on its own, but consistent with a name too small for short-seller attention.

---

## Recommended actions

1. None blocking.
2. **Human:** Confirm OTC Pink official close (vs aggregator quote) and reconcile the FY2025 10-K once downloaded against the unaudited press-release figures used here.
3. **Human:** Track Steel Partners Schedule 13D/A and any Form 15 deregistration filing for a change in the option's timeline.

---

## [HUMAN REVIEW]

- This is a single-agent mechanical-plus-manual pass on an inaugural dive for a near-dormant shell; revisit after the FY2025 10-K is filed and downloaded, and after any Steel Partners transaction announcement.
