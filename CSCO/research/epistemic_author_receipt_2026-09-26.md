# Epistemic author forecast receipt — CSCO (2026-09-26)

**Work ID:** `03df290ce01c5b0678e15d5f` · **Component:** `operating_business_and_net_assets` · **Method:** `owner_earnings_reinvestment_dcf`

## Admission boundary

- **Evidence hash:** `c25e8a6b371a8d46…` (full value in `research_agent_manifest.json`)
- **Input SHA:** `979539b6effced57a1ce1251f2d3d6e5c0cdd6dc`
- **Contract hash:** `9917aa0ae7650a7f2a4739d9d78c2a7ca40b8e60202315ce54942f12f59f330b`
- **Component fingerprint:** `590c7e00aeae584c85e240358f7ff1060c1c9a5202d41acb0267751703ddbf44`
- **Primary evidence:** `CSCO/investor-documents/DOWNLOAD_MANIFEST.json` only (manifest SHA admitted at gate)

## Forecast (draft v3, awaiting independent review)

- **Spec:** `csco-operating-owner-earnings-fy2026-v3` · **Metric:** normalized owner earnings TTM · **Comparator:** less than **13,288** USD millions
- **Measurement period end:** 2026-07-26 (Cisco FY2026) · **Observable after:** 2026-10-15
- **Probability fires:** 38% · **Severity:** 4 · **Component value impact:** ~45.1% (low vs base per share)

## Facts vs inferences

**[Fact]** Low-case proof trace locks owner earnings at 13,288M (OCF minus capex, FY2025 10-K). **[Fact]** Historical replay at Q3 FY2025 (2025-04-26) resolves 12,803M via `sec_companyfacts_ttm`. **[Fact]** Interim FY2026 TTM through Q3 FY2026 (2026-04-25) resolves 11,788M on the same adapter (2026-09-26 run).

**[Inference]** FY2026 full-year TTM could recover above 13,288M if Q4 FY2026 operating cash flow is strong enough to offset the YTD decline. **[Inference]** If FY2026 TTM resolves below the anchor, the operating component range should compress toward the low case (31.89 USD per share).

## Calibration and epistemic loop

- **Loop health:** COLLECTING (not BOOTSTRAP_BLOCKED, DEGRADED, or HALTED)
- **Calibration:** `insufficient_outcomes`; **release_hash:** null
- **Route:** `quality_reinvestment` · **Named challenge:** none · **Response:** `not_applicable`

## Deliverable

Draft only (no sidecar append): `CSCO/research/falsifier_drafts/03df290ce01c5b0678e15d5f.json` · **Status:** `awaiting_review`
